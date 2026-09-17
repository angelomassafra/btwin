# Schema

`Schema` is the vocabulary the rest of BTwin is checked against. It has two tables:

- **`Types()`** — the classes an object may have, keyed by CURIE (`bot:Space`, `brick:Zone`,
  `ifc:IfcPropertySet`, `btwin:KPISet`, …), each with its full IRI.
- **`RelationshipNames()`** — the predicates, and for each one the `(subject, object)` class
  pairs it may connect.

```python
from btwin import Schema

types = Schema.Types()
types["bot:Space"]                      # {'IRI': 'https://w3id.org/bot#Space', ...}

rels = Schema.RelationshipNames()
pairs = rels["brick:hasLocation"]["pairs"]
[(p["subject"]["label"], p["object"]["label"]) for p in pairs][:3]
# [('bot:Space', 'bot:Storey'), ...]
```

`SetRelationship(..., validate=True)` and [`NetworkX.Validate`](graph.md) consult these
tables. JSON-LD export uses a wider vocabulary that also covers every Brick equipment and
point class — see [`Serialization.IRIs`](serialization.md).

::: btwin.schema.Schema
    options:
      members_order: source
      show_source: true
