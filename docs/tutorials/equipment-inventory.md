# Tutorial: Equipment Inventory

In this tutorial you will generate an equipment template, fill it with data, import it into BTwin, and link equipment to your building model.

## Step 1: Generate the Template

```python
from btwin import Inventory

df = Inventory.Template(savePath="equipment.xlsx")
print(df)
```

This creates an Excel file with columns:

| Column | Description |
|--------|-------------|
| `id` | Unique equipment identifier |
| `name` | Human-readable name |
| `type` | Brick equipment class (e.g., `brick:Air_Handling_Unit`) |
| `brick:isPartOf System` | System this equipment belongs to |
| `brick:hasLocation` | Space or location where the equipment is installed |

## Step 2: Edit the Template

Open `equipment.xlsx` and replace the sample data with your actual equipment. For example:

| id | name | type | brick:isPartOf System | brick:hasLocation |
|----|------|------|-----------------------|-------------------|
| ahu-01 | Rooftop AHU | brick:Air_Handling_Unit | hvac-system | space-lab |
| fc-01 | Fan Coil Lab | brick:Fan_Coil_Unit | hvac-system | space-lab |
| fc-02 | Fan Coil Office | brick:Fan_Coil_Unit | hvac-system | space-office |
| meter-01 | Main Meter | brick:Electric_Meter | electrical-system | space-lab |

## Step 3: Import into BTwin

```python
objects = Inventory.ToJSONLD(
    "equipment.xlsx",
    buildingUID="bldg-01",
    createSystems=True,
    locationType="bot:Space"
)

print(f"Created {len(objects)} objects")
```

With `createSystems=True`, BTwin also creates `brick:System` nodes for each unique system name found in the spreadsheet.

## Step 4: Inspect the Results

```python
from btwin import Equipment

for obj in objects:
    print(f"{Equipment.UID(obj)} ({Equipment.Type(obj)})")
    rels = Equipment.Relationships(obj)
    for pred, targets in rels.items():
        for t in targets:
            print(f"  {pred} → {t['@id']}")
```

## Step 5: Serialize

Combine with your spatial model and export:

```python
from btwin import SpatialElement, Serialization

site = SpatialElement.Constructor("site-01", "bot:Site", name="Campus")
building = SpatialElement.Constructor("bldg-01", "bot:Building", name="Engineering Block")
SpatialElement.SetLocationRelationship(building, linkedObject=site)

all_objects = [site, building] + objects

jsonld = Serialization.JSONLDByObjects(all_objects, savePath="building_with_equipment.json")
print(f"Exported {len(jsonld['@graph'])} nodes")
```

## Result

You now have:

- An Excel-based workflow for managing equipment inventories
- Equipment objects with location, system membership, and feeding relationships
- System nodes automatically created from the spreadsheet
- A combined JSON-LD export with both spatial elements and equipment
