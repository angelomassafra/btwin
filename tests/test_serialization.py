import json

import pytest

from btwin import Serialization, SpatialElement


class TestIRIs:
    def test_returns_dict(self):
        iris = Serialization.IRIs()
        assert isinstance(iris, dict)

    def test_has_expected_keys(self):
        iris = Serialization.IRIs()
        assert "prefixes" in iris
        assert "classes" in iris
        assert "properties" in iris

    def test_prefixes_contain_namespaces(self):
        prefixes = Serialization.IRIs()["prefixes"]
        for ns in ["brick", "bot", "ifc", "eko", "kpi", "btwin"]:
            assert ns in prefixes

    def test_classes_are_strings(self):
        classes = Serialization.IRIs()["classes"]
        for k, v in classes.items():
            assert isinstance(k, str)
            assert isinstance(v, str)


class TestJSONLDByObjects:
    def test_round_trip(self, tmp_path, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(
            spatialElementObject=building_obj,
            linkedObject=site_obj,
        )
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj],
            strictValidation=False,
        )
        assert "@context" in jsonld
        assert "@graph" in jsonld
        assert len(jsonld["@graph"]) == 2

    def test_saves_to_file(self, tmp_path, site_obj):
        out = tmp_path / "test.json"
        Serialization.JSONLDByObjects(
            objects=[site_obj],
            savePath=str(out),
            strictValidation=False,
        )
        assert out.exists()
        data = json.loads(out.read_text())
        assert "@graph" in data

    def test_validates_json_structure(self, site_obj):
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj],
            strictValidation=False,
        )
        graph = jsonld["@graph"]
        assert isinstance(graph, list)
        assert graph[0]["@id"] == "site-01"

    def test_empty_objects(self):
        jsonld = Serialization.JSONLDByObjects(objects=[], strictValidation=False)
        assert jsonld["@graph"] == []

    def test_nested_objects_flattened(self, site_obj, building_obj):
        jsonld = Serialization.JSONLDByObjects(
            objects=[[site_obj], [building_obj]],
            strictValidation=False,
        )
        assert len(jsonld["@graph"]) == 2

    def test_strict_unknown_class_raises(self):
        obj = {"@id": "x", "@type": "unknown:Type", "relationships": {}}
        with pytest.raises(ValueError, match="Unknown namespace"):
            Serialization.JSONLDByObjects(objects=[obj], strictValidation=True)

    def test_strict_unknown_property_raises(self, site_obj):
        SpatialElement.SetRelationship(
            spatialElementObject=site_obj,
            relationshipName="unknown:rel",
            linkedObjectUID="x",
            linkedObjectType="bot:Space",
            validate=False,
        )
        with pytest.raises(ValueError, match="Unknown namespace"):
            Serialization.JSONLDByObjects(objects=[site_obj], strictValidation=True)

    def test_non_dict_node_raises(self):
        with pytest.raises(TypeError):
            Serialization.JSONLDByObjects(objects=["not_dict"], strictValidation=False)

    def test_non_dict_relationships_raises(self):
        obj = {"@id": "x", "@type": "bot:Site", "relationships": "bad"}
        with pytest.raises(TypeError):
            Serialization.JSONLDByObjects(objects=[obj], strictValidation=False)

    def test_save_auto_append_extension(self, tmp_path, site_obj):
        out = tmp_path / "test"
        Serialization.JSONLDByObjects(
            objects=[site_obj],
            savePath=str(out),
            strictValidation=False,
        )
        assert (tmp_path / "test.json").exists()

    def test_context_contains_used_prefixes(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(building_obj, linkedObject=site_obj)
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj],
            strictValidation=False,
        )
        ctx = jsonld["@context"]
        assert "bot" in ctx
        assert "brick" in ctx

    def test_non_string_relationship_name_raises(self):
        obj = {"@id": "x", "@type": "bot:Site", "relationships": {123: []}}
        with pytest.raises(TypeError):
            Serialization.JSONLDByObjects(objects=[obj], strictValidation=False)

    def test_none_relationships_skipped(self):
        obj = {"@id": "x", "@type": "bot:Site", "relationships": None}
        # Should not raise
        jsonld = Serialization.JSONLDByObjects(objects=[obj], strictValidation=False)
        assert len(jsonld["@graph"]) == 1
