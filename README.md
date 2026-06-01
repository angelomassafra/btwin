# BTwin

[![License](https://img.shields.io/badge/License-PolyForm_NC_1.0-blue.svg)](LICENSE)

BTwin (Building Twin) is a Python toolkit for modeling buildings as semantic knowledge graphs. It is designed for researchers and practitioners who need to prototype graph-based decision support systems in building management — connecting spatial data, equipment inventories, sensor readings, and performance indicators into a single, queryable graph structure.

## What it does

A building in BTwin is represented as a directed graph. Every element — a room, an air handling unit, a temperature sensor, an energy KPI — becomes a node. Relationships between elements (a sensor belongs to a space, a space belongs to a floor, a floor belongs to a building) become edges. This graph can be validated against semantic schemas, exported to standard formats, and used as the backbone for analysis and decision support workflows.

The package is built around three principles:

- **Semantic grounding**: every type and relationship is drawn from established building ontologies (Brick, BOT, IFC) or domain-specific standards (SOSA for sensors, EM-KPIO for energy KPIs). Objects serialize to JSON-LD with full ontology context, making them interoperable with other linked data tools.
- **Practical data ingestion**: alongside the Python API, BTwin provides Excel templates and batch importers so that equipment inventories and sensor observations can be loaded from spreadsheets without writing code.
- **Graph-first analysis**: the graph layer (built on NetworkX) supports subgraph extraction by type or UID, schema validation, compact representations of property sets and KPI sets, and export to Neo4j or RDF/Turtle for SPARQL querying.

## Modules

| Module | What it models |
|---|---|
| `SpatialElement` | Spatial hierarchy: sites, buildings, storeys, spaces, zones |
| `Equipment` | Building assets and systems with location and feeding relationships |
| `Point` | Sensor and measurement points (Brick point types, SOSA semantics) |
| `Observation` | Timeseries sensor readings stored and queried via SQLite |
| `PropertySet` / `Property` | IFC property sets attached to any spatial or equipment element |
| `KPISet` / `KPI` | Performance indicators with evaluation periods, units, and scenarios |
| `Scenario` | Hypothetical building states for comparative analysis |
| `Document` | References to external files (BIM models, databases, reports) |
| `NetworkX` | Graph construction, validation, subgraph queries, Neo4j/JSON export |
| `RDF` | Conversion of JSON-LD graphs to RDFLib and Turtle serialization |
| `Serialization` | JSON-LD document assembly with ontology context |
| `Plot` | Graph visualization via Matplotlib (static) and Plotly (interactive) |
| `Schema` | Canonical ontology types and allowed relationship patterns |

## Ontologies

BTwin maps to these open standards:

- **Brick Schema** — building metadata schema for equipment and sensor types
- **BOT (Building Topology Ontology)** — W3C standard for spatial hierarchy
- **IFC (Industry Foundation Classes)** — buildingSMART property model
- **SOSA** — W3C Sensor, Observation, Sample and Actuator ontology
- **EM-KPIO** — Energy Management Key Performance Indicators Ontology

## Installation

```bash
pip install btwin
```

Optional extras:

```bash
pip install btwin[viz]       # visualization (matplotlib, plotly)
pip install btwin[neo4j]     # Neo4j graph database export
pip install btwin[dev]       # development (pytest, ruff)
pip install btwin[docs]      # documentation (mkdocs, mkdocstrings)
```

## Quick Start

```python
from btwin import SpatialElement, Equipment, NetworkX, Serialization
import networkx as nx

# Build a spatial hierarchy
site     = SpatialElement.Constructor("site-01",    "bot:Site",      name="Campus")
building = SpatialElement.Constructor("bldg-01",    "bot:Building",  name="Main Hall")
storey   = SpatialElement.Constructor("storey-01",  "bot:Storey",    name="Ground Floor")
space    = SpatialElement.Constructor("space-01",   "bot:Space",     name="Room 101")

SpatialElement.SetLocationRelationship(building, linkedObject=site)
SpatialElement.SetLocationRelationship(storey,   linkedObject=building)
SpatialElement.SetLocationRelationship(space,    linkedObject=storey)

# Add equipment
ahu = Equipment.Constructor("ahu-01", "brick:Air_Handling_Unit", name="AHU 1")
Equipment.SetLocationRelationship(ahu, linkedObject=space)

# Build the graph
G = nx.DiGraph()
for obj in [site, building, storey, space, ahu]:
    NetworkX.AddEdgesByObject(G, obj)

print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

# Export to JSON-LD
Serialization.JSONLODByObjects(
    [site, building, storey, space, ahu],
    savePath="my_building.json"
)
```

## Documentation

Full documentation is built with MkDocs and lives under `docs/`. It includes a getting started guide, per-module user guides, hands-on tutorials, and an auto-generated API reference from docstrings. To build it locally:

```bash
pip install btwin[docs]
mkdocs serve
```

## References

BTwin's theoretical framework, design logic, and applications are presented in:

> Massafra, Angelo. *Buildings as Networks: Modelling Built Heritage Knowledge Through Graphs*. Bologna: Bologna University Press, 2026, 329 pp.  
> DOI: 10.30682/9791254777954 — Open Access

## License

BTwin is free for non-commercial use (research, education, personal projects) under the PolyForm Noncommercial License 1.0.0 — see `LICENSE`.

For commercial use, contact **massafra.angelo95@gmail.com**.
