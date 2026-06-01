"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

SPATIAL ELEMENT MODULE
This module defines the SpatialElement class, which provides the base representation
for spatial entities in the BTWIN toolkit.

© Angelo Massafra, 2025
"""

# Dependencies
from typing import Any, Dict, Iterable, Optional

# BTWIN modules
from btwin.schema import Schema


# Functions
class SpatialElement:

    @staticmethod
    def Constructor(
        spatialElementUID: str | None = None,
        spatialElementType: str | None = None,
        name: str | None = None
    ) -> dict | None:
        """
        Create a spatial element dictionary with the required fields.

        Args:
            spatialElementUID (str): Unique identifier of the spatial element.
            spatialElementType (str): Type of the spatial element. Must be one of Schema.Types().
            name (str, optional): Human-readable name of the spatial element.

        Returns:
            dict: A dictionary representing the spatial element.

        Raises:
            ValueError: If required arguments are missing or invalid.
        """
        # Validate mandatory arguments
        if not spatialElementUID:
            raise ValueError("spatialElementUID must be provided.")
        if not spatialElementType:
            raise ValueError("spatialElementType must be provided.")

        # Validate type against allowed values
        allowedTypes = Schema.Types().keys()
        if spatialElementType not in allowedTypes:
            raise ValueError(
                f"Invalid spatialElementType '{spatialElementType}'. "
                f"Must be one of: {', '.join(allowedTypes)}"
            )

        # Initialize the spatial element structure
        element = {
            "@id": spatialElementUID,
            "@type": spatialElementType,
            "relationships": {}   # Placeholder for relationships between elements
        }

        # Optionally add the name if provided
        if name:
            element["name"] = name

        return element

    @staticmethod
    def Relationships(
        spatialElementObject: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Retrieve the relationships of a spatial element.

        Args:
            spatialElementObject (dict, optional): Dictionary representing a spatial
                element. Must contain a 'relationships' key pointing to a dictionary.

        Returns:
            dict: The relationships dictionary of the spatial element.

        Raises:
            TypeError:  If spatialElementObject is not a dict.
            ValueError: If spatialElementObject is None or if the 'relationships'
                        key is missing or not a dict.
        """
        # --- Validate input ----------------------------------------------------
        if spatialElementObject is None:
            raise ValueError("spatialElementObject must be provided.")
        if not isinstance(spatialElementObject, dict):
            raise TypeError("spatialElementObject must be a dict.")

        # --- Extract relationships --------------------------------------------
        relationships = spatialElementObject.get("relationships")
        if relationships is None:
            raise ValueError("The spatialElementObject has no 'relationships' key.")
        if not isinstance(relationships, dict):
            raise ValueError("The 'relationships' key must map to a dict.")

        return relationships

    @staticmethod
    def SetLocationRelationship(
        spatialElementObject: Optional[Dict[str, Any]] = None,
        linkedObject: Optional[Dict[str, Any]] = None,
        linkedObjectUID: Optional[str] = None,
        linkedObjectType: Optional[str] = None,
        *,
        relationshipName: str = "brick:hasLocation",
        deduplicate: bool = True,
        validate: bool = False,
        inPlace: bool = True,
    ) -> Dict[str, Any]:
        """
        Link a spatial element to a location using Brick's hasLocation.

        Args:
            spatialElementObject (dict, optional): Spatial element to update. Must contain
                '@id' and '@type'. A 'relationships' dict will be created if missing.
            linkedObject (dict, optional): Location object providing '@id' and '@type'.
            linkedObjectUID (str, optional): UID of the location when `linkedObject` is not given.
            linkedObjectType (str, optional): Type of the location when `linkedObject` is not given.
            relationshipName (str, optional): Predicate to set. Default 'brick:hasLocation'.
            deduplicate (bool, optional): If True, avoid adding duplicate {'@id','@type'} entries.
            validate (bool, optional): If True, check triple against `SpatialElement.Relationships()`.
            inPlace (bool, optional): If True, mutate `spatialElementObject`; else return a shallow copy.

        Returns:
            dict: The updated spatial element (same instance if `inPlace=True`).

        Raises:
            TypeError:  If `spatialElementObject` is not a dict or malformed.
            ValueError: If required parameters are missing (e.g., no resolvable UID/type for the location).
            KeyError:   If `linkedObject` is provided but lacks '@id' or '@type'.
        """
        # --- Validate container -------------------------------------------------
        if spatialElementObject is None or not isinstance(spatialElementObject, dict):
            raise TypeError("spatialElementObject must be a dict.")
        if not spatialElementObject.get("@id") or not spatialElementObject.get("@type"):
            raise ValueError("spatialElementObject must contain '@id' and '@type'.")

        # --- Resolve target UID/type -------------------------------------------
        if linkedObject is not None:
            if "@id" not in linkedObject or "@type" not in linkedObject:
                raise KeyError("linkedObject must contain '@id' and '@type'.")
            # Prefer explicit UID/type if passed; otherwise derive from object
            linkedObjectUID = linkedObjectUID or linkedObject["@id"]
            linkedObjectType = linkedObjectType or linkedObject["@type"]

        if not linkedObjectUID or not isinstance(linkedObjectUID, str) or not linkedObjectUID.strip():
            raise ValueError("A non-empty linkedObjectUID must be provided or derivable from linkedObject['@id'].")
        if not linkedObjectType or not isinstance(linkedObjectType, str) or not linkedObjectType.strip():
            raise ValueError("A non-empty linkedObjectType must be provided or derivable from linkedObject['@type'].")

        # --- Delegate to the generic relationship setter -----------------------
        # Minimal, explicit call; deduplicate to avoid repeats
        updated = SpatialElement.SetRelationship(
            spatialElementObject=spatialElementObject,
            relationshipName=relationshipName,
            linkedObject=None,                  # already resolved UID/type above
            linkedObjectUID=linkedObjectUID,
            linkedObjectType=linkedObjectType,
            deduplicate=deduplicate,
            validate=validate,
            inPlace=inPlace,
        )

        # --- Return updated structure ------------------------------------------
        return updated

    @staticmethod
    def SetPSetRelationship(
        spatialElementObject: Optional[Dict[str, Any]] = None,
        pset: Optional[Dict[str, Any]] = None,
        psetUID: Optional[str] = None,
        *,
        relationshipName: str = "ifc:HasPropertySets",
        deduplicate: bool = True,
        validate: bool = False,
        inPlace: bool = True,
    ) -> Dict[str, Any]:
        """
        Link a spatial element to a pset using IFC's HasPropertySet.

        Args:
            spatialElementObject (dict, optional): Spatial element to update. Must contain
                '@id' and '@type'. A 'relationships' dict will be created if missing.
            pset (dict, optional): BTwin pset as JSONLD object.
            psetUID (str, optional): UID of the pset when `pset` is not given.
            relationshipName (str, optional): Predicate to set. Default 'ifc:HasPropertySets'.
            deduplicate (bool, optional): If True, avoid adding duplicate {'@id','@type'} entries.
            validate (bool, optional): If True, check triple against `SpatialElement.Relationships()`.
            inPlace (bool, optional): If True, mutate `spatialElementObject`; else return a shallow copy.

        Returns:
            dict: The updated spatial element (same instance if `inPlace=True`).

        Raises:
            TypeError:  If `spatialElementObject` is not a dict or malformed.
            ValueError: If required parameters are missing (e.g., no resolvable UID/type for the pset).
            KeyError:   If `linkedObject` is provided but lacks '@id' or '@type'.
        """
        # --- Validate container -------------------------------------------------
        if spatialElementObject is None or not isinstance(spatialElementObject, dict):
            raise TypeError("spatialElementObject must be a dict.")
        if not spatialElementObject.get("@id") or not spatialElementObject.get("@type"):
            raise ValueError("spatialElementObject must contain '@id' and '@type'.")

        # --- Resolve target UID/type -------------------------------------------
        if pset is not None:
            if "@id" not in pset or "@type" not in pset:
                raise KeyError("linkedObject must contain '@id' and '@type'.")
            # Prefer explicit UID/type if passed; otherwise derive from object
            psetUID = psetUID or pset["@id"]
            linkedObjectType = 'ifc:IfcPropertySet'

        if not psetUID or not isinstance(psetUID, str) or not psetUID.strip():
            raise ValueError("A non-empty linkedObjectUID must be provided or derivable from linkedObject['@id'].")
        if not linkedObjectType or not isinstance(linkedObjectType, str) or not linkedObjectType.strip():
            raise ValueError("A non-empty linkedObjectType must be provided or derivable from linkedObject['@type'].")

        # --- Delegate to the generic relationship setter -----------------------
        # Minimal, explicit call; deduplicate to avoid repeats
        updated = SpatialElement.SetRelationship(
            spatialElementObject=spatialElementObject,
            relationshipName=relationshipName,
            linkedObject=None,                  # already resolved UID/type above
            linkedObjectUID=psetUID,
            linkedObjectType=linkedObjectType,
            deduplicate=deduplicate,
            validate=validate,
            inPlace=inPlace,
        )

        # --- Return updated structure ------------------------------------------
        return updated


    @staticmethod
    def SetRelationship(
        spatialElementObject: Optional[Dict[str, Any]] = None,
        relationshipName: Optional[str] = None,
        linkedObject: Optional[Dict[str, Any]] = None,
        linkedObjectUID: Optional[str] = None,
        linkedObjectType: Optional[str] = None,
        *,
        deduplicate: bool = True,
        validate: bool = True,
        inPlace: bool = True,
    ) -> Dict[str, Any]:
        """
        Set a relationship between a spatial element and a linked object.

        Args:
            spatialElementObject (dict, optional): Spatial element dictionary to update.
                Must contain '@id' (str), '@type' (str). A 'relationships' dict will be
                created if missing.
            relationshipName (str, optional): Predicate label (e.g., 'brick:hasLocation').
            linkedObject (dict, optional): Object dictionary containing '@id' and '@type'.
            linkedObjectUID (str, optional): Object UID used if `linkedObject` is not provided.
            linkedObjectType (str, optional): Object type used if `linkedObject` is not provided.
            deduplicate (bool, optional): Avoid adding duplicate {'@id','@type'} entries. Default True.
            validate (bool, optional): If True, validate the triple against `Relationships()`. Default False.
            inPlace (bool, optional): If True, mutate and return the same dict; if False, return a shallow copy.

        Returns:
            dict: The updated spatial element dictionary (same object if `inPlace=True`).

        Raises:
            ValueError: If required inputs are missing/invalid (e.g., missing IDs or types).
            TypeError: If `spatialElementObject` is not a dict or has malformed structure.
            KeyError: If `linkedObject` is provided but lacks '@id' or '@type'.
        """
        # --- Basic validations -------------------------------------------------
        if spatialElementObject is None:
            raise ValueError("spatialElementObject must be provided.")
        if not isinstance(spatialElementObject, dict):
            raise TypeError("spatialElementObject must be a dict.")
        if not relationshipName or not isinstance(relationshipName, str):
            raise ValueError("relationshipName must be a non-empty string.")

        subjectId = spatialElementObject.get("@id")
        subjectType = spatialElementObject.get("@type")
        if not subjectId or not subjectType:
            raise TypeError("spatialElementObject must contain '@id' and '@type'.")

        # --- Derive linked UID/type from linkedObject if necessary ------------
        if linkedObject is not None:
            try:
                linkedObjectUID = linkedObjectUID or linkedObject["@id"]
                linkedObjectType = linkedObjectType or linkedObject["@type"]
            except KeyError as exc:
                raise KeyError("linkedObject must contain '@id' and '@type'.") from exc

        if not linkedObjectUID or not linkedObjectType:
            raise ValueError(
                "Provide either `linkedObject` with '@id' and '@type', "
                "or both `linkedObjectUID` and `linkedObjectType`."
            )

        target = {"@id": linkedObjectUID, "@type": linkedObjectType}

        # --- Choose output container (in place or copy) -----------------------
        outObject = spatialElementObject if inPlace else dict(spatialElementObject)

        # Ensure 'relationships' is a dict
        relationships = outObject.get("relationships")
        if relationships is None:
            # create relationships container if missing
            relationships = {}
            outObject["relationships"] = relationships
        if not isinstance(relationships, dict):
            raise TypeError("'relationships' must be a dict.")

        # --- Optional schema validation against Schema.RelationshipNames ---
        if validate:
            try:
                relTable = Schema.RelationshipNames()  # expects your implementation
            except Exception as exc:
                raise TypeError("Schema.RelationshipNames() is not available or failed.") from exc

            relDef = relTable.get(relationshipName)
            if not relDef:
                raise ValueError(f"Unknown relationship '{relationshipName}' in Relationships().")

            # Check (subjectType, objectType) is allowed
            allowedPairs = {(p["subject"]["label"], p["object"]["label"]) for p in relDef.get("pairs", [])}
            if (subjectType, linkedObjectType) not in allowedPairs:
                raise ValueError(
                    f"Invalid triple: ({subjectType}) -[{relationshipName}]-> ({linkedObjectType}). "
                    f"Not allowed by Relationships()."
                )

        # --- Insert or append relationship entry ------------------------------
        bucket = relationships.get(relationshipName)
        if bucket is None:
            relationships[relationshipName] = [target]
        else:
            if not isinstance(bucket, list):
                raise TypeError(f"relationships['{relationshipName}'] must be a list.")
            # Optional deduplication
            if not (deduplicate and target in bucket):
                bucket.append(target)

        # --- Return updated structure -----------------------------------------
        return outObject

    @staticmethod
    def Type(
        spatialElementObject: Optional[Dict] = None,
        *,
        fallbackKeys: Iterable[str] = ("@type", "subclass"),
    ) -> str:
        """
        Return the semantic type of a spatial element.

        Args:
            spatialElementObject (dict, optional): The spatial element object to inspect.
                Must be a dictionary-like object.
            fallbackKeys (Iterable[str], optional): Ordered keys to look up for the
                element type. The first found key determines the returned value.

        Returns:
            str: The resolved element type string (e.g., 'bot:Space', 'brick:Zone').

        Raises:
            ValueError: If `spatialElementObject` is not provided, is not a dict,
                        or none of the `fallbackKeys` are present / non-empty.
            TypeError:  If a found key maps to a non-string value.

        """
        # Validate presence
        if spatialElementObject is None:
            raise ValueError("spatialElementObject must be provided.")

        # Validate structure
        if not isinstance(spatialElementObject, dict):
            raise ValueError("spatialElement must be a dict.")

        # Try keys in priority order
        for key in fallbackKeys:
            if key in spatialElementObject:
                elementType = spatialElementObject[key]
                # Ensure the value is a non-empty string
                if not isinstance(elementType, str):
                    raise TypeError(f"Value under '{key}' must be a string.")
                if elementType.strip() == "":
                    continue  # empty string: try next key
                return elementType

        # If none of the keys yielded a valid type, raise a clear error
        orderedKeys = ", ".join(fallbackKeys)
        raise ValueError(
            f"Unable to resolve element type: none of the keys [{orderedKeys}] "
            "are present with a non-empty string value."
        )

    @staticmethod
    def UID(
        spatialElementObject: Optional[Dict] = None,
        *,
        fallbackKeys: Iterable[str] = ("@id", "UID"),
    ) -> str:
        """
        Retrieve the Unique Identifier (UID) of a spatial element.

        Args:
            spatialElementObject (dict, optional): Dictionary representing the spatial element.
                Must contain at least one of the fallback keys.
            fallbackKeys (Iterable[str], optional): Ordered keys to look for the UID.
                Default is ('@id', 'UID').

        Returns:
            str: The resolved UID value (e.g., 'mySpace').

        Raises:
            ValueError: If spatialElementObject is None, not a dict, or no valid UID found.
            TypeError:  If the UID value is not a string.
        """
        # Validate presence
        if spatialElementObject is None:
            raise ValueError("spatialElement must be provided.")
        if not isinstance(spatialElementObject, dict):
            raise ValueError("spatialElement must be a dict.")

        # Try each fallback key
        for key in fallbackKeys:
            if key in spatialElementObject:
                uidValue = spatialElementObject[key]
                # Ensure UID is a valid string
                if not isinstance(uidValue, str):
                    raise TypeError(f"UID under '{key}' must be a string.")
                if uidValue.strip() == "":
                    continue  # skip empty values
                return uidValue

        # If no valid UID found
        keysList = ", ".join(fallbackKeys)
        raise ValueError(
            f"Unable to resolve UID: none of the keys [{keysList}] "
            "contain a non-empty string value."
        )

