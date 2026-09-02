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
| 04 | [`chat-with-graph`](04-chat-with-graph/chat-with-graph.ipynb) | Turns those one-shot cycles into a conversation: a follow-up that resolves against what was already said, an edit shown before it lands, and where the edited graph is written. |
| 05 | [`timeseries-management`](05-timeseries-management/timeseries-management.ipynb) | Leaves the graph for the readings. A week of sensor data into SQLite and back out — the typed query API, raw SQL on a read-only connection, the block that describes a table to something that has never seen it, and an edit rehearsed inside a transaction before it is kept. No LLM. |
| 06 | [`chat-with-timeseries`](06-chat-with-timeseries/chat-with-timeseries.ipynb) | Hands all of that to a model: a question answered in SQL, what the validator catches, what `notes` buys you (a unit error that is four times too large and reads exactly like a right answer), an edit confirmed before it commits, and a conversation. |
| 07 | [`integrate-graph-and-timeseries`](07-integrate-graph-and-timeseries/integrate-graph-and-timeseries.ipynb) | Joins the two halves into one twin. A `btwin:Document` per database, a SPARQL locator that answers *where would I look?*, one SQL query compiled against every file it found, and a figure neither half could produce — readings divided by floor area — recorded back onto the buildings. No LLM. |
| 08 | [`chat-with-twin`](08-chat-with-twin/chat-with-twin.ipynb) | Puts a model in front of that pipeline, in exactly three places: writing the locator, writing the SQL, and naming the KPIs in a plan. One entry point routes a question to the graph, the readings or both, and a `derive` edit reads the databases and writes the graph — shown before it lands. |

00 is a reference; 01 to 08 are a narrative. Read 00 when you want to look something up, and 01
onward when you want to see a whole graph built and used.

01 to 04 are about the **graph** — what a building is. 05 and 06 are about the **readings** —
what it did. They pair up: 03 is to 05 what 04 is to 06, and the two halves of the library are
deliberately shaped the same way, so a page of 06 read beside a page of 04 shows what changes when
the thing being questioned is a table rather than a graph.

07 and 08 join the two halves into one twin, and pair up the same way: 07 drives every step by
hand, with no model anywhere, and 08 puts a model in front of exactly those steps. Read them in
that order — 08 is much easier to trust once you have seen what it is driving.

Each folder is self-contained: 02 ships its own copy of 01's JSON-LD in `input/`, and 03 to 08
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

05 and 06 write SQLite the same way — `office.db` and `office_corrected.db`, `rooms.db` and
`rooms_corrected.db` — for the same reason. An edit goes to a copy, so the readings you started
from are still there to compare against.

07 and 08 write a whole twin: six SQLite files under `output/databases/`, plus the graph that
points at them. 07 keeps `harbourside.ttl` as built and `harbourside_kpis.ttl` with the KPIs it
computed by hand; 08 keeps `harbourside.ttl` and `harbourside_edited.ttl`, the same graph after the
conversation derived them by asking.

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
- **05** — nothing beyond a plain `btwin` install; runs entirely offline and calls no model. It
  writes two SQLite files into its own `output/`.
- **06** — `btwin[llm]` and `OPENROUTER_API_KEY`, billed to your key; the committed run cost
  $0.0015 over 17 calls. It generates its own table with no model, so only the questions and the
  edit are paid for. `Cycle.SQLiteChat`, the terminal chat, blocks on input and so is described
  rather than run. Its outputs will not reproduce exactly.
- **07** — `btwin[rdf]`. No API key, no network, nothing billed: every step is SPARQL, SQL and
  arithmetic you can read. It builds both halves itself and writes six SQLite files and two
  Turtle graphs into its own `output/`.
- **08** — `btwin[llm,rdf]` and `OPENROUTER_API_KEY`, billed to your key; the committed run cost
  $0.0083 over 36 calls. It rebuilds 07's twin with no model, so only the questions, the
  conversation and the derived edit are paid for. `Cycle.TwinChat`, the terminal chat, blocks on
  input and so is described rather than run. Its outputs will not reproduce exactly.

## Generated files

Running a notebook writes into its own `output/`. The JSON-LD, Turtle and interactive HTML pages
are committed so they can be browsed without running anything; PNGs, spreadsheets and SQLite
databases are not, since they are either already embedded in the notebook or pure scratch.
