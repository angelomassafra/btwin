from btwin import Schema


class TestSchemaTypes:
    def test_returns_dict(self):
        types = Schema.Types()
        assert isinstance(types, dict)
        assert len(types) > 0

    def test_all_keys_are_curie_format(self):
        for key in Schema.Types():
            assert ":" in key, f"Key '{key}' is not in prefix:Name format"

    def test_all_values_have_iri_and_description(self):
        for key, val in Schema.Types().items():
            assert "IRI" in val, f"Type '{key}' missing 'IRI'"
            assert "description" in val, f"Type '{key}' missing 'description'"

    def test_contains_bot_spatial_types(self):
        types = Schema.Types()
        for t in ["bot:Site", "bot:Building", "bot:Storey", "bot:Space"]:
            assert t in types

    def test_contains_brick_zone_types(self):
        types = Schema.Types()
        for t in ["brick:Zone", "brick:Energy_Zone", "brick:Fire_Zone"]:
            assert t in types

    def test_contains_equipment_and_point(self):
        types = Schema.Types()
        assert "brick:Equipment" in types
        assert "brick:Point" in types

    def test_contains_system_and_sensor(self):
        types = Schema.Types()
        assert "brick:System" in types
        assert "ifc:Sensor" in types

    def test_contains_custom_types(self):
        types = Schema.Types()
        for t in ["btwin:KPISet", "btwin:Document", "kpi:Scenario"]:
            assert t in types

    def test_contains_topologic_types(self):
        types = Schema.Types()
        assert "top:Face" in types
        assert "top:Aperture" in types


class TestSchemaRelationshipNames:
    def test_returns_dict(self):
        rels = Schema.RelationshipNames()
        assert isinstance(rels, dict)
        assert len(rels) > 0

    def test_all_entries_have_iri_and_pairs(self):
        for key, val in Schema.RelationshipNames().items():
            assert "IRI" in val, f"Rel '{key}' missing 'IRI'"
            assert "pairs" in val, f"Rel '{key}' missing 'pairs'"

    def test_all_pairs_have_subject_object(self):
        for key, val in Schema.RelationshipNames().items():
            for pair in val["pairs"]:
                assert "subject" in pair, f"Pair in '{key}' missing 'subject'"
                assert "object" in pair, f"Pair in '{key}' missing 'object'"
                assert "label" in pair["subject"]
                assert "IRI" in pair["subject"]
                assert "label" in pair["object"]
                assert "IRI" in pair["object"]

    def test_contains_key_relationships(self):
        rels = Schema.RelationshipNames()
        for r in ["brick:hasLocation", "brick:isFedBy", "ifc:HasPropertySets", "eko:hasAssociatedObject"]:
            assert r in rels

    def test_has_location_includes_equipment_pair(self):
        rels = Schema.RelationshipNames()
        pairs = rels["brick:hasLocation"]["pairs"]
        subjects = {p["subject"]["label"] for p in pairs}
        assert "brick:Equipment" in subjects
