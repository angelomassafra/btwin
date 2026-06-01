from datetime import datetime, timezone

import pytest

from btwin import KPI, KPISet


class TestKPISetConstructor:
    def test_happy_path(self, kpiset_obj):
        assert kpiset_obj["@id"] == "kpiset-01"
        assert kpiset_obj["@type"] == "btwin:KPISet"
        assert kpiset_obj["name"] == "Energy KPIs"
        assert "btwin:hasKPIs" in kpiset_obj

    def test_with_timestamps(self):
        ks = KPISet.Constructor(
            "ks-01", "Test",
            hasBeginning="2025-01-01T00:00:00Z",
            hasEnd="2025-12-31T23:59:59Z",
        )
        ts = ks["relationships"]["eko:hasEvaluationTimestep"][0]
        assert ts["time:hasBeginning"] is not None
        assert ts["time:hasEnd"] is not None

    def test_empty_uid_raises(self):
        with pytest.raises(ValueError):
            KPISet.Constructor("")

    def test_non_string_uid_raises(self):
        with pytest.raises(TypeError):
            KPISet.Constructor(123)


class TestKPISetSetRelationship:
    def test_happy_path(self, kpiset_obj):
        KPISet.SetRelationship(
            kpiSet=kpiset_obj,
            relationshipName="eko:hasAssociatedObject",
            linkedObjectUID="space-01",
            linkedObjectType="bot:Space",
        )
        assert "eko:hasAssociatedObject" in kpiset_obj["relationships"]


class TestSetAssociatedObject:
    def test_happy_path(self, kpiset_obj):
        KPISet.SetAssociatedObject(
            kpiSet=kpiset_obj,
            linkedObjectUID="bldg-01",
            linkedObjectType="bot:Building",
        )
        rels = kpiset_obj["relationships"]["eko:hasAssociatedObject"]
        assert rels[0]["@id"] == "bldg-01"


class TestSetScenario:
    def test_happy_path(self, kpiset_obj, scenario_obj):
        KPISet.SetScenario(kpiSet=kpiset_obj, scenarioObject=scenario_obj)
        assert "kpi:relatedScenario" in kpiset_obj["relationships"]


class TestSetKPI:
    def test_add_kpi(self, kpiset_obj):
        kpi = KPI.Constructor("kpi-01", kpiName="Energy Use", kpiValue=100.0)
        KPISet.SetKPI(kpiset_obj, kpi)
        assert "kpi-01" in kpiset_obj["btwin:hasKPIs"]

    def test_overwrite_false_keeps_existing(self, kpiset_obj):
        kpi1 = KPI.Constructor("kpi-01", kpiName="A", kpiValue=1)
        kpi2 = KPI.Constructor("kpi-01", kpiName="B", kpiValue=2)
        KPISet.SetKPI(kpiset_obj, kpi1)
        KPISet.SetKPI(kpiset_obj, kpi2, overwrite=False)
        assert KPI.Name(kpiset_obj["btwin:hasKPIs"]["kpi-01"]) == "A"

    def test_overwrite_true_replaces(self, kpiset_obj):
        kpi1 = KPI.Constructor("kpi-01", kpiName="A", kpiValue=1)
        kpi2 = KPI.Constructor("kpi-01", kpiName="B", kpiValue=2)
        KPISet.SetKPI(kpiset_obj, kpi1)
        KPISet.SetKPI(kpiset_obj, kpi2, overwrite=True)
        assert KPI.Name(kpiset_obj["btwin:hasKPIs"]["kpi-01"]) == "B"


class TestSetTimestep:
    def test_set_timestep(self, kpiset_obj):
        KPISet.SetTimestep(
            kpiset_obj,
            hasBeginning="2025-01-01T00:00:00Z",
            hasEnd="2025-06-30T23:59:59Z",
        )
        ts = kpiset_obj["relationships"]["eko:hasEvaluationTimestep"][0]
        assert "2025-01-01" in ts["time:hasBeginning"]
        assert "2025-06-30" in ts["time:hasEnd"]


class TestSetKPIsTimestep:
    def test_propagates_to_kpis(self, kpiset_obj):
        kpi = KPI.Constructor("kpi-01", kpiName="X", kpiValue=10)
        KPISet.SetKPI(kpiset_obj, kpi)
        KPISet.SetTimestep(
            kpiset_obj,
            hasBeginning="2025-01-01T00:00:00Z",
            hasEnd="2025-12-31T23:59:59Z",
        )
        KPISet.SetKPIsTimestep(kpiset_obj)
        kpi_ts = kpiset_obj["btwin:hasKPIs"]["kpi-01"]["relationships"]["eko:hasEvaluationTimestep"][0]
        assert "2025-01-01" in kpi_ts["time:hasBeginning"]


class TestKPIConstructor:
    def test_happy_path(self):
        kpi = KPI.Constructor("kpi-01", kpiName="Energy", kpiValue=42.0)
        assert kpi["@id"] == "kpi-01"
        assert kpi["@type"] == "eko:KPI"
        assert kpi["name"] == "Energy"

    def test_with_datetime_values(self):
        kpi = KPI.Constructor(
            "kpi-01",
            hasBeginning="2025-01-01T00:00:00Z",
            hasEnd="2025-12-31T23:59:59Z",
        )
        ts = kpi["relationships"]["eko:hasEvaluationTimestep"][0]
        assert ts["time:hasBeginning"] is not None

    def test_empty_uid_raises(self):
        with pytest.raises(ValueError):
            KPI.Constructor("")


class TestKPIAccessors:
    def test_name(self):
        kpi = KPI.Constructor("k1", kpiName="Test")
        assert KPI.Name(kpi) == "Test"

    def test_uid(self):
        kpi = KPI.Constructor("k1")
        assert KPI.UID(kpi) == "k1"

    def test_value(self):
        kpi = KPI.Constructor("k1", kpiValue=99)
        assert KPI.Value(kpi) == 99

    def test_timestep(self):
        kpi = KPI.Constructor("k1", hasBeginning="2025-01-01T00:00:00Z")
        ts = KPI.Timestep(kpi)
        assert "time:hasBeginning" in ts
        assert ts["time:hasBeginning"] is not None


class TestKPISetTimestep:
    def test_set_timestep(self):
        kpi = KPI.Constructor("k1")
        KPI.SetTimestep(kpi, hasBeginning="2025-06-01T00:00:00Z", hasEnd="2025-06-30T23:59:59Z")
        ts = KPI.Timestep(kpi)
        assert "2025-06-01" in ts["time:hasBeginning"]


class TestKPISetRelationshipErrors:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            KPISet.SetRelationship(kpiSet="bad", relationshipName="rel")

    def test_empty_rel_name_raises(self, kpiset_obj):
        with pytest.raises(TypeError):
            KPISet.SetRelationship(kpiSet=kpiset_obj, relationshipName="")

    def test_missing_uid_raises(self, kpiset_obj):
        with pytest.raises(ValueError):
            KPISet.SetRelationship(
                kpiSet=kpiset_obj,
                relationshipName="eko:hasAssociatedObject",
            )

    def test_missing_type_raises(self, kpiset_obj):
        with pytest.raises(ValueError):
            KPISet.SetRelationship(
                kpiSet=kpiset_obj,
                relationshipName="eko:hasAssociatedObject",
                linkedObjectUID="x",
            )

    def test_append_mode(self, kpiset_obj):
        KPISet.SetRelationship(
            kpiSet=kpiset_obj,
            relationshipName="eko:hasAssociatedObject",
            linkedObjectUID="a", linkedObjectType="bot:Space",
        )
        KPISet.SetRelationship(
            kpiSet=kpiset_obj,
            relationshipName="eko:hasAssociatedObject",
            linkedObjectUID="b", linkedObjectType="bot:Space",
            append=True,
        )
        assert len(kpiset_obj["relationships"]["eko:hasAssociatedObject"]) == 2

    def test_linked_object_resolves(self, kpiset_obj):
        linked = {"UID": "x-01", "label": "bot:Space"}
        KPISet.SetRelationship(
            kpiSet=kpiset_obj,
            relationshipName="eko:hasAssociatedObject",
            linkedObject=linked,
        )
        assert kpiset_obj["relationships"]["eko:hasAssociatedObject"][0]["@id"] == "x-01"


class TestKPISetSetKPIErrors:
    def test_non_dict_kpiset_raises(self):
        with pytest.raises(TypeError):
            KPISet.SetKPI("bad", {})

    def test_missing_has_kpis_raises(self):
        with pytest.raises(KeyError):
            KPISet.SetKPI({"@id": "x"}, {"@id": "k"})

    def test_non_dict_kpi_raises(self, kpiset_obj):
        with pytest.raises(TypeError):
            KPISet.SetKPI(kpiset_obj, "bad")

    def test_missing_kpi_id_raises(self, kpiset_obj):
        with pytest.raises(ValueError):
            KPISet.SetKPI(kpiset_obj, {"name": "no id"})


class TestKPISetTimestepErrors:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            KPISet.SetTimestep("bad", hasBeginning=None, hasEnd=None)

    def test_invalid_order_raises(self, kpiset_obj):
        with pytest.raises(ValueError):
            KPISet.SetTimestep(
                kpiset_obj,
                hasBeginning="2025-12-31T00:00:00Z",
                hasEnd="2025-01-01T00:00:00Z",
            )


class TestKPISetKPIsTimestepErrors:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            KPISet.SetKPIsTimestep("bad")

    def test_no_timestep_raises(self):
        ks = {"relationships": {}, "btwin:hasKPIs": {}}
        with pytest.raises(ValueError):
            KPISet.SetKPIsTimestep(ks)


class TestKPISetUIDErrors:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            KPISet.UID("bad")

    def test_missing_id_raises(self):
        with pytest.raises(KeyError):
            KPISet.UID({})

    def test_empty_id_raises(self):
        with pytest.raises(ValueError):
            KPISet.UID({"@id": ""})


class TestKPIConstructorAdvanced:
    def test_with_unit(self):
        kpi = KPI.Constructor("k1", kpiValue=100, kpiUnit="kWh")
        assert kpi["nominalValue"]["unit"] == "kWh"

    def test_with_datetime_objects(self):
        dt_begin = datetime(2025, 1, 1, tzinfo=timezone.utc)
        dt_end = datetime(2025, 12, 31, tzinfo=timezone.utc)
        kpi = KPI.Constructor("k1", hasBeginning=dt_begin, hasEnd=dt_end)
        ts = KPI.Timestep(kpi)
        assert ts["time:hasBeginning"] is not None

    def test_invalid_name_type_raises(self):
        with pytest.raises(TypeError):
            KPI.Constructor("k1", kpiName=123)

    def test_invalid_value_type_raises(self):
        with pytest.raises(TypeError):
            KPI.Constructor("k1", kpiValue=[1, 2])

    def test_invalid_unit_type_raises(self):
        with pytest.raises(TypeError):
            KPI.Constructor("k1", kpiUnit=123)

    def test_invalid_order_raises(self):
        with pytest.raises(ValueError):
            KPI.Constructor(
                "k1",
                hasBeginning="2025-12-31T00:00:00Z",
                hasEnd="2025-01-01T00:00:00Z",
            )


class TestKPIAccessorErrors:
    def test_name_non_dict_raises(self):
        with pytest.raises(TypeError):
            KPI.Name("bad")

    def test_uid_non_dict_raises(self):
        with pytest.raises(TypeError):
            KPI.UID("bad")

    def test_uid_missing_raises(self):
        with pytest.raises(KeyError):
            KPI.UID({})

    def test_value_non_dict_raises(self):
        with pytest.raises(TypeError):
            KPI.Value("bad")

    def test_timestep_non_dict_raises(self):
        with pytest.raises(TypeError):
            KPI.Timestep("bad")

    def test_timestep_empty(self):
        kpi = {"relationships": {}}
        ts = KPI.Timestep(kpi)
        assert ts["time:hasBeginning"] is None
        assert ts["time:hasEnd"] is None


class TestKPISetTimestepAdvanced:
    def test_with_datetime_objects(self):
        kpi = KPI.Constructor("k1")
        dt_begin = datetime(2025, 6, 1, tzinfo=timezone.utc)
        dt_end = datetime(2025, 6, 30, tzinfo=timezone.utc)
        KPI.SetTimestep(kpi, hasBeginning=dt_begin, hasEnd=dt_end)
        ts = KPI.Timestep(kpi)
        assert "2025-06-01" in ts["time:hasBeginning"]

    def test_none_values(self):
        kpi = KPI.Constructor("k1")
        KPI.SetTimestep(kpi, hasBeginning=None, hasEnd=None)
        ts = KPI.Timestep(kpi)
        assert ts["time:hasBeginning"] is None

    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            KPI.SetTimestep("bad")

    def test_invalid_order_raises(self):
        kpi = KPI.Constructor("k1")
        with pytest.raises(ValueError):
            KPI.SetTimestep(
                kpi,
                hasBeginning="2025-12-31T00:00:00Z",
                hasEnd="2025-01-01T00:00:00Z",
            )
