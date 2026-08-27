"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

SCENARIO MODULE
This module defines the Scenario class, which provides the base representation
for scenario modeling in the BTWIN toolkit.

© Angelo Massafra, 2026
"""


from typing import Any, Dict, Optional


class Scenario():

    @staticmethod
    def Constructor(
        scenarioUID: Optional[str] = None,
        scenarioType: str = "kpi:Scenario",
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a Scenario dictionary in BTWIN JSON-LD style.

        Args:
            scenarioUID: Unique identifier for the scenario (non-empty string required).
            scenarioType: '@type' value for the scenario (default 'kpi:Scenario').
            name: Optional human-readable name.
            description: Optional description.

        Returns:
            dict: A scenario dictionary with keys '@id', '@type', optional 'name'/'description',
                  and an empty 'relationships' dict.

        Raises:
            TypeError: If argument types are invalid.
            ValueError: If 'scenarioUID' is missing/empty or 'scenarioType' is empty.
        """
        # --- Validate UID ---
        if scenarioUID is None or not isinstance(scenarioUID, str):
            raise TypeError("scenarioUID must be a non-empty string.")
        if scenarioUID.strip() == "":
            raise ValueError("scenarioUID cannot be empty.")

        # --- Validate type ---
        if not isinstance(scenarioType, str):
            raise TypeError("scenarioType must be a string.")
        if scenarioType.strip() == "":
            raise ValueError("scenarioType cannot be empty.")

        # --- Validate optional fields ---
        if name is not None and not isinstance(name, str):
            raise TypeError("name must be a string if provided.")
        if description is not None and not isinstance(description, str):
            raise TypeError("description must be a string if provided.")

        # --- Build base structure ---
        scenario: Dict[str, Any] = {
            "@id": scenarioUID,
            "@type": scenarioType,
            "relationships": {},  # empty container ready for future links
        }

        # --- Attach optional attributes (only if non-empty) ---
        if isinstance(name, str) and name.strip():
            scenario["name"] = name
        if isinstance(description, str) and description.strip():
            scenario["description"] = description

        return scenario

    @staticmethod
    def UID(scenarioObject: Dict[str, Any]) -> str:
        """
        Get the unique identifier of a Scenario.

        Args:
            scenarioObject: A Scenario dictionary (must contain '@id').

        Returns:
            str: The UID of the Scenario.

        Raises:
            TypeError: If scenarioObject is not a dict.
            KeyError: If '@id' is missing.
        """
        if not isinstance(scenarioObject, dict):
            raise TypeError("scenarioObject must be a dict.")
        if "@id" not in scenarioObject:
            raise KeyError("scenarioObject is missing '@id'.")
        return scenarioObject["@id"]

    @staticmethod
    def Name(scenarioObject: Dict[str, Any]) -> Optional[str]:
        """
        Get the human-readable name of a Scenario.

        Args:
            scenarioObject: A Scenario dictionary.

        Returns:
            str | None: The name if available, otherwise None.

        Raises:
            TypeError: If scenarioObject is not a dict.
        """
        if not isinstance(scenarioObject, dict):
            raise TypeError("scenarioObject must be a dict.")
        return scenarioObject.get("name")

    @staticmethod
    def Description(scenarioObject: Dict[str, Any]) -> Optional[str]:
        """
        Get the description of a Scenario.

        Args:
            scenarioObject: A Scenario dictionary.

        Returns:
            str | None: The description if available, otherwise None.

        Raises:
            TypeError: If scenarioObject is not a dict.
        """
        if not isinstance(scenarioObject, dict):
            raise TypeError("scenarioObject must be a dict.")
        return scenarioObject.get("description")

    @staticmethod
    def Relationships(scenarioObject: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get the relationships dictionary of a Scenario.

        Args:
            scenarioObject: A Scenario dictionary.

        Returns:
            dict: The relationships dict (empty dict if missing).

        Raises:
            TypeError: If scenarioObject is not a dict.
        """
        if not isinstance(scenarioObject, dict):
            raise TypeError("scenarioObject must be a dict.")
        return scenarioObject.get("relationships", {})

    @staticmethod
    def SetRelationship(
        scenarioObject: Dict[str, Any] = None,
        relationshipName: Optional[str] = None,
        linkedObject: Optional[Dict[str, Any]] = None,
        linkedObjectUID: Optional[str] = None,
        linkedObjectType: Optional[str] = None,
        *,
        append: bool = True,
        avoidDuplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Create or append a relationship on a Scenario JSON-LD object.

        Args:
            scenarioObject: Scenario dict to update. If 'relationships' is missing, it will be created.
            relationshipName: Predicate (e.g., 'eko:hasAssociatedObject'). Must be a non-empty string.
            linkedObject: Optional related object dict. The function tries to resolve:
                          UID from ['@id', 'id', 'UID'], and type from ['@type', 'type', 'label'].
            linkedObjectUID: Fallback UID if not present in 'linkedObject'.
            linkedObjectType: Fallback type if not present in 'linkedObject'.
            append: If True, appends to existing list; if False, overwrites with a single-item list.
            avoidDuplicates: If True, prevents inserting identical {'@id','@type'} pairs.

        Returns:
            dict: The updated scenarioObject.

        Raises:
            TypeError: If 'scenarioObject' isn't a dict, or types are invalid.
            ValueError: If 'relationshipName' is empty, or UID/type cannot be resolved.
            KeyError: If 'relationships' exists but isn't a dict.
        """
        # --- Validate scenarioObject ---
        if not isinstance(scenarioObject, dict):
            raise TypeError("scenarioObject must be a dict.")

        # Ensure 'relationships' container
        if "relationships" not in scenarioObject:
            scenarioObject["relationships"] = {}
        if not isinstance(scenarioObject["relationships"], dict):
            raise KeyError("scenarioObject['relationships'] must be a dict.")

        # --- Validate relationshipName ---
        if not isinstance(relationshipName, str) or not relationshipName.strip():
            raise ValueError("relationshipName must be a non-empty string.")

        # --- Resolve UID and type ---
        resolvedUID = None
        resolvedType = None

        if isinstance(linkedObject, dict):
            for key in ("@id", "id", "UID"):
                val = linkedObject.get(key)
                if isinstance(val, str) and val.strip():
                    resolvedUID = val
                    break
            for key in ("@type", "type", "label"):
                val = linkedObject.get(key)
                if isinstance(val, str) and val.strip():
                    resolvedType = val
                    break

        resolvedUID = resolvedUID or linkedObjectUID
        resolvedType = resolvedType or linkedObjectType

        if not isinstance(resolvedUID, str) or not resolvedUID.strip():
            raise ValueError("A related element UID is required (via linkedObject or linkedObjectUID).")
        if not isinstance(resolvedType, str) or not resolvedType.strip():
            raise ValueError("A related element type is required (via linkedObject or linkedObjectType).")

        payload = {"@id": resolvedUID, "@type": resolvedType}

        # --- Insert / append ---
        current = scenarioObject["relationships"].get(relationshipName)
        if not append or not isinstance(current, list):
            # Overwrite or initialize
            scenarioObject["relationships"][relationshipName] = [payload]
        else:
            # Append with optional duplicate check
            if avoidDuplicates:
                exists = any(
                    isinstance(it, dict)
                    and it.get("@id") == payload["@id"]
                    and it.get("@type") == payload["@type"]
                    for it in current
                )
                if not exists:
                    current.append(payload)
            else:
                current.append(payload)

        return scenarioObject

