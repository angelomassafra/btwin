"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

POINT MODULE
This module defines the functions to model and query points and timeseries via the BTWIN toolkit.

Point builds the sensor nodes; Observation moves timeseries in and out of SQLite and describes
what a table holds, which is what grounds a model writing SQL against it; SQL is the validator
that stands between a generated query and the database, the counterpart of SPARQL in graph.py.

© Angelo Massafra, 2026
"""

# Dependencies
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

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

    # =================================================================================
    # Grounding an LLM on a table: what is in it, how to read it, and what an answer rests on
    # =================================================================================

    @staticmethod
    def SQLiteFetch(
        sqlitePath: Optional[str] = None,
        sql: Optional[str] = None,
        params: Optional[Union[List[Any], Tuple[Any, ...]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run a read-only SQL query and return its rows as plain dictionaries.

        The connection is opened in SQLite's read-only mode, so a statement that slipped past
        SQL.Validate still cannot change the file. Values keep their SQLite types: a REAL
        comes back as a float, not as the string an RDF binding would give.

        Args:
            sqlitePath: Path to the SQLite database file.
            sql: The SQL text to run.
            params: Optional bound parameters for '?' placeholders.

        Returns:
            list[dict]: One dict per row, mapping column name (or alias) to its value.

        Raises:
            ValueError:            If inputs are missing, or the database file is not there.
            sqlite3.DatabaseError: If the query does not run.
        """
        if not sqlitePath or not isinstance(sqlitePath, str):
            raise ValueError("sqlitePath must be a non-empty string path.")
        if not sql or not isinstance(sql, str) or not sql.strip():
            raise ValueError("sql must be a non-empty string.")

        conn = _ReadOnlyConnection(sqlitePath)
        try:
            cur = conn.cursor()
            try:
                cur.execute(sql, tuple(params or ()))
            except sqlite3.Error as exc:
                raise sqlite3.DatabaseError(f"SQLite query failed: {exc}") from exc
            names = [d[0] for d in (cur.description or [])]
            return [dict(zip(names, row)) for row in cur.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def SQLiteIndex(
        sqlitePath: Optional[str] = None,
        tableName: Optional[str] = None,
        *,
        valueLimit: int = 40,
        timeColumn: str = "timestamp",
    ) -> Dict[str, Any]:
        """
        Index a table's columns, and the distinct values of the columns that have few.

        The value lists are the point of this. A question names a campus or a fuel in words;
        the table stores them as opaque strings in a text column, and nothing else in the
        schema says which strings exist. Without the list a model has to guess a literal, and
        a guessed literal returns zero rows that read exactly like an honest 'no data'.

        Columns with more distinct values than `valueLimit` are summarised by count instead
        of listed: a timestamp column has one value per row, and listing it would drown the
        prompt in the one thing a model can already reason about.

        Args:
            sqlitePath: Path to the SQLite database file.
            tableName: The table to inspect (must exist).
            valueLimit: Above this many distinct values, a column is counted, not listed.
            timeColumn: The column holding the observation time, summarised as a range.

        Returns:
            dict: {
                'table': str,           # the table name
                'rows': int,            # how many rows it holds
                'columns': list[dict],  # {'name', 'type', 'distinct', 'values', 'min', 'max'}
                                        # 'values' is [] when the column was too wide to list
            }

        Raises:
            ValueError:            If inputs are missing, or the table is not in the database.
            sqlite3.DatabaseError: If the database cannot be read.
        """
        if not sqlitePath or not isinstance(sqlitePath, str):
            raise ValueError("sqlitePath must be a non-empty string path.")
        if not tableName or not isinstance(tableName, str):
            raise ValueError("tableName must be a non-empty string.")
        if not isinstance(valueLimit, int) or valueLimit < 1:
            raise ValueError("valueLimit must be a positive integer.")

        conn = _ReadOnlyConnection(sqlitePath)
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name=?;",
                        (tableName,))
            if cur.fetchone() is None:
                raise ValueError(f"Table '{tableName}' is not in {os.path.abspath(sqlitePath)}.")

            quoted = _QuoteIdentifier(tableName)
            cur.execute(f"SELECT COUNT(*) FROM {quoted};")
            rowCount = int(cur.fetchone()[0])

            cur.execute(f"PRAGMA table_info({quoted});")
            declared = [(str(r[1]), str(r[2] or "")) for r in cur.fetchall()]

            columns: List[Dict[str, Any]] = []
            for name, colType in declared:
                col = _QuoteIdentifier(name)

                # An empty declared type means the column was created without one, which is
                # legal in SQLite; ask the data what it actually holds.
                if not colType and rowCount:
                    cur.execute(f"SELECT typeof({col}) FROM {quoted} "
                                f"WHERE {col} IS NOT NULL LIMIT 1;")
                    sampled = cur.fetchone()
                    colType = str(sampled[0]) if sampled else ""

                cur.execute(f"SELECT COUNT(DISTINCT {col}) FROM {quoted};")
                distinct = int(cur.fetchone()[0])

                cur.execute(f"SELECT MIN({col}), MAX({col}) FROM {quoted};")
                low, high = cur.fetchone()

                # Listed only when short enough to be read, and only for the columns whose
                # contents are vocabulary. A number is not: its range already says what it
                # spans, and listing four readings as if they were the four legal values
                # invites a model to filter on them. Nor is the time column, whose thousands
                # of distinct values would drown the prompt.
                values: List[Any] = []
                if (distinct <= valueLimit
                        and name.lower() != timeColumn.lower()
                        and not _IsNumericType(colType)):
                    cur.execute(f"SELECT DISTINCT {col} FROM {quoted} WHERE {col} IS NOT NULL "
                                f"ORDER BY 1 LIMIT {valueLimit};")
                    values = [r[0] for r in cur.fetchall()]

                columns.append({
                    "name": name,
                    "type": colType.upper(),
                    "distinct": distinct,
                    "values": values,
                    "min": low,
                    "max": high,
                })

            return {"table": tableName, "rows": rowCount, "columns": columns}
        finally:
            conn.close()

    @staticmethod
    def SQLiteSchemaSummary(
        sqlitePath: Optional[str] = None,
        tableName: Optional[str] = None,
        index: Optional[Dict[str, Any]] = None,
        *,
        notes: Optional[str] = None,
        valueLimit: int = 40,
        timeColumn: str = "timestamp",
    ) -> Dict[str, Any]:
        """
        Describe a table as the text used to ground an LLM writing SQL against it.

        Three sections, in the order a query is written: TABLE and COLUMNS say what may be
        selected, VALUES says what the string columns actually contain, and NOTES says how
        SQLite reads a timestamp. The dialect notes are not decoration - an observation table
        stores time as ISO 8601 text, so a model reaching for a date function it knows from
        another engine writes a query that parses and returns nothing.

        Args:
            sqlitePath: Path to the SQLite database file.
            tableName: The table to describe.
            index: The output of Observation.SQLiteIndex. Computed here when not supplied.
            notes: Domain context the table cannot state itself, appended to NOTES - what a
                sensor identifier is built from, say. A flat table has no labels and no types
                to carry that, so only the caller knows it.
            valueLimit: Passed through to Observation.SQLiteIndex.
            timeColumn: The column holding the observation time.

        Returns:
            dict: {
                'text': str,          # the grounding block
                'columns': set[str],  # the column names a query may use
                'table': str,         # the table name
            }

        Raises:
            ValueError:            If inputs are missing, or the table is not in the database.
            sqlite3.DatabaseError: If the database cannot be read.
        """
        if index is None:
            index = Observation.SQLiteIndex(
                sqlitePath, tableName, valueLimit=valueLimit, timeColumn=timeColumn)
        if not isinstance(index, dict) or "columns" not in index or "table" not in index:
            raise ValueError("index must be the dict returned by Observation.SQLiteIndex.")

        table = index["table"]
        lines: List[str] = ["TABLE", f"  {_QuoteIdentifier(table)}  ({index['rows']} rows)"]

        lines.append("\nCOLUMNS (name, SQLite type, what it spans)")
        for col in index["columns"]:
            span = ""
            if col["min"] is not None or col["max"] is not None:
                span = f", from {col['min']!r} to {col['max']!r}"
            lines.append(f"  {_QuoteIdentifier(col['name']):<26} {col['type'] or 'TEXT':<8}"
                         f"  {col['distinct']} distinct{span}")

        listed = [col for col in index["columns"] if col["values"]]
        if listed:
            lines.append("\nVALUES (the complete contents of the columns short enough to list -\n"
                         "        match these exactly, they are the only ones in the table)")
            for col in listed:
                rendered = ", ".join(repr(v) for v in col["values"])
                lines.append(f"  {_QuoteIdentifier(col['name'])}: {rendered}")

        lines.append(
            "\nNOTES\n"
            "  A column name containing ':' or a space MUST be double-quoted, e.g.\n"
            f'    SELECT "sosa:madeBySensor" FROM {_QuoteIdentifier(table)}\n'
            f"  {_QuoteIdentifier(timeColumn)} is ISO 8601 TEXT: it sorts and compares as text, and is\n"
            "  read with strftime - strftime('%Y', ts) for the year, '%Y-%m' for the month.\n"
            "  SQLite has no DATE type and no EXTRACT, DATEPART, DATE_TRUNC or TO_CHAR.\n"
            "  Aggregate with SUM, AVG, MIN, MAX, COUNT and group with GROUP BY. There is no\n"
            "  other table to join: everything is in this one.")
        if notes and isinstance(notes, str) and notes.strip():
            lines.append("  " + notes.strip().replace("\n", "\n  "))

        return {
            "text": "\n".join(lines),
            "columns": {col["name"] for col in index["columns"]},
            "table": table,
        }

    @staticmethod
    def SQLiteCopy(sqlitePath: Optional[str] = None, savePath: Optional[str] = None) -> str:
        """
        Copy a database, through SQLite's own backup API.

        Not shutil: a database with a write-ahead log lives in more than one file, and copying
        the bytes of the main one gives a snapshot that is missing its most recent commits.
        The backup API reads it as a database and writes a consistent one out.

        Args:
            sqlitePath: The database to copy.
            savePath: Where to write the copy. Overwritten if it is already there.

        Returns:
            str: The absolute path to the copy.

        Raises:
            ValueError:            If inputs are missing, or the source is not there.
            sqlite3.DatabaseError: If the copy could not be made.
        """
        if not savePath or not isinstance(savePath, str) or not savePath.strip():
            raise ValueError("savePath must be a non-empty string path.")

        target = os.path.abspath(savePath)
        if target == os.path.abspath(sqlitePath or ""):
            raise ValueError("savePath must differ from sqlitePath.")
        if os.path.dirname(target):
            os.makedirs(os.path.dirname(target), exist_ok=True)

        source = _ReadOnlyConnection(sqlitePath)
        try:
            destination = sqlite3.connect(target)
            try:
                source.backup(destination)
            finally:
                destination.close()
        except sqlite3.Error as exc:
            raise sqlite3.DatabaseError(f"Could not copy the database to {target}: {exc}") from exc
        finally:
            source.close()
        return target

    @staticmethod
    def SQLiteApplyUpdate(
        sqlitePath: Optional[str] = None,
        tableName: Optional[str] = None,
        sql: Optional[str] = None,
        *,
        commit: bool = False,
        diffLimit: int = 20000,
    ) -> Tuple[int, List[Dict[str, Any]], List[Dict[str, Any]], str]:
        """
        Run an update inside a transaction and report what it changed.

        The table's counterpart to Tool.RDFApplyUpdate, and it reaches the same guarantee by
        a different route: there the update is applied to a copy of the graph, here it is
        applied inside a transaction that is rolled back unless `commit` says otherwise. Both
        let the caller read the change before anything is committed, and both tell an update
        that worked apart from one that ran and moved nothing.

        The diff is a multiset difference over whole rows, so a table holding two identical
        observations and losing one of them reports one removal rather than none.

        Args:
            sqlitePath: Path to the SQLite database file.
            tableName: The table the update writes to, whose rows are diffed.
            sql: The update, already through SQL.ValidateUpdate.
            commit: When True the transaction is committed and the file changes. When False
                (default) it is rolled back and the file is left exactly as it was, which is
                what makes a rehearsal possible.
            diffLimit: Above this many rows, the table is not snapshotted and 'added' and
                'removed' come back empty. `changes` is still exact - SQLite counts it either
                way - so an edit to a table of millions still reports how many rows it moved,
                just not which.

        Returns:
            tuple: (rows changed, rows added, rows removed, "") when the update ran, or
                (0, [], [], the reason) when it did not. A statement that ran and changed
                nothing returns (0, [], [], "") - the empty reason is what tells the two apart.

        Raises:
            ValueError: If inputs are missing, or the table is not in the database.
        """
        if not sql or not isinstance(sql, str) or not sql.strip():
            raise ValueError("sql must be a non-empty string.")
        if not tableName or not isinstance(tableName, str):
            raise ValueError("tableName must be a non-empty string.")
        if not isinstance(diffLimit, int) or diffLimit < 0:
            raise ValueError("diffLimit must be a non-negative integer.")

        conn = _WritableConnection(sqlitePath)
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
                        (tableName,))
            if cur.fetchone() is None:
                raise ValueError(f"Table '{tableName}' is not in {os.path.abspath(sqlitePath)}.")

            quoted = _QuoteIdentifier(tableName)
            cur.execute(f"SELECT COUNT(*) FROM {quoted};")
            diffable = int(cur.fetchone()[0]) <= diffLimit
            names, before = _Snapshot(cur, quoted) if diffable else ([], Counter())

            # total_changes counts from when the connection was opened, not from zero
            startChanges = conn.total_changes
            try:
                cur.execute(sql)
            except sqlite3.Error as exc:
                conn.rollback()
                return 0, [], [], f"The update failed to run: {exc}"
            changes = conn.total_changes - startChanges

            added: List[Dict[str, Any]] = []
            removed: List[Dict[str, Any]] = []
            if diffable:
                _, after = _Snapshot(cur, quoted)
                added = _AsRows(names, after - before)
                removed = _AsRows(names, before - after)

            conn.commit() if commit else conn.rollback()
            return changes, added, removed, ""
        finally:
            conn.close()

    @staticmethod
    def SQLiteSourceRows(
        rows: Optional[List[Dict[str, Any]]] = None,
        column: str = "sosa:madeBySensor",
    ) -> List[str]:
        """
        The sensors an answer rests on.

        The table's counterpart to RDF.SourceNodes: an RDF answer is traced back to the nodes
        it read, a table answer to the sensors whose observations it aggregated. It works
        only when the query kept the identifying column - an answer that summed everything
        into a single number is grounded in the whole table, and says so by returning [].

        Args:
            rows: The rows returned by Observation.SQLiteFetch.
            column: The identifying column to collect. Matched case-insensitively, because a
                query is free to re-case it.

        Returns:
            list[str]: Distinct values, in the order they first appear in the rows.

        Raises:
            TypeError: If `rows` is not a list.
        """
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise TypeError("rows must be a list.")

        wanted = column.lower()
        source: List[str] = []
        for row in rows:
            for key, value in row.items():
                if str(key).lower() == wanted and value is not None and str(value) not in source:
                    source.append(str(value))
        return source


def _QuoteIdentifier(name: str) -> str:
    """Double-quote a table or column name, doubling any quote inside it."""
    return '"' + str(name).replace('"', '""') + '"'


def _IsNumericType(declaredType: str) -> bool:
    """
    Whether a declared SQLite type holds numbers.

    Matched on a substring, the way SQLite's own type affinity rules do: 'DOUBLE PRECISION'
    and 'UNSIGNED BIG INT' are both real declarations, and neither is an exact keyword.
    """
    upper = str(declaredType or "").upper()
    return any(token in upper for token in ("INT", "REAL", "FLOA", "DOUB", "NUM", "DEC"))


def _ReadOnlyConnection(sqlitePath: str) -> sqlite3.Connection:
    """
    Open a database that SQLite itself will refuse to let anything write to.

    The belt to SQL.Validate's braces: the validator reads text and can be talked around,
    'mode=ro' is enforced by the engine. The URI form is the only way to ask for it, and a
    Windows path has to be turned into one first - as_uri() also percent-encodes the spaces
    and accents a real project path is full of, which SQLite decodes back.

    Raises:
        ValueError: If the file is not there. sqlite3 would otherwise happily create an
            empty database and answer every question with 'no rows', which reads like data.
        sqlite3.DatabaseError: If the file is there but cannot be opened.
    """
    absPath = os.path.abspath(sqlitePath)
    if not os.path.isfile(absPath):
        raise ValueError(f"No SQLite database at {absPath}.")
    try:
        return sqlite3.connect(f"{Path(absPath).as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise sqlite3.DatabaseError(f"Could not open {absPath} read-only: {exc}") from exc


# Anything that writes, changes the schema, reaches another file, or steps outside the query
# engine. 'REPLACE' is handled apart, in SQL.Validate: it is also SQLite's string function,
# and rejecting replace(x, y, z) would ban a legitimate SELECT.
FORBIDDEN_SQL_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH",
                          "DETACH", "PRAGMA", "VACUUM", "REINDEX", "TRIGGER", "BEGIN",
                          "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE", "LOAD_EXTENSION",
                          "READFILE", "WRITEFILE", "EDIT", "FTS3_TOKENIZER")


def _WritableConnection(sqlitePath: str) -> sqlite3.Connection:
    """
    Open a database for writing, without ever creating one.

    sqlite3.connect() makes an empty database out of a path that is not there, which turns a
    mistyped filename into an edit that reports success and changes nothing anybody will find.

    Raises:
        ValueError:            If the file is not there.
        sqlite3.DatabaseError: If it is there but cannot be opened.
    """
    absPath = os.path.abspath(sqlitePath or "")
    if not os.path.isfile(absPath):
        raise ValueError(f"No SQLite database at {absPath}.")
    try:
        return sqlite3.connect(absPath)
    except sqlite3.Error as exc:
        raise sqlite3.DatabaseError(f"Could not open {absPath}: {exc}") from exc


def _Snapshot(cursor: sqlite3.Cursor, quotedTable: str) -> Tuple[List[str], "Counter"]:
    """
    Every row of a table as a multiset of tuples, with the column names beside it.

    A multiset, not a set: an observation table may legitimately hold the same reading twice,
    and a set would report deleting one of them as no change at all.
    """
    cursor.execute(f"SELECT * FROM {quotedTable};")
    names = [d[0] for d in (cursor.description or [])]
    return names, Counter(cursor.fetchall())


def _AsRows(names: List[str], counted: "Counter") -> List[Dict[str, Any]]:
    """A multiset difference back into dictionaries, in a stable order."""
    rows: List[Dict[str, Any]] = []
    for values in sorted(counted.elements(), key=lambda row: tuple(str(v) for v in row)):
        rows.append(dict(zip(names, values)))
    return rows


# Everything forbidden in a query, less the three writes an edit exists to make. Transaction
# control is on the list for a reason of its own: the cycle rehearses an edit inside a
# transaction it rolls back, and a model-issued COMMIT would make that rollback a no-op.
FORBIDDEN_SQL_UPDATE_KEYWORDS = tuple(
    keyword for keyword in FORBIDDEN_SQL_KEYWORDS
    if keyword not in ("INSERT", "UPDATE", "DELETE"))

# The table an INSERT, UPDATE or DELETE writes to. Read off the raw text rather than the
# scanned body, because that is where a quoted name survives.
WRITE_TARGET = re.compile(
    r'(?is)\b(?:INSERT(?:\s+OR\s+[A-Z]+)?\s+INTO|UPDATE(?:\s+OR\s+[A-Z]+)?|DELETE\s+FROM)\s+'
    r'("(?:[^"]|"")*"|\[[^\]]*\]|`(?:[^`]|``)*`|[A-Za-z_]\w*)')


def _Unquote(identifier: str) -> str:
    """Strip the quoting off a table name, in any of the four styles SQLite accepts."""
    text = identifier.strip()
    if len(text) >= 2:
        if text[0] == '"' and text[-1] == '"':
            return text[1:-1].replace('""', '"')
        if text[0] == "[" and text[-1] == "]":
            return text[1:-1]
        if text[0] == "`" and text[-1] == "`":
            return text[1:-1].replace("``", "`")
    return text


def _ScanSQL(sql: str) -> str:
    """
    Blank out string literals, quoted identifiers and comments, so keyword scanning sees
    structure only.

    Without it a column legitimately named "deleted_at", or the literal 'DROP', reads as an
    attack. Literals go first: a '--' inside a string opens no comment.
    """
    text = re.sub(r"'(?:[^']|'')*'", "''", sql)          # string literals, '' escapes itself
    text = re.sub(r'"(?:[^"]|"")*"', '""', text)         # double-quoted identifiers
    text = re.sub(r"\[[^\]]*\]", "[]", text)             # bracket identifiers
    text = re.sub(r"`(?:[^`]|``)*`", "``", text)         # backtick identifiers
    text = re.sub(r"--[^\n]*", " ", text)                # line comments
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)   # block comments
    return text


class SQL():

    @staticmethod
    def Form(sql: Optional[str] = None) -> str:
        """
        Tell what kind of statement this is, by its first keyword.

        Args:
            sql: The SQL text.

        Returns:
            str: The opening keyword in upper case ('SELECT', 'WITH', 'INSERT', ...), or ''
                when the text carries no word at all.
        """
        if not sql or not isinstance(sql, str):
            return ""
        match = re.search(r"(?is)\b([A-Za-z_]+)\b", _ScanSQL(sql))
        return match.group(1).upper() if match else ""

    @staticmethod
    def Validate(
        sql: Optional[str] = None,
        sqlitePath: Optional[str] = None,
        rowLimit: int = 100,
        columns: Optional[Set[str]] = None,
    ) -> Tuple[Optional[str], str]:
        """
        Check a query before it is allowed near a database.

        Five passes, most dangerous first: shape, safety, one statement, compilation, limit.
        The compilation pass is the one that earns its keep, and it is stricter than anything
        the SPARQL side can offer: SQLite is asked to EXPLAIN the query, which compiles it in
        full - resolving every table, column and function - without executing a single row. A
        hallucinated column is rejected here by name, instead of being left to return zero
        rows that read like an honest empty answer.

        Args:
            sql: The SQL text to check.
            sqlitePath: The database to compile against. Compilation is skipped when not
                supplied, which leaves only the text passes.
            rowLimit: LIMIT appended to a query that carries none.
            columns: The column names a query may use, from
                Observation.SQLiteSchemaSummary()['columns']. Used only to word the rejection
                a failed compilation gives back to the repair agent.

        Returns:
            tuple: (query ready to run, "") when it passes, or (None, the reason it was
                rejected) when it does not.
        """
        if not sql or not isinstance(sql, str) or not sql.strip():
            return None, "The model returned an empty query."

        body = _ScanSQL(sql)

        form = SQL.Form(sql)
        if not form:
            return None, "No SELECT found - this does not look like a query."
        if form not in ("SELECT", "WITH"):
            return None, f"{form} is not allowed; write a SELECT (a WITH ... SELECT is fine)."
        if form == "WITH" and not re.search(r"(?is)\bSELECT\b", body):
            return None, "A WITH must end in a SELECT."

        for keyword in FORBIDDEN_SQL_KEYWORDS:
            if re.search(rf"(?i)\b{keyword}\b", body):
                return None, f"'{keyword}' is not allowed in this query."
        # REPLACE the statement, not replace() the string function
        if re.search(r"(?i)\bREPLACE\b(?!\s*\()", body):
            return None, "'REPLACE' is not allowed in this query."

        # One statement only: a trailing ';' is fine, a second statement after it is not.
        if re.search(r";\s*\S", body):
            return None, "Write a single statement: ';' may only close the query."

        stripped = sql.strip().rstrip(";").rstrip()

        if sqlitePath:
            try:
                conn = _ReadOnlyConnection(sqlitePath)
            except (ValueError, sqlite3.DatabaseError) as exc:
                return None, str(exc)
            try:
                # EXPLAIN compiles and stops: it resolves names and types, and runs nothing
                conn.execute(f"EXPLAIN {stripped}")
            except sqlite3.Error as exc:
                known = f" Columns available: {', '.join(sorted(columns))}." if columns else ""
                return None, f"SQLite rejected the query: {exc}.{known}"
            finally:
                conn.close()

        # A missing LIMIT is a defect in the query, not a reason to send it back to the model
        if not re.search(r"(?i)\bLIMIT\b", body):
            stripped = f"{stripped}\nLIMIT {rowLimit}"

        return stripped, ""

    @staticmethod
    def ValidateUpdate(
        sql: Optional[str] = None,
        tableName: Optional[str] = None,
        sqlitePath: Optional[str] = None,
        columns: Optional[Set[str]] = None,
    ) -> Tuple[Optional[str], str]:
        """
        Check an update before it is allowed to change a database.

        The same passes as SQL.Validate with the shape pass inverted: here a write is the
        point, so INSERT, UPDATE and DELETE are the only openings accepted, and everything
        that would replace or empty the table rather than edit its content is not.

        Three refusals are worth naming, because each is a way of destroying data while
        answering the request as put:

        - An UPDATE or a DELETE with no WHERE. 'Delete the faulty readings' with the WHERE
          left off empties the table, and SQLite will not warn anyone. This is the table's
          version of the DROP and CLEAR that SPARQL.ValidateUpdate refuses outright.
        - REPLACE INTO, or INSERT OR REPLACE. Both delete whatever row they collide with
          before inserting, so a statement that reads as an addition silently removes data
          nobody mentioned. Plain INSERT, or an explicit UPDATE, says what it means.
        - A write to any table but the one named. An edit confined to the table the caller
          is looking at is the counterpart of confining a SPARQL update to the default graph.

        Args:
            sql: The SQL text to check.
            tableName: The only table this update may write to. The target check is skipped
                when not supplied.
            sqlitePath: The database to compile against, through EXPLAIN, which resolves
                every name and executes nothing - so this stays a read-only operation even
                for a statement that writes. Skipped when not supplied.
            columns: The column names an update may use, from
                Observation.SQLiteSchemaSummary()['columns']. Used only to word the rejection.

        Returns:
            tuple: (update ready to run, "") when it passes, or (None, the reason it was
                rejected) when it does not.
        """
        if not sql or not isinstance(sql, str) or not sql.strip():
            return None, "The model returned an empty update."

        body = _ScanSQL(sql)

        form = SQL.Form(sql)
        if not form:
            return None, "No INSERT, UPDATE or DELETE found - this does not look like an update."
        if form not in ("INSERT", "UPDATE", "DELETE", "REPLACE"):
            return None, (f"{form} is not allowed; write an INSERT, an UPDATE or a DELETE.")

        for keyword in FORBIDDEN_SQL_UPDATE_KEYWORDS:
            if re.search(rf"(?i)\b{keyword}\b", body):
                return None, f"'{keyword}' is not allowed in this update."

        # REPLACE as a statement, and its 'INSERT OR REPLACE' spelling: both delete on
        # collision. replace() the string function is left alone.
        if form == "REPLACE" or re.search(r"(?i)\bOR\s+REPLACE\b", body):
            return None, ("REPLACE deletes the row it collides with. Write a plain INSERT to "
                          "add a row, or an UPDATE to change one that is already there.")

        if re.search(r";\s*\S", body):
            return None, "Write a single statement: ';' may only close the update."

        if form in ("UPDATE", "DELETE") and not re.search(r"(?i)\bWHERE\b", body):
            article, damage = ("An", "rewrite") if form == "UPDATE" else ("A", "empty")
            return None, (f"{article} {form} must carry a WHERE clause naming the rows to "
                          f"change. Without one it would {damage} the whole table.")

        if tableName:
            # Compared case-insensitively, because SQLite identifiers are, but reported in the
            # spelling the statement used: an error naming a table the model never wrote is
            # one more thing for the repair agent to be confused by.
            targets = {_Unquote(match): _Unquote(match).lower()
                       for match in WRITE_TARGET.findall(sql)}
            if not targets:
                return None, "Could not tell which table this update writes to."
            stray = sorted(written for written, folded in targets.items()
                           if folded != tableName.lower())
            if stray:
                return None, (f"This update writes to {', '.join(repr(t) for t in stray)}. "
                              f"It may only write to '{tableName}'.")

        stripped = sql.strip().rstrip(";").rstrip()

        if sqlitePath:
            try:
                # Read-only on purpose: EXPLAIN compiles a write without being allowed to
                # make one, so a statement is checked against the real schema with the engine
                # itself guaranteeing the database cannot move while it happens
                conn = _ReadOnlyConnection(sqlitePath)
            except (ValueError, sqlite3.DatabaseError) as exc:
                return None, str(exc)
            try:
                conn.execute(f"EXPLAIN {stripped}")
            except sqlite3.Error as exc:
                known = f" Columns available: {', '.join(sorted(columns))}." if columns else ""
                return None, f"SQLite rejected the update: {exc}.{known}"
            finally:
                conn.close()

        return stripped, ""
