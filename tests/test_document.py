import pytest

from btwin import Document


class TestConstructor:
    def test_happy_path(self, document_obj):
        assert document_obj["@id"] == "doc-01"
        assert document_obj["@type"] == "btwin:Document"
        assert document_obj["name"] == "Energy Model"
        assert document_obj["relationships"] == {}

    def test_missing_uid_raises(self):
        with pytest.raises(TypeError):
            Document.Constructor(None)

    def test_empty_uid_raises(self):
        with pytest.raises(ValueError):
            Document.Constructor("")

    def test_optional_name(self):
        d = Document.Constructor("d1")
        assert "name" not in d


class TestSetRelationship:
    def test_happy_path(self, document_obj):
        Document.SetRelationship(
            documentObject=document_obj,
            relationshipName="btwin:isDocumentOf",
            linkedObjectUID="bldg-01",
            linkedObjectType="bot:Building",
        )
        assert "btwin:isDocumentOf" in document_obj["relationships"]

    def test_avoid_duplicates(self, document_obj):
        for _ in range(3):
            Document.SetRelationship(
                documentObject=document_obj,
                relationshipName="btwin:isDocumentOf",
                linkedObjectUID="bldg-01",
                linkedObjectType="bot:Building",
                avoidDuplicates=True,
            )
        assert len(document_obj["relationships"]["btwin:isDocumentOf"]) == 1


class TestSetScenario:
    def test_happy_path(self, document_obj, scenario_obj):
        Document.SetScenario(
            documentObject=document_obj,
            scenarioObject=scenario_obj,
        )
        assert "kpi:relatedScenario" in document_obj["relationships"]
        assert document_obj["relationships"]["kpi:relatedScenario"][0]["@id"] == "scenario-01"


class TestAccessors:
    def test_name(self, document_obj):
        assert Document.Name(document_obj) == "Energy Model"

    def test_uid(self, document_obj):
        assert Document.UID(document_obj) == "doc-01"

    def test_relationships(self, document_obj):
        rels = Document.Relationships(document_obj)
        assert isinstance(rels, dict)


class TestConstructorErrors:
    def test_non_string_name_raises(self):
        with pytest.raises(TypeError):
            Document.Constructor("d1", name=123)

    def test_whitespace_name_not_added(self):
        d = Document.Constructor("d1", name="   ")
        assert "name" not in d


class TestSetRelationshipErrors:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            Document.SetRelationship("bad", "rel")

    def test_empty_rel_name_raises(self, document_obj):
        with pytest.raises(ValueError):
            Document.SetRelationship(document_obj, "")

    def test_missing_uid_raises(self, document_obj):
        with pytest.raises(ValueError):
            Document.SetRelationship(document_obj, "rel")

    def test_missing_type_raises(self, document_obj):
        with pytest.raises(ValueError):
            Document.SetRelationship(document_obj, "rel", linkedObjectUID="x")

    def test_linked_object_resolves(self, document_obj):
        linked = {"@id": "t1", "@type": "bot:Space"}
        Document.SetRelationship(document_obj, "custom:rel", linkedObject=linked)
        assert document_obj["relationships"]["custom:rel"][0]["@id"] == "t1"

    def test_append_false_overwrites(self, document_obj):
        Document.SetRelationship(document_obj, "rel",
                                 linkedObjectUID="a", linkedObjectType="t")
        Document.SetRelationship(document_obj, "rel",
                                 linkedObjectUID="b", linkedObjectType="t",
                                 append=False)
        assert len(document_obj["relationships"]["rel"]) == 1
        assert document_obj["relationships"]["rel"][0]["@id"] == "b"

    def test_avoid_duplicates_false(self, document_obj):
        for _ in range(2):
            Document.SetRelationship(document_obj, "rel",
                                     linkedObjectUID="x", linkedObjectType="t",
                                     avoidDuplicates=False)
        assert len(document_obj["relationships"]["rel"]) == 2

    def test_creates_relationships_key(self):
        obj = {"@id": "d1", "@type": "btwin:Document"}
        Document.SetRelationship(obj, "rel",
                                 linkedObjectUID="x", linkedObjectType="t")
        assert "relationships" in obj

    def test_bad_relationships_type_raises(self):
        obj = {"@id": "d1", "relationships": "bad"}
        with pytest.raises(KeyError):
            Document.SetRelationship(obj, "rel",
                                     linkedObjectUID="x", linkedObjectType="t")


class TestSetScenarioErrors:
    def test_missing_scenario_raises(self, document_obj):
        with pytest.raises(ValueError):
            Document.SetScenario(documentObject=document_obj)

    def test_scenario_uid_fallback(self, document_obj):
        Document.SetScenario(
            documentObject=document_obj,
            scenarioUID="sc-01",
        )
        assert document_obj["relationships"]["kpi:relatedScenario"][0]["@id"] == "sc-01"

    def test_append_false(self, document_obj, scenario_obj):
        Document.SetScenario(document_obj, scenarioObject=scenario_obj)
        Document.SetScenario(document_obj, scenarioUID="sc-02", append=False)
        assert len(document_obj["relationships"]["kpi:relatedScenario"]) == 1
        assert document_obj["relationships"]["kpi:relatedScenario"][0]["@id"] == "sc-02"


class TestAccessorErrors:
    def test_name_non_dict_raises(self):
        with pytest.raises(TypeError):
            Document.Name("bad")

    def test_name_bad_type_raises(self):
        with pytest.raises(TypeError):
            Document.Name({"name": 123})

    def test_uid_non_dict_raises(self):
        with pytest.raises(TypeError):
            Document.UID("bad")

    def test_uid_missing_raises(self):
        with pytest.raises(KeyError):
            Document.UID({})

    def test_uid_empty_raises(self):
        with pytest.raises(ValueError):
            Document.UID({"@id": ""})

    def test_relationships_non_dict_raises(self):
        with pytest.raises(TypeError):
            Document.Relationships("bad")

    def test_relationships_bad_value_raises(self):
        with pytest.raises(KeyError):
            Document.Relationships({"relationships": "not_dict"})
