"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

EQUIPMENT MODULE
This module defines the Equipment class, which provides the base representation
for creating and modeling equipment objects in the BTWIN toolkit.

© Angelo Massafra, 2025
"""

# Dependencies
from typing import Any, Dict, List, Optional, Union

import pandas as pd


# Functions
class Equipment():

    @staticmethod
    def Constructor(
        equipmentObjectUID: Optional[str] = None,
        equipmentObjectType: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a BTWIN Equipment JSON-LD dictionary.

        Args:
            equipmentObjectUID: Unique identifier for the equipment (non-empty string).
            equipmentObjectType: '@type' of the equipment (e.g., 'brick:Air_Handling_Unit').
            name: Optional human-readable name.

        Returns:
            dict: Equipment object with '@id', '@type', optional 'name', and empty 'relationships'.

        Raises:
            TypeError: If types are invalid.
            ValueError: If 'equipmentObjectUID' or 'equipmentObjectType' is missing/empty.
        """
        # Validate required fields
        if not isinstance(equipmentObjectUID, str) or not equipmentObjectUID.strip():
            raise ValueError("equipmentObjectUID must be a non-empty string.")
        if not isinstance(equipmentObjectType, str) or not equipmentObjectType.strip():
            raise ValueError("equipmentObjectType must be a non-empty string.")
        if name is not None and not isinstance(name, str):
            raise TypeError("name must be a string if provided.")

        # Build base structure
        equipmentObject: Dict[str, Any] = {
            "@id": equipmentObjectUID,
            "@type": equipmentObjectType,
            "relationships": {},  # ready for future links
        }
        if isinstance(name, str) and name.strip():
            equipmentObject["name"] = name

        return equipmentObject

    @staticmethod
    def Name(equipmentObject: Dict[str, Any]) -> Optional[str]:
        """
        Get the equipment name.

        Args:
            equipmentObject: Equipment dict.

        Returns:
            str | None: The 'name' value or None.

        Raises:
            TypeError: If equipmentObject is not a dict.
        """
        if not isinstance(equipmentObject, dict):
            raise TypeError("equipmentObject must be a dict.")
        name = equipmentObject.get("name")
        if name is not None and not isinstance(name, str):
            raise TypeError("equipmentObject['name'] must be a string if present.")
        return name

    @staticmethod
    def Relationships(equipmentObject: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get the relationships dictionary.

        Args:
            equipmentObject: Equipment dict.

        Returns:
            dict: The 'relationships' dict (empty if missing).

        Raises:
            TypeError: If equipmentObject is not a dict.
            KeyError: If 'relationships' exists but is not a dict.
        """
        if not isinstance(equipmentObject, dict):
            raise TypeError("equipmentObject must be a dict.")
        relationships = equipmentObject.get("relationships", {})
        if not isinstance(relationships, dict):
            raise KeyError("equipmentObject['relationships'] must be a dict.")
        return relationships

    @staticmethod
    def SetFeedingRelationship(
        equipmentObject: Dict[str, Any],
        *,
        linkedObject: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        linkedObjectUID: Optional[Union[str, List[str]]] = None,
        linkedObjectType: Optional[Union[str, List[str]]] = None,
        relationshipName: str = "brick:feeds",
        append: bool = True,
        avoidDuplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Set one or more 'brick:feeds' relationships from this equipment to downstream assets.

        Args:
            equipmentObject: Equipment dict to update.
            linkedObject: A single dict or a list of BTWIN/Brick dicts for the linked objects.
            linkedObjectUID: A UID (string) or list of UIDs for the linked objects (used if 'linkedObject' is not provided).
            linkedObjectType: A type (string) or list of types for the linked objects (fallback).
            relationshipName: Predicate to use (default 'brick:feeds').
            append: If True, append; if False, overwrite the list.
            avoidDuplicates: Avoid inserting identical duplicates.

        Returns:
            dict: Updated equipmentObject.

        Raises:
            TypeError / ValueError / KeyError: On invalid inputs.
        """
        # -- normalize inputs to parallel lists --
        def _as_list(x):
            if x is None:
                return []
            return x if isinstance(x, list) else [x]

        linkedObjects = _as_list(linkedObject)
        uids = _as_list(linkedObjectUID)
        types = _as_list(linkedObjectType)

        # if nothing provided
        if not linkedObjects and not uids:
            raise ValueError("Provide at least one linkedObject via 'linkedObject' or 'linkedObjectUID'.")

        # If dict linkedObjects provided, set individually (resolves UID/type from dict)
        if linkedObjects:
            for t in linkedObjects:
                equipmentObject = Equipment.SetRelationship(
                    equipmentObject=equipmentObject,
                    relationshipName=relationshipName,
                    linkedObject=t,
                    append=append,
                    avoidDuplicates=avoidDuplicates,
                )
                # after first insert, subsequent ones should append
                append = True
        # If UID list provided, pair with types (broadcast last type if lengths differ)
        if uids:
            for idx, uid in enumerate(uids):
                ttype = types[idx] if idx < len(types) else (types[-1] if types else None)
                equipmentObject = Equipment.SetRelationship(
                    equipmentObject=equipmentObject,
                    relationshipName=relationshipName,
                    linkedObject=None,
                    linkedObjectUID=uid,
                    linkedObjectType=ttype,
                    append=append,
                    avoidDuplicates=avoidDuplicates,
                )
                append = True

        return equipmentObject

    @staticmethod
    def SetLocationRelationship(
        equipmentObject: Dict[str, Any],
        *,
        linkedObject: Optional[Dict[str, Any]] = None,
        linkedObjectUID: Optional[str] = None,
        linkedObjectType: Optional[str] = None,
        relationshipName: str = "brick:hasLocation",
        append: bool = True,
        avoidDuplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Set a location relationship for the equipment (defaults to 'brick:hasLocation').

        Args:
            equipmentObject: Equipment dict to update.
            linkedObject: Optional location dict; UID/type resolved from ['@id','id','UID'] and ['@type','type','label'].
            linkedObjectUID: Fallback UID if not present in 'linkedObject'.
            linkedObjectType: Fallback type if not present in 'linkedObject' (default 'brick:Location').
            relationshipName: Predicate to use (default 'brick:hasLocation').
            append: If True, append to the list; if False, overwrite it.
            avoidDuplicates: If True, prevents inserting identical {'@id','@type'} pairs.

        Returns:
            dict: Updated equipmentObject.

        Raises:
            TypeError / ValueError / KeyError: On invalid inputs.
        """
        return Equipment.SetRelationship(
            equipmentObject=equipmentObject,
            relationshipName=relationshipName,
            linkedObject=linkedObject,
            linkedObjectUID=linkedObjectUID,
            linkedObjectType=linkedObjectType,
            append=append,
            avoidDuplicates=avoidDuplicates,
        )

    @staticmethod
    def SetPartOfRelationship(
        equipmentObject: Dict[str, Any],
        *,
        linkedObject: Optional[Dict[str, Any]] = None,
        linkedObjectUID: Optional[str] = None,
        linkedObjectType: Optional[str] = "brick:System",
        relationshipName: str = "brick:isPartOf",
        append: bool = True,
        avoidDuplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Set a membership relationship from this equipment to a parent system (default 'brick:isPartOf').

        Args:
            equipmentObject: Equipment dict to update.
            linkedObject: Optional system dict; UID/type resolved from ['@id','id','UID'] and ['@type','type','label'].
            linkedObjectUID: Fallback UID if not present in 'linkedObject'.
            linkedObjectType: Fallback type if not present (default 'brick:System').
            relationshipName: Predicate to use (default 'brick:isPartOf').
            append: If True, append to the list; if False, overwrite it.
            avoidDuplicates: If True, prevents identical {'@id','@type'} duplicates.

        Returns:
            dict: Updated equipmentObject.

        Raises:
            TypeError / ValueError / KeyError: On invalid inputs.
        """
        return Equipment.SetRelationship(
            equipmentObject=equipmentObject,
            relationshipName=relationshipName,
            linkedObject=linkedObject,
            linkedObjectUID=linkedObjectUID,
            linkedObjectType=linkedObjectType,
            append=append,
            avoidDuplicates=avoidDuplicates,
        )

    @staticmethod
    def SetRelationship(
        equipmentObject: Dict[str, Any],
        relationshipName: str,
        linkedObject: Optional[Dict[str, Any]] = None,
        linkedObjectUID: Optional[str] = None,
        linkedObjectType: Optional[str] = None,
        *,
        append: bool = True,
        avoidDuplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Create or append a relationship on an Equipment JSON-LD object.

        Args:
            equipmentObject: Equipment dict to update. Creates 'relationships' if missing.
            relationshipName: Predicate (e.g., 'brick:isPartOf', 'eko:hasAssociatedObject').
            linkedObject: Optional related object. UID from ['@id','id','UID']; type from ['@type','type','label'].
            linkedObjectUID: Fallback UID if not resolvable from 'linkedObject'.
            linkedObjectType: Fallback type if not resolvable from 'linkedObject'.
            append: If True, append to existing list; if False, overwrite it.
            avoidDuplicates: If True, prevent inserting identical {'@id','@type'} pairs.

        Returns:
            dict: The updated equipmentObject.

        Raises:
            TypeError: If inputs are invalid types.
            ValueError: If relationship name/UID/type are empty.
            KeyError: If 'relationships' exists but is not a dict.
        """
        # Validate container
        if not isinstance(equipmentObject, dict):
            raise TypeError("equipmentObject must be a dict.")
        if "relationships" not in equipmentObject:
            equipmentObject["relationships"] = {}
        if not isinstance(equipmentObject["relationships"], dict):
            raise KeyError("equipmentObject['relationships'] must be a dict.")

        # Validate relation name
        if not isinstance(relationshipName, str) or not relationshipName.strip():
            raise ValueError("relationshipName must be a non-empty string.")

        # Resolve UID/type from linkedObject or fallbacks
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

        # Insert/append into relationship list
        current = equipmentObject["relationships"].get(relationshipName)
        if not append or not isinstance(current, list):
            equipmentObject["relationships"][relationshipName] = [payload]
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

        return equipmentObject

    @staticmethod
    def Type(equipmentObject: Dict[str, Any]) -> Optional[str]:
        """
        Get the equipment type.

        Args:
            equipmentObject: Equipment dict.

        Returns:
            str | None: The '@type' value or None.

        Raises:
            TypeError: If equipmentObject is not a dict.
        """
        if not isinstance(equipmentObject, dict):
            raise TypeError("equipmentObject must be a dict.")
        t = equipmentObject.get("@type")
        if t is not None and not isinstance(t, str):
            raise TypeError("equipmentObject['@type'] must be a string if present.")
        return t

    @staticmethod
    def Types() -> list[str]:
        """
        Return a list of all common Brick equipment classes.

        Includes mechanical, HVAC, electrical, lighting, safety, and other equipment types
        from the Brick ontology (https://brickschema.org/ontology/).

        Returns:
            list[str]: List of Brick equipment type IRIs (prefix 'brick:').
        """
        brickEquipmentTypes = [
            # --- Generic ---
            "brick:Equipment",
            "brick:HVAC_Equipment",
            "brick:Electrical_Equipment",
            "brick:Lighting_Equipment",
            "brick:Mechanical_Equipment",
            "brick:Plumbing_Equipment",
            "brick:Fire_Safety_Equipment",

            # --- HVAC Major Equipment ---
            "brick:Air_Handling_Unit",
            "brick:Fan_Coil_Unit",
            "brick:Variable_Air_Volume_Box",
            "brick:Constant_Air_Volume_Box",
            "brick:Chiller",
            "brick:Boiler",
            "brick:Heat_Exchanger",
            "brick:Cooling_Tower",
            "brick:Heat_Pump",
            "brick:Air_Conditioning_Unit",
            "brick:Dehumidifier",
            "brick:Humidifier",
            "brick:Condensing_Unit",
            "brick:Reheat_Coil",
            "brick:Cooling_Coil",
            "brick:Heating_Coil",
            "brick:Compressor",
            "brick:Economizer",
            "brick:Energy_Recovery_Ventilator",
            "brick:Air_Filter",
            "brick:Air_Damper",

            # --- HVAC Distribution ---
            "brick:Fan",
            "brick:Supply_Fan",
            "brick:Return_Fan",
            "brick:Exhaust_Fan",
            "brick:Relief_Fan",
            "brick:Pump",
            "brick:Chilled_Water_Pump",
            "brick:Condenser_Water_Pump",
            "brick:Hot_Water_Pump",
            "brick:Booster_Pump",
            "brick:Circulation_Pump",
            "brick:Variable_Speed_Pump",
            "brick:Valve",
            "brick:Control_Valve",
            "brick:Mixing_Valve",
            "brick:Isolation_Valve",

            # --- Energy / Meters ---
            "brick:Meter",
            "brick:Electric_Meter",
            "brick:Thermal_Meter",
            "brick:Water_Meter",
            "brick:Gas_Meter",
            "brick:Energy_Meter",
            "brick:BTU_Meter",
            "brick:Power_Meter",
            "brick:Current_Transformer",
            "brick:Voltage_Transformer",

            # --- Electrical Equipment ---
            "brick:Electrical_Panel",
            "brick:Distribution_Board",
            "brick:Switchboard",
            "brick:Transformer",
            "brick:Inverter",
            "brick:Generator",
            "brick:UPS",
            "brick:Battery",
            "brick:Solar_Panel",
            "brick:Photovoltaic_System",

            # --- Lighting Equipment ---
            "brick:Luminaire",
            "brick:Light_Fixture",
            "brick:Lighting_Controller",
            "brick:Lighting_Panel",
            "brick:Lighting_System",
            "brick:Occupancy_Sensor",
            "brick:Daylight_Sensor",

            # --- Domestic Hot Water / Plumbing ---
            "brick:Water_Heater",
            "brick:Hot_Water_Tank",
            "brick:Expansion_Tank",
            "brick:Water_Softener",
            "brick:Heat_Recovery_Unit",
            "brick:Circulator",
            "brick:Pump_Station",

            # --- Fire Safety / Security ---
            "brick:Smoke_Detector",
            "brick:Fire_Alarm_Panel",
            "brick:Fire_Sprinkler_System",
            "brick:Fire_Pump",
            "brick:Emergency_Lighting_System",
            "brick:Security_Camera",
            "brick:Access_Control_Panel",

            # --- ICT / Miscellaneous ---
            "brick:Network_Switch",
            "brick:Server",
            "brick:Gateway",
            "brick:Controller",
            "brick:Building_Automation_Controller",
            "brick:Thermostat",
            "brick:Sensor_Module",
            "brick:Actuator_Module",
        ]

        return brickEquipmentTypes

    @staticmethod
    def UID(equipmentObject: Dict[str, Any]) -> str:
        """
        Get the equipment unique identifier.

        Args:
            equipmentObject: Equipment dict.

        Returns:
            str: The '@id' value.

        Raises:
            TypeError: If equipmentObject is not a dict.
            KeyError: If '@id' is missing.
            ValueError: If '@id' is empty.
        """
        if not isinstance(equipmentObject, dict):
            raise TypeError("equipmentObject must be a dict.")
        if "@id" not in equipmentObject:
            raise KeyError("equipmentObject is missing '@id'.")
        uid = equipmentObject["@id"]
        if not isinstance(uid, str) or not uid.strip():
            raise ValueError("equipmentObject['@id'] must be a non-empty string.")
        return uid

class Inventory:

    @staticmethod
    def Template(savePath: Optional[str] = None) -> pd.DataFrame:
        """
        Build a Brick-compatible equipment inventory template.

        The DataFrame has the following columns:
            - 'id'                      : unique equipment identifier
            - 'name'                    : human-friendly name/label
            - 'type'                    : Brick class (e.g., 'brick:Air_Handling_Unit')
            - 'brick:isPartOf System'   : system identifier/name this asset belongs to
            - 'brick:hasLocation'       : location identifier/name

        Args:
            savePath: Optional target filepath to save an Excel (.xlsx) copy of the template.
                      If provided without extension, '.xlsx' is appended.

        Returns:
            pd.DataFrame: The generated template.

        Raises:
            ValueError: If savePath is a non-empty string but invalid.
            OSError: If saving to Excel fails.
            ImportError: If pandas/openpyxl is missing when saving.
        """
        # --- Define columns (fixed order) ---
        columns = [
            "id",
            "name",
            "type",
            "brick:isPartOf System",
            "brick:hasLocation",
        ]

        # --- Sample rows (edit as needed) ---
        data = [
            ["ahu1",   "AHU (below ceiling)", "brick:Air_Handling_Unit",     "heatingSystem", "mySpace1"],
            ["ahu2",   "AHU (below ceiling)", "brick:Air_Handling_Unit",     "heatingSystem", "mySpace2"],
            ["fc1",    "Fan coil",            "brick:Fan_Coil_Unit",         "heatingSystem", "mySpace1"],
            ["hp1",    "Heat pump",           "brick:Packaged_Heat_Pump",    "heatingSystem", "mySpace1"],
            ["hwb1",   "Hot water boiler",    "brick:Electric_Boiler",       "dhwSystem",     "mySpace2"],
        ]

        # --- Build DataFrame ---
        df = pd.DataFrame(data, columns=columns)

        # --- Save to Excel if requested ---
        if savePath is not None:
            if not isinstance(savePath, str) or not savePath.strip():
                raise ValueError("savePath must be a valid non-empty string if provided.")
            path = savePath if savePath.lower().endswith(".xlsx") else f"{savePath}.xlsx"
            try:
                # Note: requires 'openpyxl' installed
                df.to_excel(path, index=False)
            except Exception as exc:
                raise OSError(f"Failed to save template to '{path}'.") from exc

        return df

    @staticmethod
    def ToJSONLD(
        xlsxPath: str,
        *,
        buildingUID: Optional[str] = None,
        sheetNames: Optional[Union[str, int, List[Union[str, int]]]] = None,
        createSystems: bool = False,
        systemType: str = "brick:System",
        locationType: str = "bot:Space",
        defaultTypeIfMissing: Optional[str] = None,
        columnMap: Optional[Dict[str, str]] = None,
        dropEmptyId: bool = True,
        stripWhitespace: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Convert an Inventory Excel file into a list of JSON-LD equipment objects
        (and optional System nodes). Each equipment is built via Equipment.Constructor,
        and relationships are assigned via Equipment.SetRelationship. If `buildingUID`
        is provided, the function adds a `brick:feeds` relationship from each equipment
        to the Building (`bot:Building`).

        Expected columns (can be remapped via `columnMap`):
            - id
            - name
            - type
            - 'brick:isPartOf System'
            - 'brick:hasLocation'

        Args:
            xlsxPath: Path to the Excel file (.xlsx).
            buildingUID: If provided, attach `brick:feeds` → {'@id': buildingUID, '@type': 'bot:Building'} to each equipment.
            sheetNames: Name(s) or index(es) of sheets to read; None = all sheets.
            createSystems: If True, create `brick:System` nodes from unique 'isPartOf' values.
            systemType: Class for created systems (default 'brick:System').
            locationType: Class for locations (default 'brick:Location').
            defaultTypeIfMissing: Default equipment type if missing in the sheet.
            columnMap: Optional mapping Excel columns → logical keys:
                       {
                         "id": "id",
                         "name": "name",
                         "type": "type",
                         "isPartOf": "brick:isPartOf System",
                         "hasLocation": "brick:hasLocation",
                       }
            dropEmptyId: Skip rows with missing/blank id.
            stripWhitespace: Strip whitespace from string cells.

        Returns:
            list[dict]: JSON-LD objects (equipment + optional systems).

        Raises:
            FileNotFoundError: If the Excel file does not exist.
            ValueError: If required columns are missing or rows invalid.
            ImportError: If pandas/openpyxl not available.
        """
        # --- Column mapping (defaults) ---
        defaultColumnMap = {
            "id": "id",
            "name": "name",
            "type": "type",
            "isPartOf": "brick:isPartOf System",
            "hasLocation": "brick:hasLocation",
        }
        colMap = {**defaultColumnMap, **(columnMap or {})}

        # --- Helpers ---
        def norm_str(x: Any) -> Optional[str]:
            if x is None:
                return None
            if isinstance(x, str):
                return x.strip() if stripWhitespace else x
            return str(x).strip() if stripWhitespace else str(x)

        # --- Read sheets ---
        try:
            if sheetNames is None:
                sheets = pd.read_excel(xlsxPath, sheet_name=None)
            else:
                sheets = pd.read_excel(xlsxPath, sheet_name=sheetNames)
                if not isinstance(sheets, dict):
                    sheets = {str(sheetNames): sheets}
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise ValueError(f"Failed to read Excel: {exc}")

        jsonldObjects: List[Dict[str, Any]] = []
        systemIds: set[str] = set()

        # --- Process each sheet ---
        for sheetName, df in sheets.items():
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue

            # Ensure essential column 'id'
            if colMap["id"] not in df.columns:
                raise ValueError(f"Sheet '{sheetName}' is missing column: {colMap['id']}")

            for _, row in df.iterrows():
                equipId = norm_str(row.get(colMap["id"]))
                if (equipId is None or equipId == "") and dropEmptyId:
                    continue

                rawType = row.get(colMap["type"]) if colMap["type"] in df.columns else None
                equipType = norm_str(rawType)
                if not equipType:
                    if defaultTypeIfMissing:
                        equipType = defaultTypeIfMissing
                    else:
                        raise ValueError(f"Row id='{equipId}' has no type and no defaultTypeIfMissing provided.")

                equipName = norm_str(row.get(colMap["name"])) if colMap["name"] in df.columns else None
                systemVal = norm_str(row.get(colMap["isPartOf"])) if colMap["isPartOf"] in df.columns else None
                locationVal = norm_str(row.get(colMap["hasLocation"])) if colMap["hasLocation"] in df.columns else None

                # --- Build equipment via Constructor ---
                equipObj = Equipment.Constructor(
                    equipmentObjectUID=equipId,
                    equipmentObjectType=equipType,
                    name=equipName,
                )

                # --- brick:isPartOf (System) ---
                if systemVal:
                    Equipment.SetRelationship(
                        equipmentObject=equipObj,
                        relationshipName="brick:isPartOf",
                        linkedObjectUID=systemVal,
                        linkedObjectType=systemType,
                        append=True,
                        avoidDuplicates=True,
                    )
                    systemIds.add(systemVal)

                # --- brick:hasLocation (Location) ---
                if locationVal:
                    Equipment.SetRelationship(
                        equipmentObject=equipObj,
                        relationshipName="brick:hasLocation",
                        linkedObjectUID=locationVal,
                        linkedObjectType=locationType,
                        append=True,
                        avoidDuplicates=True,
                    )
                jsonldObjects.append(equipObj)

        # --- Optionally, create unique System nodes ---
        if createSystems and systemIds:
            for sid in sorted(systemIds):
                sysObj = {
                    "@id": sid,
                    "@type": systemType,
                    "name": sid,
                    "relationships": {},
                }
                if isinstance(buildingUID, str) and buildingUID.strip():
                    sysObj = Equipment.SetRelationship(
                            equipmentObject=sysObj,
                            relationshipName="brick:feeds",
                            linkedObjectUID=buildingUID,
                            linkedObjectType="bot:Building",
                            append=True,
                            avoidDuplicates=True,
                        )
                jsonldObjects.append(sysObj)

        return jsonldObjects
