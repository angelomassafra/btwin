# Serialization

`Serialization.JSONLDByObjects` collects BTwin objects — spatial elements, equipment, points,
property sets, KPI sets, scenarios, documents — into one JSON-LD document with an `@context`
and an `@graph`. Nested lists are flattened, so the output of `SpatialHierarchy.ByIFC` or
`Inventory.ToJSONLD` can be passed as it is.

```python
from btwin import SpatialElement, Serialization, NetworkX, RDF

building = SpatialElement.Constructor("bldg-01", "bot:Building", name="Main Hall")
storey = SpatialElement.Constructor("storey-01", "bot:Storey", name="Ground Floor")
SpatialElement.SetLocationRelationship(storey, linkedObject=building)

jsonld = Serialization.JSONLDByObjects([building, storey], savePath="model.json")

graph, report = NetworkX.ByJSONLD(jsonld)                 # labelled property graph
rdfGraph, turtle = RDF.ByJSONLD(jsonld, "model.ttl")      # RDF, also written as Turtle
```

Every class and predicate is checked against `Serialization.IRIs()`, which holds the prefixes
and term IRIs the export is written with, extended with every type `Point.Types()` and
`Equipment.Types()` accept. With `strictValidation=True` (the default) an unknown term raises;
with `False` it is exported anyway.

::: btwin.serialization.Serialization
    options:
      members_order: source
      show_source: true
