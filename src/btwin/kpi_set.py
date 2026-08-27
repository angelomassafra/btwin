"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

KPI MODULE
This module defines the KPI class, which provides the base representation
for attributing key performance indicators to the digital objects in the BTWIN toolkit.

© Angelo Massafra, 2026
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union


class KPISet:

    @staticmethod
    def Constructor(
        kpisetUID: str,
        name: str = "None",
        hasBeginning: Optional[str] = None,
        hasEnd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initialize a KPISet as a Python dictionary.

        Args:
            kpisetUID: Unique identifier for the KPISet (non-empty string).
            name: Human-readable name of the KPISet.
            hasBeginning: Start of the period (ISO 8601 string, e.g., '2025-09-30T10:00:00Z').
            hasEnd: End of the period (ISO 8601 string, e.g., '2025-09-30T12:00:00Z').

        Returns:
            dict: A dictionary representing the KPISet with the provided attributes.

        Raises:
            TypeError: If arguments have invalid types.
            ValueError: If UID is empty or timestamps are invalid.
        """

        # --- Validate UID
        if not isinstance(kpisetUID, str):
            raise TypeError("kpisetUID must be a string.")
        if kpisetUID.strip() == "":
            raise ValueError("kpisetUID cannot be empty.")

        # --- Validate name
        if not isinstance(name, str):
            raise TypeError("name must be a string.")

        # --- Helper: validate & normalize timestamps
        def _validate_iso8601(ts: Optional[str]) -> Optional[str]:
            if ts is None:
                return None
            if not isinstance(ts, str):
                raise TypeError("Timestamps must be strings or None.")
            if ts.strip() == "" or ts.lower() == "none":
                return None
            try:
                # Parse and normalize to standard ISO8601 with Z
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return dt.isoformat().replace("+00:00", "Z")
            except Exception:
                raise ValueError(f"Invalid ISO 8601 timestamp: {ts}")

        tsFromNorm = _validate_iso8601(hasBeginning)
        tsToNorm = _validate_iso8601(hasEnd)

        # --- Build the base structure
        kpiSet = {
            "@id": kpisetUID,
            "name": name,
            "@type": "btwin:KPISet",
            "relationships": {
                "eko:hasEvaluationTimestep": [
                    {
                        "@type": "time:interval",
                        "time:hasBeginning": tsFromNorm,  # ISO-8601 'Z'
                        "time:hasEnd": tsToNorm,          # ISO-8601 'Z'
                    }
                ],
            },
            "btwin:hasKPIs": {},
        }
        return kpiSet

    @staticmethod
    def SetAssociatedObject(
        kpiSet: Dict[str, Any],
        linkedObject: Optional[Dict[str, Any]] = None,
        linkedObjectUID: Optional[str] = None,
        linkedObjectType: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Assign a relationship between the KPISet and another element via eko:hasAssociatedObject.

        Args:
            kpiSet: KPISet dictionary produced by KPISet.Constructor.
            linkedObject: A dict for the related element. The function will try, in order:
                UID: ['UID'] then ['@id']
                type: ['label'] then ['@type'] then ['type']
            linkedObjectUID: UID of the related element (used if 'linkedObject' is None or lacks it).
            linkedObjectType: Type/label of the related element (used if 'linkedObject' is None or lacks it).

        Returns:
            dict: The updated KPISet dictionary.

        Raises:
            TypeError: If inputs have invalid types.
            ValueError: If neither UID nor type can be resolved.
            KeyError: If kpiSet lacks required keys.
        """
        return KPISet.SetRelationship(
            kpiSet=kpiSet,
            relationshipName='eko:hasAssociatedObject',
            linkedObject=linkedObject,
            linkedObjectUID=linkedObjectUID,
            linkedObjectType=linkedObjectType
        )

    @staticmethod
    def SetKPI(kpiSet: Dict[str, Any], kpi: Dict[str, Any], overwrite: bool = False) -> Dict[str, Any]:
        """
        Add or update a KPI inside the KPI set's 'btwin:hasKPIs' map.

        This method stores KPIs keyed by their '@id'. If 'overwrite' is False and the KPI already exists,
        the existing KPI is kept as-is; if True, the KPI is replaced.

        Args:
            kpiSet: KPISet dictionary (must contain 'btwin:hasKPIs' as a dict).
            kpi: KPI dictionary to add/update (must contain '@id' as non-empty string).
            overwrite: Whether to overwrite if the KPI already exists.

        Returns:
            dict: The updated KPISet dictionary.

        Raises:
            TypeError: If inputs have invalid types.
            KeyError: If required keys are missing.
            ValueError: If '@id' is absent/invalid in the KPI.
        """
        # Validate kpiSet structure
        if not isinstance(kpiSet, dict):
            raise TypeError("kpiSet must be a dict.")
        if "btwin:hasKPIs" not in kpiSet:
            raise KeyError("kpiSet is missing 'btwin:hasKPIs'.")
        if not isinstance(kpiSet["btwin:hasKPIs"], dict):
            raise TypeError("kpiSet['btwin:hasKPIs'] must be a dict.")

        # Validate kpi
        if not isinstance(kpi, dict):
            raise TypeError("kpi must be a dict.")
        kpiId = kpi.get("@id", None)
        if not isinstance(kpiId, str) or kpiId.strip() == "":
            raise ValueError("kpi['@id'] must be a non-empty string.")

        # Insert or update
        if overwrite or kpiId not in kpiSet["btwin:hasKPIs"]:
            kpiSet["btwin:hasKPIs"][kpiId] = kpi  # set/replace
        # else: keep existing if not overwriting

        return kpiSet

    @staticmethod
    def SetKPIsTimestep(kpiSet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Align every KPI's evaluation timestep to the KPISet's timestep.

        Args:
            kpiSet: KPISet dictionary containing 'btwin:hasKPIs' and optionally
                    'relationships' or 'timestamp'.

        Returns:
            dict: The updated KPISet (mutation in-place and also returned).

        Raises:
            TypeError: If kpiSet or nested structures are of invalid types.
            ValueError: If no valid timestep can be derived from KPISet.
        """
        # --- Validate container
        if not isinstance(kpiSet, dict):
            raise TypeError("kpiSet must be a dict.")

        # --- Try to get reference timestep from relationships
        relationships = kpiSet.get("relationships", {})
        refList = None
        if isinstance(relationships, dict):
            refList = relationships.get("eko:hasEvaluationTimestep")

        # --- Helper: normalize timestamp string to ISO-8601 'Z'
        def _to_iso8601_z(ts: Optional[str]) -> Optional[str]:
            if ts is None:
                return None
            if not isinstance(ts, str):
                raise TypeError("Timestamps in kpiSet['timestamp'] must be strings or None.")
            s = ts.strip()
            if s == "" or s.lower() in {"none", "null"}:
                return None
            # Accept trailing 'Z'
            if s.endswith("Z"):
                try:
                    dt = datetime.fromisoformat(s[:-1] + "+00:00")
                    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                except Exception:
                    pass
            # Generic parse
            try:
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    # Assume UTC for naive strings
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except Exception:
                raise ValueError(f"Invalid ISO 8601 timestamp in KPISet.timestamp: {ts!r}")

        # --- If no relationships timestep, attempt to build from KPISet.timestamp
        if not (isinstance(refList, list) and refList and isinstance(refList[0], dict)):
            ts = kpiSet.get("timestamp", {})
            if not isinstance(ts, dict):
                ts = {}
            beginISO = _to_iso8601_z(ts.get("from"))
            endISO = _to_iso8601_z(ts.get("to"))

            # If both present, ensure ordering
            if beginISO and endISO:
                dtB = datetime.fromisoformat(beginISO.replace("Z", "+00:00"))
                dtE = datetime.fromisoformat(endISO.replace("Z", "+00:00"))
                if dtB > dtE:
                    raise ValueError("KPISet.timestamp.from must be <= KPISet.timestamp.to.")

            # Build interval if at least one bound is present
            if beginISO or endISO:
                refList = [{
                    "@type": "time:interval",
                    "time:hasBeginning": beginISO,
                    "time:hasEnd": endISO,
                }]
                # Persist the derived relationships for consistency
                kpiSet.setdefault("relationships", {})
                kpiSet["relationships"]["eko:hasEvaluationTimestep"] = deepcopy(refList)

        # --- If we still have no valid reference, fail
        if not (isinstance(refList, list) and refList and isinstance(refList[0], dict)):
            raise ValueError(
                "No valid evaluation timestep found in KPISet. "
                "Provide relationships['eko:hasEvaluationTimestep'] or timestamp{'from'/'to'}."
            )

        # --- Access KPIs container (supports dict or list)
        kpisContainer = kpiSet.get("btwin:hasKPIs", {})
        if not isinstance(kpisContainer, (dict, list)):
            raise TypeError("kpiSet['btwin:hasKPIs'] must be a dict or a list.")

        # Build iterable of KPI dicts
        if isinstance(kpisContainer, dict):
            kpiIter: List[Dict[str, Any]] = list(kpisContainer.values())
        else:
            kpiIter = kpisContainer

        # --- Apply the reference timestep to each KPI
        for kpi in kpiIter:
            if not isinstance(kpi, dict):
                # Skip invalid entries rather than crashing the whole batch
                continue
            rel = kpi.setdefault("relationships", {})
            rel["eko:hasEvaluationTimestep"] = deepcopy(refList)

        return kpiSet

    @staticmethod
    def SetRelationship(
        kpiSet: Dict[str, Any],
        relationshipName: str,
        linkedObject: Optional[Dict[str, Any]] = None,
        linkedObjectUID: Optional[str] = None,
        linkedObjectType: Optional[str] = None,
        append: bool = False,
    ) -> Dict[str, Any]:
        """
        Assign a relationship between the KPISet and another element (e.g., via eko:hasAssociatedObject).

        Args:
            kpiSet: KPISet dictionary produced by KPISet.Constructor.
            relationshipName: Name of the relationship (e.g., "eko:hasAssociatedObject").
            linkedObject: A dict for the related element. The function will try, in order:
                UID: ['UID'] then ['@id']
                type: ['label'] then ['@type'] then ['type']
            linkedObjectUID: UID of the related element (used if 'linkedObject' is None or lacks it).
            linkedObjectType: Type/label of the related element (used if 'linkedObject' is None or lacks it).
            append: If True, appends to an existing list; otherwise overwrites the relationship list with a single value.

        Returns:
            dict: The updated KPISet dictionary.

        Raises:
            TypeError: If inputs have invalid types.
            ValueError: If neither UID nor type can be resolved.
            KeyError: If kpiSet lacks required keys.
        """
        # Basic validations
        if not isinstance(kpiSet, dict):
            raise TypeError("kpiSet must be a dict.")
        if not isinstance(relationshipName, str) or relationshipName.strip() == "":
            raise TypeError("relationshipName must be a non-empty string.")
        if "relationships" not in kpiSet or not isinstance(kpiSet["relationships"], dict):
            raise KeyError("kpiSet['relationships'] must exist and be a dict.")

        # Resolve UID and type from linkedObject if available
        resolvedUID = None
        resolvedType = None
        if isinstance(linkedObject, dict):
            # Try UID keys
            for uidKey in ("UID", "@id"):
                if uidKey in linkedObject and isinstance(linkedObject[uidKey], str) and linkedObject[uidKey].strip():
                    resolvedUID = linkedObject[uidKey]
                    break
            # Try type keys
            for typeKey in ("label", "@type", "type"):
                if typeKey in linkedObject and isinstance(linkedObject[typeKey], str) and linkedObject[typeKey].strip():
                    resolvedType = linkedObject[typeKey]
                    break

        # Fallback to explicit parameters
        resolvedUID = resolvedUID or linkedObjectUID
        resolvedType = resolvedType or linkedObjectType

        if not isinstance(resolvedUID, str) or resolvedUID.strip() == "":
            raise ValueError("A related element UID is required (via linkedObject or linkedObjectUID).")
        if not isinstance(resolvedType, str) or resolvedType.strip() == "":
            raise ValueError("A related element type is required (via linkedObject or linkedObjectType).")

        # Prepare payload
        relPayload = {"@id": resolvedUID, "@type": resolvedType}

        # Insert/append into relationships
        if append:
            current: List[Dict[str, str]] = kpiSet["relationships"].get(relationshipName, [])
            if not isinstance(current, list):
                current = []
            current.append(relPayload)
            kpiSet["relationships"][relationshipName] = current
        else:
            kpiSet["relationships"][relationshipName] = [relPayload]

        return kpiSet

    @staticmethod
    def SetScenario(
        kpiSet: Dict[str, Any],
        scenarioObject: Optional[Dict[str, Any]] = None,
        scenarioObjectUID: Optional[str] = None,
        scenarioObjectType: Optional[str] = 'kpi:Scenario',
    ) -> Dict[str, Any]:
        """
        Assign a relationship between the KPISet and a Scenario via kpi:relatedScenario.

        Args:
            kpiSet: KPISet dictionary produced by KPISet.Constructor.
            scenarioObject: A dict for the related element.
            scenarioObjectUID: UID of the related element (used if 'scenarioObject' is None or lacks it).
            scenarioObjectType: Type/label of the related element (used if 'scenarioObject' is None or lacks it).

        Returns:
            dict: The updated KPISet dictionary.

        Raises:
            TypeError: If inputs have invalid types.
            ValueError: If neither UID nor type can be resolved.
            KeyError: If kpiSet lacks required keys.
        """
        return KPISet.SetRelationship(
            kpiSet=kpiSet,
            relationshipName='kpi:relatedScenario',
            linkedObject=scenarioObject,
            linkedObjectUID=scenarioObjectUID,
            linkedObjectType=scenarioObjectType
        )

    @staticmethod
    def SetTimestep(
        kpiSet: Dict[str, Any],
        hasBeginning: Optional[Union[str, datetime]],
        hasEnd: Optional[Union[str, datetime]],
    ) -> Dict[str, Any]:
        """
        Set (or update) the KPISet time interval, validating and normalizing to ISO-8601.

        Args:
            kpiSet: KPISet dictionary; if 'timestemp' is missing it will be created.
            hasBeginning: Start of the period (str ISO-8601 or datetime). Accepts None/""/"None".
            hasEnd: End of the period (str ISO-8601 or datetime). Accepts None/""/"None".

        Returns:
            dict: The updated KPISet (mutation is in-place and also returned).

        Raises:
            TypeError: If inputs have invalid types.
            ValueError: If timestamps are invalid or if 'from' is after 'to'.
        """
        # --- Validate container
        if not isinstance(kpiSet, dict):
            raise TypeError("kpiSet must be a dict.")


        # --- Helpers
        def _emptyish(x: Any) -> bool:
            return x is None or (isinstance(x, str) and x.strip().lower() in {"", "none", "null"})

        def _to_iso8601(ts: Optional[Union[str, datetime]]) -> Optional[str]:
            """Normalize to ISO-8601 string with 'Z' for UTC. Accepts None / empty-like."""
            if _emptyish(ts):
                return None

            # If already datetime
            if isinstance(ts, datetime):
                # If naive, assume UTC (comment: adjust if you prefer to reject naive)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

            # If string, try parsing common ISO-8601 variants
            if isinstance(ts, str):
                s = ts.strip()
                # Allow trailing 'Z' which fromisoformat doesn't parse directly
                if s.endswith("Z"):
                    try:
                        dt = datetime.fromisoformat(s[:-1] + "+00:00")
                        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    except Exception:
                        pass
                # Try plain fromisoformat (may be naive or offset-aware)
                try:
                    dt = datetime.fromisoformat(s)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)  # assume UTC for naive strings
                    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                except Exception:
                    raise ValueError(f"Invalid ISO 8601 timestamp: {ts!r}")

            raise TypeError("Timestamps must be str, datetime, or None.")

        # --- Normalize
        fromNorm = _to_iso8601(hasBeginning)
        toNorm = _to_iso8601(hasEnd)

        # --- Order check: from <= to (only if both provided)
        if fromNorm is not None and toNorm is not None:
            dtFrom = datetime.fromisoformat(fromNorm.replace("Z", "+00:00"))
            dtTo = datetime.fromisoformat(toNorm.replace("Z", "+00:00"))
            if dtFrom > dtTo:
                raise ValueError("hasBeginning must be <= hasEnd.")

        # --- Persist
        kpiSet["relationships"]["eko:hasEvaluationTimestep"][0]["time:hasBeginning"] = fromNorm
        kpiSet["relationships"]["eko:hasEvaluationTimestep"][0]["time:hasEnd"]  = toNorm
        return kpiSet

    @staticmethod
    def UID(kpiSet: Dict[str, Any]) -> str:
        """
        Retrieve the Unique Identifier (UID) of a KPISet.

        Args:
            kpiSet: A KPISet dictionary.

        Returns:
            str: The UID value.

        Raises:
            TypeError: If kpiSet is not a dict.
            KeyError: If '@id' is missing.
            ValueError: If '@id' is empty or not a string.
        """
        # Validate and return UID
        if not isinstance(kpiSet, dict):
            raise TypeError("kpiSet must be a dict.")
        if "@id" not in kpiSet:
            raise KeyError("kpiSet is missing '@id'.")
        uid = kpiSet["@id"]
        if not isinstance(uid, str) or uid.strip() == "":
            raise ValueError("kpiSet['@id'] must be a non-empty string.")
        return uid

class KPI:

    @staticmethod
    def Constructor(
        kpiUID: str,
        kpiName: Optional[str] = None,
        kpiValue: Optional[Union[int, float, str]] = None,
        kpiType: str = "eko:KPI",          # type for 'nominalValue' node
        hasBeginning: Optional[Union[str, datetime]] = None,
        hasEnd: Optional[Union[str, datetime]] = None,
        kpiUnit: Optional[str] = None,
        kpiClass: str = "eko:KPI",         # class/type for the KPI resource itself
        allowNaiveDatetimeAsUTC: bool = True,
    ) -> Dict[str, Any]:
        """
        Build a KPI dictionary.

        Args:
            kpiUID: Unique identifier for the KPI (non-empty string).
            kpiName: Human-readable name of the KPI.
            kpiValue: The KPI nominal value (number or string).
            kpiType: The '@type' for the nominal value node (e.g., 'eko:KPI', 'eko:Number').
            hasBeginning: Start of the evaluation interval (ISO-8601 string or datetime). Normalized to UTC 'Z'.
            hasEnd: End of the evaluation interval (ISO-8601 string or datetime). Normalized to UTC 'Z'.
            kpiUnit: Unit of the nominal value (e.g., 'kWh', 'EUR').
            kpiClass: The '@type' of the KPI resource itself (default 'eko:KPI').
            allowNaiveDatetimeAsUTC: If True, naive datetimes are assumed UTC; if False, they raise.

        Returns:
            dict: A dictionary representing the KPI.

        Raises:
            TypeError: If inputs have invalid types.
            ValueError: If 'kpiUID' is empty or timestamps are invalid / out of order.
        """
        # --- Validate identifiers and types
        if not isinstance(kpiUID, str) or kpiUID.strip() == "":
            raise ValueError("kpiUID must be a non-empty string.")
        if kpiName is not None and not isinstance(kpiName, str):
            raise TypeError("kpiName must be a string if provided.")
        if kpiUnit is not None and not isinstance(kpiUnit, str):
            raise TypeError("kpiUnit must be a string if provided.")
        if not isinstance(kpiType, str) or kpiType.strip() == "":
            raise TypeError("kpiType must be a non-empty string.")
        if not isinstance(kpiClass, str) or kpiClass.strip() == "":
            raise TypeError("kpiClass must be a non-empty string.")
        if kpiValue is not None and not isinstance(kpiValue, (int, float, str)):
            raise TypeError("kpiValue must be int, float, str, or None.")

        # --- Helpers: normalize timestamps to ISO8601 with 'Z'
        def _emptyish(x: Any) -> bool:
            return x is None or (isinstance(x, str) and x.strip().lower() in {"", "none", "null"})

        def _to_iso8601_z(ts: Optional[Union[str, datetime]]) -> Optional[str]:
            if _emptyish(ts):
                return None
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    if not allowNaiveDatetimeAsUTC:
                        raise ValueError("Naive datetime not allowed; provide timezone-aware datetime.")
                    ts = ts.replace(tzinfo=timezone.utc)
                return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if isinstance(ts, str):
                s = ts.strip()
                # Support trailing 'Z'
                if s.endswith("Z"):
                    try:
                        dt = datetime.fromisoformat(s[:-1] + "+00:00")
                        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    except Exception:
                        pass
                # Generic parse
                try:
                    dt = datetime.fromisoformat(s)
                    if dt.tzinfo is None:
                        if not allowNaiveDatetimeAsUTC:
                            raise ValueError("Naive datetime string not allowed; include timezone.")
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                except Exception:
                    raise ValueError(f"Invalid ISO 8601 timestamp: {ts!r}")
            raise TypeError("Timestamps must be str, datetime, or None.")

        # --- Normalize and check interval order (if both provided)
        beginISO = _to_iso8601_z(hasBeginning)
        endISO = _to_iso8601_z(hasEnd)
        if beginISO and endISO:
            dtB = datetime.fromisoformat(beginISO.replace("Z", "+00:00"))
            dtE = datetime.fromisoformat(endISO.replace("Z", "+00:00"))
            if dtB > dtE:
                raise ValueError("hasBeginning must be <= hasEnd.")

        # --- Build the KPI structure
        kpi = {
            "@id": kpiUID,
            "@type": kpiClass,
            "name": kpiName,
            "relationships": {
                # Caller can later replace None/None with actual object
                "eko:hasAssociatedObject": [{"@id": None, "@type": None}],
                "eko:hasEvaluationTimestep": [
                    {
                        "@type": "time:interval",
                        "time:hasBeginning": beginISO,  # ISO-8601 'Z'
                        "time:hasEnd": endISO,          # ISO-8601 'Z'
                    }
                ],
            },
            "nominalValue": {"@type": kpiType, "value": kpiValue, "unit": kpiUnit},
        }
        return kpi

    @staticmethod
    def Name(kpi: Dict[str, Any]) -> Optional[str]:
        """
        Get the name of the KPI.

        Args:
            kpi: KPI dictionary.

        Returns:
            str or None: The name of the KPI.

        Raises:
            TypeError: If kpi is not a dict.
        """
        if not isinstance(kpi, dict):
            raise TypeError("kpi must be a dict.")
        return kpi.get("name")

    @staticmethod
    def SetTimestep(
        kpi: Dict[str, Any],
        hasBeginning: Optional[Union[str, datetime]] = None,
        hasEnd: Optional[Union[str, datetime]] = None,
        allowNaiveDatetimeAsUTC: bool = True,
    ) -> Dict[str, Any]:
        """
        Set (or update) the KPI evaluation timestep, validating and normalizing to ISO-8601 UTC.

        Args:
            kpi: KPI dictionary; if the relationships/timestep structure is missing, it will be created.
            hasBeginning: Start of the interval (ISO-8601 string or datetime). Empty/None clears the value.
            hasEnd: End of the interval (ISO-8601 string or datetime). Empty/None clears the value.
            allowNaiveDatetimeAsUTC: If True, naive datetimes are assumed UTC; otherwise a ValueError is raised.

        Returns:
            dict: The updated KPI (mutation in-place and also returned).

        Raises:
            TypeError: If inputs have invalid types.
            ValueError: If timestamps are invalid or if beginning is after end.
        """
        # --- Validate container
        if not isinstance(kpi, dict):
            raise TypeError("kpi must be a dict.")

        # --- Ensure relationships structure exists
        rel = kpi.setdefault("relationships", {})
        evalSteps = rel.setdefault("eko:hasEvaluationTimestep", [])
        if not isinstance(evalSteps, list) or (evalSteps and not isinstance(evalSteps[0], dict)):
            # reset to a clean list with a single interval dict
            evalSteps = []
            rel["eko:hasEvaluationTimestep"] = evalSteps
        if not evalSteps:
            evalSteps.append({"@type": "time:interval", "time:hasBeginning": None, "time:hasEnd": None})
        interval = evalSteps[0]

        # --- Helpers
        def _emptyish(x: Any) -> bool:
            return x is None or (isinstance(x, str) and x.strip().lower() in {"", "none", "null"})

        def _to_iso8601_z(ts: Optional[Union[str, datetime]]) -> Optional[str]:
            """Normalize to ISO-8601 string with 'Z' for UTC. Accepts None/empty-like."""
            if _emptyish(ts):
                return None

            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    if not allowNaiveDatetimeAsUTC:
                        raise ValueError("Naive datetime not allowed; provide timezone-aware datetime.")
                    ts = ts.replace(tzinfo=timezone.utc)
                return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

            if isinstance(ts, str):
                s = ts.strip()
                # Handle trailing 'Z'
                if s.endswith("Z"):
                    try:
                        dt = datetime.fromisoformat(s[:-1] + "+00:00")
                        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    except Exception:
                        pass
                # Generic parse
                try:
                    dt = datetime.fromisoformat(s)
                    if dt.tzinfo is None:
                        if not allowNaiveDatetimeAsUTC:
                            raise ValueError("Naive datetime string not allowed; include timezone.")
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                except Exception:
                    raise ValueError(f"Invalid ISO 8601 timestamp: {ts!r}")

            raise TypeError("Timestamps must be str, datetime, or None.")

        # --- Normalize inputs
        beginISO = _to_iso8601_z(hasBeginning)
        endISO = _to_iso8601_z(hasEnd)

        # --- Check ordering if both provided
        if beginISO and endISO:
            dtB = datetime.fromisoformat(beginISO.replace("Z", "+00:00"))
            dtE = datetime.fromisoformat(endISO.replace("Z", "+00:00"))
            if dtB > dtE:
                raise ValueError("hasBeginning must be <= hasEnd.")

        # --- Persist into KPI structure
        interval["time:hasBeginning"] = beginISO
        interval["time:hasEnd"] = endISO

        return kpi

    @staticmethod
    def Timestep(kpi: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """
        Get the evaluation timestep of the KPI.

        Args:
            kpi: KPI dictionary.

        Returns:
            dict: Dictionary with keys 'time:hasBeginning' and 'time:hasEnd'.
                  Values are ISO8601 strings or None if missing.

        Raises:
            TypeError: If kpi is not a dict.
        """
        if not isinstance(kpi, dict):
            raise TypeError("kpi must be a dict.")
        rel = kpi.get("relationships", {})
        evalSteps = rel.get("eko:hasEvaluationTimestep", [])
        if evalSteps and isinstance(evalSteps, list) and isinstance(evalSteps[0], dict):
            return {
                "time:hasBeginning": evalSteps[0].get("time:hasBeginning"),
                "time:hasEnd": evalSteps[0].get("time:hasEnd"),
            }
        return {"time:hasBeginning": None, "time:hasEnd": None}

    @staticmethod
    def UID(kpi: Dict[str, Any]) -> str:
        """
        Get the unique identifier (@id) of the KPI.

        Args:
            kpi: KPI dictionary.

        Returns:
            str: The UID of the KPI.

        Raises:
            TypeError: If kpi is not a dict.
            KeyError: If '@id' is missing.
        """
        if not isinstance(kpi, dict):
            raise TypeError("kpi must be a dict.")
        if "@id" not in kpi:
            raise KeyError("KPI is missing '@id'.")
        return kpi["@id"]

    @staticmethod
    def Value(kpi: Dict[str, Any]) -> Optional[Any]:
        """
        Get the nominal value of the KPI.

        Args:
            kpi: KPI dictionary.

        Returns:
            The nominal value (int, float, str, etc.) or None if missing.

        Raises:
            TypeError: If kpi is not a dict.
        """
        if not isinstance(kpi, dict):
            raise TypeError("kpi must be a dict.")
        return kpi.get("nominalValue", {}).get("value")
