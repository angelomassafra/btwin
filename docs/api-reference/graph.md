# Graph (NetworkX, RDF & SPARQL)

A JSON-LD document from [`Serialization`](serialization.md) becomes a graph in one of two
forms: a NetworkX labelled property graph, for traversal, reshaping and drawing, or an RDFLib
graph, for SPARQL and for grounding a language model. `SPARQL` checks a query before it is
run against the latter.

## NetworkX

`NetworkX.ByJSONLD` builds a `MultiDiGraph` — one node per object, one edge per relationship —
and validates its types against [`Schema`](schema.md), returning the graph with the report.

```python
from btwin import NetworkX

graph, report = NetworkX.ByJSONLD(jsonPath="model.json", printReport=False)
report["ok"]

graph = NetworkX.CompactPSets(graph)                 # properties onto their owner nodes
around = NetworkX.SubgraphByObjectUID(graph, "storey-01", nodeDegree=1)
spaces = NetworkX.NodeLinkedNodes(graph, "storey-01", linkedNodesType="bot:Space")

NetworkX.ToRDF(graph, "model.ttl")                   # or ToJSON, or ToNEO4J
```

::: btwin.graph.NetworkX
    options:
      members_order: source
      show_source: true

## RDF

`RDF.SchemaSummary` and `RDF.Chains` are what a language model is actually shown. The summary
describes the graph one hop at a time — prefixes, classes, predicates, the SHAPES list and the
labelled entities — and leaves composing those hops to the reader.

Composing is where a generated query goes wrong, so `RDF.Chains` does it in advance: it returns
the multi-hop paths the data really walks, each with one worked example from the graph itself.

```python
for chain in RDF.Chains(graph):
    print(chain["template"])    # bot:Space -brick:hasLocation-> bot:Storey -...-> bot:Site
    print(chain["example"])     # 'Cucina' -> 'Piano Terra' -> <...NgA> -> 'mySite'
```

Paths are enumerated over classes rather than instances, so the work does not grow with the size
of the graph, and every candidate is then confirmed by walking real triples — a composition no
data realises finds no example and is dropped rather than suggested. Trailing `rdfs:label` hops
and paths that are merely the opening of a longer one are left out, since both only repeat what
SHAPES already says.

::: btwin.graph.RDF
    options:
      members_order: source
      show_source: true

## SPARQL

Checks a query before it is allowed near a graph. Written for queries that come from a
language model — `SPARQL.Validate` refuses anything that writes, deletes or reaches out over
the network, and rejects vocabulary the graph does not contain.

`SPARQL.ValidateUpdate` is its counterpart for an edit, where writing is the point: it accepts
only an update opening with INSERT or DELETE, refuses everything that replaces or empties a
whole graph, and keeps the change in the default graph. Its vocabulary is deliberately wider
than a query's, because a node being added may carry a class the graph does not hold yet —
see `Tool.RDFEditTerms`.

::: btwin.graph.SPARQL
    options:
      members_order: source
      show_source: true
