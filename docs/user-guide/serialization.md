# Serialization

BTwin supports multiple serialization formats for exporting and importing building models.

## Namespace IRIs

The `Serialization.IRIs()` method returns the canonical namespace prefixes, class IRIs, and property IRIs used in exports:

```python
from btwin import Serialization

iris = Serialization.IRIs()

# Namespace prefixes
iris["prefixes"]    # {"brick": "https://brickschema.org/schema/Brick#", ...}

# Class IRIs
iris["classes"]     # {"bot:Site": "https://w3id.org/bot#Site", ...}

# Property/relationship IRIs
iris["properties"]  # {"brick:hasLocation": "https://brickschema.org/schema/Brick#hasLocation", ...}
```

## JSON-LD Export

Convert a list of BTwin objects into a JSON-LD document with `@context` and `@graph`:

```python
from btwin import SpatialElement, Serialization

site = SpatialElement.Constructor("site-01", "bot:Site", name="Campus")
building = SpatialElement.Constructor("bldg-01", "bot:Building", name="Main Hall")
SpatialElement.SetLocationRelationship(building, linkedObject=site)

jsonld = Serialization.JSONLDByObjects(
    [site, building],
    savePath="building.json"
)
```

The resulting document contains:

- `@context` — only the namespace prefixes actually used
- `@graph` — the flattened list of node dictionaries

### Strict Validation

By default, `strictValidation=True` raises errors for unknown classes or relationships. Set it to `False` to allow custom predicates:

```python
jsonld = Serialization.JSONLDByObjects(
    objects,
    strictValidation=False
)
```

## NetworkX JSON

Export and import NetworkX graphs as JSON:

```python
from btwin import NetworkX

# Export
NetworkX.ToJSON(G, savePath="graph.json")

# Import
G = NetworkX.ByJSON("graph.json")
```

## RDF Conversion

Convert a JSON-LD document into an RDF graph (requires `rdflib`):

```python
from btwin import RDF

rdf_graph = RDF.ByJSONLD(jsonld)
```
