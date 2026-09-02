# Tutorials

Hands-on, step-by-step walkthroughs that build complete working examples.

## Available Tutorials

### [Building a Spatial Model](building-model.md)

Create a full building hierarchy from site down to individual spaces, set all location relationships, export to JSON-LD, and build a NetworkX graph.

### [Equipment Inventory](equipment-inventory.md)

Generate an Excel equipment template, fill it with your building's assets, import it into BTwin, and attach equipment to spaces.

### [Timeseries Data](timeseries-data.md)

Create sensor points, build an observation DataFrame, write it to SQLite, and query it with filters and aggregations.

!!! note
    Each tutorial is self-contained. You can follow them in any order, though the spatial model tutorial provides useful context for the others.

## Runnable notebooks

The pages above are prose. The repository also ships nine Jupyter notebooks under
[`tutorials/`](https://github.com/AngeloMassafra/btwin/tree/main/tutorials), numbered in reading
order and committed with their outputs, so they can be read on GitHub without being run:

| # | Notebook | What it covers |
|---|---|---|
| 00 | `early-adopters` | The reference walkthrough: every module, method by method. |
| 01 | `create-a-btwin-graph` | One building graph built from synthetic data, serialized, queried and drawn. |
| 02 | `graph-formats` | That graph through JSON-LD, NetworkX, RDF/SPARQL and Neo4j, and what each hop keeps. |
| 03 | `llm-in-action` | A graph built from an English prompt and queried in English. |
| 04 | `chat-with-graph` | The same cycles as a conversation, with an edit shown before it lands. |
| 05 | `timeseries-management` | Readings into SQLite and back out; describing a table; editing it under a transaction. No LLM. |
| 06 | `chat-with-timeseries` | Questions, edits and a conversation over a table of readings. |
| 07 | `integrate-graph-and-timeseries` | The two halves joined: a `btwin:Document` per database, a SPARQL locator, one SQL query per file, and a KPI recorded back into the graph. No LLM. |
| 08 | `chat-with-twin` | The same twin asked questions in English — routed to the graph, the readings or both — and edited by asking. |

01–04 are about the graph — what a building *is*. 05–06 are about the readings — what it *did*.
07–08 join them into one twin: 07 by hand, 08 with a model in front of exactly the same pipeline.
