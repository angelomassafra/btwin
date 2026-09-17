# PropertySet & Property

IFC-style property sets attach structured metadata to spatial elements, equipment and
documents. A `PropertySet` is a named container; each `Property` inside it holds a single
value (`IfcPropertySingleValue`) or an enumeration (`IfcPropertyEnumeratedValue`), with a
datatype and a unit.

```python
from btwin import PropertySet, Property

pset = PropertySet.Constructor("pset-space-01", "Pset_SpaceCommon")

area = Property.Constructor("NetArea", 42.0, propertyQuantity="IfcAreaMeasure", propertyUnit="m2")
use = Property.Constructor("OccupancyType", propertyValues=["Office", "Meeting"],
                           propertyType="IfcPropertyEnumeratedValue", propertyQuantity="IfcLabel")
PropertySet.SetProperties(pset, [area, use])

area = PropertySet.Property(pset, "NetArea")
Property.Value(area), Property.Unit(area)        # (42.0, 'm2')

Property.SetValue(area, 44.5, propertyQuantity="IfcAreaMeasure", propertyUnit="m2")
```

The set is linked to its owner through `ifc:HasPropertySets` — for example
`SpatialElement.SetPSetRelationship(space, pset=pset)`. When the graph is built,
[`NetworkX.CompactPSets`](graph.md) can fold the properties into the owner node itself.

## PropertySet

::: btwin.property_set.PropertySet
    options:
      members_order: source
      show_source: true

## Property

::: btwin.property_set.Property
    options:
      members_order: source
      show_source: true
