# SpatialElement & SpatialHierarchy

Spatial elements are the building's topology: sites, buildings, storeys, spaces and zones.
`SpatialElement` builds them one at a time; `SpatialHierarchy` reads a whole hierarchy out of
an existing IFC model.

## Building a hierarchy

The hierarchy is written **upward**: each element points at its parent through
`brick:hasLocation`.

```python
from btwin import SpatialElement, PropertySet, Property

site     = SpatialElement.Constructor("site-01", "bot:Site", name="Campus")
building = SpatialElement.Constructor("bldg-01", "bot:Building", name="Main Hall")
storey   = SpatialElement.Constructor("storey-01", "bot:Storey", name="Ground Floor")
space    = SpatialElement.Constructor("space-01", "bot:Space", name="Room 101")

SpatialElement.SetLocationRelationship(building, linkedObject=site)
SpatialElement.SetLocationRelationship(storey, linkedObject=building)
SpatialElement.SetLocationRelationship(space, linkedObject=storey)

pset = PropertySet.Constructor("pset-space-01", "Pset_SpaceCommon")
PropertySet.SetProperty(pset, Property.Constructor("NetArea", 42.0, propertyQuantity="IfcAreaMeasure",
                                                   propertyUnit="m2"))
SpatialElement.SetPSetRelationship(space, pset=pset)

SpatialElement.Relationships(space)
# {'brick:hasLocation': [{'@id': 'storey-01', '@type': 'bot:Storey'}],
#  'ifc:HasPropertySets': [{'@id': 'pset-space-01', '@type': 'ifc:IfcPropertySet'}]}
```

## Reading one from IFC

`SpatialHierarchy.ByIFC` maps `IfcBuilding`, `IfcBuildingStorey`, `IfcSpace` and `IfcZone` to
their BOT and Brick classes, uses each `GlobalId` as the UID and writes the containment as
relationships. Property sets are read only when named — authoring tools export far more of
them than a building model needs. Requires `ifcopenshell`.

```python
from btwin import SpatialHierarchy, Serialization

hierarchy = SpatialHierarchy.ByIFC("model.ifc", psetNames=["Pset_SpaceCommon"])

objects = [hierarchy["building"], hierarchy["storeys"], hierarchy["spaces"],
           hierarchy["zones"], hierarchy["psets"]]
jsonld = Serialization.JSONLDByObjects(objects, savePath="model.json")
```

## SpatialElement

::: btwin.spatial_element.SpatialElement
    options:
      members_order: source
      show_source: true

## SpatialHierarchy

::: btwin.spatial_element.SpatialHierarchy
    options:
      members_order: source
      show_source: true
