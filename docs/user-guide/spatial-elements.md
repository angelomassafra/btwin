# Spatial Elements

Spatial elements represent building topology: sites, buildings, storeys, spaces, and zones.

## Creating Spatial Elements

Use `SpatialElement.Constructor` to create a spatial element dictionary:

```python
from btwin import SpatialElement

site = SpatialElement.Constructor("site-01", "bot:Site", name="Campus")
building = SpatialElement.Constructor("bldg-01", "bot:Building", name="Main Hall")
storey = SpatialElement.Constructor("storey-01", "bot:Storey", name="Ground Floor")
space = SpatialElement.Constructor("space-01", "bot:Space", name="Room 101")
```

The type must be one of the types defined in `Schema.Types()` (e.g., `bot:Site`, `bot:Building`, `bot:Storey`, `bot:Space`, `brick:Zone`, `brick:Energy_Zone`).

## Setting Location Relationships

The `SetLocationRelationship` method links a spatial element to its parent location using `brick:hasLocation`:

```python
SpatialElement.SetLocationRelationship(building, linkedObject=site)
SpatialElement.SetLocationRelationship(storey, linkedObject=building)
SpatialElement.SetLocationRelationship(space, linkedObject=storey)
```

You can also specify the target by UID and type directly:

```python
SpatialElement.SetLocationRelationship(
    space,
    linkedObjectUID="storey-01",
    linkedObjectType="bot:Storey"
)
```

## Generic Relationships

For any predicate, use `SetRelationship`:

```python
SpatialElement.SetRelationship(
    space,
    relationshipName="btwin:isAdjacentTo",
    linkedObjectUID="space-02",
    linkedObjectType="bot:Space"
)
```

Set `validate=True` to check the triple against `Schema.RelationshipNames()`:

```python
SpatialElement.SetRelationship(
    space,
    relationshipName="brick:hasLocation",
    linkedObject=storey,
    validate=True  # raises if (bot:Space, brick:hasLocation, bot:Storey) is not allowed
)
```

## Attaching Property Sets

Link a property set to a spatial element via `SetPSetRelationship`:

```python
from btwin import PropertySet

pset = PropertySet.Constructor("pset-01", "Thermal Properties")
SpatialElement.SetPSetRelationship(space, pset=pset)
```

## Accessors

```python
SpatialElement.UID(space)            # "space-01"
SpatialElement.Type(space)           # "bot:Space"
SpatialElement.Relationships(space)  # {"brick:hasLocation": [...], ...}
```
