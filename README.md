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

Nine runnable notebooks live in [`tutorials/`](https://github.com/angelomassafra/btwin/blob/main/tutorials), numbered in the order they are
meant to be read. Each sits in its own self-contained folder and is committed with its outputs, so
they can be read on GitHub without running anything.

| # | Tutorial | What it covers |
|---|---|---|
| 00 | [Early adopters](https://github.com/angelomassafra/btwin/blob/main/tutorials/00-early-adopters/early-adopters.ipynb) | The reference walkthrough: every module, method by method — schema, spatial elements, equipment, properties, KPIs, points and observations, serialization, graph operations. |
| 01 | [Create a BTwin graph](https://github.com/angelomassafra/btwin/blob/main/tutorials/01-create-a-btwin-graph/create-a-btwin-graph.ipynb) | Builds a two-storey office from synthetic data — spatial hierarchy, property sets, sensors, a KPI set, documents — then serializes, queries and draws it. No LLM. |
| 02 | [Move a graph between formats](https://github.com/angelomassafra/btwin/blob/main/tutorials/02-graph-formats/graph-formats.ipynb) | The same graph through JSON-LD, NetworkX, RDF/SPARQL and Neo4j, with a measured account of what each conversion keeps or drops. No LLM. |
| 03 | [LLM in action](https://github.com/angelomassafra/btwin/blob/main/tutorials/03-llm-in-action/llm-in-action.ipynb) | Builds a graph from an English prompt and queries it in English. Shows the validate-and-repair loop, what it catches and — importantly — what it does not. Requires an API key. |
| 04 | [Chat with a graph](https://github.com/angelomassafra/btwin/blob/main/tutorials/04-chat-with-graph/chat-with-graph.ipynb) | Turns those one-shot cycles into a conversation: a follow-up question that resolves against what was already said, and an edit shown as a triple diff before it lands. Requires an API key. |
| 05 | [Timeseries management](https://github.com/angelomassafra/btwin/blob/main/tutorials/05-timeseries-management/timeseries-management.ipynb) | Leaves the graph for the readings. A week of sensor data into SQLite and back out: the typed query API, raw SQL on a read-only connection, the block that describes a table to something that has never seen it, and an edit rehearsed in a transaction before it is kept. No LLM. |
| 06 | [Chat with a timeseries table](https://github.com/angelomassafra/btwin/blob/main/tutorials/06-chat-with-timeseries/chat-with-timeseries.ipynb) | Hands all of that to a model: a question answered in SQL, what the validator catches, what `notes` buys you (a unit error four times too large that reads exactly like a right answer), an edit confirmed before it commits, and a conversation. Requires an API key. |
| 07 | [Integrate graph and timeseries](https://github.com/angelomassafra/btwin/blob/main/tutorials/07-integrate-graph-and-timeseries/integrate-graph-and-timeseries.ipynb) | Joins the two halves into one twin. A `btwin:Document` per database, a SPARQL locator that answers *where would I look?*, one SQL query compiled against every file it found, and a figure neither half could produce — consumption per square metre — recorded back onto the buildings. No LLM. |
| 08 | [Chat with a twin](https://github.com/angelomassafra/btwin/blob/main/tutorials/08-chat-with-twin/chat-with-twin.ipynb) | Puts a model in front of that pipeline, in exactly three places: writing the locator, writing the SQL, and naming the KPIs in a plan. One entry point routes a question to the graph, the readings or both, and a `derive` edit reads the databases and writes the graph — shown before it lands. Requires an API key. |

00 is a reference to look things up in; 01 to 08 are a narrative. They come in pairs, and the
pairing is the point:

- **01–04 are about the graph** — what a building *is*. 01 builds one by hand, 02 moves it between
  formats, 03 hands the building and the querying to a model, 04 makes that a conversation.
- **05–06 are about the readings** — what the building *did*. 05 builds and queries a table with no
  model; 06 hands the same table to one. 03 is to 05 what 04 is to 06: the two halves of the
  library are deliberately shaped the same way, so a page of 06 read beside a page of 04 shows what
  changes when the thing being questioned is a table rather than a graph.
- **07–08 join the halves into one twin.** 07 drives every step by hand, with no model anywhere;
  08 puts a model in front of exactly those steps. Read them in that order — 08 is much easier to
  trust once you have seen what it is driving.

Five of the nine call no model at all — 00, 01, 02, 05 and 07 — and bill nothing (00 and 02 will
use a Neo4j database if one is reachable, and carry on without it). The other four — 03, 04, 06 and
08 — need `OPENROUTER_API_KEY` and are billed to your key; each prints its own `CostMeter` total,
and the committed runs cost between $0.0015 and $0.0083 on the default model.

Tutorials 01 to 03 write a self-contained interactive HTML page after every stage into their own
`output/` folder, so you can click through the graph as it grows — open any `step-*.html` directly
in a browser. The later ones keep their artefacts the same way, always writing an edit to a copy so
the starting point survives: 04 keeps the graph as built and as edited in Turtle, 05 and 06 keep
two SQLite files each, and 07 and 08 keep a whole twin — six SQLite databases plus the graph that
points at them.

Each folder is self-contained: 02 ships its own copy of 01's JSON-LD in `input/`, and 03 to 08
generate everything they need, so any notebook can be run on its own. Run each one **from inside
its own folder**, since the paths are relative to it:

```bash
pip install "btwin[viz,rdf,llm]" neo4j
jupyter lab tutorials/
```

See [`tutorials/README.md`](https://github.com/angelomassafra/btwin/blob/main/tutorials/README.md) for exactly what each one needs, what it costs and what it writes.

## Language models

BTwin does not need a language model. Every module listed above works without one, and five of the
nine tutorials never call out to a provider. The optional `btwin.llm` module adds a natural-language
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
| `Cycle.SQLiteQueryByPrompt` | English question → SQL → rows → an English answer, over a table of observations |
| `Cycle.RDFEditByPrompt` | English request → a validated SPARQL `UPDATE` |
| `Cycle.SQLiteEditByPrompt` | English request → a validated SQL write, rehearsed before it is committed |
| `Cycle.DocumentCreateByPrompt` | A PDF → an inferred `Document` node with its property set |
| `Cycle.RDFChatTurn` | One conversation turn: route it, then answer or edit |
| `Cycle.RDFChat` | The same, as a terminal chat that keeps its own history |
| `Cycle.SQLiteChatTurn` | One conversation turn over a table: route it, then answer or edit |
| `Cycle.SQLiteChat` | The same, as a terminal chat that keeps its own history |
| `Cycle.TwinQueryByPrompt` | English question → routed to the graph, the readings or both → an English answer |
| `Cycle.TwinChatTurn` | One conversation turn over a whole twin, including a `derive` edit that reads the databases and writes KPIs back onto the graph |
| `Cycle.TwinChat` | The same, as a terminal chat that keeps its own history |

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

### Talking to a graph

`Cycle.RDFChat` is a terminal chat over the two RDF cycles. Each turn is routed first: a question
goes to `RDFQueryByPrompt`, an edit to `RDFEditByPrompt`, and anything else is answered from the
conversation alone. The router is also where the memory lives — it rewrites "and on the second
floor?" into a question that stands on its own, so the cycles underneath stay stateless and an
answer is still written from retrieved rows and nothing else.

```python
from btwin import RDF, Cycle

graph = RDF.ByTTL("spatialHierarchy.ttl", baseIRI="https://example.org/frv9/")
Cycle.RDFChat(graph, savePath="spatialHierarchy_edited.ttl")
```

An edit is shown as a triple diff and applied only if you confirm it, then written to `savePath` —
never to the file the graph was read from. `Cycle.RDFChatTurn` is the same logic without the
terminal, for a notebook or an application.

**Know the limit.** The repair loop validates *syntax* and *vocabulary*. Nothing validates
*meaning*. A model can invert the direction of a relationship and produce a query that is perfectly
valid, passes every check, returns no rows, and yields a confident but wrong answer — tutorial 03
demonstrates exactly this and checks the model's work against a hand-written query. `RDF.Chains`
exists to narrow that gap: it hands the writer the multi-hop paths the data actually walks, each
with a real example, so the composition is given rather than guessed. Read the generated SPARQL,
which is why `RDFQueryByPrompt` returns it and why the chat prints it every turn, and treat an
empty result as suspicious rather than as an answer.

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
