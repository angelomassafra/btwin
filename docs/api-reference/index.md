# API Reference

Generated from the docstrings in `src/btwin`, so it always describes the installed version.
Every name below is importable from the top-level package:

```python
from btwin import SpatialElement, Equipment, Point, Serialization, NetworkX, RDF
```

## How the library is shaped

Almost every class is a **namespace of static methods**, not something to instantiate. The
objects they build are plain JSON-LD dictionaries:

```python
{"@id": "space-01", "@type": "bot:Space", "name": "Room 101",
 "relationships": {"brick:hasLocation": [{"@id": "storey-01", "@type": "bot:Storey"}]}}
```

A `Constructor` creates one, `Set*` methods add relationships and return the same dict, and
accessors (`UID`, `Name`, `Type`, `Relationships`) read it back. `Serialization` collects the
dictionaries into one JSON-LD document, which `NetworkX` and `RDF` turn into graphs. The
exceptions are `CostMeter`, a stateful object that accumulates cost across calls, and `LLM`,
whose `Constructor` returns a chat model.

## Modules

| Page | Classes | What it covers |
|------|---------|----------------|
| [Schema](schema.md) | `Schema` | The classes and predicates objects are validated against |
| [SpatialElement](spatial-element.md) | `SpatialElement`, `SpatialHierarchy` | Sites, buildings, storeys, spaces and zones — built by hand or read from IFC |
| [Equipment](equipment.md) | `Equipment`, `Inventory` | Devices, and bulk import from an Excel inventory |
| [Point](point.md) | `Point`, `Observation`, `SQL` | Sensor nodes, timeseries in SQLite, and the SQL validator |
| [PropertySet](property-set.md) | `PropertySet`, `Property` | IFC property sets and their properties |
| [KPISet](kpi-set.md) | `KPISet`, `KPI` | Key performance indicators over a time interval |
| [Scenario](scenario.md) | `Scenario` | The conditions KPIs were evaluated under |
| [Document](document.md) | `Document` | Files, models and databases attached to objects |
| [Graph](graph.md) | `NetworkX`, `RDF`, `SPARQL` | Graphs from JSON-LD, SPARQL, grounding text, the SPARQL validator |
| [LLM, Tool & Cycle](llm.md) | `LLM`, `CostMeter`, `Tool`, `Cycle` | Language-model pipelines that query, create and edit a twin |
| [Plot](plot.md) | `GraphPlot`, `Color` | Static, Plotly and interactive HTML graph drawings; the palette |
| [Serialization](serialization.md) | `Serialization` | JSON-LD export and its vocabulary |
