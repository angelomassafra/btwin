"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

POINT MODULE
This module defines the functions to model and query points and timeseries via the BTWIN toolkit.

© Angelo Massafra, 2025
"""

# Dependencies
import os
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Union

import pandas as pd


# Functions
class Point():

    @staticmethod
    def Constructor(
        pointUID: Optional[str] = None,
        pointType: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a BTWIN Point JSON-LD dictionary.

        Args:
            pointUID: Unique identifier for the Point (non-empty string required).
            pointType: Type of the Point (e.g., 'btwin:Sensor', 'btwin:MeasurementPoint').
            name: Optional human-readable name.

        Returns:
            dict: Point object with '@id', '@type', optional 'name', and an empty 'relationships' dict.

        Raises:
            TypeError: If arguments are of invalid types.
            ValueError: If 'pointUID' or 'pointType' are missing or empty.
        """
        # Validate UID and type
        if not isinstance(pointUID, str) or not pointUID.strip():
            raise ValueError("pointUID must be a non-empty string.")
        if not isinstance(pointType, str) or not pointType.strip():
            raise ValueError("pointType must be a non-empty string.")
        if name is not None and not isinstance(name, str):
            raise TypeError("name must be a string if provided.")

        # Build base structure
        pointObject: Dict[str, Any] = {
            "@id": pointUID,
            "@type": pointType,
            "relationships": {},
        }
        if isinstance(name, str) and name.strip():
            pointObject["name"] = name

        return pointObject

    @staticmethod
    def Name(pointObject: Dict[str, Any]) -> Optional[str]:
        """
        Retrieve the human-readable name of a Point.

        Args:
            pointObject: The BTWIN Point dictionary.

        Returns:
            str | None: The Point name if available, otherwise None.

        Raises:
            TypeError: If pointObject is not a dict.
        """
        if not isinstance(pointObject, dict):
            raise TypeError("pointObject must be a dict.")
        name = pointObject.get("name")
        if name is not None and not isinstance(name, str):
            raise TypeError("pointObject['name'] must be a string if present.")
        return name

    @staticmethod
    def Relationships(pointObject: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieve the relationships dictionary of a Point.

        Args:
            pointObject: The BTWIN Point dictionary.

        Returns:
            dict: The relationships dictionary (empty if missing).

        Raises:
            TypeError: If pointObject is not a dict.
            KeyError: If 'relationships' exists but is not a dict.
        """
        if not isinstance(pointObject, dict):
            raise TypeError("pointObject must be a dict.")
        relationships = pointObject.get("relationships", {})
        if not isinstance(relationships, dict):
            raise KeyError("pointObject['relationships'] must be a dict.")
        return relationships

    @staticmethod
    def SetRelationship(
        pointObject: Dict[str, Any],
        relationshipName: str,
        linkedObject: Optional[Dict[str, Any]] = None,
        linkedObjectUID: Optional[str] = None,
        linkedObjectType: Optional[str] = None,
        *,
        append: bool = True,
        avoidDuplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Create or append a relationship on a Point JSON-LD object.

        Args:
            pointObject: Point dictionary to update. If 'relationships' is missing, it will be created.
            relationshipName: Predicate (e.g., 'btwin:hasMeasurement'). Must be a non-empty string.
            linkedObject: Optional related object dictionary.
                          UID resolved from ['@id','id','UID']; type from ['@type','type','label'].
            linkedObjectUID: Fallback UID if not present in 'linkedObject'.
            linkedObjectType: Fallback type if not present in 'linkedObject'.
            append: If True, appends to existing list; if False, overwrites it.
            avoidDuplicates: If True, prevents inserting identical {'@id','@type'} pairs.

        Returns:
            dict: The updated pointObject.

        Raises:
            TypeError: If input types are invalid.
            ValueError: If required parameters are missing or invalid.
        """
        # Validate input
        if not isinstance(pointObject, dict):
            raise TypeError("pointObject must be a dict.")
        if not isinstance(relationshipName, str) or not relationshipName.strip():
            raise ValueError("relationshipName must be a non-empty string.")

        # Ensure relationships container
        if "relationships" not in pointObject:
            pointObject["relationships"] = {}
        if not isinstance(pointObject["relationships"], dict):
            raise KeyError("pointObject['relationships'] must be a dict.")

        # Resolve UID and type
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
            raise ValueError("A related element UID is required.")
        if not isinstance(resolvedType, str) or not resolvedType.strip():
            raise ValueError("A related element type is required.")

        payload = {"@id": resolvedUID, "@type": resolvedType}

        # Insert or append relationship
        current = pointObject["relationships"].get(relationshipName)
        if not append or not isinstance(current, list):
            pointObject["relationships"][relationshipName] = [payload]
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

        return pointObject

    @staticmethod
    def Types() -> list[str]:
        """
        Return a list of Brick ontology Point types (sensor and related point classes).

        This includes core Brick types such as:
        - Sensor points (e.g., Temperature_Sensor, CO2_Sensor)
        - Setpoints, Commands, and Status points
        - Generic Brick:Point subclasses (BTU_Meter, Flow_Sensor, etc.)

        Returns:
            list[str]: A list of Brick point type IRIs (as simplified local names).

        Reference:
            Brick Schema — https://brickschema.org/ontology/
        """
        brickPointTypes = [
            # --- Generic ---
            "brick:Point",
            "brick:Sensor",
            "brick:Command",
            "brick:Setpoint",
            "brick:Status",
            "brick:Alarm",

            # --- Temperature ---
            "brick:Temperature_Sensor",
            "brick:Temperature_Setpoint",
            "brick:Temperature_Command",
            "brick:Temperature_Status",

            # --- Air Quality ---
            "brick:CO2_Sensor",
            "brick:CO_Sensor",
            "brick:VOC_Sensor",
            "brick:PM2.5_Sensor",
            "brick:PM10_Sensor",
            "brick:Humidity_Sensor",

            # --- Energy & Power ---
            "brick:Power_Sensor",
            "brick:Energy_Sensor",
            "brick:Voltage_Sensor",
            "brick:Current_Sensor",
            "brick:Frequency_Sensor",
            "brick:BTU_Meter",
            "brick:Heat_Meter",

            # --- Flow & Pressure ---
            "brick:Flow_Sensor",
            "brick:Pressure_Sensor",
            "brick:Air_Flow_Sensor",
            "brick:Water_Flow_Sensor",
            "brick:Static_Pressure_Sensor",
            "brick:Differential_Pressure_Sensor",

            # --- HVAC control ---
            "brick:Damper_Position_Sensor",
            "brick:Valve_Position_Sensor",
            "brick:Fan_Status",
            "brick:Pump_Status",
            "brick:Damper_Command",
            "brick:Valve_Command",
            "brick:Fan_Command",
            "brick:Pump_Command",

            # --- Lighting ---
            "brick:Luminance_Sensor",
            "brick:Illuminance_Sensor",
            "brick:Light_Status",
            "brick:Light_Command",

            # --- Occupancy & Environment ---
            "brick:Occupancy_Sensor",
            "brick:Motion_Sensor",
            "brick:Presence_Sensor",
            "brick:Sound_Sensor",

            # --- Thermal Comfort & Environment ---
            "brick:Air_Quality_Sensor",
            "brick:Enthalpy_Sensor",
            "brick:Dewpoint_Sensor",
            "brick:Mean_Radiant_Temperature_Sensor",

            # --- Miscellaneous ---
            "brick:Level_Sensor",
            "brick:Position_Sensor",
            "brick:Speed_Sensor",
            "brick:Vibration_Sensor",
            "brick:Torque_Sensor",
        ]

        return brickPointTypes

    @staticmethod
    def UID(pointObject: Dict[str, Any]) -> str:
        """
        Retrieve the unique identifier (UID) of a Point.

        Args:
            pointObject: The BTWIN Point dictionary.

        Returns:
            str: The UID of the Point.

        Raises:
            TypeError: If pointObject is not a dict.
            KeyError: If '@id' is missing.
            ValueError: If '@id' is empty.
        """
        if not isinstance(pointObject, dict):
            raise TypeError("pointObject must be a dict.")
        if "@id" not in pointObject:
            raise KeyError("pointObject is missing '@id'.")
        uid = pointObject["@id"]
        if not isinstance(uid, str) or not uid.strip():
            raise ValueError("pointObject['@id'] must be a non-empty string.")
        return uid

class Observation():

    @staticmethod
    def SQLiteByDF(
        df: pd.DataFrame,
        sqlitePath: str,
        tableName: str,
        *,
        ifExists: str = "fail",           # 'fail' | 'replace' | 'append'
        index: bool = False,
        indexLabel: Optional[str] = None,
        dtype: Optional[Dict[str, str]] = None,  # explicit SQLite dtypes per column
        chunksize: Optional[int] = 5000,
        primaryKey: Optional[Union[str, List[str]]] = None,
        naRep: Optional[str] = None,      # represent NaN/NaT as string (only when using fast path)
        coerceDatetimeToISO: bool = True, # convert datetime-like cols to ISO strings
    ) -> str:
        """
        Write a pandas DataFrame into a SQLite database table.

        Args:
            df: Source DataFrame to persist.
            sqlitePath: Path to the SQLite database file (created if it doesn't exist).
            tableName: Destination table name.
            ifExists: What to do if the table already exists: 'fail', 'replace', or 'append'.
            index: If True, write DataFrame index as a column.
            indexLabel: Column name for the index (used when index=True).
            dtype: Optional explicit SQLite types per column (e.g., {'col': 'TEXT'}).
            chunksize: Insert in chunks to limit memory usage (None = single batch).
            primaryKey: Optional column name (or list of columns) to set as PRIMARY KEY.
                        When provided, a custom CREATE TABLE + INSERT path is used.
            naRep: Optional string to replace missing values for TEXT columns on the custom path.
            coerceDatetimeToISO: If True, convert datetime-like columns to ISO 8601 strings before insert.

        Returns:
            str: The absolute path to the SQLite database file.

        Raises:
            TypeError: If inputs have invalid types.
            ValueError: If parameters are invalid (e.g., empty tableName, bad ifExists).
            ImportError: If pandas is not installed.
            sqlite3.DatabaseError: If a DB error occurs.
        """
        # --- Validate inputs ---
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame.")
        if not isinstance(sqlitePath, str) or not sqlitePath.strip():
            raise ValueError("sqlitePath must be a non-empty string path.")
        if not isinstance(tableName, str) or not tableName.strip():
            raise ValueError("tableName must be a non-empty string.")
        if ifExists not in {"fail", "replace", "append"}:
            raise ValueError("ifExists must be one of: 'fail', 'replace', 'append'.")
        if primaryKey is not None and not isinstance(primaryKey, (str, list, tuple)):
            raise TypeError("primaryKey must be None, str, list, or tuple.")
        if dtype is not None and not isinstance(dtype, dict):
            raise TypeError("dtype must be a dict mapping column names to SQLite types.")

        # --- Prepare a working copy (optional conversions) ---
        workDf = df.copy()

        # Convert datetimes to ISO strings if requested
        if coerceDatetimeToISO:
            for col in workDf.columns:
                if pd.api.types.is_datetime64_any_dtype(workDf[col]) or pd.api.types.is_datetime64tz_dtype(workDf[col]):
                    workDf[col] = workDf[col].dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ") \
                        if pd.api.types.is_datetime64tz_dtype(workDf[col]) \
                        else workDf[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Replace NaN for TEXT columns if naRep is provided (only applied on custom path below)
        # (Pandas to_sql handles NaN as NULL by default; we keep that behavior unless naRep is set)
        def _apply_na_rep(frame: pd.DataFrame) -> pd.DataFrame:
            if naRep is None:
                return frame
            out = frame.copy()
            for col in out.columns:
                if out[col].dtype == object:
                    out[col] = out[col].where(~out[col].isna(), naRep)
            return out

        # --- Helpers for the custom path (primary key or explicit dtype) ---
        def _infer_sqlite_type(series: pd.Series) -> str:
            if pd.api.types.is_integer_dtype(series):
                return "INTEGER"
            if pd.api.types.is_float_dtype(series):
                return "REAL"
            if pd.api.types.is_bool_dtype(series):
                return "INTEGER"
            # We already coerced datetimes to strings above if requested
            return "TEXT"

        def _create_table_with_schema(cur: sqlite3.Cursor, cols: Iterable[str], pk: Optional[Union[str, List[str]]]) -> None:
            # Build column definitions
            colDefs = []
            for c in cols:
                colType = dtype.get(c) if dtype and c in dtype else _infer_sqlite_type(workDf[c])
                colDefs.append(f'"{c}" {colType}')
            pkClause = ""
            if pk:
                if isinstance(pk, str):
                    pkClause = f", PRIMARY KEY(\"{pk}\")"
                else:
                    colsJoined = ", ".join([f'"{c}"' for c in pk])
                    pkClause = f", PRIMARY KEY({colsJoined})"
            createSql = f'CREATE TABLE "{tableName}" ({", ".join(colDefs)}{pkClause});'
            cur.execute(createSql)

        def _chunked_tuples(frame: pd.DataFrame, size: int):
            """Yield batches of row tuples of given size (memory friendly)."""
            batch = []
            for row in frame.itertuples(index=False, name=None):
                batch.append(row)
                if len(batch) >= size:
                    yield batch
                    batch = []
            if batch:
                yield batch

        # --- Decide path: fast (pandas.to_sql) or custom (for PRIMARY KEY) ---
        absPath = os.path.abspath(sqlitePath)
        os.makedirs(os.path.dirname(absPath), exist_ok=True) if os.path.dirname(absPath) else None

        conn = sqlite3.connect(absPath)
        try:
            cur = conn.cursor()

            # Handle ifExists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (tableName,))
            exists = cur.fetchone() is not None
            if exists:
                if ifExists == "fail":
                    raise ValueError(f"Table '{tableName}' already exists (ifExists='fail').")
                elif ifExists == "replace":
                    cur.execute(f'DROP TABLE "{tableName}";')
                    conn.commit()

            # When no PK specified and no explicit dtype/naRep need, defer to pandas.to_sql (fast path)
            useCustom = primaryKey is not None

            if not useCustom:
                # pandas handles dtype (SQLAlchemy types are not used with sqlite3 driver here),
                # so we leave dtype to None and let sqlite decide types dynamically.
                workDf.to_sql(
                    tableName,
                    conn,
                    if_exists=("append" if exists and ifExists == "append" else ("replace" if exists and ifExists == "replace" else "fail")),
                    index=index,
                    index_label=indexLabel,
                    chunksize=chunksize,
                )
                conn.commit()
                return absPath

            # --- Custom path: create table with explicit schema + insert ---
            # Prepare frame to insert (apply index if requested)
            insertDf = workDf
            if index:
                idxName = indexLabel or "index"
                insertDf = workDf.reset_index().rename(columns={"index": idxName})

            # Replace NaN in TEXT columns if requested
            insertDf = _apply_na_rep(insertDf)

            # Create table with schema (if not exists or after drop on replace)
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (tableName,))
            exists = cur.fetchone() is not None
            if not exists:
                _create_table_with_schema(cur, insertDf.columns, primaryKey)
            elif ifExists == "replace":
                # already dropped above and will be recreated here
                _create_table_with_schema(cur, insertDf.columns, primaryKey)
            elif ifExists == "append":
                # assume compatible schema
                pass

            # Build INSERT statement
            placeholders = ", ".join(["?"] * len(insertDf.columns))
            colList = ", ".join([f'"{c}"' for c in insertDf.columns])
            insertSql = f'INSERT INTO "{tableName}" ({colList}) VALUES ({placeholders});'

            # Execute in chunks
            iterable = (
                insertDf.itertuples(index=False, name=None)
                if chunksize is None
                else _chunked_tuples(insertDf, chunksize)
            )
            if chunksize is None:
                cur.executemany(insertSql, iterable)  # type: ignore[arg-type]
            else:
                for batch in iterable:  # type: ignore[assignment]
                    cur.executemany(insertSql, batch)
            conn.commit()
            return absPath
        finally:
            conn.close()

    @staticmethod
    def SQLiteByXLSX(
        xlsxPath: str,
        sqlitePath: str,
        tableName: str,
        *,
        sheetName: Union[str, int] = 0,
        header: Union[int, List[int], None] = 0,
        useCols: Optional[Union[str, List[int], List[str]]] = None,
        parseDates: Optional[List[str]] = None,
        naValues: Optional[Union[str, List[str]]] = None,
        dtype: Optional[Dict[str, Any]] = None,  # pandas dtype on read
        engine: Optional[str] = None,            # e.g., "openpyxl"
        # DFtoSQLITE passthrough:
        ifExists: str = "fail",
        index: bool = False,
        indexLabel: Optional[str] = None,
        sqlDtype: Optional[Dict[str, str]] = None,
        chunksize: Optional[int] = 5000,
        primaryKey: Optional[Union[str, List[str]]] = None,
        naRep: Optional[str] = None,
        coerceDatetimeToISO: bool = True,
    ) -> str:
        """
        Read an Excel worksheet and write it into a SQLite table.

        Args:
            xlsxPath: Path to the Excel file (.xlsx).
            sqlitePath: Path to the SQLite database file (created if missing).
            tableName: Destination table name.
            sheetName: Excel sheet name or index (default 0 = first sheet).
            header: Row (0-indexed) to use as column names, or list of rows; None = no header.
            useCols: Subset of columns to read (e.g., 'A:D' or list of names/indices).
            parseDates: List of column names to parse as datetimes.
            naValues: Additional strings to consider as NA/NaN on read.
            dtype: Optional pandas dtype mapping during read_excel.
            engine: Excel engine (e.g., 'openpyxl'); if None, pandas chooses.
            ifExists: Passed through to Observation.SQLiteByDF.
            index: Passed through to Observation.SQLiteByDF.
            indexLabel: Passed through to Observation.SQLiteByDF.
            sqlDtype: Passed through to Observation.SQLiteByDF (as its 'dtype').
            chunksize: Passed through to Observation.SQLiteByDF.
            primaryKey: Passed through to Observation.SQLiteByDF.
            naRep: Passed through to Observation.SQLiteByDF.
            coerceDatetimeToISO: Passed through to Observation.SQLiteByDF.

        Returns:
            str: The absolute path to the SQLite database file.

        Raises:
            FileNotFoundError: If the Excel file is missing.
            ImportError: If pandas/openpyxl is missing.
            ValueError / sqlite3.DatabaseError: On invalid params or DB errors.
        """
        if not isinstance(xlsxPath, str) or not xlsxPath.strip():
            raise ValueError("xlsxPath must be a non-empty string.")
        if not os.path.exists(xlsxPath):
            raise FileNotFoundError(f"Excel file not found: {xlsxPath}")

        # Read Excel into DataFrame
        try:
            df = pd.read_excel(
                xlsxPath,
                sheet_name=sheetName,
                header=header,
                usecols=useCols,
                parse_dates=parseDates,
                na_values=naValues,
                dtype=dtype,
                engine=engine,
            )
        except ImportError as exc:
            raise ImportError("Reading .xlsx requires pandas and an Excel engine (e.g., 'openpyxl').") from exc

        # Push to SQLite (reuse DFtoSQLITE)
        return Observation.SQLiteByDF(
            df=df,
            sqlitePath=sqlitePath,
            tableName=tableName,
            ifExists=ifExists,
            index=index,
            indexLabel=indexLabel,
            dtype=sqlDtype,
            chunksize=chunksize,
            primaryKey=primaryKey,
            naRep=naRep,
            coerceDatetimeToISO=coerceDatetimeToISO,
        )

    @staticmethod
    def SQLiteQuery(
        sqlitePath: str,
        tableName: str,
        *,
        sensor: Optional[Union[str, List[str]]] = None,
        observedProperty: Optional[Union[str, List[str]]] = None,
        unit: Optional[Union[str, List[str]]] = None,
        aggregate: Optional[str] = None,       # "min", "max", "mean", "sum", "count", or None
        groupByTime: Optional[str] = None,     # "hour", "day", "month" — optional time grouping
        startTime: Optional[str] = None,       # ISO 8601 start time filter
        endTime: Optional[str] = None,         # ISO 8601 end time filter
        limit: Optional[int] = None,           # limit number of results
    ) -> pd.DataFrame:
        """
        Query and optionally aggregate data from a SQLite table containing SOSA-like observations.

        The table is expected to have columns:
            ['sosa:madeBySensor', 'sosa:ObservedProperty', 'Unit', 'Value', 'Timestamp']

        Args:
            sqlitePath: Path to the SQLite database.
            tableName: Table name (must exist in database).
            sensor: Filter by one or multiple sensors (string or list of strings).
            observedProperty: Filter by one or multiple observed properties.
            unit: Filter by one or multiple units.
            aggregate: Optional aggregate function over 'Value':
                       one of {'min', 'max', 'mean', 'sum', 'count'}.
            groupByTime: Optional grouping of 'Timestamp':
                         'hour', 'day', or 'month'.
            startTime: Optional lower bound (inclusive) for Timestamp filter (ISO string).
            endTime: Optional upper bound (inclusive) for Timestamp filter (ISO string).
            limit: Optional integer limit for number of results.

        Returns:
            pd.DataFrame: Resulting query as a DataFrame.

        Raises:
            FileNotFoundError: If SQLite file not found.
            sqlite3.DatabaseError: If SQL query fails.
            ValueError: For invalid parameters or missing columns.
        """

        if not sqlitePath or not isinstance(sqlitePath, str):
            raise ValueError("sqlitePath must be a valid string path.")
        if not tableName or not isinstance(tableName, str):
            raise ValueError("tableName must be a valid string.")
        if aggregate not in {None, "min", "max", "mean", "sum", "count"}:
            raise ValueError("aggregate must be one of None, 'min', 'max', 'mean', 'sum', 'count'.")
        if groupByTime not in {None, "hour", "day", "month"}:
            raise ValueError("groupByTime must be None, 'hour', 'day', or 'month'.")

        # --- Base query ---
        selectClause = "*"
        groupClause = ""
        aggAlias = ""
        if aggregate:
            aggFunc = aggregate.upper()
            selectClause = '"sosa:madeBySensor", "sosa:ObservedProperty", "Unit", '
            # handle time grouping
            if groupByTime:
                if groupByTime == "hour":
                    selectClause += "strftime('%Y-%m-%dT%H:00:00', Timestamp) AS period, "
                    groupClause = "GROUP BY \"sosa:madeBySensor\", \"sosa:ObservedProperty\", Unit, period"
                elif groupByTime == "day":
                    selectClause += "strftime('%Y-%m-%d', Timestamp) AS period, "
                    groupClause = "GROUP BY \"sosa:madeBySensor\", \"sosa:ObservedProperty\", Unit, period"
                elif groupByTime == "month":
                    selectClause += "strftime('%Y-%m', Timestamp) AS period, "
                    groupClause = "GROUP BY \"sosa:madeBySensor\", \"sosa:ObservedProperty\", Unit, period"
            else:
                groupClause = "GROUP BY \"sosa:madeBySensor\", \"sosa:ObservedProperty\", Unit"

            selectClause += f"{aggFunc}(Value) AS Value"
            aggAlias = f"_{aggregate}"

        # --- WHERE clause construction ---
        whereClauses = []
        params = []

        def _build_in_clause(field: str, value: Union[str, List[str]]) -> str:
            if isinstance(value, str):
                return f'"{field}" = ?'
            elif isinstance(value, (list, tuple, set)):
                placeholders = ", ".join(["?"] * len(value))
                return f'"{field}" IN ({placeholders})'
            else:
                raise TypeError(f"Invalid type for {field}: {type(value)}")

        if sensor:
            whereClauses.append(_build_in_clause("sosa:madeBySensor", sensor))
            params.extend(sensor if isinstance(sensor, (list, tuple, set)) else [sensor])
        if observedProperty:
            whereClauses.append(_build_in_clause("sosa:ObservedProperty", observedProperty))
            params.extend(observedProperty if isinstance(observedProperty, (list, tuple, set)) else [observedProperty])
        if unit:
            whereClauses.append(_build_in_clause("Unit", unit))
            params.extend(unit if isinstance(unit, (list, tuple, set)) else [unit])
        if startTime:
            whereClauses.append("Timestamp >= ?")
            params.append(startTime)
        if endTime:
            whereClauses.append("Timestamp <= ?")
            params.append(endTime)

        whereClause = ""
        if whereClauses:
            whereClause = "WHERE " + " AND ".join(whereClauses)

        limitClause = f"LIMIT {limit}" if limit else ""

        query = f"""
            SELECT {selectClause}
            FROM "{tableName}"
            {whereClause}
            {groupClause}
            ORDER BY Timestamp ASC
            {limitClause};
        """

        # --- Execute query ---
        conn = sqlite3.connect(sqlitePath)
        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as exc:
            raise sqlite3.DatabaseError(f"SQLite query failed: {exc}") from exc
        finally:
            conn.close()

        # rename aggregated column if needed
        if aggregate and "Value" in df.columns:
            df.rename(columns={"Value": f"Value{aggAlias}"}, inplace=True)

        return df

    @staticmethod
    def Template(savePath: Optional[str] = None) -> pd.DataFrame:
        """
        Create a sample SOSA observation template for sensor points.

        Args:
            savePath: Optional path (including filename) where the Excel file (.xlsx)
                      will be saved. Example: "data/point_template.xlsx".

        Returns:
            pd.DataFrame: The generated SOSA observation template.

        Raises:
            ImportError: If pandas or openpyxl are not available.
            OSError: If saving to Excel fails.
        """
        # --- Validate dependencies ---
        try:
            import pandas as pd  # noqa
        except ImportError as exc:
            raise ImportError("pandas is required to generate the template.") from exc

        # --- Create example data ---
        data = [
            ["temperaturePoint1", "Temperature", "°C", 22.5, "2025-03-01 10:00"],
            ["temperaturePoint1", "Temperature", "°C", 22.7, "2025-03-01 10:10"],
            ["temperaturePoint1", "Temperature", "°C", 22.8, "2025-03-01 10:20"],
            ["temperaturePoint1", "Temperature", "°C", 22.3, "2025-03-01 10:30"],
        ]

        columns = [
            "sosa:madeBySensor",
            "sosa:ObservedProperty",
            "unit",
            "value",
            "timestamp",
        ]

        # --- Build DataFrame ---
        df = pd.DataFrame(data, columns=columns)

        # --- Save to Excel if requested ---
        if savePath is not None:
            if not isinstance(savePath, str) or not savePath.strip():
                raise ValueError("savePath must be a valid non-empty string.")
            if not savePath.lower().endswith(".xlsx"):
                savePath += ".xlsx"

            try:
                df.to_excel(savePath, index=False)
                print(f"✅ Template saved successfully to: {savePath}")
            except Exception as exc:
                raise OSError(f"Failed to save template to '{savePath}'.") from exc

        return df
