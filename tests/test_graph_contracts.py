"""
Contract tests for the graph layer.

Each class here pins a defect fixed in 0.5.5, where the implementation and the
documented behaviour had drifted apart.
"""

import pytest

from btwin import RDF, NetworkX, Property, PropertySet, SpatialElement


class TestValidateAcceptsPointAndEquipment:
    """
    Validate checked node types against Schema.Types(), which stops at brick:Point and
    brick:Equipment, so every concrete sensor and asset reported as invalid. It now
    validates against the export vocabulary, which is the superset of everything BTwin
    can represent.
    """

    def _graph(self, nodeType):
        import networkx as nx

        G = nx.MultiDiGraph()
        G.add_node("space-01", type="bot:Space")
        G.add_node("n1", type=nodeType)
        G.add_edge("n1", "space-01", type="brick:hasLocation")
        return G

    @pytest.mark.parametrize("nodeType", [
        "brick:Temperature_Sensor",
        "brick:CO2_Sensor",
        "brick:Energy_Sensor",
        "brick:Occupancy_Sensor",
    ])
    def test_sensor_types_are_valid(self, nodeType):
        report = NetworkX.Validate(self._graph(nodeType), printReport=False)
        assert report["ok"] is True, report["invalidNodes"]

    @pytest.mark.parametrize("nodeType", ["brick:Boiler", "brick:Air_Handling_Unit"])
    def test_equipment_types_are_valid(self, nodeType):
        report = NetworkX.Validate(self._graph(nodeType), printReport=False)
        assert report["ok"] is True, report["invalidNodes"]

    @pytest.mark.parametrize("nodeType", [
        # in the export vocabulary but named by no constructor list: these were rejected
        # even after the first widening, which was built from Equipment.Types()
        "brick:Packaged_Heat_Pump",
        "brick:Electric_Boiler",
        "brick:PM1_Sensor",
        "brick:TVOC_Sensor",
        "ifc:IfcSensor",
    ])
    def test_export_only_types_are_valid(self, nodeType):
        report = NetworkX.Validate(self._graph(nodeType), printReport=False)
        assert report["ok"] is True, report["invalidNodes"]

    def test_everything_exportable_validates(self):
        """
        The two vocabularies must not drift again: anything JSONLDByObjects can write
        has to pass Validate, classes and predicates alike.
        """
        import networkx as nx

        from btwin import Serialization

        iris = Serialization.IRIs()

        G = nx.MultiDiGraph()
        for index, curie in enumerate(iris["classes"]):
            G.add_node(f"n{index}", type=curie)
        for index, predicate in enumerate(iris["properties"]):
            G.add_edge("n0", f"n{index + 1}", type=predicate)

        report = NetworkX.Validate(G, printReport=False)
        assert report["invalidNodes"] == []
        assert report["invalidEdges"] == []

    @pytest.mark.parametrize("predicate", [
        # Equipment's own setters emit these by default, yet Schema.RelationshipNames()
        # does not list them, so every such edge reported as invalid
        "brick:isPartOf",
        "brick:feeds",
        "brick:hasPart",
        "eko:hasEvaluationTimestep",
    ])
    def test_export_only_predicates_are_valid(self, predicate):
        import networkx as nx

        G = nx.MultiDiGraph()
        G.add_node("a", type="brick:Air_Handling_Unit")
        G.add_node("b", type="brick:System")
        G.add_edge("a", "b", type=predicate)

        report = NetworkX.Validate(G, printReport=False)
        assert report["ok"] is True, report["invalidEdges"]

    def test_unknown_predicate_is_still_rejected(self):
        import networkx as nx

        G = nx.MultiDiGraph()
        G.add_node("a", type="bot:Space")
        G.add_node("b", type="bot:Storey")
        G.add_edge("a", "b", type="brick:notAThing")

        report = NetworkX.Validate(G, printReport=False)
        assert report["ok"] is False
        assert [e["foundType"] for e in report["invalidEdges"]] == ["brick:notAThing"]

    def test_unknown_type_is_still_rejected(self):
        report = NetworkX.Validate(self._graph("brick:Not_A_Real_Class"), printReport=False)
        assert report["ok"] is False

    def test_custom_provider_is_not_widened(self):
        """A caller who supplies a provider gets exactly what that provider allows."""

        class OnlySpaces:
            @staticmethod
            def Types():
                return {"bot:Space": ""}

            @staticmethod
            def RelationshipNames():
                return {"brick:hasLocation": ""}

        report = NetworkX.Validate(
            self._graph("brick:CO2_Sensor"), schemaProvider=OnlySpaces, printReport=False)
        assert report["ok"] is False


class TestValidateReturnsReport:
    """Validate is documented to return a report dict; it used to return the graph."""

    def test_returns_the_report_not_the_graph(self):
        import networkx as nx

        G = nx.MultiDiGraph()
        G.add_node("n1", type="bot:Space")
        report = NetworkX.Validate(G, printReport=False)
        assert isinstance(report, dict)
        assert not isinstance(report, nx.Graph)
        assert set(report) >= {"ok", "invalidNodes", "invalidEdges", "counts", "allowed"}


class TestMarkFallsBackToAscii:
    """The tick and cross raise UnicodeEncodeError on a cp1252 Windows console."""

    def test_ascii_fallback_when_console_cannot_encode(self, monkeypatch):
        from btwin.graph import _mark

        class Cp1252Stdout:
            encoding = "cp1252"

        monkeypatch.setattr("sys.stdout", Cp1252Stdout())
        assert _mark(True) == "[ok]"
        assert _mark(False) == "[!!]"

    def test_glyphs_when_console_can_encode(self, monkeypatch):
        from btwin.graph import _mark

        class Utf8Stdout:
            encoding = "utf-8"

        monkeypatch.setattr("sys.stdout", Utf8Stdout())
        assert _mark(True) == "✓"
        assert _mark(False) == "✖"


class TestByJSONLDReturnsGraphAndReport:
    def _doc(self):
        return {
            "@context": {"bot": "https://w3id.org/bot#",
                         "brick": "https://brickschema.org/schema/Brick#"},
            "@graph": [
                {"@id": "b1", "@type": "bot:Building", "name": "B", "relationships": {}},
                {"@id": "s1", "@type": "bot:Space", "name": "S",
                 "relationships": {"brick:hasLocation": [{"@id": "b1", "@type": "bot:Building"}]}},
            ],
        }

    def test_returns_a_two_tuple(self):
        import networkx as nx

        graph, report = NetworkX.ByJSONLD(self._doc(), printReport=False)
        assert isinstance(graph, nx.MultiDiGraph)
        assert isinstance(report, dict) and report["ok"] is True

    def test_report_is_a_stub_when_validation_is_off(self):
        graph, report = NetworkX.ByJSONLD(self._doc(), validateGraph=False, printReport=False)
        assert graph.number_of_nodes() == 2
        assert report["ok"] is True
        assert report["counts"]["nodesChecked"] == 0

    def test_halt_on_invalid_raises_value_error(self):
        """It raised AttributeError, because report was the graph and graphs have no get()."""
        doc = self._doc()
        doc["@graph"].append({"@id": "x1", "@type": "bot:NotAClass", "relationships": {}})
        with pytest.raises(ValueError):
            NetworkX.ByJSONLD(doc, printReport=False, haltOnInvalid=True)


class TestRDFByJSONLDBlankNodeTargets:
    """
    Strict mode rejected any relationship target without an '@id', which meant it
    rejected the time interval BTwin's own serializer writes under a KPI set.
    """

    def _doc(self):
        return {
            "@context": {"eko": "http://energy.linkeddata.es/em-kpi/ontology#",
                         "btwin": "btwin#",
                         "time": "https://www.w3.org/TR/2022/CRD-owl-time-20221115#"},
            "@graph": [{
                "@id": "kpiset-1",
                "@type": "btwin:KPISet",
                "name": "Q1",
                "relationships": {
                    "eko:hasEvaluationTimestep": [{
                        "@type": "time:interval",
                        "time:hasBeginning": "2026-01-01T00:00:00Z",
                        "time:hasEnd": "2026-03-31T23:59:59Z",
                    }],
                },
            }],
        }

    def test_strict_mode_accepts_the_blank_node(self):
        pytest.importorskip("rdflib")
        _, turtle = RDF.ByJSONLD(self._doc(), strict=True)
        assert "hasBeginning" in turtle and "hasEnd" in turtle

    def test_interval_fields_are_preserved(self):
        pytest.importorskip("rdflib")
        graph, _ = RDF.ByJSONLD(self._doc(), strict=True)
        values = {str(o) for _, _, o in graph}
        assert "2026-01-01T00:00:00Z" in values
        assert "2026-03-31T23:59:59Z" in values

    def test_target_without_id_or_type_is_still_rejected(self):
        pytest.importorskip("rdflib")
        doc = self._doc()
        doc["@graph"][0]["relationships"]["eko:hasEvaluationTimestep"] = [{"note": "nothing"}]
        with pytest.raises(ValueError):
            RDF.ByJSONLD(doc, strict=True)


class TestToNEO4J:
    def _graph(self):
        space = SpatialElement.Constructor("space-01", "bot:Space", "Meeting Room")
        pset = PropertySet.Constructor("pset-space-01", "Pset_SpaceCommon")
        PropertySet.SetProperties(pset, [
            Property.Constructor("netFloorArea", 28.5, None,
                                 "IfcQuantityArea", "IfcPropertySingleValue", "sqm"),
        ])
        SpatialElement.SetPSetRelationship(space, pset=pset)

        objects = [space, pset]
        G = NetworkX.Constructor("MultiDiGraph")
        for obj in objects:
            NetworkX.AddNodeByObject(G, obj)
        for obj in objects:
            NetworkX.AddEdgesByObject(G, obj)
        return G

    def test_requires_a_uri(self):
        pytest.importorskip("neo4j")
        with pytest.raises(ValueError, match="NEO4J_URI"):
            NetworkX.ToNEO4J(self._graph())

    def test_requires_a_password(self):
        pytest.importorskip("neo4j")
        with pytest.raises(ValueError, match="NEO4J_PASSWORD"):
            NetworkX.ToNEO4J(self._graph(), NEO4J_URI="bolt://localhost:7687")

    def test_property_set_values_reach_the_node(self, monkeypatch):
        """
        The PSet enrichment called NodeLinkedPSets with the wrong keyword names, and the
        resulting TypeError was swallowed by a bare except, so values never arrived.
        """
        written = {}

        class FakeTx:
            def run(self, query, **params):
                if "MERGE (n:" in query:
                    written[params["uid"]] = params["props"]

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute_write(self, fn, *args):
                return fn(FakeTx(), *args)

        class FakeDriver:
            def verify_connectivity(self):
                return True

            def session(self):
                return FakeSession()

            def close(self):
                return None

        neo4j = pytest.importorskip("neo4j")
        monkeypatch.setattr(neo4j.GraphDatabase, "driver",
                            staticmethod(lambda *a, **k: FakeDriver()))

        summary = NetworkX.ToNEO4J(self._graph(), NEO4J_URI="bolt://x", NEO4J_PASSWORD="pw")

        assert summary["nodesSkipped"] == 0
        assert written["space-01"]["netFloorArea"] == 28.5
