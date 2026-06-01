"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

GRAPH MODULE
This module defines the Graph class, which provides the base representation
for graphs (LPGs and KGs) in the BTWIN toolkit.

© Angelo Massafra, 2025
"""

# Dependencies
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Set, Tuple, Union

# BTWIN modules
from btwin.schema import Schema


# Functions
class NetworkX():

    @staticmethod
    def AddEdgesByObject(
        nxGraph,
        object: Dict[str, Any],
        *,
        deduplicate: bool = True
    ):
        """
        Add directed edges to a NetworkX graph from an object's relationships.

        Args:
            nxGraph: A NetworkX graph instance (Graph, DiGraph, MultiGraph, MultiDiGraph).
            object (dict): Source object containing at least `@id`. May include `@type` and a
                `relationships` dict mapping predicates → list of target dicts.
            deduplicate (bool, optional): If True, skip adding an edge when an existing
                edge (u→v) with the same `type` already exists. Default True.

        Returns:
            The same `nxGraph` instance, with any valid edges added.

        Raises:
            ImportError: If NetworkX is not installed.
            TypeError:   If `obj` is not a dict or `nxGraph` lacks the expected API.
            ValueError:  If required fields inside `obj` or `relationships` are malformed.
        """
        # Import networkx locally to provide a clear error if it's missing
        try:
            import networkx as nx  # noqa: F401
        except Exception as exc:
            raise ImportError("NetworkX is required. Install with `pip install networkx`.") from exc

        # --- Basic input checks ------------------------------------------------
        if not hasattr(nxGraph, "add_edge") or not hasattr(nxGraph, "nodes"):
            raise TypeError("nxGraph must be a NetworkX graph instance.")
        if not isinstance(object, dict):
            raise TypeError("object must be a dict.")

        # Extract subject UID/type
        subjectUid = object.get("@id")
        if not isinstance(subjectUid, str) or not subjectUid.strip():
            raise ValueError("obj['@id'] must be a non-empty string.")
        subjectType = object.get("@type")

        # Ensure subject node exists (do NOT create it)
        if subjectUid not in nxGraph:
            # Print error and exit early as requested
            print(f"Error: source node '{subjectUid}' not found in graph. No edges were added.")
            return nxGraph

        # Pull relationships map
        relationships = object.get("relationships", {})
        if relationships is None:
            return nxGraph  # nothing to add
        if not isinstance(relationships, dict):
            raise ValueError("'relationships' must be a dict mapping predicate → list of targets.")

        # Helper: add one directed edge if both nodes exist (no creation)
        def add_edge_if_present(u: str, v: str, rel: str, attrs: Dict[str, Any]) -> None:
            # Check target presence (do NOT create)
            if v not in nxGraph:
                print(f"Error: target node '{v}' not found in graph for relationship '{rel}'. Edge skipped.")
                return

            # Deduplicate if requested
            if deduplicate and nxGraph.has_edge(u, v):
                try:
                    # MultiGraphs: iterate keyed edges
                    for _, data in nxGraph.get_edge_data(u, v).items():
                        if isinstance(data, dict) and data.get("type") == rel:
                            return  # duplicate edge found
                except AttributeError:
                    # Simple Graphs/DiGraphs
                    data = nxGraph.get_edge_data(u, v) or {}
                    if isinstance(data, dict) and data.get("type") == rel:
                        return

            # Add the edge with attributes
            nxGraph.add_edge(u, v, **attrs)

        # --- Iterate over all relationships -----------------------------------
        for relName, targets in relationships.items():
            # Validate predicate name
            if not isinstance(relName, str) or not relName.strip():
                raise ValueError("Relationship names must be non-empty strings.")

            if targets is None:
                continue
            if not isinstance(targets, list):
                raise ValueError(f"Relationship '{relName}' must map to a list of target dicts.")

            for target in targets:
                # Validate target shape
                if not isinstance(target, dict):
                    raise ValueError(f"Targets of '{relName}' must be dicts with '@id' and (optionally) '@type'.")

                targetUid = target.get("@id")
                targetType = target.get("@type")
                if "time" not in targetType:
                    if not isinstance(targetUid, str) or not targetUid.strip():
                        raise ValueError(f"Target under '{relName}' must contain a non-empty '@id'.")

                # Compose edge attributes
                edgeAttrs: Dict[str, Any] = {
                    "type": relName,
                    "subjectType": subjectType or "",
                    "objectType": targetType or "",
                }

                # Add forward edge only if both nodes already present
                if relName not in ["eko:hasEvaluationTimestep"]:
                    add_edge_if_present(subjectUid, targetUid, relName, edgeAttrs)

                # No automatic reverse edges here (requirement focuses on no creation/validation)

        return nxGraph

    @staticmethod
    def AddNodeByObject(
        nxGraph,
        object: dict,
        *,
        upsert: bool = True,
        applyDefaults: bool = True,
        extraAttrs: Optional[dict] = None,
        keepPSetMetadata: bool = False,   # keep original ifc:HasProperties only if True
    ):
        """
        Add a node to a NetworkX graph from a BTWIN JSON object.

        Args:
            nxGraph: A NetworkX graph instance (Graph, DiGraph, MultiGraph, MultiDiGraph).
            object: BTWIN object with at minimum '@id'. May include '@type' and 'name'.
            upsert: If True, update attributes when node exists; if False raise on duplicate.
            applyDefaults: If True, merge defaults from nxGraph.graph['node_defaults'].
            extraAttrs: Extra attributes to attach/override on the node.
            keepPSetMetadata: For IFC PropertySet, keep 'ifc:HasProperties' structure (in addition to flatten).

        Returns:
            nx.Graph: The same graph instance after insertion/update.

        Raises:
            ImportError: If NetworkX is not installed.
            TypeError: If inputs have invalid types or graph lacks NetworkX API.
            ValueError: If object['@id'] is missing/empty, or duplicate when upsert=False.
        """
        # -- imports & checks --
        try:
            import networkx as nx  # noqa: F401
        except Exception as exc:
            raise ImportError("NetworkX is required.") from exc

        if not hasattr(nxGraph, "nodes") or not hasattr(nxGraph, "add_node"):
            raise TypeError("nxGraph must be a NetworkX graph instance.")
        if not isinstance(object, dict):
            raise TypeError("object must be a dict.")

        uid = object.get("@id")
        if not isinstance(uid, str) or not uid.strip():
            raise ValueError("object['@id'] must be a non-empty string.")

        nodeType = object.get("@type")
        nodeName = object.get("name")

        # -- helpers ---------------------------------------------------------
        def is_pset(t) -> bool:
            return isinstance(t, str) and t.lower().replace("_", ":") == "ifc:ifcpropertyset"

        def flatten_pset_props(obj: dict) -> dict:
            """Return {propName: propValue} from 'ifc:HasProperties'/'hasProperties'."""
            out = {}
            propList = obj.get("ifc:HasProperties", obj.get("hasProperties", []))
            if isinstance(propList, list):
                for p in propList:
                    if not isinstance(p, dict):
                        continue
                    key = p.get("name")
                    if not key:
                        continue
                    # single or enumerated
                    if isinstance(p.get("nominalValue"), dict) and "value" in p["nominalValue"]:
                        val = p["nominalValue"]["value"]
                    elif isinstance(p.get("enumeratedValues"), list):
                        val = [it.get("value") for it in p["enumeratedValues"] if isinstance(it, dict)]
                    else:
                        val = None
                    out[str(key)] = val
            return out

        def normalize_iso_z(ts: Optional[str]) -> Optional[str]:
            """Try to normalize timestamps to ISO-8601 'Z'. Accept None/empty-like."""
            if ts is None:
                return None
            if not isinstance(ts, str):
                return None
            s = ts.strip()
            if not s or s.lower() in {"none", "null"}:
                return None
            # allow trailing Z
            try:
                if s.endswith("Z"):
                    dt = datetime.fromisoformat(s[:-1] + "+00:00")
                else:
                    dt = datetime.fromisoformat(s)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except Exception:
                # if parsing fails, keep original string (do not block)
                return s

        def extract_kpi_pairs(kpisObj) -> dict:
            """Return {kpiName: kpiValue} from btwin:hasKPIs (dict or list)."""
            pairs = {}
            if isinstance(kpisObj, dict):
                iterable = kpisObj.values()
            elif isinstance(kpisObj, list):
                iterable = kpisObj
            else:
                return pairs

            for kpi in iterable:
                if not isinstance(kpi, dict):
                    continue
                kName = kpi.get("name") or kpi.get("@id")
                # nominalValue → value
                kVal = None
                nv = kpi.get("nominalValue")
                if isinstance(nv, dict):
                    kVal = nv.get("value")
                if isinstance(kName, str) and kName.strip():
                    pairs[kName] = kVal
            return pairs

        # --- KPISet helpers ------------------------------------------
        def get_eval_timestep_from_relationships(obj: dict) -> tuple[Optional[str], Optional[str]]:
            """
            Extract (hasBeginning, hasEnd) from relationships['eko:hasEvaluationTimestep'][0].
            Returns (None, None) if missing or malformed. Uses normalize_iso_z when available.
            """
            rel = obj.get("relationships")
            if not isinstance(rel, dict):
                return None, None
            lst = rel.get("eko:hasEvaluationTimestep")
            if not (isinstance(lst, list) and lst and isinstance(lst[0], dict)):
                return None, None
            begin = lst[0].get("time:hasBeginning")
            end = lst[0].get("time:hasEnd")

            # optional: normalize if the normalize_iso_z helper is available
            try:
                b_norm = normalize_iso_z(begin)
            except Exception:
                b_norm = begin
            try:
                e_norm = normalize_iso_z(end)
            except Exception:
                e_norm = end
            return b_norm, e_norm


        def get_associated_object(obj: dict) -> tuple[Optional[str], Optional[str]]:
            """
            Extract first associated object (@id, @type) from relationships['eko:hasAssociatedObject'][0].
            """
            rel = obj.get("relationships")
            if not isinstance(rel, dict):
                return None, None
            lst = rel.get("eko:hasAssociatedObject")
            if not (isinstance(lst, list) and lst and isinstance(lst[0], dict)):
                return None, None
            rid = lst[0].get("@id")
            rtype = lst[0].get("@type")
            return (rid if isinstance(rid, str) and rid.strip() else None,
                    rtype if isinstance(rtype, str) and rtype.strip() else None)


        def extract_kpi_pairs_from_dict(kpis_dict: dict) -> dict:
            """
            From btwin:hasKPIs (DICT) extract {kpiName: kpiValue} and, when available, {kpiName_unit: unit}.
            For a KPI without 'name', use its '@id' as the key.
            """
            out = {}
            if not isinstance(kpis_dict, dict):
                return out
            for kpi_id, kpi in kpis_dict.items():
                if not isinstance(kpi, dict):
                    continue
                k_name = (kpi.get("name") or kpi.get("@id") or str(kpi_id)).strip() if isinstance(kpi.get("name"), str) else (kpi.get("@id") or str(kpi_id))
                nv = kpi.get("nominalValue", {})
                val = nv.get("value") if isinstance(nv, dict) else None
                unit = nv.get("unit") if isinstance(nv, dict) else None
                if isinstance(k_name, str) and k_name:
                    out[k_name] = val
                    if unit is not None:
                        out[f"{k_name}_unit"] = unit
            return out


        # -- defaults (optional) ---------------------------------------------
        attrs: dict = {}
        if applyDefaults:
            defaults = nxGraph.graph.get("node_defaults")
            if defaults is not None:
                if not isinstance(defaults, dict):
                    raise TypeError("nxGraph.graph['node_defaults'] must be a dict.")
                attrs.update(defaults)

        # -- build attrs ------------------------------------------------------
        if is_pset(nodeType) and not keepPSetMetadata:
            # Minimal schema for PSet: id, type, optional name, flattened key/values
            attrs = {"id": uid, "type": nodeType}
            if isinstance(nodeName, str) and nodeName.strip():
                attrs["name"] = nodeName
            attrs.update(flatten_pset_props(object))

        elif nodeType == "btwin:KPISet":
            # KPISet compression (BTWIN structure-aware):
            # - id, type, name
            # - hasBeginning/hasEnd from relationships['eko:hasEvaluationTimestep'][0]
            # - associated object (optional) as lightweight fields
            # - KPI pairs {kpiName: kpiValue} + {kpiName_unit: unit}
            attrs["id"] = uid
            attrs["type"] = nodeType
            if isinstance(nodeName, str) and nodeName.strip():
                attrs["name"] = nodeName

            # timestep from relationships
            begin, end = get_eval_timestep_from_relationships(object)
            attrs["hasBeginning"] = begin
            attrs["hasEnd"] = end

            # associated object (lightweight, without carrying the whole relationships structure)
            assoc_id, assoc_type = get_associated_object(object)
            if assoc_id:
                attrs["associatedObjectId"] = assoc_id
            if assoc_type:
                attrs["associatedObjectType"] = assoc_type

            # KPIs (dict) -> {name: value} (+ unit)
            kpi_pairs = extract_kpi_pairs_from_dict(object.get("btwin:hasKPIs", {}))
            attrs.update(kpi_pairs)

            # optional: copy extra "lightweight" fields, avoiding heavy structures
            # (we don't copy 'relationships' nor 'btwin:hasKPIs' since they are already compressed)
            for k, v in object.items():
                if k in {"@id", "@type", "name", "relationships", "btwin:hasKPIs"}:
                    continue
                attrs[k] = v

        else:
            # General case (and PSet with metadata kept): copy everything except 'relationships'
            attrs["id"] = uid
            if isinstance(nodeType, str) and nodeType.strip():
                attrs["type"] = nodeType
            if isinstance(nodeName, str) and nodeName.strip():
                attrs["name"] = nodeName

            for k, v in object.items():
                if k in {"@id", "@type", "name", "relationships"}:
                    continue
                # If PSet and keeping metadata, keep original structures and also flatten
                if is_pset(nodeType):
                    if keepPSetMetadata or k not in {"ifc:HasProperties", "hasProperties"}:
                        attrs[k] = v
                else:
                    attrs[k] = v

            # If PSet, add flattened pairs on top of metadata (if kept)
            if is_pset(nodeType):
                attrs.update(flatten_pset_props(object))

        # -- extra overrides (highest priority) -------------------------------
        if extraAttrs is not None:
            if not isinstance(extraAttrs, dict):
                raise TypeError("extraAttrs must be a dict.")
            attrs.update(extraAttrs)

        # -- upsert behavior --------------------------------------------------
        if uid in nxGraph:
            if not upsert:
                raise ValueError(f"Node '{uid}' already exists and upsert=False.")
            nxGraph.nodes[uid].update(attrs)  # update existing node attrs
        else:
            nxGraph.add_node(uid, **attrs)    # insert new node

        return nxGraph

    @staticmethod
    def ByJSON(
        source: Optional[Union[str, Path, dict]] = None,
        *,
        multigraph: bool = True,
        directed: bool = True
    ):
        """
        Import a NetworkX graph from JSON (node-link format).

        Args:
            source (str | Path | dict, optional): Path to the JSON file, a loaded dict,
                or a JSON string containing the node-link graph data.
            multigraph (bool, optional): Whether to treat the graph as a MultiGraph.
                Default True.
            directed (bool, optional): Whether to treat the graph as directed.
                Default True.

        Returns:
            networkx.Graph: The reconstructed NetworkX graph.

        Raises:
            ImportError: If `networkx` is not installed.
            ValueError: If the input cannot be parsed into a valid graph.
            OSError: If reading a file path fails.
        """
        # --- Dependencies -----------------------------------------------------
        try:
            import json

            import networkx as nx
        except Exception as exc:
            raise ImportError("networkx and json are required.") from exc

        # --- Load JSON data ---------------------------------------------------
        data = None
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise OSError(f"File not found: {path}")
            try:
                text = path.read_text(encoding="utf-8")
                data = json.loads(text)
            except Exception as exc:
                raise ValueError(f"Failed to read or parse JSON file '{path}'.") from exc
        elif isinstance(source, dict):
            data = source
        elif isinstance(source, str):
            # JSON string
            try:
                data = json.loads(source)
            except Exception as exc:
                raise ValueError("Failed to parse JSON string.") from exc
        else:
            raise ValueError("source must be a file path, JSON dict, or JSON string.")

        # --- Validate content -------------------------------------------------
        # NetworkX >= 3.2 uses "edges"; older versions use "links"
        has_edges = isinstance(data, dict) and "nodes" in data and ("links" in data or "edges" in data)
        if not has_edges:
            raise ValueError("Invalid JSON graph: expected keys 'nodes' and 'links' (or 'edges').")

        # --- Reconstruct the graph --------------------------------------------
        try:
            # nx.node_link_graph accepts whichever key is present
            G = nx.node_link_graph(data, multigraph=multigraph, directed=directed)
        except Exception as exc:
            raise ValueError("Failed to construct NetworkX graph from JSON.") from exc

        return G

    @staticmethod
    def ByJSONLD(
        jsonld: Optional[Dict[str, Any]] = None,
        *,
        jsonPath: Optional[Union[str, Path]] = None,
        graph=None,
        graphType: str = "MultiDiGraph",
        nodeUpsert: bool = True,
        applyNodeDefaults: bool = True,
        edgeDeduplicate: bool = True,
        validateGraph: bool = True,
        printReport: bool = True,
        haltOnInvalid: bool = False
    ) -> Tuple[Any, Dict[str, Any]]:
        """
        Build a NetworkX graph from a JSON-LD document (BTWIN format).

        Args:
            jsonld (dict, optional): JSON-LD document containing '@graph': [...].
                Provide either this or `jsonPath`.
            jsonPath (str | Path, optional): Path to a JSON file containing the JSON-LD.
            graph (NetworkX Graph, optional): Existing graph to populate. If None,
                a new graph is created with `graphType`.
            graphType (str, optional): Graph class to create when `graph` is None.
                One of {'Graph','DiGraph','MultiGraph','MultiDiGraph'}. Default 'MultiDiGraph'.
            nodeUpsert (bool, optional): Pass-through to NetworkXAddNodeByObject; if True,
                update existing nodes, else raise on duplicate. Default True.
            applyNodeDefaults (bool, optional): Apply `graph.graph['node_defaults']`
                when adding nodes. Default True.
            edgeDeduplicate (bool, optional): If True, skip adding duplicate edges
                with the same type. Default True.
            validateGraph (bool, optional): If True, run `NetworkXValidate` at the end.
            printReport (bool, optional): If validating, print the validation report.
            haltOnInvalid (bool, optional): If validating and invalidities are found,
                raise `ValueError`. Default False.

        Returns:
            (graph, report): A tuple with the populated NetworkX graph and a validation
                report dict. If `validateGraph=False`, the report is:
                {"ok": True, "invalidNodes": [], "invalidEdges": [], "counts": {...}, "allowed": {...}}
                with counts set to zeros.

        Raises:
            ImportError: If NetworkX is not installed.
            ValueError:  If neither `jsonld` nor `jsonPath` is provided, or the JSON-LD
                        lacks a proper `@graph` list.
            TypeError:   If `@graph` is not a list of dict nodes.
            OSError:     If reading `jsonPath` fails.

        Examples:
            >>> G, report = SpatialElement.ByJSONLD(jsonld=my_jsonld, validateGraph=True)
            >>> report["ok"]
            True
        """
        # --- Dependencies ------------------------------------------------------
        try:
            import json

            import networkx as nx  # noqa: F401
        except Exception as exc:
            raise ImportError("NetworkX (and json) are required. Install with `pip install networkx`.") from exc

        # --- Load JSON-LD from path if requested ------------------------------
        if jsonld is None and jsonPath is None:
            raise ValueError("Provide either `jsonld` or `jsonPath`.")
        if jsonld is None:
            p = Path(jsonPath)  # type: ignore[arg-type]
            with p.open("r", encoding="utf-8") as fh:
                jsonld = json.load(fh)

        # --- Extract @graph ----------------------------------------------------
        graphObjects = jsonld.get("@graph") if isinstance(jsonld, dict) else None
        if not isinstance(graphObjects, list):
            raise ValueError("JSON-LD must contain an '@graph' list.")

        # --- Prepare / create graph -------------------------------------------
        if graph is None:
            # Create a new empty graph using your constructor (robust default)
            graph = NetworkX.Constructor(graphType=graphType)
        # Quick API check
        if not hasattr(graph, "add_node") or not hasattr(graph, "add_edge"):
            raise TypeError("`graph` must be a NetworkX graph instance.")

        # --- First pass: add all nodes ----------------------------------------
        for obj in graphObjects:
            if obj is None:
                continue
            if not isinstance(obj, dict):
                raise TypeError("Each entry in '@graph' must be a dict representing a node.")
            # Add or update node with core attributes
            NetworkX.AddNodeByObject(
                graph,
                obj,
                upsert=nodeUpsert,
                applyDefaults=applyNodeDefaults,
            )

        # --- Second pass: add all edges ---------------------------------------
        for obj in graphObjects:
            if obj is None or not isinstance(obj, dict):
                continue
            NetworkX.AddEdgesByObject(
                graph,
                obj,
                deduplicate=edgeDeduplicate,
            )

        # --- Optional validation ----------------------------------------------
        if validateGraph:
            report = NetworkX.Validate(
                graph,
                printReport=printReport
            )
            if haltOnInvalid and not report.get("ok", False):
                raise ValueError("NetworkX validation failed; see report for details.")
            if printReport:
                print('Report:',report)
        else:
            report = {
                "ok": True,
                "invalidNodes": [],
                "invalidEdges": [],
                "counts": {"nodesChecked": 0, "edgesChecked": 0, "invalidNodes": 0, "invalidEdges": 0},
                "allowed": {"nodeTypes": set(), "edgeTypes": set()},
            }
            if printReport:
                print(report)

        # --- Done --------------------------------------------------------------
        return graph

    @staticmethod
    def CompactKPISets(
        nxGraph=None,
        *,
        overwriteExisting: bool = True,
        preferNonNull: bool = True,
        kpiSetTypeCandidates: Tuple[str, ...] = ("btwin:KPISet",),
        relCandidates: Tuple[str, ...] = ("eko:hasAssociatedObject", "HAS_ASSOCIATED_OBJECT"),
        relAttrKeys: Tuple[str, ...] = ("type", "label", "relationship", "relation", "name"),
        reservedKeys: Tuple[str, ...] = ("@id", "@type", "id", "type", "name", "relationships", "btwin:hasKPIs"),
        deleteOrphanKpiSets: bool = False,
        attachAllIfNoRelMatch: bool = False,
        # KPI projection options:
        includeUnits: bool = True,
        kpiNamePrefix: str = "",
        kpiUnitSuffix: str = "__unit",
        # >>> DO NOT emit these fields unless explicitly enabled
        includeTimestep: bool = False,
        includeAssociatedObject: bool = False,
        stripForbiddenKeys: bool = True,
        beginningKey: str = "hasBeginning",
        endKey: str = "hasEnd",
    ):
        """
        Flatten KPISet nodes into their associated owner nodes and (optionally) remove the KPISet nodes.

        Copies ONLY KPI pairs and lightweight attributes. By default it does NOT add
        'hasBeginning', 'hasEnd', 'associatedObjectId', 'associatedObjectType'.
        If 'stripForbiddenKeys' is True, these keys are removed from owners if already present.

        Args:
            nxGraph: NetworkX graph instance.
            overwriteExisting: Conflict policy for copied fields (overwrite on conflict).
            preferNonNull: When overwriting, keep the non-null value on conflict.
            kpiSetTypeCandidates: Type labels identifying KPISet nodes.
            relCandidates: Relationship labels used to detect owner edges.
            relAttrKeys: Edge attribute keys where the relationship label may be stored.
            reservedKeys: KPISet attributes NOT to propagate (meta/structural).
            deleteOrphanKpiSets: Delete KPISet nodes with no owners.
            attachAllIfNoRelMatch: Fallback attaching to all adjacent when no rel match.
            includeUnits: Also attach units as {name + kpiUnitSuffix: unit}.
            kpiNamePrefix: Prefix for KPI names on owner nodes.
            includeTimestep: If True, add {beginningKey, endKey} (default False).
            includeAssociatedObject: If True, add {'associatedObjectId', 'associatedObjectType'} (default False).
            stripForbiddenKeys: If True, remove forbidden keys from owners after processing.
            beginningKey: Field name for the interval beginning, if enabled.
            endKey: Field name for the interval end, if enabled.

        Returns:
            nxGraph
        """
        try:
            import networkx as nx
        except Exception as exc:
            raise ImportError("NetworkX is required. Install with `pip install networkx`.") from exc

        if nxGraph is None:
            raise ValueError("`nxGraph` must be provided.")
        if not isinstance(nxGraph, (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph)):
            raise TypeError("`nxGraph` must be a NetworkX graph instance.")

        kpiSetTypesCI = {str(t).lower() for t in kpiSetTypeCandidates}
        relCandidatesCI = {str(r).lower() for r in relCandidates}
        reservedSet = set(reservedKeys)

        forbiddenKeys = {beginningKey, endKey, "associatedObjectId", "associatedObjectType"}

        # ---- helpers
        def is_kpiset_node(nid) -> bool:
            data = nxGraph.nodes[nid]
            if not isinstance(data, dict):
                return False
            t = (data.get("type") or data.get("@type") or data.get("label") or "")
            return str(t).lower() in kpiSetTypesCI

        def edge_matches_rel(edgeData: dict) -> bool:
            for k in relAttrKeys:
                if k in edgeData and str(edgeData[k]).lower() in relCandidatesCI:
                    return True
            return False

        def normalize_iso_z(ts: Optional[str]) -> Optional[str]:
            if ts is None:
                return None
            if not isinstance(ts, str):
                return None
            s = ts.strip()
            if not s or s.lower() in {"none", "null"}:
                return None
            try:
                if s.endswith("Z"):
                    dt = datetime.fromisoformat(s[:-1] + "+00:00")
                else:
                    dt = datetime.fromisoformat(s)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except Exception:
                return s

        def get_eval_timestep_from_relationships(data: dict) -> Tuple[Optional[str], Optional[str]]:
            rel = data.get("relationships")
            if not isinstance(rel, dict):
                return None, None
            lst = rel.get("eko:hasEvaluationTimestep")
            if not (isinstance(lst, list) and lst and isinstance(lst[0], dict)):
                return None, None
            b = normalize_iso_z(lst[0].get("time:hasBeginning"))
            e = normalize_iso_z(lst[0].get("time:hasEnd"))
            return b, e

        def get_associated_object(data: dict) -> Tuple[Optional[str], Optional[str]]:
            rel = data.get("relationships")
            if not isinstance(rel, dict):
                return None, None
            lst = rel.get("eko:hasAssociatedObject")
            if not (isinstance(lst, list) and lst and isinstance(lst[0], dict)):
                return None, None
            rid = lst[0].get("@id")
            rtype = lst[0].get("@type")
            rid = rid if isinstance(rid, str) and rid.strip() else None
            rtype = rtype if isinstance(rtype, str) and rtype.strip() else None
            return rid, rtype

        def extract_kpi_pairs_from_dict(kpis: Any) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            if not isinstance(kpis, dict):
                return out
            for _, kpi in kpis.items():
                if not isinstance(kpi, dict):
                    continue
                name = kpi.get("name") or kpi.get("@id")
                if not isinstance(name, str) or not name.strip():
                    continue
                key = f"{kpiNamePrefix}{name}"
                nv = kpi.get("nominalValue")
                val = nv.get("value") if isinstance(nv, dict) else None
                out[key] = val
                if includeUnits and isinstance(nv, dict) and "unit" in nv:
                    out[f"{key}{kpiUnitSuffix}"] = nv.get("unit")
            return out

        def owner_nodes_for_kpiset(kpisetId) -> List[Any]:
            owners = set()
            if isinstance(nxGraph, (nx.DiGraph, nx.MultiDiGraph)):
                for _, v, ed in nxGraph.out_edges(kpisetId, data=True):
                    if edge_matches_rel(ed) or attachAllIfNoRelMatch:
                        owners.add(v)
                for u, _, ed in nxGraph.in_edges(kpisetId, data=True):
                    if edge_matches_rel(ed) or attachAllIfNoRelMatch:
                        owners.add(u)
                if not owners and not attachAllIfNoRelMatch:
                    for _, v, ed in nxGraph.out_edges(kpisetId, data=True):
                        if edge_matches_rel(ed):
                            owners.add(v)
                    for u, _, ed in nxGraph.in_edges(kpisetId, data=True):
                        if edge_matches_rel(ed):
                            owners.add(u)
            else:
                for u, v, ed in nxGraph.edges(kpisetId, data=True):
                    other = v if u == kpisetId else u
                    if edge_matches_rel(ed) or attachAllIfNoRelMatch:
                        owners.add(other)
                if not owners and not attachAllIfNoRelMatch:
                    for u, v, ed in nxGraph.edges(kpisetId, data=True):
                        other = v if u == kpisetId else u
                        if edge_matches_rel(ed):
                            owners.add(other)
            return list(owners)

        def attach_kv(ownerData: dict, key: str, val: Any) -> Tuple[bool, bool]:
            # Skip forbidden keys unconditionally
            if key in forbiddenKeys:
                return False, False
            if key not in ownerData:
                ownerData[key] = val
                return True, False
            # conflict
            if overwriteExisting:
                if preferNonNull and ownerData[key] is None and val is not None:
                    ownerData[key] = val
                elif not preferNonNull:
                    ownerData[key] = val
                # else: keep existing non-null
            return False, True

        # --- Scan KPISet nodes ---------------------------------------------
        kpiSetIds = [n for n in nxGraph.nodes if is_kpiset_node(n)]
        report = {
            "kpiSetsFound": len(kpiSetIds),
            "kpiSetsCompacted": 0,
            "kpiSetsOrphanDeleted": 0,
            "ownersTouched": 0,
            "propertiesAttached": 0,
            "conflicts": 0,
        }
        ownersTouchedSet = set()
        toDelete: List[Any] = []

        # --- Process each KPISet -------------------------------------------
        for ksid in kpiSetIds:
            data = nxGraph.nodes[ksid] if isinstance(nxGraph.nodes[ksid], dict) else {}
            owners = owner_nodes_for_kpiset(ksid)

            if not owners:
                if deleteOrphanKpiSets:
                    toDelete.append(ksid)
                    report["kpiSetsOrphanDeleted"] += 1
                continue

            # Prepare compacted fields from KPISet
            begin, end = get_eval_timestep_from_relationships(data)
            assoc_id, assoc_type = get_associated_object(data)
            kpiPairs = extract_kpi_pairs_from_dict(data.get("btwin:hasKPIs", {}))
            lightweight = {k: v for k, v in data.items() if k not in reservedSet}

            for ownerId in owners:
                ownerData = nxGraph.nodes[ownerId]
                attachedNow = 0
                conflictsNow = 0

                # 1) Timestep (only if explicitly enabled)
                if includeTimestep:
                    for key, val in ((beginningKey, begin), (endKey, end)):
                        a, c = attach_kv(ownerData, key, val)
                        attachedNow += int(a)
                        conflictsNow += int(c)

                # 2) Associated object (only if explicitly enabled)
                if includeAssociatedObject:
                    a, c = attach_kv(ownerData, "associatedObjectId", assoc_id)
                    attachedNow += int(a)
                    conflictsNow += int(c)
                    a, c = attach_kv(ownerData, "associatedObjectType", assoc_type)
                    attachedNow += int(a)
                    conflictsNow += int(c)

                # 3) KPI pairs (values + units)
                for k, v in kpiPairs.items():
                    a, c = attach_kv(ownerData, k, v)
                    attachedNow += int(a)
                    conflictsNow += int(c)

                # 4) Lightweight extra fields (NEVER emit forbidden keys)
                for k, v in lightweight.items():
                    a, c = attach_kv(ownerData, k, v)
                    attachedNow += int(a)
                    conflictsNow += int(c)

                # 5) Optionally strip forbidden keys if already present
                if stripForbiddenKeys:
                    for fk in forbiddenKeys:
                        if fk in ownerData:
                            del ownerData[fk]

                if attachedNow or conflictsNow:
                    ownersTouchedSet.add(ownerId)
                    report["propertiesAttached"] += attachedNow
                    report["conflicts"] += conflictsNow

            # Mark KPISet for deletion (compaction)
            toDelete.append(ksid)
            report["kpiSetsCompacted"] += 1

        # --- Delete KPISet nodes and incident edges ------------------------
        if toDelete:
            nxGraph.remove_nodes_from(toDelete)

        report["ownersTouched"] = len(ownersTouchedSet)
        print(report)
        return nxGraph


    @staticmethod
    def CompactPSets(
        nxGraph=None,
        *,
        overwriteExisting: bool = True,
        preferNonNull: bool = True,
        psetTypeCandidates = ("ifc:IfcPropertySet", "ifc_IfcPropertySet"),
        relCandidates = ("ifc:HasPropertySets", "ifc:HasPropertySet", "IFC_HASPROPERTYSET"),
        relAttrKeys = ("type", "label", "relationship", "relation", "name"),
        reservedKeys = ("@id", "@type", "id", "type", "name", "ifc:HasProperties", "hasProperties", "relationships"),
        deleteOrphanPSets: bool = False,
        attachAllIfNoRelMatch: bool = False,
    ):
        """
        Flatten PropertySet nodes into their owner nodes and remove the PSet nodes.

        Args:
            nxGraph (networkx.Graph | DiGraph | MultiGraph | MultiDiGraph):
                The input NetworkX graph to be compacted.
            overwriteExisting (bool):
                Overwrite owner properties on conflict. If False, existing owner values win.
            preferNonNull (bool):
                When both values exist and at least one is None, keep the non-null one.
                Applied only if `overwriteExisting=True`.
            psetTypeCandidates (tuple[str, ...]):
                Type/label candidates that identify PSet nodes (case-insensitive).
            relCandidates (tuple[str, ...]):
                Relationship labels that link owner → PSet (case-insensitive).
            relAttrKeys (tuple[str, ...]):
                Edge attribute keys where the relationship label may be stored.
            reservedKeys (tuple[str, ...]):
                PSet attributes NOT to propagate onto the owner (meta/structural).
            deleteOrphanPSets (bool):
                If True, delete PSet nodes with no owners; otherwise keep them.
            attachAllIfNoRelMatch (bool):
                If True and no edge matches `relCandidates`, attach PSet props to **all**
                adjacent nodes (fallback).

        Returns:
            tuple[nx.Graph, dict]:
                - The updated NetworkX graph (same instance, mutated).
                - A report dict:
                    {
                    "psetsFound": int,
                    "psetsCompacted": int,
                    "psetsOrphanDeleted": int,
                    "ownersTouched": int,
                    "propertiesAttached": int,
                    "conflicts": int
                    }

        Raises:
            ValueError: If `nxGraph` is None.
            TypeError:  If `nxGraph` is not a NetworkX graph instance.
        """
        # --- Imports & validations ---
        try:
            import networkx as nx
        except Exception as exc:
            raise ImportError("NetworkX is required. Install with `pip install networkx`.") from exc

        if nxGraph is None:
            raise ValueError("`nxGraph` must be provided.")
        if not isinstance(nxGraph, (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph)):
            raise TypeError("`nxGraph` must be a NetworkX graph instance.")

        # --- Normalize helpers ---
        psetTypesCI = {str(t).lower() for t in psetTypeCandidates}
        relCandidatesCI = {str(r).lower() for r in relCandidates}
        reservedSet = set(reservedKeys)

        def is_pset_node(nid) -> bool:
            data = nxGraph.nodes[nid]
            if not isinstance(data, dict):
                return False
            t = (data.get("type") or data.get("@type") or data.get("label") or "")
            return str(t).lower() in psetTypesCI

        def edge_matches_rel(edgeData: dict) -> bool:
            for k in relAttrKeys:
                if k in edgeData:
                    if str(edgeData[k]).lower() in relCandidatesCI:
                        return True
            return False

        def pset_props_to_copy(data: dict) -> dict:
            # Extract KVs to attach (exclude reserved/meta keys)
            return {k: v for k, v in data.items() if k not in reservedSet}

        def owner_nodes_for_pset(psetId):
            owners = set()
            if isinstance(nxGraph, (nx.DiGraph, nx.MultiDiGraph)):
                # Outgoing edges
                for _, v, ed in nxGraph.out_edges(psetId, data=True):
                    if edge_matches_rel(ed) or attachAllIfNoRelMatch:
                        owners.add(v)
                # Incoming edges
                for u, _, ed in nxGraph.in_edges(psetId, data=True):
                    if edge_matches_rel(ed) or attachAllIfNoRelMatch:
                        owners.add(u)
                # If no match and attachAllIfNoRelMatch=False, try strict match only
                if not owners and not attachAllIfNoRelMatch:
                    # strict: only edges matching relCandidates
                    for _, v, ed in nxGraph.out_edges(psetId, data=True):
                        if edge_matches_rel(ed):
                            owners.add(v)
                    for u, _, ed in nxGraph.in_edges(psetId, data=True):
                        if edge_matches_rel(ed):
                            owners.add(u)
            else:
                # Undirected: consider all incident edges
                for u, v, ed in nxGraph.edges(psetId, data=True):
                    other = v if u == psetId else u
                    if edge_matches_rel(ed) or attachAllIfNoRelMatch:
                        owners.add(other)
                if not owners and not attachAllIfNoRelMatch:
                    for u, v, ed in nxGraph.edges(psetId, data=True):
                        other = v if u == psetId else u
                        if edge_matches_rel(ed):
                            owners.add(other)
            return list(owners)

        # --- Scan PSet nodes ---
        psetIds = [n for n in nxGraph.nodes if is_pset_node(n)]
        report = {
            "psetsFound": len(psetIds),
            "psetsCompacted": 0,
            "psetsOrphanDeleted": 0,
            "ownersTouched": 0,
            "propertiesAttached": 0,
            "conflicts": 0,
        }

        ownersTouchedSet = set()
        toDelete = []

        # --- Process each PSet ---
        for psetId in psetIds:
            data = nxGraph.nodes[psetId] if isinstance(nxGraph.nodes[psetId], dict) else {}
            props = pset_props_to_copy(data)
            owners = owner_nodes_for_pset(psetId)

            if not owners:
                if deleteOrphanPSets:
                    toDelete.append(psetId)
                    report["psetsOrphanDeleted"] += 1
                # If not deleting orphans, leave the node as-is
                continue

            # Attach properties to each owner
            for ownerId in owners:
                ownerData = nxGraph.nodes[ownerId]
                attachedNow = 0
                conflictsNow = 0

                for k, v in props.items():
                    if k not in ownerData:
                        ownerData[k] = v
                        attachedNow += 1
                    else:
                        # Conflict resolution
                        conflictsNow += 1
                        if overwriteExisting:
                            if preferNonNull and (ownerData[k] is None) and (v is not None):
                                ownerData[k] = v
                            elif not preferNonNull:
                                ownerData[k] = v
                            else:
                                # preferNonNull=True and owner has non-null -> do nothing
                                pass
                        # else overwriteExisting=False -> keep existing

                if attachedNow or conflictsNow:
                    ownersTouchedSet.add(ownerId)
                    report["propertiesAttached"] += attachedNow
                    report["conflicts"] += conflictsNow

            # Mark PSet for deletion
            toDelete.append(psetId)
            report["psetsCompacted"] += 1

        # --- Delete PSets (and incident edges) ---
        if toDelete:
            nxGraph.remove_nodes_from(toDelete)

        report["ownersTouched"] = len(ownersTouchedSet)
        print(report)
        return nxGraph

    @staticmethod
    def Constructor(
        graphType: Literal["Graph", "DiGraph", "MultiGraph", "MultiDiGraph"] = "MultiDiGraph",
        *,
        name: Optional[str] = None,
        graphAttrs: Optional[Dict[str, Any]] = None,
        nodeDefaults: Optional[Dict[str, Any]] = None,
        edgeDefaults: Optional[Dict[str, Any]] = None
    ):
        """
        Create and return an empty NetworkX graph suitable for BTWIN.

        Args:
            graphType (Literal["Graph","DiGraph","MultiGraph","MultiDiGraph"], optional):
                The NetworkX graph class to instantiate. Default "MultiDiGraph".
            name (str, optional):
                A human-readable name saved under G.graph['name'].
            graphAttrs (dict, optional):
                Arbitrary metadata stored under G.graph (e.g., version, author).
            nodeDefaults (dict, optional):
                Default attributes to apply to future nodes (stored under
                G.graph['node_defaults'] for your pipeline to use).
            edgeDefaults (dict, optional):
                Default attributes to apply to future edges (stored under
                G.graph['edge_defaults'] for your pipeline to use).

        Returns:
            networkx.Graph:
                An empty NetworkX graph instance matching the requested type.

        Raises:
            ImportError:
                If NetworkX is not installed.
            ValueError:
                If `graphType` is not one of the allowed values.
            TypeError:
                If `graphAttrs`, `nodeDefaults`, or `edgeDefaults` are not dicts.

        """
        # Import locally to provide a clean ImportError if missing
        try:
            import networkx as nx
        except Exception as exc:
            raise ImportError("NetworkX is required to construct graphs. Install with `pip install networkx`.") from exc

        # Validate inputs (basic defensive checks)
        if graphType not in {"Graph", "DiGraph", "MultiGraph", "MultiDiGraph"}:
            raise ValueError("graphType must be one of {'Graph','DiGraph','MultiGraph','MultiDiGraph'}.")

        if graphAttrs is not None and not isinstance(graphAttrs, dict):
            raise TypeError("graphAttrs must be a dict if provided.")
        if nodeDefaults is not None and not isinstance(nodeDefaults, dict):
            raise TypeError("nodeDefaults must be a dict if provided.")
        if edgeDefaults is not None and not isinstance(edgeDefaults, dict):
            raise TypeError("edgeDefaults must be a dict if provided.")

        # Choose the NetworkX class based on graphType
        # (MultiDiGraph is a good default for semantic graphs: multiple typed edges, direction)
        graphClass = getattr(nx, graphType)

        # Instantiate empty graph
        G = graphClass()

        # Set optional metadata on the graph
        if name:
            G.graph["name"] = name
        if graphAttrs:
            # Merge provided graph attributes
            for k, v in graphAttrs.items():
                G.graph[k] = v

        # Store defaults for later use by your pipeline (not automatically applied)
        if nodeDefaults:
            G.graph["node_defaults"] = dict(nodeDefaults)  # shallow copy
        if edgeDefaults:
            G.graph["edge_defaults"] = dict(edgeDefaults)  # shallow copy

        # Return the empty, ready-to-use graph
        return G

    @staticmethod
    def IsolatedNodes(nxGraph=None):
        """
        Identify and return a list of isolated nodes in the given NetworkX graph.

        Args:
            nxGraph (networkx.Graph): A valid NetworkX graph object containing nodes and edges.

        Returns:
            list: A list of nodes that are isolated within the graph.
                Each element in the list is a node identifier (e.g., int, str).

        Raises:
            TypeError: If the provided graph is not a valid NetworkX Graph object.
        """

        # Validate input type
        import networkx as nx
        if not isinstance(nxGraph, (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph)):
            raise TypeError("Input must be a valid NetworkX graph object.")

        # Extract nodes with degree equal to 0 (isolated)
        isolatedNodes = [node for node, degree in nxGraph.degree() if degree == 0]

        return isolatedNodes

    @staticmethod
    def NodeLinkedPSets(nxGraph=None, nodeObjectUID=None):
        """
        Return all Property Set (PSet) nodes linked to a given object node.

        Args:
            nxGraph (networkx.Graph | networkx.DiGraph | networkx.MultiGraph | networkx.MultiDiGraph):
                The NetworkX graph containing object and PSet nodes.
            nodeObjectUID (hashable | str | int):
                The unique identifier of the object node. It can be:
                - the actual node key in `nxGraph`, or
                - a value stored in node attributes 'UID' or 'id'.

        Returns:
            list[tuple[hashable, dict]]:
                A list of `(psetNodeId, psetData)` for all linked PSet nodes found.
                The list is de-duplicated and order-preserving.

        Raises:
            ValueError: If inputs are missing or the source node cannot be resolved.
            TypeError: If `nxGraph` is not a supported NetworkX graph instance.
        """
        # --- Imports & validation ---
        import networkx as nx

        if nxGraph is None or nodeObjectUID is None:
            raise ValueError("Both `nxGraph` and `nodeObjectUID` must be provided.")
        if not isinstance(nxGraph, (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph)):
            raise TypeError("`nxGraph` must be a NetworkX graph instance.")

        # --- Resolve the source node by ID or by attributes (UID / id) ---
        if nodeObjectUID in nxGraph:
            sourceNode = nodeObjectUID
        else:
            candidates = []
            for nodeId, nodeData in nxGraph.nodes(data=True):
                if isinstance(nodeData, dict) and (
                    nodeData.get("UID") == nodeObjectUID or nodeData.get("id") == nodeObjectUID
                ):
                    candidates.append(nodeId)
            if not candidates:
                raise ValueError(f"No node found matching UID/id '{nodeObjectUID}'.")
            if len(candidates) > 1:
                raise ValueError(f"Multiple nodes match UID/id '{nodeObjectUID}': {candidates}")
            sourceNode = candidates[0]

        # --- Helper: normalize label checks (case-insensitive, variant-friendly) ---
        def is_pset_node(nodeId):
            data = nxGraph.nodes[nodeId]
            if not isinstance(data, dict):
                return False
            val = (data.get("label") or data.get("type") or data.get("@type") or "").lower()
            return val in ("ifc:ifcpropertyset", "ifc_ifcpropertyset")

        rel_candidates_ci = {"ifc:haspropertysets", "ifc:haspropertyset", "ifc_haspropertyset"}

        def edge_matches(edgeData):
            if not isinstance(edgeData, dict):
                return False
            # Common attributes where a relationship/type label could be stored
            for key in ("relationship", "relation", "label", "type", "name"):
                if key in edgeData:
                    val = str(edgeData[key]).lower()
                    if val in rel_candidates_ci:
                        return True
            return False

        # --- Collect neighbor nodes (handle directed/undirected & multi graphs) ---
        psetIds = []

        if isinstance(nxGraph, (nx.DiGraph, nx.MultiDiGraph)):
            # Outgoing edges
            for _, v, eData in nxGraph.out_edges(sourceNode, data=True):
                if is_pset_node(v) and edge_matches(eData):
                    psetIds.append(v)
            # Incoming edges
            for u, _, eData in nxGraph.in_edges(sourceNode, data=True):
                if is_pset_node(u) and edge_matches(eData):
                    psetIds.append(u)
        else:
            for u, v, eData in nxGraph.edges(sourceNode, data=True):
                other = v if u == sourceNode else u
                if is_pset_node(other) and edge_matches(eData):
                    psetIds.append(other)

        # --- Deduplicate while preserving order ---
        seen = set()
        psetIdsUnique = []
        for nid in psetIds:
            if nid not in seen:
                seen.add(nid)
                psetIdsUnique.append(nid)

        # --- Return pairs (nodeId, nodeData) for downstream compatibility ---
        return [(nid, nxGraph.nodes[nid]) for nid in psetIdsUnique]

    @staticmethod
    def NodeLinkedNodes(nxGraph=None, nodeObjectUID=None, nodeNumber=None,
                        linkedNodesType=None, relationshipName=None):
        """
        Retrieve neighboring nodes filtered by node type and/or relationship label.

        Args:
            nxGraph (nx.Graph | nx.DiGraph | nx.MultiGraph | nx.MultiDiGraph): Graph.
            nodeObjectUID (hashable | str | int | None): UID stored in node attributes
                (tries 'uid','UID','id','objectUID'). Ignored if nodeNumber is given.
            nodeNumber (hashable | None): ID of the source node in the graph (takes priority).
            linkedNodesType (str | None): Required type of the neighbor node; checks
                the neighbor attributes among ('label','type','node_type').
            relationshipName (str | None): Required relationship label; checks
                the edge attributes among ('relationship','relation','label','type','name').

        Returns:
            list: Identifiers of the neighbor nodes matching the filters.

        Raises:
            ValueError: Missing/ambiguous inputs or unresolved UID.
            TypeError: nxGraph is not a supported NetworkX instance.
            KeyError: nodeNumber does not exist in the graph.
        """
        # --- Validate inputs ---
        import networkx as nx
        if nxGraph is None:
            raise ValueError("`graph` must be provided.")
        if not isinstance(nxGraph, (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph)):
            raise TypeError("`graph` must be a NetworkX graph instance.")
        if nodeNumber is None and nodeObjectUID is None:
            raise ValueError("Provide `nodeNumber` or `nodeObjectUID`.")

        # --- Resolve source node ---
        if nodeNumber is not None:
            if nodeNumber not in nxGraph:
                raise KeyError(f"`nodeNumber` '{nodeNumber}' not found in graph.")
            sourceNode = nodeNumber
        else:
            uidAttrs = ("uid", "UID", "id", "objectUID")
            matches = []
            for nodeId, data in nxGraph.nodes(data=True):
                if isinstance(data, dict) and any(
                    attr in data and data[attr] == nodeObjectUID for attr in uidAttrs
                ):
                    matches.append(nodeId)
            if not matches:
                raise ValueError(f"No node matches `nodeObjectUID` '{nodeObjectUID}'.")
            if len(matches) > 1:
                raise ValueError(f"Multiple nodes match `nodeObjectUID` '{nodeObjectUID}': {matches}")
            sourceNode = matches[0]

        # --- Helpers for filters ---
        relAttrs = ("relationship", "relation", "label", "type", "name")
        nodeTypeAttrs = ("label", "type", "node_type")

        def edge_matches(data):
            # Accept all if no relationship filter
            if relationshipName is None:
                return True
            if not isinstance(data, dict):
                return False
            # MultiGraph/MultiDiGraph: data may already be the edge attribute dict
            # or a container of multiple edges; normalize it.
            candidates = []
            if data and all(isinstance(v, dict) for v in data.values()) and not any(k in relAttrs for k in data.keys()):
                candidates = list(data.values())
            else:
                candidates = [data]
            for ed in candidates:
                if any(ed.get(a) == relationshipName for a in relAttrs):
                    return True
            return False

        def node_type_matches(nid):
            if linkedNodesType is None:
                return True
            nd = nxGraph.nodes[nid]
            if not isinstance(nd, dict):
                return False
            return any(nd.get(a) == linkedNodesType for a in nodeTypeAttrs)

        # --- Collect neighbors and apply filters on the fly (no unhashable in set) ---
        results = []

        if isinstance(nxGraph, (nx.DiGraph, nx.MultiDiGraph)):
            # Outgoing
            for _, v, data in nxGraph.out_edges(sourceNode, data=True):
                if edge_matches(data) and node_type_matches(v):
                    results.append(v)
            # Incoming
            for u, _, data in nxGraph.in_edges(sourceNode, data=True):
                if edge_matches(data) and node_type_matches(u):
                    results.append(u)
        else:
            for u, v, data in nxGraph.edges(sourceNode, data=True):
                other = v if u == sourceNode else u
                if edge_matches(data) and node_type_matches(other):
                    results.append(other)

        # --- Deduplicate preserving order ---
        seen = set()
        dedup = []
        for n in results:
            if n not in seen:
                seen.add(n)
                dedup.append(n)
        return dedup

    @staticmethod
    def SubgraphByObjectTypes(
        nxGraph=None,
        objectTypes: Optional[Iterable[str]] = None,
        *,
        typeAttr: str = "type",
        keepIsolates: bool = True
    ):
        """
        Create an induced subgraph keeping only nodes whose type is in `objectTypes`.

        Args:
            nxGraph (networkx.Graph, required):
                Source NetworkX graph (Graph/DiGraph/MultiGraph/MultiDiGraph).
            objectTypes (Iterable[str], required):
                Collection of allowed node types (e.g., ['bot:Space','bot:Storey']).
            typeAttr (str, optional):
                Name of the node attribute holding the semantic type. Default "type".
            keepIsolates (bool, optional):
                If False, drop nodes with no incident edges in the resulting subgraph.
                Default True.

        Returns:
            networkx.Graph:
                A *copy* of the induced subgraph containing only nodes whose
                `typeAttr` value is in `objectTypes` (and, optionally, without isolates).

        Raises:
            ImportError:
                If NetworkX is not installed.
            TypeError:
                If `graph` is not a NetworkX graph-like object, or `objectTypes` is not iterable of str.
            ValueError:
                If `objectTypes` is missing/empty, or if `typeAttr` is empty.
        """
        # --- Dependencies ------------------------------------------------------
        try:
            import networkx as nx  # noqa: F401
        except Exception as exc:
            raise ImportError("NetworkX is required. Install with `pip install networkx`.") from exc

        # --- Basic validations -------------------------------------------------
        if nxGraph is None or not hasattr(nxGraph, "nodes") or not hasattr(nxGraph, "subgraph"):
            raise TypeError("graph must be a valid NetworkX graph instance.")

        if objectTypes is None:
            raise ValueError("objectTypes must be provided (e.g., ['bot:Space','bot:Storey']).")

        # Ensure objectTypes is a set of non-empty strings
        try:
            objectTypeSet: Set[str] = {t for t in objectTypes if isinstance(t, str) and t.strip()}
        except Exception as exc:
            raise TypeError("objectTypes must be an iterable of strings.") from exc
        if not objectTypeSet:
            raise ValueError("objectTypes must contain at least one non-empty string.")

        if not isinstance(typeAttr, str) or not typeAttr.strip():
            raise ValueError("typeAttr must be a non-empty string.")

        # --- Select nodes matching requested types -----------------------------
        # (Prefer induced subgraph for correctness & speed)
        keepNodes = [
            n for n, data in nxGraph.nodes(data=True)
            if isinstance(data, dict) and data.get(typeAttr) in objectTypeSet
        ]

        # If nothing matches, return an empty graph of the same class
        if not keepNodes:
            # Create an empty graph of same type
            G_empty = nxGraph.__class__()
            # Preserve graph-level attributes to keep metadata
            if hasattr(nxGraph, "graph"):
                G_empty.graph.update(getattr(nxGraph, "graph", {}))
            return G_empty

        # Build induced subgraph and make it independent of the original
        subGraph = nxGraph.subgraph(keepNodes).copy()

        # Optionally drop isolates
        if not keepIsolates:
            isolates = list(nx.isolates(subGraph))
            if isolates:
                subGraph.remove_nodes_from(isolates)

        return subGraph

    @staticmethod
    def SubgraphByObjectUID(nxGraph=None, objectUID=None, nodeDegree=2):
        """
        Extract a subgraph around a node identified by UID or ID, limited by degree distance.

        Args:
            nxGraph (networkx.Graph | networkx.DiGraph | networkx.MultiGraph | networkx.MultiDiGraph):
                The source NetworkX graph.
            objectUID (str | int | hashable):
                Unique identifier of the target node. May be the actual node key in the graph
                or stored in node attributes ('UID', 'id').
            nodeDegree (int, optional):
                The maximum distance (number of edges) from the target node to include.
                Default is 2.

        Returns:
            networkx.Graph:
                A subgraph induced by all nodes within `nodeDegree` steps from the target node.
                The subgraph is a copy (safe to modify independently).

        Raises:
            ValueError: If inputs are missing or the node cannot be resolved.
            TypeError: If the graph type is not a NetworkX graph.
        """
        import networkx as nx

        # --- Validate inputs ---
        if nxGraph is None or objectUID is None:
            raise ValueError("Both `graph` and `objectUID` must be provided.")
        if not isinstance(nxGraph, (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph)):
            raise TypeError("`graph` must be a NetworkX graph instance.")

        # --- Resolve the source node ---
        if objectUID in nxGraph:
            sourceNode = objectUID
        else:
            # Try to resolve via node attributes
            candidates = []
            for nodeId, nodeData in nxGraph.nodes(data=True):
                if not isinstance(nodeData, dict):
                    continue
                if nodeData.get("UID") == objectUID or nodeData.get("id") == objectUID:
                    candidates.append(nodeId)
            if not candidates:
                raise ValueError(f"No node found with UID/id = '{objectUID}'.")
            if len(candidates) > 1:
                raise ValueError(f"Multiple nodes found for UID/id = '{objectUID}': {candidates}")
            sourceNode = candidates[0]

        # --- BFS: find all nodes within the specified degree ---
        nodesWithinDegree = nx.single_source_shortest_path_length(
            nxGraph, source=sourceNode, cutoff=nodeDegree
        ).keys()

        # --- Induce subgraph ---
        subgraph = nxGraph.subgraph(nodesWithinDegree).copy()

        print(f"Subgraph for {objectUID} (resolved as '{sourceNode}') with degree {nodeDegree}")
        return subgraph

    @staticmethod
    def ToNEO4J(
        nxGraph=None,
        NEO4J_URI='neo4j+s://53a5a7ce.databases.neo4j.io',
        NEO4J_USERNAME='neo4j',
        NEO4J_PASSWORD='***',
        wipeDb=False,
        authorDefault='AM',
    ):
        """
        Import a NetworkX graph into Neo4j. Falls back to node 'id' or node key when 'UID' is missing.

        Args:
            nxGraph: NetworkX graph (nodes may have 'UID' or 'id'; edges may have 'label' or 'type').
            NEO4J_URI: Neo4j connection URI.
            NEO4J_USERNAME: Neo4j username.
            NEO4J_PASSWORD: Neo4j password.
            wipeDb: if True, clears the DB before import.
            authorDefault: default 'author' property on nodes.

        Returns:
            dict: {"nodesCreatedOrMerged": int, "relsCreatedOrMerged": int, "nodesSkipped": int, "relsSkipped": int}

        Raises:
            ValueError: If `nxGraph` is None.
            TypeError: If `nxGraph` is not a NetworkX graph instance.
            neo4j.exceptions.Neo4jError: On Neo4j database errors.
        """
        # --- Imports & helpers ---
        import json
        import re

        import networkx as nx
        from neo4j import GraphDatabase

        if nxGraph is None:
            raise ValueError("`nxGraph` must be provided.")
        if not isinstance(nxGraph, (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph)):
            raise TypeError("`nxGraph` must be a NetworkX graph instance.")

        def sanitize_identifier(name: str, prefix: str = "L_") -> str:
            safe = re.sub(r"[:\W]+", "_", str(name))
            if not safe:
                safe = f"{prefix}EMPTY"
            if safe[0].isdigit():
                safe = f"{prefix}{safe}"
            return safe

        def sanitize_prop_key(key: str) -> str:
            safe = re.sub(r"[:\W]+", "_", str(key))
            if not safe:
                safe = "P_EMPTY"
            if safe[0].isdigit():
                safe = f"P_{safe}"
            return safe

        def to_json_safe(value):
            try:
                json.dumps(value)
                return value
            except Exception:
                return str(value)

        # Optional: P-Sets (best-effort)
        def extract_pset_props(graph, nodeUid: str) -> dict:
            props = {}
            try:
                btwinPsets = NetworkX.NodeLinkedPSets(graph=graph, nodeUID=nodeUid)
            except Exception:
                btwinPsets = []
            for pset in btwinPsets or []:
                if not isinstance(pset, (list, tuple)) or len(pset) < 2:
                    continue
                for prop in (pset[1].get('hasProperties') or []):
                    key = prop.get('name')
                    val = (prop.get('nominalValue') or {}).get('value')
                    if key is not None:
                        props[sanitize_prop_key(key)] = to_json_safe(val)
            return props

        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        driver.verify_connectivity()

        def cy_delete_all(tx):
            tx.run("MATCH (n) DETACH DELETE n")

        def cy_merge_node(tx, label: str, uid: str, props: dict):
            tx.run(f"MERGE (n:{label} {{UID: $uid}}) SET n += $props", uid=uid, props=props)

        def cy_merge_rel(tx, uid1: str, uid2: str, rel_type: str):
            tx.run(
                f"MATCH (a {{UID: $uid1}}), (b {{UID: $uid2}}) MERGE (a)-[r:{rel_type}]->(b)",
                uid1=uid1, uid2=uid2
            )

        nodesCreatedOrMerged = relsCreatedOrMerged = nodesSkipped = relsSkipped = 0

        try:
            with driver.session() as session:
                if wipeDb:
                    try: session.execute_write(cy_delete_all)
                    except AttributeError: session.write_transaction(cy_delete_all)

                # --- Nodes ---
                for nodeId, nodeData in nxGraph.nodes(data=True):
                    try:
                        nodeData = nodeData or {}
                        # UID fallback chain: nodeData['UID'] -> nodeData['id'] -> nodeId
                        rawUid = nodeData.get("UID", nodeData.get("id", nodeId))
                        uid = str(rawUid)

                        # Label fallback chain: 'label' -> 'type' -> 'DefaultLabel'
                        rawLabel = nodeData.get("label") or nodeData.get("type") or "DefaultLabel"
                        label = sanitize_identifier(rawLabel)

                        # Properties (exclude UID if present)
                        props = {"author": authorDefault}
                        for k, v in nodeData.items():
                            if k == "UID":
                                continue
                            props[sanitize_prop_key(k)] = to_json_safe(v)

                        # Ensure 'name' matches the NetworkX node identifier
                        props["name"] = str(nodeData['name']) if 'name' in nodeData else str(nodeId)

                        # Enrich from P-Sets
                        props.update(extract_pset_props(nxGraph, uid))

                        # Sort for deterministic order
                        props = {k: props[k] for k in sorted(props)}

                        try: session.execute_write(cy_merge_node, label, uid, props)
                        except AttributeError: session.write_transaction(cy_merge_node, label, uid, props)
                        nodesCreatedOrMerged += 1
                    except Exception:
                        nodesSkipped += 1

                # --- Relationships ---
                for u, v, edgeData in nxGraph.edges(data=True):
                    try:
                        uData = nxGraph.nodes[u] or {}
                        vData = nxGraph.nodes[v] or {}

                        uid1 = str(uData.get("UID", uData.get("id", u)))
                        uid2 = str(vData.get("UID", vData.get("id", v)))

                        # Relationship: prefer 'label', fallback 'type', default RELATED
                        rawRel = (edgeData or {}).get("label") or (edgeData or {}).get("type") or "RELATED"
                        relType = sanitize_identifier(rawRel).upper()

                        if relType == "IFC_HASPROPERTYSET":
                            relsSkipped += 1
                            continue

                        try: session.execute_write(cy_merge_rel, uid1, uid2, relType)
                        except AttributeError: session.write_transaction(cy_merge_rel, uid1, uid2, relType)
                        relsCreatedOrMerged += 1
                    except Exception:
                        relsSkipped += 1

            summary = {
                "nodesCreatedOrMerged": nodesCreatedOrMerged,
                "relsCreatedOrMerged": relsCreatedOrMerged,
                "nodesSkipped": nodesSkipped,
                "relsSkipped": relsSkipped,
            }
            print("Graph imported into Neo4j successfully!", summary)
            return summary
        finally:
            driver.close()



    @staticmethod
    def ToJSON(
        nxGraph=None,
        savePath: Optional[Union[str, Path]] = None,
        *,
        indent: int = 2,
        sortKeys: bool = True,
        ensureAscii: bool = False
    ) -> str:
        """
        Export a NetworkX graph to a JSON file (node-link format).

        Args:
            nxGraph (networkx.Graph, required): A NetworkX Graph/DiGraph/MultiGraph/MultiDiGraph.
            savePath (str | Path, optional): File path to save the JSON. If None, no file is written.
            indent (int, optional): Indentation level for pretty-printing JSON. Default 2.
            sortKeys (bool, optional): Whether to sort keys in the output JSON. Default True.
            ensureAscii (bool, optional): If True, non-ASCII characters are escaped. Default False.

        Returns:
            str: The JSON string representation of the graph in node-link format.

        Raises:
            ImportError: If `networkx` is not installed.
            TypeError: If `nxGraph` is not a NetworkX graph-like object.
            OSError: If saving to `savePath` fails.
        """
        # --- Import dependencies ----------------------------------------------
        try:
            import json

            import networkx as nx
        except Exception as exc:
            raise ImportError("networkx and json are required.") from exc

        # --- Validate graph ---------------------------------------------------
        if nxGraph is None or not hasattr(nxGraph, "nodes") or not hasattr(nxGraph, "edges"):
            raise TypeError("graph must be a valid NetworkX graph instance.")

        # --- Convert graph to node-link dict ----------------------------------
        try:
            data = nx.node_link_data(nxGraph)
        except Exception as exc:
            raise ValueError("Failed to convert NetworkX graph to node-link format.") from exc

        # --- Serialize dict to JSON string ------------------------------------
        try:
            jsonData = json.dumps(
                data,
                indent=indent,
                sort_keys=sortKeys,
                ensure_ascii=ensureAscii
            )
        except Exception as exc:
            raise ValueError("Failed to serialize graph data to JSON.") from exc

        # --- Optionally save to file ------------------------------------------
        if savePath:
            outPath = Path(savePath)
            if outPath.suffix.lower() != ".json":
                outPath = outPath.with_suffix(".json")
            try:
                outPath.write_text(jsonData, encoding="utf-8")
            except Exception as exc:
                raise OSError(f"Failed to write JSON to '{outPath}'.") from exc

        # --- Return JSON string -----------------------------------------------
        return jsonData

    @staticmethod
    def Validate(
        nxGraph,
        *,
        schemaProvider: Optional[Any] = None,
        nodeTypeAttr: str = "type",
        edgeTypeAttr: str = "type",
        printReport: bool = True
    ) -> Dict[str, Any]:
        """
        Validate node and edge types in a NetworkX graph against the schema.

        Description:
            Checks that:
              1) Each node has a valid semantic type (by default in node['type'])
                 and that this value exists in the schema's allowed classes.
              2) Each edge has a valid predicate (by default in edge['type'])
                 and that this value exists in the schema's allowed relationships.

        Args:
            nxGraph: A NetworkX graph instance (Graph, DiGraph, MultiGraph, MultiDiGraph).
            schemaProvider (optional): Object providing Types()/Relationships() (or RelationshipNames()).
                                       Defaults to `SpatialElement`.
            nodeTypeAttr (str, optional): Attribute name holding node type. Default "type".
            edgeTypeAttr (str, optional): Attribute name holding edge type (predicate). Default "type".
            printReport (bool, optional): If True, print a human-readable report on validation failures.

        Returns:
            dict: A report with the following structure:
                {
                  "ok": bool,
                  "invalidNodes": [
                      {"id": "<nodeId>", "foundType": "<value>", "reason": "<msg>"}, ...
                  ],
                  "invalidEdges": [
                      {"u": "<src>", "v": "<dst>", "key": "<k or None>", "foundType": "<value>", "reason": "<msg>"}, ...
                  ],
                  "counts": {
                      "nodesChecked": int,
                      "edgesChecked": int,
                      "invalidNodes": int,
                      "invalidEdges": int
                  },
                  "allowed": {
                      "nodeTypes": set([...]),
                      "edgeTypes": set([...])
                  }
                }

        Raises:
            ImportError: If NetworkX is not installed.
            TypeError:   If `nxGraph` does not look like a NetworkX graph or schema provider is invalid.
        """

        # --- Import here to give a precise error if networkx is missing --------
        try:
            import networkx as nx  # noqa: F401
        except Exception as exc:
            raise ImportError("NetworkX is required. Install with `pip install networkx`.") from exc

        # --- Basic graph sanity check ------------------------------------------
        if not hasattr(nxGraph, "nodes") or not hasattr(nxGraph, "edges"):
            raise TypeError("nxGraph must be a NetworkX graph instance.")

        # --- Resolve schema provider -------------------------------------------
        provider = schemaProvider or Schema
        if not (hasattr(provider, "Types") and callable(getattr(provider, "Types"))):
            raise TypeError("schemaProvider must implement Types().")
        # Relationships can be provided either via Relationships() or RelationshipNames()
        relNames: Optional[Iterable[str]] = None
        if hasattr(provider, "Relationships") and callable(getattr(provider, "Relationships")):
            try:
                relNames = list((provider.Relationships() or {}).keys())
            except Exception:
                relNames = None
        if relNames is None:
            if hasattr(provider, "RelationshipNames") and callable(getattr(provider, "RelationshipNames")):
                relNames = list(provider.RelationshipNames())
            else:
                raise TypeError("schemaProvider must implement Relationships() or RelationshipNames().")

        # --- Build allowed sets -------------------------------------------------
        try:
            allowedNodeTypes: Set[str] = set((provider.Types() or {}).keys())
        except Exception as exc:
            raise TypeError("Failed to load class types from schemaProvider.Types().") from exc

        allowedEdgeTypes: Set[str] = set(relNames or [])

        # --- Prepare report containers -----------------------------------------
        invalidNodes = []
        invalidEdges = []
        nodesChecked = 0
        edgesChecked = 0

        # --- Validate nodes ----------------------------------------------------
        for nodeId, data in nxGraph.nodes(data=True):
            nodesChecked += 1
            foundType = data.get(nodeTypeAttr)
            # Require a non-empty string for type
            if not isinstance(foundType, str) or not foundType.strip():
                invalidNodes.append({
                    "id": nodeId,
                    "foundType": foundType,
                    "reason": f"Missing or invalid node '{nodeTypeAttr}'"
                })
                continue
            # Check membership in allowed set
            if foundType not in allowedNodeTypes:
                invalidNodes.append({
                    "id": nodeId,
                    "foundType": foundType,
                    "reason": "Node type not found in schema Types()"
                })

        # --- Validate edges ----------------------------------------------------
        isMulti = hasattr(nxGraph, "is_multigraph") and nxGraph.is_multigraph()
        if isMulti:
            # MultiGraph / MultiDiGraph iterate with keys
            for u, v, k, data in nxGraph.edges(keys=True, data=True):
                edgesChecked += 1
                foundType = data.get(edgeTypeAttr)
                if not isinstance(foundType, str) or not foundType.strip():
                    invalidEdges.append({
                        "u": u, "v": v, "key": k, "foundType": foundType,
                        "reason": f"Missing or invalid edge '{edgeTypeAttr}'"
                    })
                    continue
                if foundType not in allowedEdgeTypes:
                    invalidEdges.append({
                        "u": u, "v": v, "key": k, "foundType": foundType,
                        "reason": "Edge type not found in schema RelationshipNames()/Relationships()"
                    })
        else:
            # Graph / DiGraph
            for u, v, data in nxGraph.edges(data=True):
                edgesChecked += 1
                foundType = data.get(edgeTypeAttr)
                if not isinstance(foundType, str) or not foundType.strip():
                    invalidEdges.append({
                        "u": u, "v": v, "key": None, "foundType": foundType,
                        "reason": f"Missing or invalid edge '{edgeTypeAttr}'"
                    })
                    continue
                if foundType not in allowedEdgeTypes:
                    invalidEdges.append({
                        "u": u, "v": v, "key": None, "foundType": foundType,
                        "reason": "Edge type not found in schema RelationshipNames()/Relationships()"
                    })

        # --- Assemble report ---------------------------------------------------
        report = {
            "ok": not invalidNodes and not invalidEdges,
            "invalidNodes": invalidNodes,
            "invalidEdges": invalidEdges,
            "counts": {
                "nodesChecked": nodesChecked,
                "edgesChecked": edgesChecked,
                "invalidNodes": len(invalidNodes),
                "invalidEdges": len(invalidEdges),
            },
            "allowed": {
                "nodeTypes": allowedNodeTypes,
                "edgeTypes": allowedEdgeTypes,
            }
        }

        # --- Optional printing -------------------------------------------------
        if printReport and not report["ok"]:
            print("✖ NetworkX validation failed")
            if invalidNodes:
                print(f"  Invalid nodes ({len(invalidNodes)}/{nodesChecked} checked):")
                for n in invalidNodes:
                    print(f"    - id={n['id']!r} type={n['foundType']!r} : {n['reason']}")
            if invalidEdges:
                print(f"  Invalid edges ({len(invalidEdges)}/{edgesChecked} checked):")
                for e in invalidEdges:
                    keyStr = f", key={e['key']!r}" if e['key'] is not None else ""
                    print(f"    - {e['u']!r} -> {e['v']!r}{keyStr} type={e['foundType']!r} : {e['reason']}")
        elif printReport and report["ok"]:
            print("✓ NetworkX validation passed (all node/edge types are valid).")

        return nxGraph

class RDF():

    @staticmethod
    def ByJSONLD(
        jsonld: Optional[Dict[str, Any]] = None,
        savePath: Optional[str | Path] = None,
        *,
        strict: bool = True
    ):
        """
        Build an RDFLib Graph from a JSON-LD-like BTWIN structure and (optionally) save it.

        Args:
            jsonld (dict, optional): JSON-LD-like data with '@context' and '@graph'.
            savePath (str | Path, optional): File path to serialize the graph (Turtle). If omitted,
                the graph is not written to disk.
            strict (bool, optional): When True (default), raise on any malformed/missing
                data (e.g., invalid CURIE, unknown prefix). When False, skip faulty
                entries, printing a warning.

        Returns:
            tuple: (rdfGraph, turtleText)
                - rdfGraph: rdflib.Graph containing the generated triples
                - turtleText: serialized Turtle string of the graph (also written to disk if savePath)

        Raises:
            ImportError: If `rdflib` is not installed.
            ValueError:  If inputs are missing or malformed and `strict=True`.
            OSError:     If writing to `savePath` fails.
        """
        # --- Import locally to give clear error messages -----------------------
        try:
            from rdflib import Graph as RDFGraph
            from rdflib import Namespace, URIRef
            from rdflib.namespace import RDF
        except Exception as exc:
            raise ImportError("rdflib is required. Install with `pip install rdflib`.") from exc

        # --- Helpers -----------------------------------------------------------
        def ensure_dict(obj, name: str):
            if not isinstance(obj, dict):
                msg = f"{name} must be a dict."
                if strict: raise ValueError(msg)
                print("Warning:", msg); return False
            return True

        def ensure_list(obj, name: str):
            if not isinstance(obj, list):
                msg = f"{name} must be a list."
                if strict: raise ValueError(msg)
                print("Warning:", msg); return False
            return True

        def split_curie(curie: str) -> Tuple[str, str]:
            """Split 'prefix:Local' into (prefix, Local) with validation."""
            if not isinstance(curie, str) or ":" not in curie:
                raise ValueError(f"Invalid CURIE (expected 'prefix:Local'): {curie!r}")
            pref, local = curie.split(":", 1)
            if not pref or not local:
                raise ValueError(f"Invalid CURIE (empty prefix/local): {curie!r}")
            return pref, local

        # --- Validate top-level structure -------------------------------------
        if not ensure_dict(jsonld, "jsonld"):
            return RDFGraph(), ""
        context = jsonld.get("@context")
        graphNodes = jsonld.get("@graph")
        if context is None or graphNodes is None:
            raise ValueError("jsonld must contain both '@context' and '@graph' keys.")
        if not ensure_dict(context, "@context"):
            return RDFGraph(), ""
        if not ensure_list(graphNodes, "@graph"):
            return RDFGraph(), ""

        # --- Create RDF graph and bind namespaces ------------------------------
        rdfGraph = RDFGraph()

        namespaces: Dict[str, Any] = {}
        for prefix, baseIri in context.items():
            if not isinstance(prefix, str) or not isinstance(baseIri, str) or not baseIri:
                msg = f"Invalid context entry: {prefix!r} → {baseIri!r}"
                if strict: raise ValueError(msg)
                print("Warning:", msg); continue
            ns = Namespace(baseIri if baseIri.endswith(("#", "/", ":")) else baseIri + "#")
            namespaces[prefix] = ns
            rdfGraph.bind(prefix, ns)

        # --- Add node types ----------------------------------------------------
        for obj in graphNodes:
            if obj is None:
                continue
            if not ensure_dict(obj, "node in @graph"):
                continue

            # Subject IRI
            subjId = obj.get("@id")
            if not isinstance(subjId, str) or not subjId.strip():
                msg = "Node missing a non-empty '@id'."
                if strict: raise ValueError(msg)
                print("Warning:", msg); continue
            subj = URIRef(subjId)

            # @type may be string or list
            typesVal = obj.get("@type", [])
            typesList = typesVal if isinstance(typesVal, list) else ([typesVal] if typesVal else [])
            for t in typesList:
                if not isinstance(t, str):
                    msg = f"@type value must be a string CURIE: {t!r}"
                    if strict: raise ValueError(msg)
                    print("Warning:", msg); continue
                try:
                    pref, local = split_curie(t)
                except ValueError as e:
                    if strict: raise
                    print("Warning:", str(e)); continue
                if pref not in namespaces:
                    msg = f"Prefix '{pref}' not found in @context for type {t!r}."
                    if strict: raise ValueError(msg)
                    print("Warning:", msg); continue
                rdfGraph.add((subj, RDF.type, namespaces[pref][local]))

        # --- Add relationships (edges) ----------------------------------------
        for obj in graphNodes:
            if obj is None or not isinstance(obj, dict):
                continue
            subjId = obj.get("@id")
            if not isinstance(subjId, str) or not subjId.strip():
                # already warned/raised above; skip here
                continue
            subj = URIRef(subjId)

            rels = obj.get("relationships")
            if rels is None:
                continue
            if not isinstance(rels, dict):
                msg = "'relationships' must be a dict mapping predicate CURIE → list of targets."
                if strict: raise ValueError(msg)
                print("Warning:", msg); continue

            for predCurie, targets in rels.items():
                if not isinstance(predCurie, str):
                    msg = f"Predicate must be a CURIE string, got: {type(predCurie).__name__}"
                    if strict: raise ValueError(msg)
                    print("Warning:", msg); continue
                try:
                    pfx, local = split_curie(predCurie)
                except ValueError as e:
                    if strict: raise
                    print("Warning:", str(e)); continue
                if pfx not in namespaces:
                    msg = f"Prefix '{pfx}' not found in @context for predicate {predCurie!r}."
                    if strict: raise ValueError(msg)
                    print("Warning:", msg); continue

                # Targets list
                if targets is None:
                    continue
                if not isinstance(targets, list):
                    msg = f"Predicate '{predCurie}' must map to a list of target dicts."
                    if strict: raise ValueError(msg)
                    print("Warning:", msg); continue

                for tgt in targets:
                    if not isinstance(tgt, dict):
                        msg = f"Target under '{predCurie}' must be a dict with '@id'."
                        if strict: raise ValueError(msg)
                        print("Warning:", msg); continue
                    tgtId = tgt.get("@id")
                    if not isinstance(tgtId, str) or not tgtId.strip():
                        msg = f"Target under '{predCurie}' missing non-empty '@id'."
                        if strict: raise ValueError(msg)
                        print("Warning:", msg); continue

                    rdfGraph.add((subj, namespaces[pfx][local], URIRef(tgtId)))

        # --- Serialize (Turtle) and optionally save ----------------------------
        try:
            turtleText: str = rdfGraph.serialize(format="turtle")  # rdflib returns str in recent versions
        except Exception as exc:
            raise ValueError("Failed to serialize RDF graph to Turtle.") from exc

        if savePath:
            outPath = Path(savePath)
            if outPath.suffix.lower() != ".ttl":
                outPath = outPath.with_suffix(".ttl")
            try:
                outPath.write_text(turtleText, encoding="utf-8")
            except Exception as exc:
                raise OSError(f"Failed to write Turtle file to '{outPath}'.") from exc

        return rdfGraph, turtleText

