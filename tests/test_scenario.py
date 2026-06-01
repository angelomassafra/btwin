import pytest

from btwin import Scenario


class TestConstructor:
    def test_happy_path(self, scenario_obj):
        assert scenario_obj["@id"] == "scenario-01"
        assert scenario_obj["@type"] == "kpi:Scenario"
        assert scenario_obj["relationships"] == {}

    def test_with_name_and_description(self):
        s = Scenario.Constructor("s1", name="Baseline", description="Current state")
        assert s["name"] == "Baseline"
        assert s["description"] == "Current state"

    def test_missing_uid_raises(self):
        with pytest.raises(TypeError):
            Scenario.Constructor(None)

    def test_empty_uid_raises(self):
        with pytest.raises(ValueError):
            Scenario.Constructor("")


class TestSetRelationship:
    def test_happy_path(self, scenario_obj):
        Scenario.SetRelationship(
            scenarioObject=scenario_obj,
            relationshipName="eko:hasAssociatedObject",
            linkedObjectUID="bldg-01",
            linkedObjectType="bot:Building",
        )
        assert "eko:hasAssociatedObject" in scenario_obj["relationships"]

    def test_append_true(self, scenario_obj):
        Scenario.SetRelationship(
            scenarioObject=scenario_obj,
            relationshipName="custom:rel",
            linkedObjectUID="a", linkedObjectType="bot:Space",
        )
        Scenario.SetRelationship(
            scenarioObject=scenario_obj,
            relationshipName="custom:rel",
            linkedObjectUID="b", linkedObjectType="bot:Space",
            append=True,
        )
        assert len(scenario_obj["relationships"]["custom:rel"]) == 2


class TestAccessors:
    def test_uid(self, scenario_obj):
        assert Scenario.UID(scenario_obj) == "scenario-01"

    def test_name_none(self, scenario_obj):
        assert Scenario.Name(scenario_obj) is None

    def test_name_present(self):
        s = Scenario.Constructor("s1", name="Test")
        assert Scenario.Name(s) == "Test"

    def test_description_none(self, scenario_obj):
        assert Scenario.Description(scenario_obj) is None

    def test_description_present(self):
        s = Scenario.Constructor("s1", description="Desc")
        assert Scenario.Description(s) == "Desc"

    def test_relationships(self, scenario_obj):
        rels = Scenario.Relationships(scenario_obj)
        assert isinstance(rels, dict)


class TestConstructorErrors:
    def test_non_string_type_raises(self):
        with pytest.raises(TypeError):
            Scenario.Constructor("s1", scenarioType=123)

    def test_empty_type_raises(self):
        with pytest.raises(ValueError):
            Scenario.Constructor("s1", scenarioType="")

    def test_non_string_name_raises(self):
        with pytest.raises(TypeError):
            Scenario.Constructor("s1", name=123)

    def test_non_string_description_raises(self):
        with pytest.raises(TypeError):
            Scenario.Constructor("s1", description=123)

    def test_whitespace_name_not_added(self):
        s = Scenario.Constructor("s1", name="   ")
        assert "name" not in s

    def test_whitespace_description_not_added(self):
        s = Scenario.Constructor("s1", description="   ")
        assert "description" not in s


class TestSetRelationshipErrors:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            Scenario.SetRelationship(scenarioObject="bad", relationshipName="rel")

    def test_empty_rel_name_raises(self, scenario_obj):
        with pytest.raises(ValueError):
            Scenario.SetRelationship(scenarioObject=scenario_obj, relationshipName="")

    def test_none_rel_name_raises(self, scenario_obj):
        with pytest.raises(ValueError):
            Scenario.SetRelationship(scenarioObject=scenario_obj, relationshipName=None)

    def test_missing_uid_raises(self, scenario_obj):
        with pytest.raises(ValueError):
            Scenario.SetRelationship(
                scenarioObject=scenario_obj,
                relationshipName="rel",
            )

    def test_missing_type_raises(self, scenario_obj):
        with pytest.raises(ValueError):
            Scenario.SetRelationship(
                scenarioObject=scenario_obj,
                relationshipName="rel",
                linkedObjectUID="x",
            )

    def test_linked_object_resolves(self, scenario_obj):
        linked = {"@id": "target", "@type": "bot:Space"}
        Scenario.SetRelationship(
            scenarioObject=scenario_obj,
            relationshipName="custom:rel",
            linkedObject=linked,
        )
        assert scenario_obj["relationships"]["custom:rel"][0]["@id"] == "target"

    def test_avoid_duplicates(self, scenario_obj):
        for _ in range(3):
            Scenario.SetRelationship(
                scenarioObject=scenario_obj,
                relationshipName="rel",
                linkedObjectUID="x", linkedObjectType="t",
                avoidDuplicates=True,
            )
        assert len(scenario_obj["relationships"]["rel"]) == 1

    def test_avoid_duplicates_false(self, scenario_obj):
        for _ in range(2):
            Scenario.SetRelationship(
                scenarioObject=scenario_obj,
                relationshipName="rel",
                linkedObjectUID="x", linkedObjectType="t",
                avoidDuplicates=False,
            )
        assert len(scenario_obj["relationships"]["rel"]) == 2

    def test_append_false_overwrites(self, scenario_obj):
        Scenario.SetRelationship(
            scenarioObject=scenario_obj,
            relationshipName="rel",
            linkedObjectUID="a", linkedObjectType="t",
        )
        Scenario.SetRelationship(
            scenarioObject=scenario_obj,
            relationshipName="rel",
            linkedObjectUID="b", linkedObjectType="t",
            append=False,
        )
        assert len(scenario_obj["relationships"]["rel"]) == 1
        assert scenario_obj["relationships"]["rel"][0]["@id"] == "b"

    def test_creates_relationships_key(self):
        obj = {"@id": "s1"}
        Scenario.SetRelationship(
            scenarioObject=obj,
            relationshipName="rel",
            linkedObjectUID="x", linkedObjectType="t",
        )
        assert "relationships" in obj

    def test_bad_relationships_type_raises(self):
        obj = {"@id": "s1", "relationships": "bad"}
        with pytest.raises(KeyError):
            Scenario.SetRelationship(
                scenarioObject=obj,
                relationshipName="rel",
                linkedObjectUID="x", linkedObjectType="t",
            )


class TestAccessorErrors:
    def test_uid_non_dict_raises(self):
        with pytest.raises(TypeError):
            Scenario.UID("bad")

    def test_uid_missing_raises(self):
        with pytest.raises(KeyError):
            Scenario.UID({})

    def test_name_non_dict_raises(self):
        with pytest.raises(TypeError):
            Scenario.Name("bad")

    def test_description_non_dict_raises(self):
        with pytest.raises(TypeError):
            Scenario.Description("bad")

    def test_relationships_non_dict_raises(self):
        with pytest.raises(TypeError):
            Scenario.Relationships("bad")
