import pytest

from btwin import SpatialElement


class TestConstructor:
    def test_happy_path(self, site_obj):
        assert site_obj["@id"] == "site-01"
        assert site_obj["@type"] == "bot:Site"
        assert site_obj["name"] == "Test Site"
        assert site_obj["relationships"] == {}

    def test_missing_uid_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.Constructor(None, "bot:Site")

    def test_empty_uid_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.Constructor("", "bot:Site")

    def test_missing_type_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.Constructor("id-1", None)

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Invalid spatialElementType"):
            SpatialElement.Constructor("id-1", "invalid:Type")

    def test_optional_name(self):
        obj = SpatialElement.Constructor("id-1", "bot:Site")
        assert "name" not in obj

    def test_all_schema_types_accepted(self):
        from btwin import Schema
        for t in Schema.Types():
            obj = SpatialElement.Constructor(f"uid-{t}", t)
            assert obj["@type"] == t


class TestRelationships:
    def test_returns_dict(self, site_obj):
        rels = SpatialElement.Relationships(site_obj)
        assert isinstance(rels, dict)

    def test_none_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.Relationships(None)

    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            SpatialElement.Relationships("not a dict")

    def test_missing_key_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.Relationships({"@id": "x"})

    def test_non_dict_value_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.Relationships({"relationships": "bad"})


class TestSetRelationship:
    def test_happy_path_with_linked_object(self, space_obj, storey_obj):
        updated = SpatialElement.SetRelationship(
            spatialElementObject=space_obj,
            relationshipName="brick:hasLocation",
            linkedObject=storey_obj,
            validate=False,
        )
        rels = updated["relationships"]["brick:hasLocation"]
        assert len(rels) == 1
        assert rels[0]["@id"] == "storey-01"

    def test_happy_path_with_uid_type(self, space_obj):
        updated = SpatialElement.SetRelationship(
            spatialElementObject=space_obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="storey-01",
            linkedObjectType="bot:Storey",
            validate=False,
        )
        assert len(updated["relationships"]["brick:hasLocation"]) == 1

    def test_missing_object_raises(self, space_obj):
        with pytest.raises(ValueError):
            SpatialElement.SetRelationship(
                spatialElementObject=space_obj,
                relationshipName="brick:hasLocation",
                validate=False,
            )

    def test_missing_relationship_name_raises(self, space_obj):
        with pytest.raises(ValueError):
            SpatialElement.SetRelationship(
                spatialElementObject=space_obj,
                relationshipName=None,
                linkedObjectUID="x",
                linkedObjectType="bot:Storey",
            )

    def test_deduplicate_prevents_dupes(self, space_obj):
        SpatialElement.SetRelationship(
            spatialElementObject=space_obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="storey-01",
            linkedObjectType="bot:Storey",
            deduplicate=True, validate=False,
        )
        SpatialElement.SetRelationship(
            spatialElementObject=space_obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="storey-01",
            linkedObjectType="bot:Storey",
            deduplicate=True, validate=False,
        )
        assert len(space_obj["relationships"]["brick:hasLocation"]) == 1

    def test_validate_true_checks_schema(self, space_obj):
        updated = SpatialElement.SetRelationship(
            spatialElementObject=space_obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="storey-01",
            linkedObjectType="bot:Storey",
            validate=True,
        )
        assert len(updated["relationships"]["brick:hasLocation"]) == 1

    def test_validate_rejects_invalid_pair(self, space_obj):
        with pytest.raises(ValueError, match="Invalid triple"):
            SpatialElement.SetRelationship(
                spatialElementObject=space_obj,
                relationshipName="brick:hasLocation",
                linkedObjectUID="x",
                linkedObjectType="kpi:Scenario",
                validate=True,
            )

    def test_inplace_false_returns_copy(self, space_obj):
        updated = SpatialElement.SetRelationship(
            spatialElementObject=space_obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="storey-01",
            linkedObjectType="bot:Storey",
            validate=False, inPlace=False,
        )
        assert updated is not space_obj


class TestSetLocationRelationship:
    def test_happy_path(self, space_obj, storey_obj):
        updated = SpatialElement.SetLocationRelationship(
            spatialElementObject=space_obj,
            linkedObject=storey_obj,
        )
        assert "brick:hasLocation" in updated["relationships"]

    def test_delegates_correctly(self, building_obj, site_obj):
        updated = SpatialElement.SetLocationRelationship(
            spatialElementObject=building_obj,
            linkedObject=site_obj,
        )
        targets = updated["relationships"]["brick:hasLocation"]
        assert targets[0]["@id"] == "site-01"


class TestSetPSetRelationship:
    def test_happy_path(self, space_obj, pset_obj):
        updated = SpatialElement.SetPSetRelationship(
            spatialElementObject=space_obj,
            pset=pset_obj,
        )
        assert "ifc:HasPropertySets" in updated["relationships"]
        assert updated["relationships"]["ifc:HasPropertySets"][0]["@id"] == "pset-01"


class TestType:
    def test_returns_type(self, site_obj):
        assert SpatialElement.Type(site_obj) == "bot:Site"

    def test_fallback_to_subclass(self):
        obj = {"subclass": "bot:Space"}
        assert SpatialElement.Type(obj) == "bot:Space"

    def test_missing_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.Type({})


class TestUID:
    def test_returns_id(self, site_obj):
        assert SpatialElement.UID(site_obj) == "site-01"

    def test_fallback_to_uid_key(self):
        obj = {"UID": "fallback-uid"}
        assert SpatialElement.UID(obj) == "fallback-uid"

    def test_missing_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.UID({})

    def test_none_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.UID(None)

    def test_non_dict_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.UID("bad")

    def test_non_string_uid_raises(self):
        with pytest.raises(TypeError):
            SpatialElement.UID({"@id": 123})

    def test_empty_uid_skips_to_next(self):
        obj = {"@id": "", "UID": "fallback"}
        assert SpatialElement.UID(obj) == "fallback"


class TestTypeErrors:
    def test_none_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.Type(None)

    def test_non_dict_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.Type("bad")

    def test_non_string_value_raises(self):
        with pytest.raises(TypeError):
            SpatialElement.Type({"@type": 123})

    def test_empty_type_skips_to_next(self):
        obj = {"@type": "", "subclass": "bot:Space"}
        assert SpatialElement.Type(obj) == "bot:Space"


class TestSetRelationshipErrors:
    def test_none_object_raises(self):
        with pytest.raises(ValueError):
            SpatialElement.SetRelationship(
                spatialElementObject=None,
                relationshipName="rel",
            )

    def test_non_dict_object_raises(self):
        with pytest.raises(TypeError):
            SpatialElement.SetRelationship(
                spatialElementObject="bad",
                relationshipName="rel",
            )

    def test_missing_subject_id_raises(self):
        with pytest.raises(TypeError):
            SpatialElement.SetRelationship(
                spatialElementObject={"relationships": {}},
                relationshipName="rel",
                linkedObjectUID="x",
                linkedObjectType="t",
            )

    def test_linked_object_missing_id_raises(self, space_obj):
        with pytest.raises(KeyError):
            SpatialElement.SetRelationship(
                spatialElementObject=space_obj,
                relationshipName="rel",
                linkedObject={"name": "no id"},
                validate=False,
            )

    def test_validate_unknown_relationship_raises(self, space_obj):
        with pytest.raises(ValueError, match="Unknown relationship"):
            SpatialElement.SetRelationship(
                spatialElementObject=space_obj,
                relationshipName="unknown:relationship",
                linkedObjectUID="x",
                linkedObjectType="bot:Space",
                validate=True,
            )

    def test_non_list_bucket_raises(self, space_obj):
        space_obj["relationships"]["brick:hasLocation"] = "bad"
        with pytest.raises(TypeError):
            SpatialElement.SetRelationship(
                spatialElementObject=space_obj,
                relationshipName="brick:hasLocation",
                linkedObjectUID="x",
                linkedObjectType="bot:Storey",
                validate=False,
            )

    def test_creates_relationships_if_missing(self):
        obj = {"@id": "x", "@type": "bot:Space"}
        SpatialElement.SetRelationship(
            spatialElementObject=obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="y",
            linkedObjectType="bot:Storey",
            validate=False,
        )
        assert "relationships" in obj
        assert "brick:hasLocation" in obj["relationships"]


class TestSetLocationRelationshipErrors:
    def test_none_object_raises(self):
        with pytest.raises(TypeError):
            SpatialElement.SetLocationRelationship(
                spatialElementObject=None,
                linkedObjectUID="x",
                linkedObjectType="bot:Storey",
            )

    def test_missing_ids_raises(self, space_obj):
        with pytest.raises(ValueError):
            SpatialElement.SetLocationRelationship(
                spatialElementObject=space_obj,
            )

    def test_linked_object_missing_type_raises(self, space_obj):
        with pytest.raises(KeyError):
            SpatialElement.SetLocationRelationship(
                spatialElementObject=space_obj,
                linkedObject={"@id": "x"},
            )

    def test_inplace_false(self, space_obj, storey_obj):
        result = SpatialElement.SetLocationRelationship(
            spatialElementObject=space_obj,
            linkedObject=storey_obj,
            inPlace=False,
        )
        assert result is not space_obj


class TestSetPSetRelationshipErrors:
    def test_none_object_raises(self):
        with pytest.raises(TypeError):
            SpatialElement.SetPSetRelationship(
                spatialElementObject=None,
                psetUID="x",
            )

    def test_missing_pset_uid_raises(self, space_obj):
        with pytest.raises(ValueError):
            SpatialElement.SetPSetRelationship(
                spatialElementObject=space_obj,
            )

    def test_pset_missing_id_raises(self, space_obj):
        with pytest.raises(KeyError):
            SpatialElement.SetPSetRelationship(
                spatialElementObject=space_obj,
                pset={"name": "no id"},
            )

    def test_by_uid(self, space_obj):
        result = SpatialElement.SetPSetRelationship(
            spatialElementObject=space_obj,
            pset={"@id": "pset-01", "@type": "ifc:IfcPropertySet"},
        )
        assert "ifc:HasPropertySets" in result["relationships"]
