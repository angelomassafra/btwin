# Properties

BTwin uses IFC-style property sets to attach structured metadata to spatial elements and other objects.

## Property Sets

A property set is a named container for properties:

```python
from btwin import PropertySet

pset = PropertySet.Constructor("pset-thermal", "Thermal Properties")
```

This creates a dictionary with `@type: "ifc:IfcPropertySet"` and an empty `ifc:HasProperties` list.

## Creating Properties

### Single Value

```python
from btwin import Property

prop = Property.Constructor(
    propertyName="U-Value",
    propertyValue=1.2,
    propertyQuantity="IfcReal",
    propertyType="IfcPropertySingleValue",
    propertyUnit="W/(m2*K)"
)
```

### Enumerated Value

```python
prop_enum = Property.Constructor(
    propertyName="Wall Layers",
    propertyValues=["Brick", "Insulation", "Plaster"],
    propertyQuantity="IfcLabel",
    propertyType="IfcPropertyEnumeratedValue"
)
```

## Adding Properties to a Set

### Single property

```python
PropertySet.SetProperty(pset, property=prop)
```

### Multiple properties at once

```python
PropertySet.SetProperties(pset, properties=[prop, prop_enum])
```

Use `overwrite=True` to replace existing properties with the same name:

```python
PropertySet.SetProperty(pset, property=updated_prop, overwrite=True)
```

## Reading Properties

```python
# Get all properties
all_props = PropertySet.Properties(pset)

# Get a specific property by name
thermal = PropertySet.Property(pset, "U-Value")

# Read value, type, and unit
Property.Value(thermal)         # 1.2
Property.QuantityType(thermal)  # "IfcReal"
Property.Unit(thermal)          # "W/(m2*K)"
```

## Updating Values

```python
Property.SetValue(
    thermal,
    propertyValue=0.8,
    propertyQuantity="IfcReal",
    propertyUnit="W/(m2*K)"
)
```

## Linking to Spatial Elements

```python
from btwin import SpatialElement

space = SpatialElement.Constructor("space-01", "bot:Space", name="Room 101")
SpatialElement.SetPSetRelationship(space, pset=pset)
```

This adds an `ifc:HasPropertySets` relationship from the space to the property set.
