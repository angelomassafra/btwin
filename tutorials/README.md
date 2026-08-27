# Tutorials

Runnable, end-to-end notebooks, numbered in the order they are meant to be read. Each one lives in
its own folder with its own inputs and outputs, and each builds something complete rather than
walking the API method by method — for that, see
[`../docs/tutorials/tutorial.ipynb`](../docs/tutorials/tutorial.ipynb).

| # | Tutorial | What it covers |
|---|---|---|
| 00 | [`create-a-btwin-graph`](00-create-a-btwin-graph/create-a-btwin-graph.ipynb) | Builds one small building graph from synthetic data — spatial hierarchy, property sets, sensors, a KPI set and documents — serializes it to JSON-LD, queries it, and draws it. No LLM. |
| 01 | [`graph-formats`](01-graph-formats/graph-formats.ipynb) | Moves that graph between JSON-LD, NetworkX, RDF/SPARQL and Neo4j, and measures what each hop keeps or drops. |
| 02 | [`llm-in-action`](02-llm-in-action/llm-in-action.ipynb) | Builds a graph from an English prompt and queries it in English, via `Cycle`. Shows the validate-and-repair loop, what it catches, and — importantly — what it does not. |

Each folder is self-contained: 01 ships its own copy of 00's JSON-LD in `input/`, and 02 generates
everything it needs. You can run any of them on its own, in any order.

## Step-by-step graph views

Every notebook writes an interactive HTML page after each stage into its own `output/` folder, named
`step-01-*.html`, `step-02-*.html` and so on. They are embedded in the notebooks and also open
directly in a browser — each is a single self-contained file with no CDN to reach and nothing to
install. Click a node to inspect its attributes, drag to rearrange, use the legend to hide a class.

Watching the node count climb is the quickest way to see what each section actually added:

- **00** — 8 nodes (spatial) → 12 (property sets) → 19 (sensors) → 22 (complete) → 18 (flattened)
- **01** — the same 22 nodes through each conversion, then 18 once property sets are folded in
- **02** — 11 nodes written by the model → 13 after the JSON-LD edit → 14 after the RDF edit

## Running them

```bash
pip install "btwin[viz,rdf,llm]" neo4j
jupyter lab tutorials/
```

Run each notebook **from inside its own folder**, since the paths are relative to it.

Notebooks are committed with their outputs, so they read correctly on GitHub without being run.

## What each one needs

- **00** — nothing beyond `btwin[viz]`; runs entirely offline.
- **01** — `btwin[rdf]`. Its Neo4j section is skipped unless `NEO4J_URI` and `NEO4J_PASSWORD` are
  set; everything else runs offline.
- **02** — `btwin[llm]` and `OPENROUTER_API_KEY`, and **every run is billed to your key**. On the
  default model (`google/gemini-2.5-flash-lite`) a full pass is about $0.003; the notebook prints
  its own `CostMeter` total at the end. Its outputs will not reproduce exactly.

## Generated files

Running a notebook writes into its own `output/`. The JSON-LD, Turtle and interactive HTML pages
are committed so they can be browsed without running anything; PNGs are not, since the same figure
is already embedded in the notebook.
