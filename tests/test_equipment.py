import pandas as pd
import pytest

from btwin import Equipment
from btwin.equipment import Inventory


class TestConstructor:
    def test_happy_path(self, equipment_obj):
        assert equipment_obj["@id"] == "equip-01"
        assert equipment_obj["@type"] == "brick:Equipment"
        assert equipment_obj["name"] == "AHU-1"
        assert equipment_obj["relationships"] == {}

    def test_missing_uid_raises(self):
        with pytest.raises(ValueError):
            Equipment.Constructor(None, "brick:Equipment")

    def test_empty_uid_raises(self):
        with pytest.raises(ValueError):
            Equipment.Constructor("", "brick:Equipment")

    def test_missing_type_raises(self):
        with pytest.raises(ValueError):
            Equipment.Constructor("e1", None)

    def test_optional_name(self):
        obj = Equipment.Constructor("e1", "brick:Equipment")
        assert "name" not in obj

    def test_invalid_name_type_raises(self):
        with pytest.raises(TypeError):
            Equipment.Constructor("e1", "brick:Equipment", name=123)


class TestSetRelationship:
    def test_happy_path(self, equipment_obj):
        Equipment.SetRelationship(
            equipmentObject=equipment_obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="space-01",
            linkedObjectType="bot:Space",
        )
        assert "brick:hasLocation" in equipment_obj["relationships"]

    def test_append_true_adds_multiple(self, equipment_obj):
        Equipment.SetRelationship(
            equipmentObject=equipment_obj,
            relationshipName="brick:feeds",
            linkedObjectUID="a", linkedObjectType="bot:Building",
        )
        Equipment.SetRelationship(
            equipmentObject=equipment_obj,
            relationshipName="brick:feeds",
            linkedObjectUID="b", linkedObjectType="bot:Building",
            append=True,
        )
        assert len(equipment_obj["relationships"]["brick:feeds"]) == 2

    def test_avoid_duplicates(self, equipment_obj):
        for _ in range(3):
            Equipment.SetRelationship(
                equipmentObject=equipment_obj,
                relationshipName="brick:feeds",
                linkedObjectUID="a", linkedObjectType="bot:Building",
                avoidDuplicates=True,
            )
        assert len(equipment_obj["relationships"]["brick:feeds"]) == 1

    def test_linked_object_dict(self, equipment_obj, space_obj):
        Equipment.SetRelationship(
            equipmentObject=equipment_obj,
            relationshipName="brick:hasLocation",
            linkedObject=space_obj,
        )
        target = equipment_obj["relationships"]["brick:hasLocation"][0]
        assert target["@id"] == "space-01"


class TestSetFeedingRelationship:
    def test_happy_path(self, equipment_obj):
        Equipment.SetFeedingRelationship(
            equipment_obj,
            linkedObjectUID="bldg-01",
            linkedObjectType="bot:Building",
        )
        assert "brick:feeds" in equipment_obj["relationships"]


class TestSetLocationRelationship:
    def test_happy_path(self, equipment_obj):
        Equipment.SetLocationRelationship(
            equipment_obj,
            linkedObjectUID="space-01",
            linkedObjectType="bot:Space",
        )
        assert "brick:hasLocation" in equipment_obj["relationships"]


class TestSetPartOfRelationship:
    def test_happy_path(self, equipment_obj):
        Equipment.SetPartOfRelationship(
            equipment_obj,
            linkedObjectUID="sys-01",
        )
        assert "brick:isPartOf" in equipment_obj["relationships"]


class TestAccessors:
    def test_name(self, equipment_obj):
        assert Equipment.Name(equipment_obj) == "AHU-1"

    def test_name_none(self):
        obj = Equipment.Constructor("e1", "brick:Equipment")
        assert Equipment.Name(obj) is None

    def test_type(self, equipment_obj):
        assert Equipment.Type(equipment_obj) == "brick:Equipment"

    def test_uid(self, equipment_obj):
        assert Equipment.UID(equipment_obj) == "equip-01"

    def test_relationships(self, equipment_obj):
        rels = Equipment.Relationships(equipment_obj)
        assert isinstance(rels, dict)


class TestTypes:
    def test_returns_list(self):
        types = Equipment.Types()
        assert isinstance(types, list)
        assert len(types) > 0

    def test_all_strings(self):
        for t in Equipment.Types():
            assert isinstance(t, str)
            assert ":" in t


class TestSetRelationshipErrors:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            Equipment.SetRelationship("not_dict", "rel")

    def test_empty_rel_name_raises(self, equipment_obj):
        with pytest.raises(ValueError):
            Equipment.SetRelationship(equipment_obj, "")

    def test_missing_uid_raises(self, equipment_obj):
        with pytest.raises(ValueError):
            Equipment.SetRelationship(equipment_obj, "rel")

    def test_missing_type_raises(self, equipment_obj):
        with pytest.raises(ValueError):
            Equipment.SetRelationship(equipment_obj, "rel", linkedObjectUID="x")

    def test_append_false_overwrites(self, equipment_obj):
        Equipment.SetRelationship(equipment_obj, "rel", linkedObjectUID="a", linkedObjectType="t")
        Equipment.SetRelationship(equipment_obj, "rel", linkedObjectUID="b", linkedObjectType="t", append=False)
        assert len(equipment_obj["relationships"]["rel"]) == 1
        assert equipment_obj["relationships"]["rel"][0]["@id"] == "b"


class TestAccessorErrors:
    def test_name_non_dict_raises(self):
        with pytest.raises(TypeError):
            Equipment.Name("bad")

    def test_name_bad_type_raises(self):
        with pytest.raises(TypeError):
            Equipment.Name({"name": 123})

    def test_type_non_dict_raises(self):
        with pytest.raises(TypeError):
            Equipment.Type("bad")

    def test_type_bad_type_raises(self):
        with pytest.raises(TypeError):
            Equipment.Type({"@type": 123})

    def test_uid_non_dict_raises(self):
        with pytest.raises(TypeError):
            Equipment.UID("bad")

    def test_uid_missing_raises(self):
        with pytest.raises(KeyError):
            Equipment.UID({})

    def test_uid_empty_raises(self):
        with pytest.raises(ValueError):
            Equipment.UID({"@id": ""})

    def test_relationships_non_dict_raises(self):
        with pytest.raises(TypeError):
            Equipment.Relationships("bad")

    def test_relationships_bad_value_raises(self):
        with pytest.raises(KeyError):
            Equipment.Relationships({"relationships": "not_dict"})


class TestSetFeedingRelationshipMultiple:
    def test_multiple_linked_objects(self, equipment_obj):
        objs = [
            {"@id": "a", "@type": "bot:Building"},
            {"@id": "b", "@type": "bot:Building"},
        ]
        Equipment.SetFeedingRelationship(equipment_obj, linkedObject=objs)
        assert len(equipment_obj["relationships"]["brick:feeds"]) == 2

    def test_multiple_uids(self, equipment_obj):
        Equipment.SetFeedingRelationship(
            equipment_obj,
            linkedObjectUID=["a", "b"],
            linkedObjectType=["bot:Building", "bot:Building"],
        )
        assert len(equipment_obj["relationships"]["brick:feeds"]) == 2

    def test_no_linked_raises(self, equipment_obj):
        with pytest.raises(ValueError):
            Equipment.SetFeedingRelationship(equipment_obj)


class TestInventoryTemplate:
    def test_returns_dataframe(self):
        df = Inventory.Template()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "id" in df.columns
        assert "type" in df.columns

    def test_save_to_file(self, tmp_path):
        out = tmp_path / "inv.xlsx"
        df = Inventory.Template(savePath=str(out))
        assert out.exists()
        assert isinstance(df, pd.DataFrame)

    def test_auto_append_extension(self, tmp_path):
        out = tmp_path / "inv"
        Inventory.Template(savePath=str(out))
        assert (tmp_path / "inv.xlsx").exists()

    def test_empty_save_path_raises(self):
        with pytest.raises(ValueError):
            Inventory.Template(savePath="")


class TestInventoryToJSONLD:
    def test_round_trip(self, tmp_path):
        xlsx = tmp_path / "inv.xlsx"
        Inventory.Template(savePath=str(xlsx))
        objects = Inventory.ToJSONLD(str(xlsx))
        assert isinstance(objects, list)
        assert len(objects) > 0
        for obj in objects:
            assert "@id" in obj
            assert "@type" in obj

    def test_with_create_systems(self, tmp_path):
        xlsx = tmp_path / "inv.xlsx"
        Inventory.Template(savePath=str(xlsx))
        objects = Inventory.ToJSONLD(str(xlsx), createSystems=True)
        types = [o["@type"] for o in objects]
        assert "brick:System" in types

    def test_with_building_uid(self, tmp_path):
        xlsx = tmp_path / "inv.xlsx"
        Inventory.Template(savePath=str(xlsx))
        objects = Inventory.ToJSONLD(str(xlsx), buildingUID="bldg-01", createSystems=True)
        assert len(objects) > 0

    def test_missing_file_raises(self):
        with pytest.raises(Exception):
            Inventory.ToJSONLD("nonexistent.xlsx")
