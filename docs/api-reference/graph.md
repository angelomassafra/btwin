# Graph (NetworkX & RDF)

Graph operations for building, querying, and exporting knowledge graphs.

## NetworkX

::: btwin.graph.NetworkX
    options:
      members_order: source
      show_source: true

## RDF

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
