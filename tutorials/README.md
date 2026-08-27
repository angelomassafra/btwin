# Tutorials

Runnable, end-to-end notebooks. Each one builds something complete rather than walking the API
method by method — for that, see [`docs/tutorials/tutorial.ipynb`](../docs/tutorials/tutorial.ipynb).

| Notebook | What it covers |
|---|---|
| [`create-a-btwin-graph.ipynb`](create-a-btwin-graph.ipynb) | Builds one small building graph from synthetic data — spatial hierarchy, property sets, sensors, a KPI set and documents — serializes it to JSON-LD, queries it, and draws it. No LLM. |

## Running them

```bash
pip install "btwin[viz]"
jupyter lab tutorials/
```

Notebooks are committed with their outputs, so they read correctly on GitHub without being run.

## Generated files

Running a notebook writes into `tutorials/output/`. The JSON-LD and the interactive HTML page are
committed so they can be browsed without running anything; the PNG is not, since the same figure is
already embedded in the notebook.
