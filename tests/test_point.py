import pandas as pd
import pytest

from btwin import Point
from btwin.point import Observation


class TestConstructor:
    def test_happy_path(self, point_obj):
        assert point_obj["@id"] == "point-01"
        assert point_obj["@type"] == "brick:Temperature_Sensor"
        assert point_obj["name"] == "Temp Sensor"
        assert point_obj["relationships"] == {}

    def test_missing_uid_raises(self):
        with pytest.raises(ValueError):
            Point.Constructor(None, "brick:Sensor")

    def test_empty_uid_raises(self):
        with pytest.raises(ValueError):
            Point.Constructor("", "brick:Sensor")

    def test_missing_type_raises(self):
        with pytest.raises(ValueError):
            Point.Constructor("p1", None)

    def test_optional_name(self):
        obj = Point.Constructor("p1", "brick:Sensor")
        assert "name" not in obj

    def test_invalid_name_type_raises(self):
        with pytest.raises(TypeError):
            Point.Constructor("p1", "brick:Sensor", name=42)


class TestSetRelationship:
    def test_happy_path(self, point_obj):
        Point.SetRelationship(
            pointObject=point_obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="space-01",
            linkedObjectType="bot:Space",
        )
        assert "brick:hasLocation" in point_obj["relationships"]

    def test_deduplication(self, point_obj):
        for _ in range(3):
            Point.SetRelationship(
                pointObject=point_obj,
                relationshipName="brick:hasLocation",
                linkedObjectUID="space-01",
                linkedObjectType="bot:Space",
                avoidDuplicates=True,
            )
        assert len(point_obj["relationships"]["brick:hasLocation"]) == 1

    def test_append_false_overwrites(self, point_obj):
        Point.SetRelationship(
            pointObject=point_obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="s1", linkedObjectType="bot:Space",
        )
        Point.SetRelationship(
            pointObject=point_obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="s2", linkedObjectType="bot:Space",
            append=False,
        )
        targets = point_obj["relationships"]["brick:hasLocation"]
        assert len(targets) == 1
        assert targets[0]["@id"] == "s2"


class TestAccessors:
    def test_name(self, point_obj):
        assert Point.Name(point_obj) == "Temp Sensor"

    def test_uid(self, point_obj):
        assert Point.UID(point_obj) == "point-01"

    def test_relationships(self, point_obj):
        rels = Point.Relationships(point_obj)
        assert isinstance(rels, dict)


class TestTypes:
    def test_returns_list(self):
        types = Point.Types()
        assert isinstance(types, list)
        assert len(types) > 0

    def test_all_strings(self):
        for t in Point.Types():
            assert isinstance(t, str)


class TestPointSetRelationshipErrors:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            Point.SetRelationship("not_dict", "rel")

    def test_empty_rel_name_raises(self, point_obj):
        with pytest.raises(ValueError):
            Point.SetRelationship(point_obj, "")

    def test_missing_uid_raises(self, point_obj):
        with pytest.raises(ValueError):
            Point.SetRelationship(point_obj, "rel", linkedObjectUID=None, linkedObjectType=None)

    def test_missing_type_raises(self, point_obj):
        with pytest.raises(ValueError):
            Point.SetRelationship(point_obj, "rel", linkedObjectUID="x", linkedObjectType=None)

    def test_linked_object_resolves_uid(self, point_obj):
        linked = {"@id": "target-01", "@type": "bot:Space"}
        Point.SetRelationship(point_obj, "custom:rel", linkedObject=linked)
        assert point_obj["relationships"]["custom:rel"][0]["@id"] == "target-01"

    def test_no_duplicates_false(self, point_obj):
        for _ in range(2):
            Point.SetRelationship(
                point_obj, "custom:rel",
                linkedObjectUID="x", linkedObjectType="bot:Space",
                avoidDuplicates=False,
            )
        assert len(point_obj["relationships"]["custom:rel"]) == 2


class TestPointAccessorErrors:
    def test_name_non_dict_raises(self):
        with pytest.raises(TypeError):
            Point.Name("bad")

    def test_name_bad_type_raises(self):
        with pytest.raises(TypeError):
            Point.Name({"name": 123})

    def test_uid_non_dict_raises(self):
        with pytest.raises(TypeError):
            Point.UID("bad")

    def test_uid_missing_raises(self):
        with pytest.raises(KeyError):
            Point.UID({})

    def test_uid_empty_raises(self):
        with pytest.raises(ValueError):
            Point.UID({"@id": ""})

    def test_relationships_non_dict_raises(self):
        with pytest.raises(TypeError):
            Point.Relationships("bad")

    def test_relationships_bad_value_raises(self):
        with pytest.raises(KeyError):
            Point.Relationships({"relationships": "not_dict"})


class TestObservationTemplate:
    def test_returns_dataframe(self):
        df = Observation.Template()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "sosa:madeBySensor" in df.columns

    def test_save_to_file(self, tmp_path):
        out = tmp_path / "template.xlsx"
        df = Observation.Template(savePath=str(out))
        assert out.exists()
        assert isinstance(df, pd.DataFrame)

    def test_empty_save_path_raises(self):
        with pytest.raises(ValueError):
            Observation.Template(savePath="")


class TestObservationSQLiteByDF:
    def _sample_df(self):
        return pd.DataFrame({
            "sosa:madeBySensor": ["s1", "s1", "s2"],
            "sosa:ObservedProperty": ["Temperature", "Temperature", "Humidity"],
            "Unit": ["°C", "°C", "%"],
            "Value": [22.5, 23.0, 55.0],
            "Timestamp": ["2025-01-01T10:00:00", "2025-01-01T11:00:00", "2025-01-01T10:00:00"],
        })

    def test_write_and_read(self, tmp_path):
        df = self._sample_df()
        db = tmp_path / "obs.db"
        result = Observation.SQLiteByDF(df, str(db), "observations", ifExists="fail")
        assert db.exists()
        assert isinstance(result, str)

    def test_replace_mode(self, tmp_path):
        df = self._sample_df()
        db = tmp_path / "obs.db"
        Observation.SQLiteByDF(df, str(db), "observations", ifExists="fail")
        Observation.SQLiteByDF(df, str(db), "observations", ifExists="replace")

    def test_append_mode(self, tmp_path):
        df = self._sample_df()
        db = tmp_path / "obs.db"
        Observation.SQLiteByDF(df, str(db), "observations", ifExists="fail")
        Observation.SQLiteByDF(df, str(db), "observations", ifExists="append")

    def test_fail_on_existing(self, tmp_path):
        df = self._sample_df()
        db = tmp_path / "obs.db"
        Observation.SQLiteByDF(df, str(db), "observations", ifExists="fail")
        with pytest.raises(ValueError):
            Observation.SQLiteByDF(df, str(db), "observations", ifExists="fail")

    def test_with_primary_key(self, tmp_path):
        df = pd.DataFrame({"id": [1, 2], "val": [10, 20]})
        db = tmp_path / "pk.db"
        Observation.SQLiteByDF(df, str(db), "t", primaryKey="id")

    def test_invalid_df_raises(self, tmp_path):
        with pytest.raises(TypeError):
            Observation.SQLiteByDF("not_df", str(tmp_path / "x.db"), "t")

    def test_empty_table_name_raises(self, tmp_path):
        with pytest.raises(ValueError):
            Observation.SQLiteByDF(pd.DataFrame(), str(tmp_path / "x.db"), "")

    def test_invalid_if_exists_raises(self, tmp_path):
        with pytest.raises(ValueError):
            Observation.SQLiteByDF(pd.DataFrame(), str(tmp_path / "x.db"), "t", ifExists="bad")


class TestObservationSQLiteQuery:
    def _setup_db(self, tmp_path):
        df = pd.DataFrame({
            "sosa:madeBySensor": ["s1", "s1", "s2", "s2"],
            "sosa:ObservedProperty": ["Temp", "Temp", "Hum", "Hum"],
            "Unit": ["C", "C", "%", "%"],
            "Value": [22.0, 23.0, 55.0, 60.0],
            "Timestamp": [
                "2025-01-01T10:00:00", "2025-01-01T11:00:00",
                "2025-01-01T10:00:00", "2025-01-01T11:00:00",
            ],
        })
        db = str(tmp_path / "query.db")
        Observation.SQLiteByDF(df, db, "obs", ifExists="fail")
        return db

    def test_basic_query(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 4

    def test_filter_by_sensor(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", sensor="s1")
        assert len(result) == 2

    def test_filter_by_sensor_list(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", sensor=["s1", "s2"])
        assert len(result) == 4

    def test_filter_by_property(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", observedProperty="Temp")
        assert len(result) == 2

    def test_filter_by_unit(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", unit="C")
        assert len(result) == 2

    def test_aggregate_sum(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", aggregate="sum")
        assert len(result) >= 1

    def test_aggregate_count(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", aggregate="count")
        assert len(result) >= 1

    def test_aggregate_min(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", aggregate="min")
        assert len(result) >= 1

    def test_aggregate_max(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", aggregate="max")
        assert len(result) >= 1

    def test_group_by_hour(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", aggregate="sum", groupByTime="hour")
        assert len(result) >= 1

    def test_group_by_day(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", aggregate="sum", groupByTime="day")
        assert len(result) >= 1

    def test_group_by_month(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", aggregate="count", groupByTime="month")
        assert len(result) >= 1

    def test_time_range_filter(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(
            db, "obs",
            startTime="2025-01-01T10:30:00",
            endTime="2025-01-01T12:00:00",
        )
        assert len(result) == 2

    def test_limit(self, tmp_path):
        db = self._setup_db(tmp_path)
        result = Observation.SQLiteQuery(db, "obs", limit=2)
        assert len(result) == 2

    def test_invalid_aggregate_raises(self, tmp_path):
        db = self._setup_db(tmp_path)
        with pytest.raises(ValueError):
            Observation.SQLiteQuery(db, "obs", aggregate="invalid")

    def test_invalid_group_by_raises(self, tmp_path):
        db = self._setup_db(tmp_path)
        with pytest.raises(ValueError):
            Observation.SQLiteQuery(db, "obs", groupByTime="invalid")
