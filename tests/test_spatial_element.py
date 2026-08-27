import pytest

from btwin import Serialization, SpatialElement, SpatialHierarchy


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


class TestSpatialHierarchyByIFC:
    """The IFC reader, against a file made on the spot."""

    @staticmethod
    def _model(path):
        """2 storeys, 2 spaces each, and 3 zones: one per flat, one crossing storeys, one stray."""
        ifcopenshell = pytest.importorskip("ifcopenshell")
        pytest.importorskip("ifcopenshell.api")
        import ifcopenshell.api

        run = ifcopenshell.api.run
        model = ifcopenshell.file(schema="IFC4")

        project = run("root.create_entity", model, ifc_class="IfcProject", name="P")
        site = run("root.create_entity", model, ifc_class="IfcSite", name="Site")
        building = run("root.create_entity", model, ifc_class="IfcBuilding", name="Ferrovia 9")
        run("aggregate.assign_object", model, products=[site], relating_object=project)
        run("aggregate.assign_object", model, products=[building], relating_object=site)

        spaces = {}
        for level in (1, 2):
            storey = run("root.create_entity", model, ifc_class="IfcBuildingStorey",
                         name=f"Floor {level}")
            run("aggregate.assign_object", model, products=[storey], relating_object=building)
            for number in (1, 2):
                space = run("root.create_entity", model, ifc_class="IfcSpace",
                            name=f"S{level}.{number}")
                space.LongName = f"Room {level}.{number}"
                run("aggregate.assign_object", model, products=[space], relating_object=storey)
                spaces[(level, number)] = space

        flat = run("root.create_entity", model, ifc_class="IfcZone", name="Appartamento")
        flat.LongName = "Appartamento A"
        run("group.assign_group", model, products=[spaces[(1, 1)], spaces[(1, 2)]], group=flat)

        # A zone over both storeys: a zone is not a level of the containment chain
        stack = run("root.create_entity", model, ifc_class="IfcZone", name="Vano scale")
        run("group.assign_group", model, products=[spaces[(1, 2)], spaces[(2, 2)]], group=stack)

        # A zone whose only space is in another building, and a zone with no members at all
        other = run("root.create_entity", model, ifc_class="IfcBuilding", name="Elsewhere")
        run("aggregate.assign_object", model, products=[other], relating_object=site)
        outside = run("root.create_entity", model, ifc_class="IfcSpace", name="X")
        run("aggregate.assign_object", model, products=[outside], relating_object=other)
        stray = run("root.create_entity", model, ifc_class="IfcZone", name="Stray")
        run("group.assign_group", model, products=[outside], group=stray)
        run("root.create_entity", model, ifc_class="IfcZone", name="Empty")

        model.write(str(path))
        return model

    @pytest.fixture
    def hierarchy(self, tmp_path):
        path = tmp_path / "zones.ifc"
        self._model(path)
        return SpatialHierarchy.ByIFC(path)

    def test_reads_the_spatial_chain(self, hierarchy):
        assert hierarchy["building"]["name"] == "Ferrovia 9"
        assert len(hierarchy["storeys"]) == 2 and len(hierarchy["spaces"]) == 4

    def test_reads_the_zones(self, hierarchy):
        names = sorted(zone["name"] for zone in hierarchy["zones"])
        assert names == ["Appartamento A", "Vano scale"]   # LongName wins over Name
        assert all(zone["@type"] == "brick:Zone" for zone in hierarchy["zones"])

    def test_a_zone_points_at_the_building(self, hierarchy):
        buildingUID = hierarchy["building"]["@id"]
        for zone in hierarchy["zones"]:
            targets = zone["relationships"]["brick:hasLocation"]
            assert targets == [{"@id": buildingUID, "@type": "bot:Building"}]

    def test_a_space_points_at_its_zones_as_well_as_its_storey(self, hierarchy):
        byName = {space["name"]: space for space in hierarchy["spaces"]}
        zoneUIDs = {zone["name"]: zone["@id"] for zone in hierarchy["zones"]}
        targets = {t["@id"] for t in byName["Room 1.2"]["relationships"]["brick:hasLocation"]}
        # Its storey, its flat and the stairwell: three links under the one predicate
        assert len(targets) == 3
        assert {zoneUIDs["Appartamento A"], zoneUIDs["Vano scale"]} <= targets

    def test_a_zone_may_cross_storeys(self, hierarchy):
        stack = next(z for z in hierarchy["zones"] if z["name"] == "Vano scale")
        members = [space for space in hierarchy["spaces"]
                   if any(t["@id"] == stack["@id"]
                          for t in space["relationships"]["brick:hasLocation"])]
        assert sorted(space["name"] for space in members) == ["Room 1.2", "Room 2.2"]

    def test_a_space_outside_the_building_takes_its_zone_with_it(self, hierarchy):
        assert "Stray" not in {zone["name"] for zone in hierarchy["zones"]}

    def test_an_empty_zone_is_left_out(self, hierarchy):
        assert "Empty" not in {zone["name"] for zone in hierarchy["zones"]}

    def test_the_result_serializes(self, hierarchy):
        objects = [hierarchy["building"], *hierarchy["storeys"], *hierarchy["spaces"],
                   *hierarchy["zones"]]
        jsonld = Serialization.JSONLDByObjects(objects=objects)
        assert len(jsonld["@graph"]) == 9
        assert set(jsonld["@context"]) == {"bot", "brick"}

    def test_a_file_without_a_building_gives_empty_lists(self, tmp_path):
        ifcopenshell = pytest.importorskip("ifcopenshell")
        path = tmp_path / "empty.ifc"
        ifcopenshell.file(schema="IFC4").write(str(path))
        assert SpatialHierarchy.ByIFC(path) == {"building": None, "storeys": [], "spaces": [],
                                                "zones": []}

    def test_missing_path_raises(self):
        with pytest.raises(ValueError):
            SpatialHierarchy.ByIFC()

    def test_missing_file_raises(self, tmp_path):
        pytest.importorskip("ifcopenshell")
        with pytest.raises(OSError):
            SpatialHierarchy.ByIFC(tmp_path / "nope.ifc")
