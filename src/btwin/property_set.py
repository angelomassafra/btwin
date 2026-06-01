"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

PROPERTY MODULE
This module defines the Property class, which provides the base representation
for attributing properties to the digital objects in the BTWIN toolkit.

© Angelo Massafra, 2025
"""

class PropertySet:

    @staticmethod
    def Constructor(psetUID=None, psetName=None):
        """
        Create a new Property Set (PSet) dictionary.

        Args:
            psetUID (str | None): Unique identifier for the property set (used as '@id').
            psetName (str | None): Human-readable name of the property set.

        Returns:
            dict: A dictionary representing an IFC Property Set with keys:
                  '@id', '@type' (fixed 'ifc:IfcPropertySet'), 'name', 'ifc:HasProperties' (list).

        Raises:
            ValueError: If psetUID or psetName is missing or empty.
            TypeError: If inputs are not str/None.
        """
        # Basic validation
        if psetUID is None or (isinstance(psetUID, str) and not psetUID.strip()):
            raise ValueError("psetUID must be a non-empty string.")
        if psetName is None or (isinstance(psetName, str) and not psetName.strip()):
            raise ValueError("psetName must be a non-empty string.")
        if not isinstance(psetUID, str) or not isinstance(psetName, str):
            raise TypeError("psetUID and psetName must be strings.")

        # Build minimal IFC PSet structure
        pSet = {
            '@id': psetUID,
            '@type': 'ifc:IfcPropertySet',
            'name': psetName,
            'ifc:HasProperties': []
        }
        return pSet

    @staticmethod
    def Properties(pset=None):
        """
        Get the list of properties from a property set.

        Args:
            pset (dict | None): Property set dictionary.

        Returns:
            list: The list stored under 'ifc:HasProperties'. Returns an empty list if absent.

        Raises:
            TypeError: If pset is not a dict.
        """
        if not isinstance(pset, dict):
            raise TypeError("pset must be a dict.")
        # Return a live reference to the list (caller may append/remove)
        return pset.get('ifc:HasProperties', [])

    @staticmethod
    def Property(pset=None, propertyName=None):
        """
        Retrieve a property from a property set by its 'name'.

        Args:
            pset (dict | None): Property set dictionary containing 'ifc:HasProperties' list.
            propertyName (str | None): Name of the property to search.

        Returns:
            dict | None: The matching property dict if found; otherwise None.

        Raises:
            TypeError: If inputs are of wrong type.
            ValueError: If propertyName is empty.
        """
        if not isinstance(pset, dict):
            raise TypeError("pset must be a dict.")
        if propertyName is None or (isinstance(propertyName, str) and not propertyName.strip()):
            raise ValueError("propertyName must be a non-empty string.")

        for propObj in pset.get('ifc:HasProperties', []):
            if isinstance(propObj, dict) and propObj.get('name') == propertyName:
                return propObj
        return None

    @staticmethod
    def SetProperties(pset=None, properties=None, overwrite=False):
        """
        Add (and optionally overwrite) multiple properties into a property set.

        Args:
            pset (dict | None):
                Property set dictionary. Must contain (or will create) 'ifc:HasProperties' as a list.
            properties (Iterable[dict] | None):
                Iterable of property dictionaries to add. Each dict must have a non-empty 'name' key.
            overwrite (bool):
                Replace existing properties with the same name if True; otherwise keep existing.

        Returns:
            dict:
                The updated property set (same reference as input).

        Raises:
            TypeError:
                - If `pset` is not a dict.
                - If `pset['ifc:HasProperties']` is not a list.
                - If `properties` is not an iterable of dicts.
            ValueError:
                - If any property lacks a valid non-empty 'name'.
        """
        # --- Validate pset ---
        if not isinstance(pset, dict):
            raise TypeError("pset must be a dict.")
        if 'ifc:HasProperties' not in pset:
            pset['ifc:HasProperties'] = []
        if not isinstance(pset['ifc:HasProperties'], list):
            raise TypeError("pset['ifc:HasProperties'] must be a list.")

        # --- Validate properties input ---
        if properties is None:
            return pset  # nothing to do, keep idempotent
        try:
            iter(properties)
        except TypeError:
            raise TypeError("properties must be an iterable of dicts.")

        # --- Build index for existing properties by name (for O(1) lookups) ---
        nameToIndex = {}
        for i, existing in enumerate(pset['ifc:HasProperties']):
            if isinstance(existing, dict):
                n = existing.get('name')
                if isinstance(n, str) and n.strip():
                    # keep first occurrence; in case of duplicates, first wins
                    nameToIndex.setdefault(n, i)

        # --- Process incoming properties ---
        for prop in properties:
            if not isinstance(prop, dict):
                raise TypeError("Each element of `properties` must be a dict.")
            propName = prop.get('name')
            if propName is None or (isinstance(propName, str) and not propName.strip()):
                raise ValueError("Every property must have a non-empty 'name' field.")

            if propName in nameToIndex:
                if overwrite:
                    # Replace in-place the first occurrence
                    idx = nameToIndex[propName]
                    pset['ifc:HasProperties'][idx] = prop
                    # index remains valid; content replaced
                else:
                    # Keep existing, skip incoming
                    continue
            else:
                # Append new property and index it
                pset['ifc:HasProperties'].append(prop)
                nameToIndex[propName] = len(pset['ifc:HasProperties']) - 1

        return pset

    @staticmethod
    def SetProperty(pset=None, property=None, overwrite=False):
        """
        Add or optionally overwrite a property inside a property set.

        If a property with the same 'name' exists:
          - If overwrite is False, the set is left unchanged.
          - If overwrite is True, the existing property is replaced in-place.

        Args:
            pset (dict | None): Property set dictionary with 'ifc:HasProperties' list.
            property (dict | None): Property dictionary to add or replace. Must contain 'name'.
            overwrite (bool): Whether to replace an existing property with the same name.

        Returns:
            dict: The updated property set (same reference as input).

        Raises:
            TypeError: If pset/property types are invalid or 'ifc:HasProperties' is not a list.
            ValueError: If property has no 'name' or name is empty.
        """
        if not isinstance(pset, dict):
            raise TypeError("pset must be a dict.")
        if 'ifc:HasProperties' not in pset:
            pset['ifc:HasProperties'] = []
        if not isinstance(pset['ifc:HasProperties'], list):
            raise TypeError("pset['ifc:HasProperties'] must be a list.")
        if not isinstance(property, dict):
            raise TypeError("prop must be a dict.")
        propName = property.get('name')
        if propName is None or (isinstance(propName, str) and not propName.strip()):
            raise ValueError("prop['name'] must be a non-empty string.")

        # Find existing property by name
        for i, existing in enumerate(pset['ifc:HasProperties']):
            if isinstance(existing, dict) and existing.get('name') == propName:
                if overwrite:
                    # Replace in-place
                    pset['ifc:HasProperties'][i] = property
                # If not overwriting, leave as is
                return pset

        # If not found, append
        pset['ifc:HasProperties'].append(property)
        return pset

    @staticmethod
    def UID(pset=None):
        """
            Return the unique identifier of the property set JSONLD object
        """
        return pset['@id']

class Property:

    @staticmethod
    def Constructor(propertyName=None, propertyValue=None, propertyValues=None,
                    propertyQuantity=None, propertyType='IfcPropertySingleValue', propertyUnit=None):
        """
        Create an IFC property dictionary (Single or Enumerated value).

        Args:
            propertyName (str | None): Property name (required).
            propertyValue (any | None): Single value for 'IfcPropertySingleValue'.
            propertyValues (list | None): Values for 'IfcPropertyEnumeratedValue'.
            propertyQuantity (str | None): Datatype/quantity of the value(s) (e.g., 'IfcLabel').
            propertyType (str): Either 'IfcPropertySingleValue' or 'IfcPropertyEnumeratedValue'.

        Returns:
            dict: IFC property dictionary with keys '@type', 'name', and one of:
                  - 'nominalValue': {'type': propertyQuantity, 'value': propertyValue}
                  - 'enumeratedValues': [{'type': propertyQuantity, 'value': v}, ...]

        Raises:
            ValueError: If required inputs are missing or inconsistent with propertyType.
            TypeError: If input types are invalid.
        """
        # --- Validate inputs ---
        if propertyName is None or (isinstance(propertyName, str) and not propertyName.strip()):
            raise ValueError("propertyName must be a non-empty string.")
        if not isinstance(propertyType, str):
            raise TypeError("propertyType must be a string.")
        if propertyType not in ('IfcPropertySingleValue', 'IfcPropertyEnumeratedValue'):
            raise ValueError("propertyType must be 'IfcPropertySingleValue' or 'IfcPropertyEnumeratedValue'.")

        propObj = {'@type': propertyType, 'name': propertyName}

        if propertyType == 'IfcPropertySingleValue':
            # For single value, quantity and value should be provided
            if propertyQuantity is None:
                raise ValueError("propertyQuantity is required for 'IfcPropertySingleValue'.")
            propObj['nominalValue'] = {'type': propertyQuantity, 'value': propertyValue, 'unit': propertyUnit}
        else:
            # For enumerated value, expect a list of values
            if propertyValues is None:
                propertyValues = []
            if not isinstance(propertyValues, list):
                raise TypeError("propertyValues must be a list for 'IfcPropertyEnumeratedValue'.")
            if propertyQuantity is None:
                raise ValueError("propertyQuantity is required for 'IfcPropertyEnumeratedValue'.")
            propObj['enumeratedValues'] = [
                {'type': propertyQuantity, 'value': v, 'unit': propertyUnit} for v in propertyValues
            ]

        return propObj

    @staticmethod
    def QuantityType(property=None):
        """
        Return the quantity/datatype of an IFC property.

        Args:
            property (dict | None): IFC property dictionary.

        Returns:
            str | list[str] | None:
                - str: the unique quantity type when determinable.
                - list[str]: distinct types for heterogeneous enumerations.
                - None: when the quantity type cannot be determined.

        Raises:
            TypeError: If `property` is not a dict.
        """
        # --- Validate input ---
        if not isinstance(property, dict):
            raise TypeError("prop must be a dict.")

        # --- Helper: unique types preserving order ---
        def unique_in_order(seq):
            seen = set()
            result = []
            for x in seq:
                if x not in seen:
                    seen.add(x)
                    result.append(x)
            return result

        propType = property.get('@type')

        # Single value: try nominalValue.type
        if propType == 'IfcPropertySingleValue':
            nv = property.get('nominalValue') or {}
            qtyType = nv.get('type')
            return qtyType if isinstance(qtyType, str) and qtyType.strip() else None

        # Enumerated value: aggregate item['type']
        if propType == 'IfcPropertyEnumeratedValue':
            enumItems = property.get('enumeratedValues') or []
            types = [item.get('type') for item in enumItems if isinstance(item, dict) and item.get('type')]
            types = unique_in_order(types)
            if not types:
                return None
            return types[0] if len(types) == 1 else types

        # Fallback for unknown @type: attempt nominalValue.type
        nv = property.get('nominalValue')
        if isinstance(nv, dict):
            qtyType = nv.get('type')
            return qtyType if isinstance(qtyType, str) and qtyType.strip() else None

        return None

    @staticmethod
    def SetValue(property=None, propertyValue=None, propertyType='IfcPropertySingleValue', propertyQuantity=None, propertyUnit=None):
        """
        Set/overwrite the value and metadata of an IFC property object.

        Behavior:
          - If propertyType == 'IfcPropertySingleValue': sets/creates 'nominalValue' (type, value).
          - If propertyType == 'IfcPropertyEnumeratedValue': expects propertyValue to be an iterable
            of values; creates 'enumeratedValues' accordingly.

        Args:
            property (dict | None): Property dictionary to update (must have 'name').
            propertyValue (any | list | None): Value for single; list of values for enumerated.
            propertyType (str): 'IfcPropertySingleValue' or 'IfcPropertyEnumeratedValue'.
            propertyQuantity (str | None): Datatype/quantity of the value(s).

        Returns:
            dict: The updated property dictionary (same reference as input).

        Raises:
            TypeError: If prop is not a dict or propertyType is invalid.
            ValueError: If required fields are missing or inconsistent with propertyType.
        """
        if not isinstance(property, dict):
            raise TypeError("prop must be a dict.")
        if 'name' not in property:
            raise ValueError("prop must contain a 'name' key.")
        if not isinstance(propertyType, str) or propertyType not in ('IfcPropertySingleValue', 'IfcPropertyEnumeratedValue'):
            raise ValueError("propertyType must be 'IfcPropertySingleValue' or 'IfcPropertyEnumeratedValue'.")

        # Normalize structure based on desired type
        property['@type'] = propertyType

        if propertyType == 'IfcPropertySingleValue':
            # Ensure quantity provided; value may be None intentionally
            if propertyQuantity is None:
                raise ValueError("propertyQuantity is required for 'IfcPropertySingleValue'.")
            property['nominalValue'] = {'type': propertyQuantity, 'value': propertyValue, 'unit': propertyUnit}
            # Remove enumeratedValues if previously set
            if 'enumeratedValues' in property:
                del property['enumeratedValues']
        else:
            # Enumerated values: propertyValue must be iterable (list/tuple)
            if propertyValue is None:
                propertyValue = []
            if not isinstance(propertyValue, (list, tuple)):
                raise ValueError("propertyValue must be a list/tuple for 'IfcPropertyEnumeratedValue'.")
            if propertyQuantity is None:
                raise ValueError("propertyQuantity is required for 'IfcPropertyEnumeratedValue'.")
            property['enumeratedValues'] = [{'type': propertyQuantity, 'value': v, 'unit':propertyUnit} for v in propertyValue]
            # Remove nominalValue if previously set
            if 'nominalValue' in property:
                del property['nominalValue']

        return property

    @staticmethod
    def Unit(property=None):
        """
        Return the unit of an IFC property, if available.

        Args:
            property (dict | None): IFC property dictionary.

        Returns:
            str | list[str] | None:
                - str: the unique unit when determinable.
                - list[str]: distinct units if enumerated values use multiple units.
                - None: if no unit info is present.

        Raises:
            TypeError: If `property` is not a dict.
        """
        if not isinstance(property, dict):
            raise TypeError("prop must be a dict.")

        def unique_in_order(seq):
            seen, result = set(), []
            for x in seq:
                if x not in seen:
                    seen.add(x)
                    result.append(x)
            return result

        propType = property.get('@type')

        # Single value property
        if propType == 'IfcPropertySingleValue':
            nv = property.get('nominalValue') or {}
            return nv.get('unit')

        # Enumerated value property
        if propType == 'IfcPropertyEnumeratedValue':
            enumItems = property.get('enumeratedValues') or []
            units = [item.get('unit') for item in enumItems if isinstance(item, dict) and 'unit' in item]
            units = unique_in_order([u for u in units if u])
            if not units:
                return None
            return units[0] if len(units) == 1 else units

        # Fallback for unknown type
        nv = property.get('nominalValue')
        if isinstance(nv, dict):
            return nv.get('unit')

        return None

    @staticmethod
    def Value(property=None):
        """
        Retrieve the value(s) from an IFC property.

        Args:
            property (dict | None): Property dictionary.

        Returns:
            any | list | None:
                - If single value: returns the scalar at `property['nominalValue']['value']`.
                - If enumerated: returns a list of values.
                - None if value not present.

        Raises:
            TypeError: If property is not a dict.
        """
        if not isinstance(property, dict):
            raise TypeError("prop must be a dict.")

        # Extract value depending on property type
        pType = property.get('@type')
        if pType == 'IfcPropertySingleValue':
            try:
                return property['nominalValue']['value']
            except Exception:
                return None
        elif pType == 'IfcPropertyEnumeratedValue':
            try:
                return [item.get('value') for item in property.get('enumeratedValues', [])]
            except Exception:
                return None
        else:
            # Unknown type; attempt best-effort extraction
            if isinstance(property.get('nominalValue'), dict):
                return property.get('nominalValue', {}).get('value')
            return None




