# Tutorial: Timeseries Data

In this tutorial you will create sensor points, generate observation data, write it to SQLite, and query it with filters and aggregations.

## Step 1: Create Sensor Points

```python
from btwin import Point

temp = Point.Constructor("temp-lab", "brick:Temperature_Sensor", name="Lab Temperature")
co2 = Point.Constructor("co2-lab", "brick:CO2_Sensor", name="Lab CO2")
humidity = Point.Constructor("rh-lab", "brick:Humidity_Sensor", name="Lab Humidity")

# Link sensors to their space
for sensor in [temp, co2, humidity]:
    Point.SetRelationship(
        sensor,
        relationshipName="brick:hasLocation",
        linkedObjectUID="space-lab",
        linkedObjectType="bot:Space"
    )
```

## Step 2: Build an Observation DataFrame

Create a DataFrame following the SOSA observation pattern:

```python
import pandas as pd

timestamps = pd.date_range("2025-03-01", periods=24, freq="h")

observations = pd.DataFrame({
    "sosa:madeBySensor": ["temp-lab"] * 24 + ["co2-lab"] * 24 + ["rh-lab"] * 24,
    "sosa:ObservedProperty": ["Temperature"] * 24 + ["CO2"] * 24 + ["Humidity"] * 24,
    "Unit": ["degC"] * 24 + ["ppm"] * 24 + ["%RH"] * 24,
    "Value": (
        [20 + i * 0.3 for i in range(24)] +      # temperature
        [400 + i * 15 for i in range(24)] +       # CO2
        [45 + i * 0.5 for i in range(24)]         # humidity
    ),
    "Timestamp": list(timestamps) * 3,
})

print(observations.head())
```

## Step 3: Write to SQLite

```python
from btwin import Observation

db_path = Observation.SQLiteByDF(
    observations,
    sqlitePath="sensor_data.db",
    tableName="observations",
    ifExists="replace"
)
print(f"Database: {db_path}")
```

## Step 4: Query All Data for a Sensor

```python
results = Observation.SQLiteQuery(
    "sensor_data.db",
    "observations",
    sensor="temp-lab"
)
print(results)
```

## Step 5: Filter by Time Range

```python
results = Observation.SQLiteQuery(
    "sensor_data.db",
    "observations",
    sensor="temp-lab",
    startTime="2025-03-01T06:00:00",
    endTime="2025-03-01T12:00:00"
)
print(f"Rows in time window: {len(results)}")
```

## Step 6: Aggregate Data

### Daily mean temperature

```python
daily_mean = Observation.SQLiteQuery(
    "sensor_data.db",
    "observations",
    sensor="temp-lab",
    aggregate="mean",
    groupByTime="day"
)
print(daily_mean)
```

### Max CO2 across all time

```python
max_co2 = Observation.SQLiteQuery(
    "sensor_data.db",
    "observations",
    sensor="co2-lab",
    aggregate="max"
)
print(max_co2)
```

## Step 7: Query Multiple Sensors

```python
results = Observation.SQLiteQuery(
    "sensor_data.db",
    "observations",
    sensor=["temp-lab", "co2-lab"],
    aggregate="mean",
    groupByTime="hour",
    limit=10
)
print(results)
```

## Result

You now have:

- Three sensor points linked to a space
- 72 observation records (24 hours x 3 sensors) in SQLite
- Queries filtering by sensor, time range, and observed property
- Aggregations by hour, day, or month with min/max/mean/sum/count
