# Equipment & Inventory

`Equipment` objects are the building's physical devices, typed with a Brick equipment class
(`Equipment.Types()` lists them). Three relationships place a device: where it is, the
system it belongs to, and what it serves.

```python
from btwin import Equipment

ahu = Equipment.Constructor("ahu-01", "brick:Air_Handling_Unit", name="AHU 1")

Equipment.SetLocationRelationship(ahu, linkedObjectUID="space-plant", linkedObjectType="bot:Space")
Equipment.SetPartOfRelationship(ahu, linkedObjectUID="hvac-01")            # brick:System by default
Equipment.SetFeedingRelationship(ahu, linkedObjectUID=["space-01", "space-02"],
                                 linkedObjectType=["bot:Space", "bot:Space"])

sorted(Equipment.Relationships(ahu))
# ['brick:feeds', 'brick:hasLocation', 'brick:isPartOf']
```

## Bulk import

For more than a handful of devices, keep the list in a spreadsheet. `Inventory.Template`
lays out the columns — `id`, `name`, `type`, `brick:isPartOf System`, `brick:hasLocation` —
and `Inventory.ToJSONLD` reads a filled-in workbook back as Equipment dictionaries.

```python
from btwin import Inventory

Inventory.Template(savePath="inventory.xlsx")      # fill it in, then:
equipment = Inventory.ToJSONLD("inventory.xlsx", createSystems=True)
```

With `createSystems=True`, every system named in the sheet is also returned as a
`brick:System` object, so the `brick:isPartOf` links have something to point at.

## Equipment

::: btwin.equipment.Equipment
    options:
      members_order: source
      show_source: true

## Inventory

::: btwin.equipment.Inventory
    options:
      members_order: source
      show_source: true
