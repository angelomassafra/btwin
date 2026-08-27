"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

SERIALIZATION MODULE
This module defines the Serialization operations which provides the representation
of graph data structures (knowledge graphs and labeled property graphs) in the BTWIN toolkit.

© Angelo Massafra, 2026
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


class Serialization():

    @staticmethod
    def IRIs() -> Dict[str, Any]:
        """
        Return canonical namespaces and selected term IRIs for BTWIN export.

        Returns:
            dict: {
                "prefixes": { "brick": "...#", "bot": "...#", "ifc": "...#", ... },
                "classes":  { "brick:Building": "...#Building", ... },
                "properties": { "brick:hasLocation": "...#hasLocation", ... }
            }
        """
        prefixes = {
            "brick": "https://brickschema.org/schema/Brick#",
            "bot":   "https://w3id.org/bot#",
            "ifc":   "https://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2_TC1/OWL#",
            "eko":   "http://energy.linkeddata.es/em-kpi/ontology#",
            "kpi":   "http://bimerr.iot.linkeddata.es/def/key-performance-indicator#",
            "btwin": "btwin#",          # placeholder
            "top":   "top#",            # placeholder
            "time":  "https://www.w3.org/TR/2022/CRD-owl-time-20221115#"
        }

        def iri(curie: str) -> str:
            pref, local = curie.split(":", 1)
            return prefixes[pref] + local

        # Selected classes frequently used in your toolkit
        classes = {
            # Brick locations and assets
            "brick:Portfolio": iri("brick:Portfolio"),
            "brick:Region": iri("brick:Region"),
            "brick:Site": iri("brick:Site"),
            "brick:Building": iri("brick:Building"),
            "brick:Storey": iri("brick:Storey"),
            "brick:Space": iri("brick:Space"),
            "brick:Zone": iri("brick:Zone"),
            "brick:Energy_Zone": iri("brick:Energy_Zone"),
            "brick:Fire_Zone": iri("brick:Fire_Zone"),
            "brick:Equipment": iri("brick:Equipment"),
            "brick:System": iri("brick:System"),
            # Common Brick sensors (extend as you need)
            "brick:Temperature_Sensor": iri("brick:Temperature_Sensor"),
            "brick:Humidity_Sensor": iri("brick:Humidity_Sensor"),
            "brick:Luminance_Sensor": iri("brick:Luminance_Sensor"),
            "brick:Pressure_Sensor": iri("brick:Pressure_Sensor"),
            "brick:CO2_Sensor": iri("brick:CO2_Sensor"),
            "brick:PM1_Sensor": iri("brick:PM1_Sensor"),
            "brick:PM2.5_Sensor": iri("brick:PM2.5_Sensor"),
            "brick:PM10_Sensor": iri("brick:PM10_Sensor"),
            "brick:TVOC_Sensor": iri("brick:TVOC_Sensor"),
            "brick:Current_Sensor": iri("brick:Current_Sensor"),
            "brick:Air_Flow_Sensor": iri("brick:Air_Flow_Sensor"),
            "brick:Speed_Sensor": iri("brick:Speed_Sensor"),
            "brick:Air_Handling_Unit": iri("brick:Air_Handling_Unit"),
            "brick:Electric_Boiler": iri("brick:Electric_Boiler"),
            "brick:Fan_Coil_Unit": iri("brick:Fan_Coil_Unit"),
            "brick:Packaged_Heat_Pump": iri("brick:Packaged_Heat_Pump"),

            # BOT spatial hierarchy
            "bot:Site": iri("bot:Site"),
            "bot:Building": iri("bot:Building"),
            "bot:Storey": iri("bot:Storey"),
            "bot:Space": iri("bot:Space"),
            "bot:Zone": iri("bot:Zone"),
            "bot:Element": iri("bot:Element"),
            "bot:Interface": iri("bot:Interface"),
            # IFC property sets and elements
            "ifc:PropertySet": iri("ifc:PropertySet"),
            "ifc:IfcPropertySet": iri("ifc:IfcPropertySet"),
            "ifc:IfcSensor": iri("ifc:IfcSensor"),
            # Project-local examples
            "btwin:Document": iri("btwin:Document"),
            "btwin:KPISet": iri("btwin:KPISet"),
            # EM-KPIO
            "eko:KPI": iri("eko:KPI"),
            # KPI Ontology
            "kpi:Scenario": iri("kpi:Scenario"),
            # Topologic
            "top:Face": iri("top:Face"),
            "top:Aperture": iri("top:Aperture"),
            # Time
            "time:interval": iri("time:interval")
        }

        relationshipNames = {
            # Relationships requested
            "brick:hasLocation": iri("brick:hasLocation"),
            "brick:isLocation": iri("brick:isLocation"),
            "brick:isFedBy": iri("brick:isFedBy"),
            "brick:feeds": iri("brick:feeds"),
            "brick:isPartOf": iri("brick:isPartOf"),
            "brick:hasPart": iri("brick:hasPart"),
            "ifc:HasPropertySets": iri("ifc:HasPropertySets"),
            "ifc:HasProperties": iri("ifc:HasProperties"),
            "bot:interfaceOf": iri("bot:interfaceOf"),
            # Useful BOT hierarchy
            "bot:hasBuilding": iri("bot:hasBuilding"),
            "bot:hasStorey": iri("bot:hasStorey"),
            "bot:hasSpace": iri("bot:hasSpace"),
            # Project-local examples
            "btwin:hasDocument": iri("btwin:hasDocument"),
            "btwin:isDocumentOf": iri("btwin:isDocumentOf"),
            "btwin:isAdjacentTo": iri("btwin:isAdjacentTo"),
            "btwin:hasPassageTo": iri("btwin:hasPassageTo"),
            # Eko
            "eko:hasAssociatedObject": iri("eko:hasAssociatedObject"),
            "eko:hasEvaluationTimestep": iri("eko:hasEvaluationTimestep"),
            # KPI
            "kpi:relatedScenario": iri("kpi:relatedScenario")

        }

        return {"prefixes": prefixes, "classes": classes, "properties": relationshipNames}

    @staticmethod
    def JSONLDByObjects(
        objects: Optional[Iterable[Any]] = None,
        savePath: Optional[str | Path] = None,
        *,
        strictValidation: bool = True
    ) -> Dict[str, Any]:
        """
        Build a JSON-LD document from BTWIN objects, with context + validation.

        Args:
            objects (Iterable[Any], optional): List/nested lists of graph nodes (dicts).
                Each node may include '@id', '@type' (or 'subclass'), and a 'relationships'
                dict mapping CURIE predicates → list of {'@id','@type'} targets.
            savePath (str | Path, optional): Output path for the JSON-LD file.
            strictValidation (bool, optional): If True, raise on unknown classes/relations.
                If False, build context from known prefixes and continue.

        Returns:
            dict: The constructed JSON-LD document with '@context' and '@graph'.

        Raises:
            ValueError: If inputs are malformed or if unknown classes/relationships
                are found while `strictValidation=True`.
            TypeError:  If nodes are not dicts or relationships are not the expected shape.
            OSError:    If saving to disk fails.
        """
        # --- Imports (local) ---------------------------------------------------
        # (json imported at module level above)

        # --- Prepare sources and helpers --------------------------------------
        iriTable = Serialization.IRIs()
        prefixes: Dict[str, str] = iriTable["prefixes"]
        allowedClasses: Set[str] = set(iriTable["classes"].keys())
        allowedProps: Set[str] = set(iriTable["properties"].keys())

        def flatten(items: Iterable[Any]) -> List[Any]:
            """Recursively flatten nested lists of items."""
            out: List[Any] = []
            for it in (items or []):
                if isinstance(it, list):
                    out.extend(flatten(it))
                elif it is not None:
                    out.append(it)
            return out

        def curiePrefix(curie: str) -> str:
            """Extract prefix from a CURIE like 'brick:Space'."""
            if ":" not in curie:
                raise ValueError(f"Expected CURIE 'prefix:Local', got: {curie!r}")
            return curie.split(":", 1)[0]

        def collectUsedTerms(graphNodes: List[Dict[str, Any]]) -> Tuple[Set[str], Set[str], Set[str]]:
            """
            Collect:
              - usedPrefixes: any CURIE prefix found in classes/props
              - usedClasses:  class CURIEs discovered
              - usedProps:    predicate CURIEs discovered
            """
            usedPrefixes: Set[str] = set()
            usedClasses: Set[str] = set()
            usedProps: Set[str] = set()

            for node in graphNodes:
                if not isinstance(node, dict):
                    raise TypeError("Graph nodes must be dictionaries.")

                # Class detection: '@type' and optional 'subclass'
                for k in ("@type", "subclass"):
                    if k in node and node[k]:
                        if isinstance(node[k], list):
                            types = node[k]
                        else:
                            types = [node[k]]
                        for t in types:
                            if not isinstance(t, str):
                                raise TypeError(f"Type value must be string, got {type(t).__name__}.")
                            usedClasses.add(t)
                            usedPrefixes.add(curiePrefix(t))

                # Relationships: dict of predicate → list of targets
                rels = node.get("relationships", {})
                if rels is None:
                    continue
                if not isinstance(rels, dict):
                    raise TypeError("'relationships' must be a dict if present.")
                for pred, targets in rels.items():
                    if not isinstance(pred, str):
                        raise TypeError("Relationship names must be strings (CURIE).")
                    usedProps.add(pred)
                    usedPrefixes.add(curiePrefix(pred))
                    if targets is None:
                        continue
                    if not isinstance(targets, list):
                        raise TypeError(f"Relationship '{pred}' must map to a list of objects.")
                    for target in targets:
                        if not isinstance(target, dict):
                            raise TypeError(f"Targets of '{pred}' must be dicts with '@id'/'@type'.")
                        # Target type (if given) contributes a class CURIE
                        ttype = target.get("@type")
                        if ttype:
                            if not isinstance(ttype, str):
                                raise TypeError(f"Target '@type' under '{pred}' must be string.")
                            usedClasses.add(ttype)
                            usedPrefixes.add(curiePrefix(ttype))

            return usedPrefixes, usedClasses, usedProps

        # --- Build @graph ------------------------------------------------------
        graphNodes: List[Dict[str, Any]] = flatten(objects or [])
        jsonld: Dict[str, Any] = {"@context": {}, "@graph": graphNodes}

        # --- Validation + context construction --------------------------------
        usedPrefixes, usedClasses, usedProps = collectUsedTerms(graphNodes)

        # 1) Ensure all prefixes used are known; fill @context with those prefixes
        unknownPrefixes = {p for p in usedPrefixes if p not in prefixes}
        if strictValidation and unknownPrefixes:
            raise ValueError(f"Unknown namespace prefix(es) in graph: {sorted(unknownPrefixes)}")

        # Keep only prefixes actually used to keep context compact
        contextMap: Dict[str, str] = {p: iri for p, iri in prefixes.items() if p in usedPrefixes}
        jsonld["@context"].update(contextMap)

        # 2) Check classes against allow-list (if strict)
        unknownClasses = {c for c in usedClasses if c not in allowedClasses}
        if strictValidation and unknownClasses:
            raise ValueError(
                "Found class(es) not declared in context/IRIs(): "
                + ", ".join(sorted(unknownClasses))
            )

        # 3) Check properties against allow-list (if strict)
        unknownProps = {p for p in usedProps if p not in allowedProps}
        if strictValidation and unknownProps:
            raise ValueError(
                "Found relationship(s) not declared in context/IRIs(): "
                + ", ".join(sorted(unknownProps))
            )

        # --- Save to disk (optional) -------------------------------------------
        if savePath:
            path = Path(savePath)
            if path.suffix.lower() != ".json":
                path = path.with_suffix(".json")
            # Write JSON with indentation
            with path.open("w", encoding="utf-8") as fh:
                json.dump(jsonld, fh, indent=4, ensure_ascii=False)

        # --- Return JSON-LD document -------------------------------------------
        return jsonld

