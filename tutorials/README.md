# Tutorials

Runnable, end-to-end notebooks, numbered in the order they are meant to be read. Each one lives in
its own folder with its own inputs and outputs, and each is committed with its outputs so it reads
correctly on GitHub without being run.

| # | Tutorial | What it covers |
|---|---|---|
| 00 | [`early-adopters`](00-early-adopters/early-adopters.ipynb) | The reference walkthrough: every module, method by method — schema, spatial elements, equipment, properties, KPIs, points and observations, serialization, graph operations. Start here if you want the whole API surface. |
| 01 | [`create-a-btwin-graph`](01-create-a-btwin-graph/create-a-btwin-graph.ipynb) | Builds one small building graph from synthetic data — spatial hierarchy, property sets, sensors, a KPI set and documents — serializes it to JSON-LD, queries it, and draws it. No LLM. |
| 02 | [`graph-formats`](02-graph-formats/graph-formats.ipynb) | Moves that graph between JSON-LD, NetworkX, RDF/SPARQL and Neo4j, and measures what each hop keeps or drops. |
| 03 | [`llm-in-action`](03-llm-in-action/llm-in-action.ipynb) | Builds a graph from an English prompt and queries it in English, via `Cycle`. Shows the validate-and-repair loop, what it catches, and — importantly — what it does not. |
| 04 | [`chat-with-llm`](04-chat-with-llm/chat-with-llm.ipynb) | Turns those one-shot cycles into a conversation: a follow-up that resolves against what was already said, an edit shown before it lands, and where the edited graph is written. |

00 is a reference; 01 to 04 are a narrative. Read 00 when you want to look something up, and 01
onward when you want to see a whole graph built and used.

Each folder is self-contained: 02 ships its own copy of 01's JSON-LD in `input/`, and 03 and 04
generate everything they need. You can run any of them on its own, in any order.

## Step-by-step graph views

Tutorials 01 to 03 write an interactive HTML page after each stage into their own `output/` folder,
named `step-01-*.html`, `step-02-*.html` and so on. They are embedded in the notebooks and also open
directly in a browser — each is a single self-contained file with no CDN to reach and nothing to
install. Click a node to inspect its attributes, drag to rearrange, use the legend to hide a class.

Watching the node count climb is the quickest way to see what each section actually added:

- **01** — 8 nodes (spatial) → 12 (property sets) → 19 (sensors) → 22 (complete) → 18 (flattened)
- **02** — the same 22 nodes through each conversion, then 18 once property sets are folded in
- **03** — 11 nodes written by the model → 13 after the JSON-LD edit → 14 after the RDF edit

04 writes Turtle rather than HTML pages: `riverside.ttl` as built, and `riverside_edited.ttl`
after the chat's edit, so the two can be diffed.

## Running them

```bash
pip install "btwin[viz,rdf,llm]" neo4j
jupyter lab tutorials/
```

Run each notebook **from inside its own folder**, since the paths are relative to it.

## What each one needs

- **00** — `btwin[viz,rdf]`. Its Neo4j cell is wrapped in a `try`, so it reports the connection
  error and carries on. It writes scratch files into its own `output/`.
- **01** — nothing beyond `btwin[viz]`; runs entirely offline.
- **02** — `btwin[rdf]`. Its Neo4j section is skipped unless `NEO4J_URI` and `NEO4J_PASSWORD` are
  set; everything else runs offline.
- **03** — `btwin[llm]` and `OPENROUTER_API_KEY`, and **every run is billed to your key**. On the
  default model (`google/gemini-2.5-flash-lite`) a full pass is about $0.003; the notebook prints
  its own `CostMeter` total at the end. Its outputs will not reproduce exactly.
- **04** — `btwin[llm,rdf]` and `OPENROUTER_API_KEY`, billed the same way; the committed run cost
  $0.0015 over 17 calls. It builds its own graph with no model, so only the conversation is paid
  for. `Cycle.RDFChat`, the terminal chat, blocks on input and so is
  described rather than run, with the few lines that wire it to a graph on disk.

## Generated files

Running a notebook writes into its own `output/`. The JSON-LD, Turtle and interactive HTML pages
are committed so they can be browsed without running anything; PNGs, spreadsheets and SQLite
databases are not, since they are either already embedded in the notebook or pure scratch.
