# LLM, Tool & Cycle

Four things live in `btwin.llm`, in widening order of specificity:

- **`LLM`** — the connection to an OpenAI-compatible chat model (OpenRouter by default). It
  knows nothing about buildings, RDF or JSON-LD, so any cycle can use it.
- **`CostMeter`** — the tokens and money a run spends.
- **`Tool`** — the individual steps a pipeline is built from: one model call, or one
  deterministic helper that prepares or checks what a model produced. Every method does its
  one thing and returns; the prompts live here too, beside the method that sends them.
- **`Cycle`** — one method per complete pipeline, chaining those steps. A cycle owns the
  control flow and nothing else: which tool runs when, how often a rejected result may be
  sent back, and what the caller gets at the end.

Tools reuse the deterministic library rather than reimplementing it:
[`RDF` and `SPARQL`](graph.md) do the graph and query work, `Schema`, `Serialization` and
`SpatialElement` supply the BTwin vocabulary and notation.

Install the optional dependencies with `pip install btwin[llm]`, and put an OpenRouter key in
`OPENROUTER_API_KEY`.

## The cycles

`Cycle.RDFQueryByPrompt` answers a question **from** an existing graph:

```python
from btwin import RDF, LLM, Cycle, CostMeter

graph = RDF.ByTTL("spatialHierarchy.ttl", baseIRI="https://example.org/frv9/")
llm = LLM.Constructor()
meter = CostMeter()

result = Cycle.RDFQueryByPrompt(
    graph, "Which storey is the Appartamento zone on?", llm=llm, meter=meter,
)
print(result["answer"], result["sparql"], result["source"])
print(CostMeter.Describe(meter.Total()))
```

`Cycle.JSONLDCreateByPrompt` goes the other way and **builds** a graph from a description.
The whole document arrives in one reply, so raise `maxTokens` well above the default:

```python
from btwin import LLM, Cycle, NetworkX

llm = LLM.Constructor(maxTokens=32000)
result = Cycle.JSONLDCreateByPrompt(
    "1 building, 3 floors, 10 spaces per floor, each space has 4 sensors", llm=llm,
)
graph = NetworkX.ByJSONLD(jsonld=result["jsonld"])
```

Both return a `usage` dict, and both take a shared `CostMeter` so a run can be subtotalled
per question. Both accept `verbose=True` to print each agent's outcome and cost.

`Cycle.DocumentCreateByPrompt` reads a PDF and builds the `Document`, its `PropertySet` and
the node it belongs to. The PDF is read as text when it has a text layer and as page images
when it does not, so a scan works too. Nothing is wired into the graph: the result names the
owning node and leaves the linking to you, so a wrong inference can be seen before it lands.

```python
from btwin import Cycle, SpatialElement

plan = Cycle.DocumentCreateByPrompt(
    "document/A3 PLN_244316736_1.pdf",
    "Create a PSet named 'Dati catastali' with exactly these properties: "
    "Foglio, Particella, Subalterno, Comune, Indirizzo, Piano.",
    objects=[site, building, *storeys, *spaces, zone],
    mode="manual",          # 'auto' lets the model choose the properties itself
)
SpatialElement.SetRelationship(
    spatialElementObject=plan["linkToObject"],
    relationshipName="btwin:hasDocument",
    linkedObject=plan["document"],
)
```

`mode="auto"` leaves the property set to the model; `mode="manual"` binds it to the prompt,
which names the set and the properties to extract. Reading a PDF needs `pip install btwin[pdf]`
(`pypdf` for the text layer, `pymupdf` to render a scan).

### Editing what already exists

The two create cycles have an edit counterpart each, for a model that already exists and has to
change: "add two spaces on floor 2", "remove the sensors in S07", "link the zone to the storey".

`Cycle.JSONLDEditByPrompt` edits a JSON-LD document. The model writes a **patch**, never the
document: `addNodes`, `removeNodes`, `addRelationships`, `removeRelationships`, `renameNodes`.
The patch is applied deterministically by `Tool.JSONLDApplyEdit` and the result goes through the
same `Tool.JSONLDValidate` the create cycle uses, so a node the request never mentions cannot be
dropped or reworded on the way through — and the reply stays the size of the edit rather than the
size of the graph:

```python
result = Cycle.JSONLDEditByPrompt(
    result["jsonld"], "add a CO2 sensor in every space on floor 1", llm=llm,
)
print(result["changes"])     # {'addNodes': 10, 'removeNodes': 0, ...}
```

The document you pass in is not modified; `result["jsonld"]` is a new one.

`Cycle.RDFEditByPrompt` does the same to a graph of triples, through SPARQL 1.1 Update. It is
`RDFQueryByPrompt` with the safety catch turned the other way: there the model writes a SELECT and
may not write, here it writes an update and nothing else. `SPARQL.ValidateUpdate` holds it to an
INSERT or a DELETE in the default graph, and `Tool.RDFApplyUpdate` runs it against a **copy**, so
the change can be read before it is committed:

```python
edit = Cycle.RDFEditByPrompt(graph, "add a temperature sensor in the Camera", llm=llm)
print(edit["added"], edit["removed"])   # triples, compacted
graph = edit["graph"]                   # or pass inPlace=True to commit to your own
```

New IRIs are the one thing the model invents, because a node being added does not exist yet. An
update that runs but changes nothing is this cycle's empty SELECT, and gets the same treatment: one
rewrite, kept only if it actually moves a triple.

### Holding a conversation

The two RDF cycles each take one self-contained prompt and remember nothing. `Cycle.RDFChat`
puts a conversation on top of them without changing that.

Every turn is routed first. `Tool.ChatRoute` reads the transcript and the new message and
returns an intent with a **restatement that stands on its own**:

```python
{"intent": "question", "request": "Which sensors are on the second floor?"}
```

from a message that was only `and the second floor?`. That restatement is what reaches
`RDFQueryByPrompt` or `RDFEditByPrompt`, so the cycles stay exactly as they were, and the
transcript never enters the window where an answer is written from retrieved rows. An intent of
`talk` — a greeting, or "what did I just ask?" — is answered from the conversation alone and
touches no graph, so it cannot become a SPARQL query that confidently returns nothing.

`Cycle.RDFChatTurn` is one turn, with no terminal attached: it returns the updated history and
the caller passes it back for the next one.

```python
history, schema, chains = [], None, None
for message in ["Which spaces are on the first floor?", "and on the ground floor?"]:
    turn = Cycle.RDFChatTurn(graph, message, history=history, schema=schema, chains=chains)
    history, schema, chains = turn["history"], turn["schema"], turn["chains"]
    print(turn["request"], "->", turn["answer"])
```

Nothing is read from a keyboard there, and the graph does not move on its own. An edit runs
against a copy, and a `confirm` callable decides whether the caller's graph follows:

```python
turn = Cycle.RDFChatTurn(
    graph, "add a storage room on the first floor",
    confirm=lambda proposal: True,          # or show proposal["added"] and ask
)
```

Passing no `confirm` proposes the edit without applying it, which is how you see what an
instruction *would* do. After an applied edit the schema and the chains are rebuilt, because
both describe the graph as it was and the next question must not be grounded in a graph that
has moved.

`Cycle.RDFChat` is the same logic as a terminal chat, and the only thing in the module that
reads a keyboard:

```python
session = Cycle.RDFChat(graph, savePath="spatialHierarchy_edited.ttl")
print(session["edits"], session["saved"])
```

An edit is printed as a triple diff and applied only on `y`. Each one that lands is written to
`savePath` immediately — `autoSave=True` by default, so a session cannot end with confirmed
edits lost to a forgotten command. **`savePath` must not be the file the graph was read from**:
an edit is the model's work, and overwriting the source leaves nothing to compare it against.
A session that only asks questions writes nothing at all.

Every turn prints the query it ran and what it cost, because the reading that catches a wrong
answer is the query rather than the sentence; `silent=True` leaves only the answers. The
commands are `/sparql`, `/history`, `/schema`, `/cost`, `/silent`, `/verbose`, `/save` and
`/exit`, and Escape leaves too — at the edit confirmation it means no.

### Paths through the graph

`RDFQueryByPrompt` grounds the writer on `RDF.SchemaSummary` **and** [`RDF.Chains`](graph.md),
rendered by `Tool.RDFChainBlock`. SHAPES gives one hop at a time; chains give the multi-hop
paths the data actually walks, each with a real example, so the composition is handed over
instead of guessed — and the example fixes the direction, since "Cucina is located in Piano
Terra" cannot be read backwards while an arrow between two class names can.

Both are computed for you. Pass them in to reuse them across questions, or pass `chains=[]`
to ground the writer on the schema alone:

```python
schema, chains = RDF.SchemaSummary(graph), RDF.Chains(graph)
for question in questions:
    result = Cycle.RDFQueryByPrompt(graph, question, schema=schema, chains=chains, meter=meter)
```

Chains cost tokens: on a small building graph the block roughly doubles the grounding. They
buy the most where a question needs several hops, or where two different routes join the same
pair of classes.

Reaching for a single step instead of a whole cycle is a `Tool` call:

```python
from btwin import RDF, LLM, Tool, SPARQL

schema = RDF.SchemaSummary(graph)
grounding = schema["text"] + "

" + Tool.RDFChainBlock(RDF.Chains(graph))
sparql = Tool.RDFWriteSPARQL(llm, grounding, "How many spaces are there?")
checked, error = SPARQL.Validate(sparql, schema["terms"])
```

## Cycle

::: btwin.llm.Cycle
    options:
      members_order: source
      show_source: true

## Tool

::: btwin.llm.Tool
    options:
      members_order: source
      show_source: true

## LLM

::: btwin.llm.LLM
    options:
      members_order: source
      show_source: true

## CostMeter

OpenRouter reports the real charge for every call, so the total is what was actually billed
rather than an estimate from a price table.

::: btwin.llm.CostMeter
    options:
      members_order: source
      show_source: true
