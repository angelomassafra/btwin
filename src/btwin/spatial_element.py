"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

SPATIAL ELEMENT MODULE
This module defines the SpatialElement class, which provides the base representation
for spatial entities in the BTWIN toolkit.

© Angelo Massafra, 2026
"""

# Dependencies
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

# BTWIN modules
from .property_set import Property, PropertySet
from .schema import Schema

# What an IFC quantity carries: the attribute holding the value, and the measure it is.
# IfcPhysicalComplexQuantity is absent on purpose - it nests further quantities rather than
# carrying a value of its own, and flattening it would invent property names.
_IFC_QUANTITY_KINDS = {
    "IfcQuantityLength": ("LengthValue", "IfcLengthMeasure"),
    "IfcQuantityArea": ("AreaValue", "IfcAreaMeasure"),
    "IfcQuantityVolume": ("VolumeValue", "IfcVolumeMeasure"),
    "IfcQuantityCount": ("CountValue", "IfcCountMeasure"),
    "IfcQuantityWeight": ("WeightValue", "IfcMassMeasure"),
    "IfcQuantityTime": ("TimeValue", "IfcTimeMeasure"),
}


def _IFCUnitLabel(ifcUnit) -> Optional[str]:
    """
    A readable unit for one property, or None.

    Most IFC properties carry no unit at all: the file states its units once, in the project's
    IfcUnitAssignment, and every value is understood in those. None is therefore the ordinary
    case rather than a failure, and it maps to a property with no 'unit'.
    """
    if ifcUnit is None:
        return None
    name = getattr(ifcUnit, "Name", None)
    if not isinstance(name, str) or not name.strip():
        return None
    prefix = getattr(ifcUnit, "Prefix", None)
    return f"{prefix}{name}" if isinstance(prefix, str) and prefix.strip() else name


def _IFCProperty(ifcProperty) -> Optional[Dict[str, Any]]:
    """
    One IFC property as a BTWIN property, or None for a kind BTWIN cannot carry.

    The datatype recorded is the IFC measure, not the Python type behind it: 'IfcAreaMeasure'
    says what 14.44 means, where 'float' does not.
    """
    name = getattr(ifcProperty, "Name", None)
    if not isinstance(name, str) or not name.strip():
        return None

    if ifcProperty.is_a("IfcPropertySingleValue"):
        nominal = getattr(ifcProperty, "NominalValue", None)
        if nominal is None:
            return None
        return Property.Constructor(
            propertyName=name.strip(),
            propertyValue=nominal.wrappedValue,
            propertyQuantity=nominal.is_a(),
            propertyUnit=_IFCUnitLabel(getattr(ifcProperty, "Unit", None)),
        )

    if ifcProperty.is_a("IfcPropertyEnumeratedValue"):
        values = list(getattr(ifcProperty, "EnumerationValues", None) or [])
        if not values:
            return None
        return Property.Constructor(
            propertyName=name.strip(),
            propertyValues=[value.wrappedValue for value in values],
            propertyQuantity=values[0].is_a(),
            propertyType="IfcPropertyEnumeratedValue",
        )

    # IfcPropertyListValue, IfcPropertyBoundedValue, IfcPropertyTableValue and
    # IfcComplexProperty have no BTWIN counterpart, so they are left out rather than
    # flattened into a shape the schema does not describe.
    return None


def _IFCQuantity(ifcQuantity) -> Optional[Dict[str, Any]]:
    """
    One IFC quantity as a BTWIN property.

    A quantity is a measurement and a property is an assertion, but both are a name with a
    typed value, and the graph has one shape for that. The distinction survives in the set's
    own name, which is 'Qto_...' by IFC convention.
    """
    kind = _IFC_QUANTITY_KINDS.get(ifcQuantity.is_a())
    name = getattr(ifcQuantity, "Name", None)
    if kind is None or not isinstance(name, str) or not name.strip():
        return None

    attribute, measure = kind
    value = getattr(ifcQuantity, attribute, None)
    if value is None:
        return None
    return Property.Constructor(
        propertyName=name.strip(),
        propertyValue=value,
        propertyQuantity=measure,
        propertyUnit=_IFCUnitLabel(getattr(ifcQuantity, "Unit", None)),
    )


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
        # A pset is always this one type, so it is settled before the branch below: leaving it
        # to be bound only when `pset` is given made the psetUID-only path - the documented
        # way to link a set by UID alone - raise UnboundLocalError instead of reaching its
        # own check.
        linkedObjectType = 'ifc:IfcPropertySet'
        if pset is not None:
            if "@id" not in pset or "@type" not in pset:
                raise KeyError("linkedObject must contain '@id' and '@type'.")
            # Prefer explicit UID/type if passed; otherwise derive from object
            psetUID = psetUID or pset["@id"]

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


class SpatialHierarchy():

    @staticmethod
    def ByIFC(
        ifcFilePath: Optional[Union[str, Path]] = None,
        *,
        relationshipName: str = "brick:hasLocation",
        psetNames: Optional[Iterable[str]] = None,
        validate: bool = True,
    ) -> Dict[str, Any]:
        """
        Extract the spatial hierarchy of an IFC model as BTWIN objects.

        Maps IfcBuilding to 'bot:Building', IfcBuildingStorey to 'bot:Storey',
        IfcSpace to 'bot:Space' and IfcZone to 'brick:Zone', using each entity's GlobalId
        as UID. Containment is read from the IFC decomposition (and from spatial
        containment as a fallback) and written as upward relationships:
        space -> storey -> building.

        A zone is not part of that chain. IfcZone is a group, so its members are read from
        IfcRelAssignsToGroup instead, and the membership is written the way the schema
        allows it: the space points at the zone, as it already points at its storey, and
        the zone itself points at the building. A space may therefore be in several zones,
        and a zone with no space in this building is left out.

        Args:
            ifcFilePath (str | Path, optional): Path to the IFC file to parse.
            relationshipName (str, optional): Predicate linking a child to its parent.
                Default 'brick:hasLocation'.
            psetNames (iterable[str], optional): Names of the property sets to read, matched
                exactly against IfcPropertySet.Name and IfcElementQuantity.Name. Nothing is
                read unless this is given: an authoring tool writes far more property sets
                than a building model needs - a Revit export of eleven spatial elements
                carries eighty-five of them, most describing the export rather than the
                building - so which ones are worth keeping is the caller's judgement, not
                a default. Quantity sets are read the same way, by name.
            validate (bool, optional): If True, validate each relationship against
                `Schema.RelationshipNames()`. Default True.

        Returns:
            dict: {'building': dict | None, 'storeys': list[dict], 'spaces': list[dict],
                'zones': list[dict], 'psets': list[dict]}. 'building' is None and the lists
                are empty when the file has no IfcBuilding; 'psets' is empty unless
                `psetNames` asked for something. Every object is ready for Serialization.

        Raises:
            ImportError: If ifcopenshell is not installed.
            ValueError:  If `ifcFilePath` is not provided, or if a relationship is
                         rejected while `validate=True`.
            OSError:     If the IFC file does not exist or cannot be read.
        """
        # Import ifcopenshell locally to provide a clear error if it's missing
        try:
            import ifcopenshell
        except Exception as exc:
            raise ImportError("ifcopenshell is required. Install with `pip install ifcopenshell`.") from exc

        # --- Validate input ----------------------------------------------------
        if not ifcFilePath:
            raise ValueError("ifcFilePath must be provided.")

        path = Path(ifcFilePath)
        if not path.exists():
            raise OSError(f"IFC file not found: {path}")

        try:
            ifcFile = ifcopenshell.open(str(path))
        except Exception as exc:
            raise OSError(f"Failed to open IFC file '{path}'.") from exc

        # --- Helpers -----------------------------------------------------------
        def elementName(ifcEntity) -> Optional[str]:
            """Prefer LongName, fall back to Name; ignore empty strings."""
            for candidate in (getattr(ifcEntity, "LongName", None), getattr(ifcEntity, "Name", None)):
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            return None

        def childrenOf(ifcEntity, ifcClass: str) -> List[Any]:
            """Children of a spatial element, via decomposition and spatial containment."""
            found: List[Any] = []
            seen = set()
            for rel in getattr(ifcEntity, "IsDecomposedBy", None) or []:
                for child in rel.RelatedObjects or []:
                    if child.is_a(ifcClass) and child.GlobalId not in seen:
                        seen.add(child.GlobalId)
                        found.append(child)
            for rel in getattr(ifcEntity, "ContainsElements", None) or []:
                for child in rel.RelatedElements or []:
                    if child.is_a(ifcClass) and child.GlobalId not in seen:
                        seen.add(child.GlobalId)
                        found.append(child)
            return found

        wanted = set(psetNames or ())
        psetByUID: Dict[str, Dict[str, Any]] = {}

        def attachPSets(spatialObject: Dict[str, Any], ifcEntity) -> None:
            """Link every named property set of `ifcEntity` to `spatialObject`."""
            if not wanted:
                return
            for rel in getattr(ifcEntity, "IsDefinedBy", None) or []:
                definition = getattr(rel, "RelatingPropertyDefinition", None)
                if definition is None or getattr(definition, "Name", None) not in wanted:
                    continue

                # One IfcRelDefinesByProperties can define several elements at once, so a set
                # shared by two spaces becomes one node with two owners rather than a copy
                # each - which is also what makes the two spaces comparable in the graph.
                uid = definition.GlobalId
                pset = psetByUID.get(uid)
                if pset is None:
                    if definition.is_a("IfcPropertySet"):
                        read = [_IFCProperty(p) for p in (definition.HasProperties or [])]
                    elif definition.is_a("IfcElementQuantity"):
                        read = [_IFCQuantity(q) for q in (definition.Quantities or [])]
                    else:
                        continue
                    properties = [entry for entry in read if entry is not None]
                    if not properties:
                        # Every property was of a kind BTWIN cannot carry: an empty set would
                        # claim the element has one when nothing of it survived
                        continue
                    pset = PropertySet.Constructor(psetUID=uid, psetName=definition.Name)
                    pset["ifc:HasProperties"] = properties
                    psetByUID[uid] = pset

                SpatialElement.SetPSetRelationship(
                    spatialElementObject=spatialObject, pset=pset, validate=validate)

        # --- Building (first one in the file) ----------------------------------
        ifcBuildings = ifcFile.by_type("IfcBuilding")
        if not ifcBuildings:
            return {"building": None, "storeys": [], "spaces": [], "zones": [], "psets": []}

        ifcBuilding = ifcBuildings[0]
        building = SpatialElement.Constructor(
            spatialElementUID=ifcBuilding.GlobalId,
            spatialElementType="bot:Building",
            name=elementName(ifcBuilding),
        )
        attachPSets(building, ifcBuilding)

        # --- Storeys, linked to the building -----------------------------------
        storeys: List[Dict[str, Any]] = []
        spaces: List[Dict[str, Any]] = []
        for ifcStorey in childrenOf(ifcBuilding, "IfcBuildingStorey"):
            storey = SpatialElement.Constructor(
                spatialElementUID=ifcStorey.GlobalId,
                spatialElementType="bot:Storey",
                name=elementName(ifcStorey),
            )
            SpatialElement.SetLocationRelationship(
                spatialElementObject=storey,
                linkedObject=building,
                relationshipName=relationshipName,
                validate=validate,
            )
            attachPSets(storey, ifcStorey)
            storeys.append(storey)

            # --- Spaces, linked to their storey ---------------------------------
            for ifcSpace in childrenOf(ifcStorey, "IfcSpace"):
                space = SpatialElement.Constructor(
                    spatialElementUID=ifcSpace.GlobalId,
                    spatialElementType="bot:Space",
                    name=elementName(ifcSpace),
                )
                SpatialElement.SetLocationRelationship(
                    spatialElementObject=space,
                    linkedObject=storey,
                    relationshipName=relationshipName,
                    validate=validate,
                )
                attachPSets(space, ifcSpace)
                spaces.append(space)

        # --- Zones, and the spaces that belong to them --------------------------
        # An IfcZone is a group rather than a spatial structure element, so its members come
        # from IfcRelAssignsToGroup, not from decomposition. Only spaces already parsed above
        # count: a zone whose spaces all sit in another building is not part of this hierarchy.
        spaceByUID = {space["@id"]: space for space in spaces}
        zones: List[Dict[str, Any]] = []
        for ifcZone in ifcFile.by_type("IfcZone"):
            grouped = getattr(ifcZone, "IsGroupedBy", None) or []
            # IFC4 carries a set of relationships here, IFC2X3 a single one
            if not isinstance(grouped, (list, tuple)):
                grouped = [grouped]

            members = [
                spaceByUID[member.GlobalId]
                for rel in grouped
                for member in (getattr(rel, "RelatedObjects", None) or [])
                if member.is_a("IfcSpace") and member.GlobalId in spaceByUID
            ]
            if not members:
                continue

            zone = SpatialElement.Constructor(
                spatialElementUID=ifcZone.GlobalId,
                spatialElementType="brick:Zone",
                name=elementName(ifcZone),
            )
            SpatialElement.SetLocationRelationship(
                spatialElementObject=zone,
                linkedObject=building,
                relationshipName=relationshipName,
                validate=validate,
            )

            attachPSets(zone, ifcZone)

            # The space points at the zone, not the reverse: that is the direction the schema
            # allows, and it is the same shape as the link the space already has to its storey
            for space in members:
                SpatialElement.SetLocationRelationship(
                    spatialElementObject=space,
                    linkedObject=zone,
                    relationshipName=relationshipName,
                    validate=validate,
                )
            zones.append(zone)

        # --- Return the parsed hierarchy ---------------------------------------
        return {"building": building, "storeys": storeys, "spaces": spaces, "zones": zones,
                "psets": list(psetByUID.values())}

