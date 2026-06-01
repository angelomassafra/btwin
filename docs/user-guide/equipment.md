# Equipment

Equipment objects represent physical devices in a building — HVAC units, meters, pumps, lighting, and more.

## Creating Equipment

```python
from btwin import Equipment

ahu = Equipment.Constructor("ahu-01", "brick:Air_Handling_Unit", name="AHU 1")
fc = Equipment.Constructor("fc-01", "brick:Fan_Coil_Unit", name="Fan Coil 1")
```

Use `Equipment.Types()` to see all supported Brick equipment classes:

```python
for t in Equipment.Types():
    print(t)
# brick:Equipment, brick:HVAC_Equipment, brick:Air_Handling_Unit, ...
```

## Relationships

### Location

Place equipment in a space:

```python
Equipment.SetLocationRelationship(ahu, linkedObject=space)
```

### Feeding

Connect equipment to downstream assets:

```python
Equipment.SetFeedingRelationship(
    ahu,
    linkedObject=[fc],          # list of targets
    relationshipName="brick:feeds"
)
```

### Part-of (Systems)

Assign equipment to a system:

```python
Equipment.SetPartOfRelationship(ahu, linkedObjectUID="hvac-system", linkedObjectType="brick:System")
```

### Generic

Use `Equipment.SetRelationship` for any predicate:

```python
Equipment.SetRelationship(
    ahu,
    relationshipName="eko:hasAssociatedObject",
    linkedObjectUID="kpiset-01",
    linkedObjectType="btwin:KPISet"
)
```

## Accessors

```python
Equipment.UID(ahu)            # "ahu-01"
Equipment.Type(ahu)           # "brick:Air_Handling_Unit"
Equipment.Name(ahu)           # "AHU 1"
Equipment.Relationships(ahu)  # {"brick:hasLocation": [...]}
```

## Inventory

The `Inventory` class helps you bulk-import equipment from Excel spreadsheets.

### Generate a Template

```python
from btwin import Inventory

df = Inventory.Template(savePath="equipment_template.xlsx")
```

This creates an Excel file with columns: `id`, `name`, `type`, `brick:isPartOf System`, `brick:hasLocation`.

### Import from Excel

```python
objects = Inventory.ToJSONLD(
    "equipment_template.xlsx",
    buildingUID="bldg-01",
    createSystems=True
)
```

This returns a list of JSON-LD equipment dictionaries (and optionally system nodes) with relationships already set.
