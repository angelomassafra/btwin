# Point, Observation & SQL

Points represent sensors, setpoints, commands, and other data sources. Observations handle
timeseries storage and querying via SQLite, and describe a table well enough for an LLM to
write SQL against it. `SQL` is the validator that stands between a generated query and the
database, the table-side counterpart of [`SPARQL`](graph.md).

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
