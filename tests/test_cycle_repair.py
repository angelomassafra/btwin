"""
The repair loops must not spend the whole budget re-sending an identical reply.

At temperature 0.0 a model handed the same rejected text and the same reason answers
with the same text, so before 0.5.5 `maxRepairs=3` meant four identical calls and four
identical rejections before failing.
"""

import pytest

from btwin import RDF, Cycle, Tool

RDF_BASE_IRI = "https://example.org/test/"
RDF_TURTLE = """
@prefix bot: <https://w3id.org/bot#> .
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<bldg-01> a bot:Building ; rdfs:label "Main Hall" .
<space-01> a bot:Space ; rdfs:label "Room 101" ; brick:hasLocation <bldg-01> .
"""

PREFIXES = """PREFIX bot: <https://w3id.org/bot#>
PREFIX brick: <https://brickschema.org/schema/Brick#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""


@pytest.fixture
def rdf_graph(tmp_path):
    pytest.importorskip("rdflib")
    ttl = tmp_path / "repair.ttl"
    ttl.write_text(RDF_TURTLE, encoding="utf-8")
    return RDF.ByTTL(ttl, baseIRI=RDF_BASE_IRI)


@pytest.fixture
def rdf_schema(rdf_graph):
    return RDF.SchemaSummary(rdf_graph)

# 'brick:hasSpace' is not in the vocabulary, so agent 4 rejects this every time.
UNFIXABLE_QUERY = PREFIXES + "SELECT ?s WHERE { ?s brick:hasSpace ?o } LIMIT 100"

# Two operations with no ';' between them: a syntax error the validator always catches.
UNFIXABLE_UPDATE = PREFIXES + """DELETE WHERE {
  <https://example.org/test/space-01> rdfs:label "Old" .
}
INSERT DATA {
  <https://example.org/test/space-01> rdfs:label "New" .
}
"""


class TestQueryRepairStall:
    def test_raises_when_the_repair_repeats_itself(self, monkeypatch, rdf_graph, rdf_schema):
        calls = []

        monkeypatch.setattr(Tool, "RDFWriteSPARQL", staticmethod(
            lambda llm, grounding, question, meter=None, rowLimit=100: UNFIXABLE_QUERY))

        def repair(llm, grounding, question, sparql, reason, meter=None):
            calls.append(sparql)
            return sparql          # what a temperature-0 model does

        monkeypatch.setattr(Tool, "RDFRepairSPARQL", staticmethod(repair))

        with pytest.raises(ValueError, match="stalled"):
            Cycle.RDFQueryByPrompt(
                rdf_graph, "spaces?", llm=object(), schema=rdf_schema, maxRepairs=3)

        # One repair attempt, not the full budget of four.
        assert len(calls) == 1

    def test_a_repair_that_changes_something_still_runs(
            self, monkeypatch, rdf_graph, rdf_schema):
        good = PREFIXES + "SELECT ?s WHERE { ?s a bot:Space } LIMIT 10"

        monkeypatch.setattr(Tool, "RDFWriteSPARQL", staticmethod(
            lambda llm, grounding, question, meter=None, rowLimit=100: UNFIXABLE_QUERY))
        monkeypatch.setattr(Tool, "RDFRepairSPARQL", staticmethod(
            lambda llm, grounding, question, sparql, reason, meter=None: good))
        monkeypatch.setattr(Tool, "RDFAnswer", staticmethod(
            lambda llm, question, rows, meter=None, rowLimit=100: f"{len(rows)} rows"))

        result = Cycle.RDFQueryByPrompt(
            rdf_graph, "spaces?", llm=object(), schema=rdf_schema, maxRepairs=3)
        assert result["sparql"].strip().startswith("PREFIX")


class TestUpdateRepairStall:
    def test_raises_when_the_repair_repeats_itself(self, monkeypatch, rdf_graph, rdf_schema):
        calls = []

        monkeypatch.setattr(Tool, "RDFWriteUpdate", staticmethod(
            lambda llm, grounding, request, meter=None: UNFIXABLE_UPDATE))

        def repair(llm, grounding, request, sparql, reason, meter=None):
            calls.append(sparql)
            return sparql

        monkeypatch.setattr(Tool, "RDFRepairUpdate", staticmethod(repair))

        with pytest.raises(ValueError, match="stalled"):
            Cycle.RDFEditByPrompt(
                rdf_graph, "rename it", llm=object(), schema=rdf_schema, maxRepairs=3)

        assert len(calls) == 1


class TestCreateRepairStall:
    def test_raises_when_the_repair_repeats_itself(self, monkeypatch):
        calls = []

        monkeypatch.setattr(Tool, "JSONLDWrite", staticmethod(
            lambda llm, vocabulary, notation, request, meter=None: "not JSON at all"))

        def repair(llm, vocabulary, notation, request, document, reason, meter=None):
            calls.append(document)
            return document

        monkeypatch.setattr(Tool, "JSONLDRepair", staticmethod(repair))

        with pytest.raises(ValueError, match="stalled"):
            Cycle.JSONLDCreateByPrompt("a clinic", llm=object(), maxRepairs=3)

        assert len(calls) == 1
