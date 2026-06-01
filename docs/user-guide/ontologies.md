# Ontologies

BTwin builds on three open standards for describing buildings and their systems.

## Brick Schema

[Brick](https://brickschema.org/) is a metadata schema for buildings. It defines classes for equipment, points (sensors, setpoints, commands), and relationships like `brick:hasLocation`, `brick:feeds`, and `brick:isPartOf`.

BTwin uses Brick for:

- Equipment types (e.g., `brick:Air_Handling_Unit`, `brick:Fan_Coil_Unit`)
- Sensor/point types (e.g., `brick:Temperature_Sensor`, `brick:CO2_Sensor`)
- Location and feeding relationships

## BOT (Building Topology Ontology)

[BOT](https://w3id.org/bot) is a W3C-backed ontology for building topology. It defines the spatial hierarchy:

- `bot:Site` — a campus or plot of land
- `bot:Building` — a building within a site
- `bot:Storey` — a level within a building
- `bot:Space` — a room or bounded area within a storey

BTwin uses BOT types as the primary spatial element classes.

## IFC (Industry Foundation Classes)

[IFC](https://www.buildingsmart.org/standards/bsi-standards/industry-foundation-classes/) is the buildingSMART data model for BIM. BTwin uses IFC concepts for:

- Property sets (`ifc:IfcPropertySet`) — structured property containers
- Property types (`IfcPropertySingleValue`, `IfcPropertyEnumeratedValue`)
- The `ifc:HasPropertySets` relationship

## Exploring Types and Relationships

Use `Schema` to inspect the available types and relationship patterns:

```python
from btwin import Schema

# All canonical types (spatial, equipment, points, etc.)
types = Schema.Types()
for label, info in types.items():
    print(f"{label}: {info['description']}")

# Relationship patterns (subject-predicate-object triples)
rels = Schema.RelationshipNames()
for predicate, definition in rels.items():
    print(f"{predicate} — {len(definition['pairs'])} allowed pair(s)")
```

The `Schema.Types()` dictionary maps CURIE labels to their IRIs and descriptions. `Schema.RelationshipNames()` returns the valid subject-object pairs for each predicate, which is used for validation when `validate=True` is passed to relationship setters.
