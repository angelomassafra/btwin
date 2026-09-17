# Point, Observation & SQL

A `Point` is a sensor, setpoint, command or other data source, as a node in the graph. Its
readings do not live on the node: they live in a SQLite table handled by `Observation`,
keyed by the point's UID. `SQL` is the validator that stands between a generated query and
that database — the table-side counterpart of [`SPARQL`](graph.md).

## Points

```python
from btwin import Point

sensor = Point.Constructor("temp-101", "brick:Air_Temperature_Sensor", name="Room 101 temperature")
Point.SetRelationship(sensor, "brick:hasLocation",
                      linkedObjectUID="space-01", linkedObjectType="bot:Space")
```

## Observations

One row per reading, in the shape of a SOSA observation: `sosa:madeBySensor`,
`sosa:ObservedProperty`, `unit`, `value`, `timestamp`. `Observation.Template` returns an
example frame in that shape.

```python
from btwin import Observation

frame = Observation.Template()
Observation.SQLiteByDF(frame, "readings.db", "observations", ifExists="replace")

daily = Observation.SQLiteQuery("readings.db", "observations",
                                sensor=frame["sosa:madeBySensor"].iloc[0],
                                aggregate="max", groupByTime="day")
```

## Grounding a model on a table

The remaining `Observation` methods serve a language model writing SQL.
`SQLiteSchemaSummary` describes the table — its columns and the distinct values of the columns
that have few — and `SQL.Validate` decides whether what came back may run:

```python
from btwin import Observation, SQL

schema = Observation.SQLiteSchemaSummary("readings.db", "observations")
checked, error = SQL.Validate('SELECT "value" FROM observations',
                              sqlitePath="readings.db", columns=schema["columns"])
rows = Observation.SQLiteFetch("readings.db", checked)       # read-only connection
```

`Validate` has SQLite compile the query with `EXPLAIN`, which resolves every table and column
without running it, so an invented column is refused by name instead of returning zero rows.
A query with no `LIMIT` gets one. For edits, `SQL.ValidateUpdate` accepts one `INSERT`,
`UPDATE` or `DELETE` on the named table and refuses `UPDATE`/`DELETE` without `WHERE` and
`REPLACE`; `Observation.SQLiteApplyUpdate` then runs it in a transaction, reports the rows it
changed, and commits only when asked. See [`Cycle.SQLiteQueryByPrompt`](llm.md) for the
full pipeline.

## Point

::: btwin.point.Point
    options:
      members_order: source
      show_source: true

## Observation

::: btwin.point.Observation
    options:
      members_order: source
      show_source: true

## SQL

::: btwin.point.SQL
    options:
      members_order: source
      show_source: true
