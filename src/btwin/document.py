"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

DOCUMENT MODULE
This module defines the Document class, which provides the base representation
for creating document objects in the BTWIN toolkit.

© Angelo Massafra, 2026
"""

# Dependencies
from typing import Any, Dict, Optional


# Functions
class Document():

    @staticmethod
    def Constructor(
        documentObjectUID: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a BTWIN Document JSON-LD dictionary.

        Args:
            documentObjectUID: Unique identifier for the Document (non-empty string required).
            name: Optional human-readable name.

        Returns:
            dict: Document object with '@id', '@type'='btwin:Document', optional 'name',
                  and an empty 'relationships' dict.

        Raises:
            TypeError: If argument types are invalid.
            ValueError: If 'documentObjectUID' is missing or empty.
        """
        # Validate UID
        if not isinstance(documentObjectUID, str):
            raise TypeError("documentObjectUID must be a string.")
        if documentObjectUID.strip() == "":
            raise ValueError("documentObjectUID cannot be empty.")
        # Validate name
        if name is not None and not isinstance(name, str):
            raise TypeError("name must be a string if provided.")

        # Build base structure
        documentObject: Dict[str, Any] = {
            "@id": documentObjectUID,
            "@type": "btwin:Document",
            "relationships": {},
        }
        if isinstance(name, str) and name.strip():
            documentObject["name"] = name

        return documentObject

    @staticmethod
    def Name(documentObject: Dict[str, Any]) -> Optional[str]:
        """
        Retrieve the human-readable name of a Document.

        Args:
            documentObject: The BTWIN Document dictionary.

        Returns:
            str | None: The document name if present, otherwise None.

        Raises:
            TypeError: If documentObject is not a dict.
        """
        # Validate input
        if not isinstance(documentObject, dict):
            raise TypeError("documentObject must be a dict.")
        name = documentObject.get("name")
        if name is not None and not isinstance(name, str):
            raise TypeError("documentObject['name'] must be a string if present.")
        return name

    @staticmethod
    def Relationships(documentObject: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieve the 'relationships' dictionary of a Document.

        Args:
            documentObject: The BTWIN Document dictionary.

        Returns:
            dict: The relationships dictionary (empty dict if missing).

        Raises:
            TypeError: If documentObject is not a dict.
            KeyError: If 'relationships' exists but is not a dict.
        """
        # Validate input
        if not isinstance(documentObject, dict):
            raise TypeError("documentObject must be a dict.")

        relationships = documentObject.get("relationships", {})
        if not isinstance(relationships, dict):
            raise KeyError("documentObject['relationships'] must be a dict.")
        return relationships

    @staticmethod
    def SetPSet(
        documentObject: Dict[str, Any],
        *,
        pset: Optional[Dict[str, Any]] = None,
        psetUID: Optional[str] = None,
        append: bool = True,
        avoidDuplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Set the **ifc:HasPropertySets** relationship for a Document.

        Args:
            documentObject: Document dict to update.
            pset: Optional Property Set dict, as built by 'PropertySet.Constructor()'.
                  UID resolved from ['@id','id','UID'].
            psetUID: Fallback UID if not present in 'pset'.
            append: If True, appends; if False, overwrites the relation list.
            avoidDuplicates: If True, avoids inserting identical {'@id','@type'} pairs.

        Returns:
            dict: The updated documentObject with 'ifc:HasPropertySets' set.

        Raises:
            TypeError: If inputs are invalid types.
            ValueError: If UID cannot be resolved.
        """
        # Resolve UID from pset or fallback
        resolvedUID = None
        if pset is not None:
            if not isinstance(pset, dict):
                raise TypeError("pset must be a dict if provided.")
            for key in ("@id", "id", "UID"):
                val = pset.get(key)
                if isinstance(val, str) and val.strip():
                    resolvedUID = val
                    break

        resolvedUID = resolvedUID or psetUID

        if not isinstance(resolvedUID, str) or not resolvedUID.strip():
            raise ValueError("Property Set UID is required (via pset or psetUID).")

        # Delegate to SetRelationship enforcing predicate and IFC property set type
        return Document.SetRelationship(
            documentObject=documentObject,
            relationshipName="ifc:HasPropertySets",
            linkedObjectUID=resolvedUID,
            linkedObjectType="ifc:IfcPropertySet",
            append=append,
            avoidDuplicates=avoidDuplicates,
        )

    @staticmethod
    def SetRelationship(
        documentObject: Dict[str, Any],
        relationshipName: str,
        linkedObject: Optional[Dict[str, Any]] = None,
        linkedObjectUID: Optional[str] = None,
        linkedObjectType: Optional[str] = None,
        *,
        append: bool = True,
        avoidDuplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Create or append a relationship on a Document JSON-LD object.

        Args:
            documentObject: Document dict to update. If 'relationships' is missing, it will be created.
            relationshipName: Predicate (e.g., 'eko:hasAssociatedObject'). Must be non-empty.
            linkedObject: Optional related object. UID/type resolved from (in order):
                          UID: ['@id', 'id', 'UID']; type: ['@type', 'type', 'label'].
            linkedObjectUID: Fallback UID if not present in 'linkedObject'.
            linkedObjectType: Fallback type if not present in 'linkedObject'.
            append: If True, appends to existing list; if False, overwrites with a single-item list.
            avoidDuplicates: If True, prevents inserting identical {'@id','@type'} pairs.

        Returns:
            dict: The updated documentObject.

        Raises:
            TypeError: If inputs are of invalid types.
            ValueError: If 'relationshipName' is empty, or UID/type cannot be resolved.
            KeyError: If 'relationships' exists but is not a dict.
        """
        # Validate container
        if not isinstance(documentObject, dict):
            raise TypeError("documentObject must be a dict.")
        # Ensure relationships container
        if "relationships" not in documentObject:
            documentObject["relationships"] = {}
        if not isinstance(documentObject["relationships"], dict):
            raise KeyError("documentObject['relationships'] must be a dict.")

        # Validate relationship name
        if not isinstance(relationshipName, str) or not relationshipName.strip():
            raise ValueError("relationshipName must be a non-empty string.")

        # Resolve UID/type
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

        # Insert/append
        current = documentObject["relationships"].get(relationshipName)
        if not append or not isinstance(current, list):
            documentObject["relationships"][relationshipName] = [payload]
        else:
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

        return documentObject

    @staticmethod
    def SetScenario(
        documentObject: Dict[str, Any],
        *,
        scenarioObject: Optional[Dict[str, Any]] = None,
        scenarioUID: Optional[str] = None,
        scenarioType: Optional[str] = "kpi:Scenario",
        append: bool = True,
        avoidDuplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Set the **kpi:relatedScenario** relationship for a Document.

        Args:
            documentObject: Document dict to update.
            scenarioObject: Optional Scenario dict. UID/type resolved from ['@id','id','UID'] and ['@type','type','label'].
            scenarioUID: Fallback UID if not present in 'scenarioObject'.
            scenarioType: Fallback type if not present in 'scenarioObject' (default 'kpi:Scenario').
            append: If True, appends; if False, overwrites the relation list.
            avoidDuplicates: If True, avoids inserting identical {'@id','@type'} pairs.

        Returns:
            dict: The updated documentObject with 'kpi:relatedScenario' set.

        Raises:
            TypeError: If inputs are invalid types.
            ValueError: If UID cannot be resolved.
        """
        # Resolve UID/type from scenarioObject or fallbacks
        resolvedUID = None
        resolvedType = None
        if isinstance(scenarioObject, dict):
            for key in ("@id", "id", "UID"):
                val = scenarioObject.get(key)
                if isinstance(val, str) and val.strip():
                    resolvedUID = val
                    break
            for key in ("@type", "type", "label"):
                val = scenarioObject.get(key)
                if isinstance(val, str) and val.strip():
                    resolvedType = val
                    break

        resolvedUID = resolvedUID or scenarioUID
        resolvedType = resolvedType or scenarioType

        if not isinstance(resolvedUID, str) or not resolvedUID.strip():
            raise ValueError("Scenario UID is required (via scenarioObject or scenarioUID).")
        if not isinstance(resolvedType, str) or not resolvedType.strip():
            raise ValueError("Scenario type is required (via scenarioObject or scenarioType).")

        # Delegate to SetRelationship enforcing the predicate
        return Document.SetRelationship(
            documentObject=documentObject,
            relationshipName="kpi:relatedScenario",
            linkedObjectUID=resolvedUID,
            linkedObjectType=resolvedType,
            append=append,
            avoidDuplicates=avoidDuplicates,
        )

    @staticmethod
    def UID(documentObject: Dict[str, Any]) -> str:
        """
        Retrieve the unique identifier (UID) of a Document.

        Args:
            documentObject: The BTWIN Document dictionary (must contain '@id').

        Returns:
            str: The UID of the document.

        Raises:
            TypeError: If documentObject is not a dict.
            KeyError: If '@id' is missing from the document.
            ValueError: If '@id' is empty or invalid.
        """
        # Validate input
        if not isinstance(documentObject, dict):
            raise TypeError("documentObject must be a dict.")
        if "@id" not in documentObject:
            raise KeyError("documentObject is missing '@id'.")
        uid = documentObject["@id"]
        if not isinstance(uid, str) or not uid.strip():
            raise ValueError("documentObject['@id'] must be a non-empty string.")
        return uid
