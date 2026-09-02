# Points & Observations

Points represent sensors, setpoints, commands, and other data sources in a building.
Observations are their timeseries data, stored in SQLite — written, queried, described
well enough for an LLM to write SQL against, and changed under a validator that will not
let a generated statement empty the table.

## Creating Points

```python
from btwin import Point

temp_sensor = Point.Constructor(
    "temp-01",
    "brick:Temperature_Sensor",
    name="Room 101 Temperature"
)
```

Use `Point.Types()` to list all available Brick point types:

```python
for t in Point.Types():
    print(t)
# brick:Point, brick:Sensor, brick:Temperature_Sensor, ...
```

## Point Relationships

Link a sensor to the space it monitors:

```python
Point.SetRelationship(
    temp_sensor,
    relationshipName="brick:hasLocation",
    linkedObjectUID="space-01",
    linkedObjectType="bot:Space"
)
```

## Accessors

```python
Point.UID(temp_sensor)            # "temp-01"
Point.Name(temp_sensor)           # "Room 101 Temperature"
Point.Relationships(temp_sensor)  # {"brick:hasLocation": [...]}
```

## Observation Templates

Generate a sample SOSA observation DataFrame:

```python
from btwin import Observation

df = Observation.Template(savePath="observations.xlsx")
print(df)
```

The template has columns: `sosa:madeBySensor`, `sosa:ObservedProperty`, `unit`, `value`, `timestamp`.

## Writing Observations to SQLite

### From a DataFrame

```python
import pandas as pd

data = {
    "sosa:madeBySensor": ["temp-01"] * 4,
    "sosa:ObservedProperty": ["Temperature"] * 4,
    "Unit": ["degC"] * 4,
    "Value": [21.5, 22.0, 22.3, 21.8],
    "Timestamp": pd.date_range("2025-03-01 10:00", periods=4, freq="10min"),
}
df = pd.DataFrame(data)

db_path = Observation.SQLiteByDF(
    df,
    sqlitePath="observations.db",
    tableName="sensor_data",
    ifExists="replace"
)
```

### From an Excel file

```python
db_path = Observation.SQLiteByXLSX(
    "observations.xlsx",
    sqlitePath="observations.db",
    tableName="sensor_data",
    ifExists="replace"
)
```

## Querying Observations

```python
# All data for a sensor
results = Observation.SQLiteQuery(
    "observations.db",
    "sensor_data",
    sensor="temp-01"
)

# Filtered by time range
results = Observation.SQLiteQuery(
    "observations.db",
    "sensor_data",
    sensor="temp-01",
    startTime="2025-03-01T10:00:00",
    endTime="2025-03-01T10:30:00"
)

# Aggregated: daily mean
results = Observation.SQLiteQuery(
    "observations.db",
    "sensor_data",
    sensor="temp-01",
    aggregate="mean",
    groupByTime="day"
)
```

The `aggregate` parameter supports `"min"`, `"max"`, `"mean"`, `"sum"`, and `"count"`. The `groupByTime` parameter supports `"hour"`, `"day"`, and `"month"`.

## Describing a table for a model

`Observation.SQLiteQuery` above is the typed API: you say which sensor, which aggregate, which
period, and it builds the SQL. Everything below is what it takes to let a **model** write that
SQL instead — starting with telling it what is in the table.

`Observation.SQLiteIndex` reads the columns and, for every column short enough to list, its
complete set of distinct values:

```python
index = Observation.SQLiteIndex("energyBills.db", "energyBills")

index["rows"]                                    # 864
[c["name"] for c in index["columns"]]            # the five template columns
next(c for c in index["columns"] if c["name"] == "unit")["values"]
# ['EUR', 'Smc', 'kWh', 'm3']
```

Those value lists are the point of it. A question names a campus or a fuel in words; the table
stores them as opaque strings, and nothing in a SQL schema says which strings exist. Without the
list a model has to guess a literal, and a guessed literal returns zero rows that read exactly
like an honest "no data".

Wide columns are counted rather than listed, and so are numeric ones — four readings are not four
legal values, and listing them invites a filter on them. The timestamp column is always given as a
range.

`Observation.SQLiteSchemaSummary` renders that into the block a model is actually given:

```python
schema = Observation.SQLiteSchemaSummary(
    "energyBills.db", "energyBills",
    notes="A sensor identifier reads CAMPUS-BUILDING-METER.",
)
print(schema["text"])
```

```
TABLE
  "energyBills"  (864 rows)

COLUMNS (name, SQLite type, what it spans)
  "sosa:madeBySensor"        TEXT      18 distinct, from 'NAV-B1-EM' to 'TER-B2-WM'
  ...
VALUES (the complete contents of the columns short enough to list -
        match these exactly, they are the only ones in the table)
  "unit": 'EUR', 'Smc', 'kWh', 'm3'
  ...
NOTES
  A column name containing ':' or a space MUST be double-quoted, e.g.
    SELECT "sosa:madeBySensor" FROM "energyBills"
  "timestamp" is ISO 8601 TEXT: it sorts and compares as text, and is
  read with strftime - strftime('%Y', ts) for the year, '%Y-%m' for the month.
  SQLite has no DATE type and no EXTRACT, DATEPART, DATE_TRUNC or TO_CHAR.
  ...
  A sensor identifier reads CAMPUS-BUILDING-METER.
```

The dialect notes are not decoration. The template stores time as ISO 8601 **text**, so a model
reaching for a date function it knows from another engine writes a query that parses and returns
nothing.

`notes` is the one thing the table cannot say about itself. A graph carries labels and types; a
flat table carries neither, so what a sensor identifier *means* — that `NAV-B1-EM` is the
electricity meter of building B1 on the Navile campus — is known only to you. It is usually the
difference between a right answer and a plausible one.

## Running SQL

`Observation.SQLiteFetch` runs a query and returns plain dicts. The connection is opened in
SQLite's read-only mode, so nothing it is handed can change the file:

```python
Observation.SQLiteFetch(
    "energyBills.db",
    'SELECT "unit", SUM(value) AS total FROM energyBills GROUP BY "unit"',
)
# [{'unit': 'EUR', 'total': 596596.19}, ...]
```

Values keep their SQLite types — a `REAL` comes back as a float, not as the string an RDF binding
would give.

## Checking SQL before it runs

`SQL` is the table-side counterpart of [`SPARQL`](graph.md): the gate between a generated query
and the database.

```python
from btwin import SQL

SQL.Validate('SELECT campus FROM energyBills', "energyBills.db")
# (None, "SQLite rejected the query: no such column: campus. ...")

SQL.Validate('SELECT "unit" FROM energyBills', "energyBills.db", rowLimit=25)
# ('SELECT "unit" FROM energyBills\nLIMIT 25', '')
```

Five passes, most dangerous first: shape, safety, one statement, compilation, limit. The
compilation pass is the one that earns its keep, and it is stricter than anything the SPARQL side
can offer — SQLite is asked to `EXPLAIN` the query, which compiles it in full, resolving every
table, column and function, **without executing a single row**. A hallucinated column is rejected
here by name instead of returning zero rows that read like an honest empty answer. The `EXPLAIN`
runs on a read-only connection, so validation cannot write even when the statement would.

A missing `LIMIT` is a defect the validator repairs rather than a reason to reject.

`SQL.ValidateUpdate` is the same gate with the shape test inverted: `INSERT`, `UPDATE` and
`DELETE` are the only openings accepted. Three refusals are worth naming, because each is a way of
destroying data while answering the request as put:

| Refused | Why |
|---|---|
| `UPDATE`/`DELETE` with no `WHERE` | Empties or rewrites the whole table. The table's version of the `DROP` and `CLEAR` that `SPARQL.ValidateUpdate` refuses outright. |
| `REPLACE INTO`, `INSERT OR REPLACE` | Deletes whatever row it collides with, so a statement that reads as an addition silently removes data nobody mentioned. |
| A write to any other table | An edit confined to the table you are looking at is the counterpart of confining a SPARQL update to the default graph. |

## Changing a table

`Observation.SQLiteApplyUpdate` runs a statement **inside a transaction** and reports what it
changed. Unless `commit=True`, the transaction is rolled back and the file is left exactly as it
was — which is what makes a rehearsal possible:

```python
changes, added, removed, error = Observation.SQLiteApplyUpdate(
    "energyBills.db", "energyBills",
    "UPDATE energyBills SET value = 21000.0 "
    "WHERE \"sosa:madeBySensor\" = 'NAV-B1-EM' "
    "  AND \"sosa:ObservedProperty\" = 'ElectricityConsumption' "
    "  AND \"timestamp\" = '2025-01-01T00:00:00Z'",
)
changes              # 1
removed[0]["value"]  # 17533.46   — what it would replace
added[0]["value"]    # 21000.0    — what with
```

All three conditions are load-bearing. Drop the observed property and the same statement matches
**two** rows, because that meter reports its consumption *and* its cost at that instant, and both
would be set to 21000. This is the mistake the edit cycle's prompt spends a rule on, and the
rehearsal is what puts it in front of you: `changes` comes back as 2, and nothing has been written
yet.

It reaches the same guarantee as `Tool.RDFApplyUpdate` by a different route: there the update is
applied to a copy of the graph, here it is applied inside a transaction that is rolled back. Both
let you read the change before anything is committed, and both tell an update that worked apart
from one that ran and moved nothing — `(0, [], [], "")` is a statement that ran and matched no row,
and the empty error is what distinguishes it from one that failed.

The diff is a **multiset** difference over whole rows: a table holding two identical observations
and losing one of them reports one removal rather than none. Above `diffLimit` rows the table is
not snapshotted and only `changes` comes back, which is still exact.

`Observation.SQLiteCopy` copies a database through SQLite's own backup API — not `shutil`, because
a database with a write-ahead log lives in more than one file:

```python
Observation.SQLiteCopy("energyBills.db", "energyBills_edited.db")
```

## Asking in English

Three cycles sit on top of all of the above. They are documented with the rest of the pipeline in
[LLM, Tool & Cycle](llm.md):

| Cycle | What it does |
|---|---|
| `Cycle.SQLiteQueryByPrompt` | A question → SQL → rows → an English answer |
| `Cycle.SQLiteEditByPrompt` | A request → a validated write, rehearsed before it is committed |
| `Cycle.SQLiteChat` | The two of them as a conversation at the terminal |

```python
from btwin import LLM, Cycle

result = Cycle.SQLiteQueryByPrompt(
    "energyBills.db", "energyBills",
    "Which campus spent the most on energy in 2025?",
    llm=LLM.Constructor(),
    notes="A sensor identifier reads CAMPUS-BUILDING-METER.",
)
print(result["answer"], result["sql"], result["source"])
```
