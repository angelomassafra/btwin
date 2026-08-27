# Tutorials

Runnable, end-to-end notebooks. Each one builds something complete rather than walking the API
method by method — for that, see [`docs/tutorials/tutorial.ipynb`](../docs/tutorials/tutorial.ipynb).

| Notebook | What it covers |
|---|---|
| [`create-a-btwin-graph.ipynb`](create-a-btwin-graph.ipynb) | Builds one small building graph from synthetic data — spatial hierarchy, property sets, sensors, a KPI set and documents — serializes it to JSON-LD, queries it, and draws it. No LLM. |
| [`graph-formats.ipynb`](graph-formats.ipynb) | Moves that graph between JSON-LD, NetworkX, RDF/SPARQL and Neo4j, and measures what each hop keeps or drops. Run the first notebook before this one. |
| [`llm-in-action.ipynb`](llm-in-action.ipynb) | Builds a graph from an English prompt and queries it in English, via `Cycle`. Shows the validate-and-repair loop, what it catches, and — importantly — what it does not. Calls a real API and costs money. |

## Running them

```bash
pip install "btwin[viz,rdf,llm]" neo4j
jupyter lab tutorials/
```

The first two notebooks run entirely offline, except that `graph-formats.ipynb` skips its Neo4j
section unless `NEO4J_URI` and `NEO4J_PASSWORD` are set.

`llm-in-action.ipynb` is different: it needs `OPENROUTER_API_KEY` and **every run is billed to your
key**. On the default model (`google/gemini-2.5-flash-lite`) a full pass is around $0.003; the
notebook prints its own `CostMeter` total at the end. Its outputs will not reproduce exactly.

Notebooks are committed with their outputs, so they read correctly on GitHub without being run.

## Generated files

Running a notebook writes into `tutorials/output/`. The JSON-LD and the interactive HTML page are
committed so they can be browsed without running anything; the PNG is not, since the same figure is
already embedded in the notebook.
