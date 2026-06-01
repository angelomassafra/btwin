# Points & Observations

Points represent sensors, setpoints, commands, and other data sources in a building. Observations are their timeseries data, stored in SQLite.

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
