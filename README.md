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
| `LLM` / `Tool` / `Cycle` | Optional natural-language layer: build, edit and query graphs by prompt |
| `CostMeter` | Token and cost accounting for every model call |

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
pip install btwin[rdf]       # RDF and SPARQL (rdflib)
pip install btwin[neo4j]     # Neo4j graph database export
pip install btwin[pdf]       # PDF reading (pypdf, pymupdf)
pip install btwin[llm]       # natural-language cycles (langchain, rdflib, pdf)
pip install btwin[dev]       # development (pytest, ruff)
pip install btwin[docs]      # documentation (mkdocs, mkdocstrings)
```

## Quick Start

```python
from btwin import SpatialElement, Equipment, NetworkX, Serialization

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

# Build the graph: nodes first, then edges, so every edge finds both endpoints
objects = [site, building, storey, space, ahu]

G = NetworkX.Constructor("MultiDiGraph", name="Campus")
for obj in objects:
    NetworkX.AddNodeByObject(G, obj)
for obj in objects:
    NetworkX.AddEdgesByObject(G, obj)

print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")
# Nodes: 5, Edges: 4

# Export to JSON-LD
Serialization.JSONLDByObjects(objects, savePath="my_building.json")
```

## Tutorials

Three runnable notebooks live in [`tutorials/`](https://github.com/angelomassafra/btwin/blob/main/tutorials), numbered in the order they are meant
to be read. Each sits in its own self-contained folder and is committed with its outputs, so they
can be read on GitHub without running anything.

| # | Tutorial | What it covers |
|---|---|---|
| 00 | [Create a BTwin graph](https://github.com/angelomassafra/btwin/blob/main/tutorials/00-create-a-btwin-graph/create-a-btwin-graph.ipynb) | Builds a two-storey office from synthetic data — spatial hierarchy, property sets, sensors, a KPI set, documents — then serializes, queries and draws it. No LLM. |
| 01 | [Move a graph between formats](https://github.com/angelomassafra/btwin/blob/main/tutorials/01-graph-formats/graph-formats.ipynb) | JSON-LD, NetworkX, RDF/SPARQL and Neo4j, and a measured account of what each conversion keeps or drops. |
| 02 | [LLM in action](https://github.com/angelomassafra/btwin/blob/main/tutorials/02-llm-in-action/llm-in-action.ipynb) | Builds a graph from an English prompt and queries it in English. Requires an API key and bills your account. |

Each notebook writes a self-contained interactive HTML page after every stage into its own
`output/` folder, so you can click through the graph as it grows — open any `step-*.html` directly
in a browser.

See [`tutorials/README.md`](https://github.com/angelomassafra/btwin/blob/main/tutorials/README.md) for what each one needs and how to run them.

## Language models

BTwin does not need a language model. Every module listed above works without one, and the first
two tutorials never call out to a provider. The optional `btwin.llm` module adds a natural-language
layer *on top of* the graph, installed with `pip install btwin[llm]`.

The design principle is that **the model is never trusted to know the ontologies**. Instead:

1. **Grounding.** Before any prompt, BTwin generates a vocabulary block from its own schema — the
   allowed classes, the allowed properties, and the legal *subject type → relationship → object
   type* combinations — plus a block describing the JSON-LD notation. The model is handed these and
   told to use nothing else, so it is never asked to recall Brick or BOT from memory.
2. **Validation.** Whatever comes back is parsed and checked against that same vocabulary before it
   is allowed near the graph. A `@type` that is not in the schema, or a relationship between two
   types that is not a legal pair, is rejected.
3. **Repair.** A rejection is sent back to the model with the reason, up to `maxRepairs` times.
4. **Patches, not rewrites.** Edits are applied as a validated patch (JSON-LD) or a validated
   SPARQL `UPDATE` (RDF), so an edit cannot silently rewrite parts of the graph you did not mention.

`Cycle` wraps each of these end to end:

| Call | What it does |
|---|---|
| `Cycle.JSONLDCreateByPrompt` | English description → a validated BTwin graph |
| `Cycle.JSONLDEditByPrompt` | English request → a validated patch applied to a document |
| `Cycle.RDFQueryByPrompt` | English question → SPARQL → rows → an English answer |
| `Cycle.RDFEditByPrompt` | English request → a validated SPARQL `UPDATE` |
| `Cycle.DocumentCreateByPrompt` | A PDF → an inferred `Document` node with its property set |

`Tool` exposes the individual agents if you would rather drive the pipeline yourself, and
`CostMeter` records tokens and cost for every call so a run's price is never a surprise.

```python
from btwin import Cycle, RDF

built = Cycle.JSONLDCreateByPrompt(
    "A two-storey clinic with a waiting room and a lab, "
    "and a CO2 sensor in the waiting room."
)

graph, turtle = RDF.ByJSONLD(built["jsonld"], strict=False)
answer = Cycle.RDFQueryByPrompt(graph, "Which rooms have a CO2 sensor?")

print(answer["answer"])   # the sentence
print(answer["sparql"])   # the query it actually ran - read this
```

Requests go to [OpenRouter](https://openrouter.ai) by default: set `OPENROUTER_API_KEY`, and
optionally `OPENROUTER_MODEL` (the default is `google/gemini-2.5-flash-lite`). `LLM.Constructor`
takes a `baseURL`, so any OpenAI-compatible endpoint — including a local one — works too.

**Know the limit.** The repair loop validates *syntax* and *vocabulary*. Nothing validates
*meaning*. A model can invert the direction of a relationship and produce a query that is perfectly
valid, passes every check, returns no rows, and yields a confident but wrong answer — tutorial 02
demonstrates exactly this and checks the model's work against a hand-written query. Read the
generated SPARQL, which is why `RDFQueryByPrompt` returns it, and treat an empty result as
suspicious rather than as an answer.

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
