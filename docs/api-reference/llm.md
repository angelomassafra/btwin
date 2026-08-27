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

Reaching for a single step instead of a whole cycle is a `Tool` call:

```python
from btwin import RDF, LLM, Tool, SPARQL

schema = RDF.SchemaSummary(graph)
sparql = Tool.RDFWriteSPARQL(llm, schema["text"], "How many spaces are there?")
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
