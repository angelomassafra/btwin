
import json

import pytest

from btwin import RDF, SPARQL, CostMeter, Cycle, NetworkX, Tool

# --- Cycle 1 fixtures: an RDF graph to ask questions about -----------------------------
RDF_BASE_IRI = "https://example.org/test/"
RDF_TURTLE = """
@prefix bot: <https://w3id.org/bot#> .
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix btwin: <btwin#> .
@prefix ifc: <https://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2_TC1/OWL#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<site-01> a bot:Site ; rdfs:label "Lotto" .
<bldg-01> a bot:Building ; brick:hasLocation <site-01> .
<storey-01> a bot:Storey ; rdfs:label "Piano Primo" ; brick:hasLocation <bldg-01> .
<space-01> a bot:Space ; rdfs:label "Camera" ; brick:hasLocation <storey-01>, <zone-01> .
<zone-01> a brick:Zone ; rdfs:label "Appartamento" ;
    brick:hasLocation <bldg-01>, <storey-01> ; btwin:hasDocument <doc-01> .
<doc-01> a btwin:Document ; rdfs:label "APE.pdf" ; ifc:HasPropertySets <pset-01> .
<pset-01> a ifc:IfcPropertySet ; rdfs:label "Indici" ;
    ifc:HasProperties [ a ifc:IfcPropertySingleValue ;
        rdfs:label "EPgl,nren" ; ifc:NominalValue 66.98 ; ifc:Unit "kWh/m2 anno" ] .
"""

PREFIXES = """PREFIX bot: <https://w3id.org/bot#>
PREFIX brick: <https://brickschema.org/schema/Brick#>
PREFIX btwin: <https://example.org/test/btwin#>
PREFIX ifc: <https://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2_TC1/OWL#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

Q_INDEX = PREFIXES + """SELECT ?label ?value ?unit WHERE {
  <https://example.org/test/zone-01> btwin:hasDocument ?doc .
  ?doc ifc:HasPropertySets ?pset . ?pset ifc:HasProperties ?p .
  ?p rdfs:label ?label ; ifc:NominalValue ?value ; ifc:Unit ?unit . } LIMIT 100"""
# Legal vocabulary, clean parse, invented hop: matches nothing
Q_WRONG = PREFIXES + """SELECT ?label WHERE {
  <https://example.org/test/zone-01> btwin:hasDocument ?doc .
  ?doc btwin:hasDocument ?other . ?other rdfs:label ?label . } LIMIT 100"""
Q_ASK_FALSE = PREFIXES + "ASK { <https://example.org/test/site-01> a bot:Space }"


@pytest.fixture
def rdf_graph(tmp_path):
    pytest.importorskip("rdflib")
    ttl = tmp_path / "test.ttl"
    ttl.write_text(RDF_TURTLE, encoding="utf-8")
    return RDF.ByTTL(ttl, baseIRI=RDF_BASE_IRI)


@pytest.fixture
def rdf_schema(rdf_graph):
    return RDF.SchemaSummary(rdf_graph)


@pytest.fixture
def stubAgents(monkeypatch):
    """Replace the three model-calling agents of cycle 1: no network, no key."""
    def apply(written, repaired=None):
        monkeypatch.setattr(Tool, "RDFWriteSPARQL", staticmethod(
            lambda llm, grounding, question, meter=None, rowLimit=100: written))
        monkeypatch.setattr(Tool, "RDFRepairSPARQL", staticmethod(
            lambda llm, grounding, question, sparql, reason, meter=None: repaired))
        monkeypatch.setattr(Tool, "RDFAnswer", staticmethod(
            lambda llm, question, rows, meter=None, rowLimit=100: f"{len(rows)} rows"))
    return apply


class TestRDFQueryByPrompt:
    def test_answers_from_the_rows(self, stubAgents, rdf_graph, rdf_schema):
        stubAgents(Q_INDEX)
        result = Cycle.RDFQueryByPrompt(rdf_graph, "indexes?", llm=object(), schema=rdf_schema)
        assert result["rows"][0]["value"] == "66.98"
        assert result["answer"] == "1 rows"

    def test_reports_usage(self, stubAgents, rdf_graph, rdf_schema):
        stubAgents(Q_INDEX)
        result = Cycle.RDFQueryByPrompt(rdf_graph, "indexes?", llm=object(), schema=rdf_schema)
        assert set(result["usage"]) >= {"calls", "cost", "promptTokens"}

    def test_collects_source_nodes(self, stubAgents, rdf_graph, rdf_schema):
        stubAgents(PREFIXES + "SELECT ?s WHERE { ?s a bot:Space } LIMIT 10")
        result = Cycle.RDFQueryByPrompt(rdf_graph, "spaces?", llm=object(), schema=rdf_schema)
        assert result["source"] == [RDF_BASE_IRI + "space-01"]

    def test_empty_select_is_rewritten_and_adopted(self, stubAgents, rdf_graph, rdf_schema):
        stubAgents(Q_WRONG, repaired=Q_INDEX)
        result = Cycle.RDFQueryByPrompt(rdf_graph, "indexes?", llm=object(), schema=rdf_schema)
        assert len(result["rows"]) == 1 and result["sparql"] == Q_INDEX

    def test_rewrite_kept_only_when_it_finds_rows(self, stubAgents, rdf_graph, rdf_schema):
        stillEmpty = PREFIXES + "SELECT ?s WHERE { ?s btwin:hasDocument ?s } LIMIT 100"
        stubAgents(Q_WRONG, repaired=stillEmpty)
        result = Cycle.RDFQueryByPrompt(rdf_graph, "indexes?", llm=object(), schema=rdf_schema)
        assert result["rows"] == [] and result["sparql"] == Q_WRONG

    def test_invalid_rewrite_keeps_the_original(self, stubAgents, rdf_graph, rdf_schema):
        broken = PREFIXES + "SELECT ?s WHERE { ?s brick:hasSpace ?o } LIMIT 100"
        stubAgents(Q_WRONG, repaired=broken)
        result = Cycle.RDFQueryByPrompt(rdf_graph, "indexes?", llm=object(), schema=rdf_schema)
        assert result["rows"] == [] and result["sparql"] == Q_WRONG

    def test_no_rewrite_when_rows_are_found(self, stubAgents, rdf_graph, rdf_schema):
        stubAgents(Q_INDEX, repaired=Q_WRONG)
        result = Cycle.RDFQueryByPrompt(rdf_graph, "indexes?", llm=object(), schema=rdf_schema)
        assert result["sparql"] == Q_INDEX

    def test_false_ask_is_an_answer_not_a_miss(self, monkeypatch, stubAgents, rdf_graph,
                                               rdf_schema):
        repairs = []
        stubAgents(Q_ASK_FALSE)
        monkeypatch.setattr(Tool, "RDFRepairSPARQL", staticmethod(
            lambda *a, **k: repairs.append(1) or Q_ASK_FALSE))
        result = Cycle.RDFQueryByPrompt(rdf_graph, "is it a space?", llm=object(),
                                        schema=rdf_schema)
        assert result["rows"] == [{"result": "false"}] and repairs == []

    def test_invalid_query_is_repaired(self, stubAgents, rdf_graph, rdf_schema):
        stubAgents("not a query at all", repaired=Q_INDEX)
        result = Cycle.RDFQueryByPrompt(rdf_graph, "indexes?", llm=object(), schema=rdf_schema)
        assert result["sparql"] == Q_INDEX and result["attempts"] == 2

    def test_gives_up_after_the_repair_budget(self, stubAgents, rdf_graph, rdf_schema):
        stubAgents("not a query", repaired="still not a query")
        with pytest.raises(ValueError):
            Cycle.RDFQueryByPrompt(rdf_graph, "indexes?", llm=object(), schema=rdf_schema,
                                   maxRepairs=1)

    def test_builds_the_schema_when_not_supplied(self, stubAgents, rdf_graph):
        stubAgents(Q_INDEX)
        assert Cycle.RDFQueryByPrompt(rdf_graph, "indexes?", llm=object())["rows"]

    def test_missing_inputs_raise(self, rdf_graph):
        with pytest.raises(ValueError):
            Cycle.RDFQueryByPrompt(None, "q")
        with pytest.raises(ValueError):
            Cycle.RDFQueryByPrompt(rdf_graph, "")


class TestRDFAgentInputValidation:
    """The agents reject bad input before spending a call on it."""

    def test_write_needs_grounding(self):
        with pytest.raises(ValueError):
            Tool.RDFWriteSPARQL(object(), "", "a question")

    def test_write_needs_question(self):
        with pytest.raises(ValueError):
            Tool.RDFWriteSPARQL(object(), "SCHEMA", "")

    def test_repair_needs_a_reason(self):
        with pytest.raises(ValueError):
            Tool.RDFRepairSPARQL(object(), "SCHEMA", "q", "SELECT ?s", "")

    def test_answer_needs_a_list_of_rows(self):
        with pytest.raises(TypeError):
            Tool.RDFAnswer(object(), "q", "not a list")


# --- Cycle 2: a description compiled into JSON-LD --------------------------------------

def node(nodeID, nodeType, name, rels=None):
    return {"@id": nodeID, "@type": nodeType, "name": name, "relationships": rels or {}}


def link(targetID, targetType):
    return [{"@id": targetID, "@type": targetType}]


def buildDocument():
    """1 building, 2 floors, 2 spaces each, 2 sensors per space: 15 nodes."""
    nodes = [node("BLDG", "bot:Building", "Building")]
    for f in (1, 2):
        nodes.append(node(f"BLDG-F{f}", "bot:Storey", f"Floor {f}",
                          {"brick:hasLocation": link("BLDG", "bot:Building")}))
        for s in (1, 2):
            spaceID = f"BLDG-F{f}-S{s}"
            nodes.append(node(spaceID, "bot:Space", f"Space {f}.{s}",
                              {"brick:hasLocation": link(f"BLDG-F{f}", "bot:Storey")}))
            for kind, cls in (("T", "brick:Temperature_Sensor"), ("H", "brick:Humidity_Sensor")):
                nodes.append(node(f"{spaceID}-{kind}1", cls, f"{kind} sensor",
                                  {"brick:hasLocation": link(spaceID, "bot:Space")}))
    return {"@context": {}, "@graph": nodes}


@pytest.fixture
def vocabulary():
    return Tool.JSONLDVocabulary()


@pytest.fixture
def document():
    return json.dumps(buildDocument())


class TestJSONLDVocabulary:
    def test_classes_come_from_the_serializer(self, vocabulary):
        # Serialization.IRIs() is the authority: it is what the graph is finally built from
        assert {"bot:Space", "brick:Temperature_Sensor"} <= vocabulary["classes"]

    def test_pairs_come_from_the_schema(self, vocabulary):
        assert ("bot:Space", "bot:Storey") in vocabulary["pairs"]["brick:hasLocation"]

    def test_block_lists_classes_and_pairs(self, vocabulary):
        block = Tool.JSONLDVocabularyBlock(vocabulary)
        assert "brick:Temperature_Sensor" in block
        assert "bot:Space -brick:hasLocation->" in block

    def test_block_builds_its_own_vocabulary(self):
        assert "CLASSES" in Tool.JSONLDVocabularyBlock()


class TestJSONLDNotationBlock:
    def test_example_is_generated_by_the_library(self):
        notation = Tool.JSONLDNotationBlock()
        example = json.loads(notation[notation.find("{"):])
        assert len(example["@graph"]) == 4

    def test_example_passes_its_own_validator(self):
        notation = Tool.JSONLDNotationBlock()
        example = notation[notation.find("{"):]
        assert Tool.JSONLDValidate(example)[0] is not None


class TestJSONLDLegalPair:
    def test_unknown_subject_class_cannot_be_judged(self, vocabulary):
        # Sensor classes are absent from the pair table, so there is nothing to check
        assert Tool.JSONLDLegalPair(vocabulary, "brick:hasLocation",
                                     "brick:Temperature_Sensor", "bot:Space")

    def test_known_pair_allowed(self, vocabulary):
        assert Tool.JSONLDLegalPair(vocabulary, "brick:hasLocation", "bot:Space", "bot:Storey")

    def test_known_subject_with_illegal_object(self, vocabulary):
        assert not Tool.JSONLDLegalPair(vocabulary, "brick:hasLocation", "bot:Space", "bot:Site")


class TestJSONLDValidate:
    def test_accepts_a_correct_document(self, document, vocabulary):
        jsonld, error = Tool.JSONLDValidate(document, vocabulary)
        assert jsonld is not None and error == ""
        assert len(jsonld["@graph"]) == 15

    def test_rebuilds_the_context(self, document, vocabulary):
        # The model's own '@context' is not trusted: it is derived from the prefixes used
        jsonld, _ = Tool.JSONLDValidate(document, vocabulary)
        assert set(jsonld["@context"]) == {"bot", "brick"}

    def test_accepts_a_fenced_reply(self, document, vocabulary):
        assert Tool.JSONLDValidate(f"```json\n{document}\n```", vocabulary)[0] is not None

    def test_accepts_prose_around_the_document(self, document, vocabulary):
        assert Tool.JSONLDValidate(f"Sure!\n{document}\nHope it helps.", vocabulary)[0] is not None

    def test_rejects_a_truncated_document(self, document, vocabulary):
        jsonld, error = Tool.JSONLDValidate(document[:200], vocabulary)
        assert jsonld is None and "not valid JSON" in error

    def test_rejects_prose_only(self, vocabulary):
        jsonld, error = Tool.JSONLDValidate("I cannot do that.", vocabulary)
        assert jsonld is None and "no JSON document" in error

    def test_rejects_a_missing_graph(self, vocabulary):
        assert Tool.JSONLDValidate('{"@context": {}}', vocabulary)[0] is None

    def test_rejects_an_empty_graph(self, vocabulary):
        assert Tool.JSONLDValidate('{"@context": {}, "@graph": []}', vocabulary)[0] is None

    def test_rejects_an_invented_class(self, vocabulary):
        bad = buildDocument()
        bad["@graph"][0]["@type"] = "brick:Wormhole"
        jsonld, error = Tool.JSONLDValidate(json.dumps(bad), vocabulary)
        assert jsonld is None and "not in the vocabulary" in error

    def test_rejects_an_invented_relationship(self, vocabulary):
        bad = buildDocument()
        bad["@graph"][1]["relationships"] = {"brick:teleportsTo": link("BLDG", "bot:Building")}
        jsonld, error = Tool.JSONLDValidate(json.dumps(bad), vocabulary)
        assert jsonld is None and "not in the vocabulary" in error

    def test_rejects_a_dangling_reference(self, vocabulary):
        bad = buildDocument()
        bad["@graph"][1]["relationships"]["brick:hasLocation"] = link("NOPE", "bot:Building")
        jsonld, error = Tool.JSONLDValidate(json.dumps(bad), vocabulary)
        assert jsonld is None and "no node with that" in error

    def test_rejects_a_duplicate_id(self, vocabulary):
        bad = buildDocument()
        bad["@graph"][2]["@id"] = "BLDG"
        jsonld, error = Tool.JSONLDValidate(json.dumps(bad), vocabulary)
        assert jsonld is None and "more than one node" in error

    def test_rejects_an_inconsistent_target_type(self, vocabulary):
        bad = buildDocument()
        bad["@graph"][1]["relationships"]["brick:hasLocation"] = link("BLDG", "bot:Space")
        jsonld, error = Tool.JSONLDValidate(json.dumps(bad), vocabulary)
        assert jsonld is None and "declared as" in error

    def test_rejects_an_illegal_pair(self, vocabulary):
        bad = buildDocument()
        bad["@graph"].append(node("SITE", "bot:Site", "Site"))
        bad["@graph"][2]["relationships"]["brick:hasLocation"] = link("SITE", "bot:Site")
        jsonld, error = Tool.JSONLDValidate(json.dumps(bad), vocabulary)
        assert jsonld is None and "not a legal pair" in error

    def test_rejects_a_node_without_an_id(self, vocabulary):
        bad = buildDocument()
        del bad["@graph"][1]["@id"]
        assert Tool.JSONLDValidate(json.dumps(bad), vocabulary)[0] is None

    def test_builds_its_own_vocabulary(self, document):
        assert Tool.JSONLDValidate(document)[0] is not None


class TestJSONLDCreateByPrompt:
    @staticmethod
    def _stub(monkeypatch, written, repaired=None):
        monkeypatch.setattr(Tool, "JSONLDWrite", staticmethod(
            lambda llm, vocabulary, notation, request, meter=None: written))
        monkeypatch.setattr(Tool, "JSONLDRepair", staticmethod(
            lambda llm, vocabulary, notation, request, document, reason, meter=None: repaired))

    def test_returns_a_validated_document(self, monkeypatch, document):
        self._stub(monkeypatch, document)
        result = Cycle.JSONLDCreateByPrompt("a building", llm=object())
        assert len(result["jsonld"]["@graph"]) == 15
        assert result["attempts"] == 1

    def test_reports_usage(self, monkeypatch, document):
        self._stub(monkeypatch, document)
        result = Cycle.JSONLDCreateByPrompt("a building", llm=object())
        assert set(result["usage"]) >= {"calls", "cost", "promptTokens"}

    def test_repairs_a_rejected_document(self, monkeypatch, document):
        self._stub(monkeypatch, "not JSON at all", repaired=document)
        result = Cycle.JSONLDCreateByPrompt("a building", llm=object())
        assert result["attempts"] == 2 and len(result["jsonld"]["@graph"]) == 15

    def test_gives_up_after_the_repair_budget(self, monkeypatch):
        self._stub(monkeypatch, "not JSON", repaired="still not JSON")
        with pytest.raises(ValueError):
            Cycle.JSONLDCreateByPrompt("a building", llm=object(), maxRepairs=1)

    def test_result_builds_a_graph(self, monkeypatch, document):
        self._stub(monkeypatch, document)
        result = Cycle.JSONLDCreateByPrompt("a building", llm=object())
        graph, _ = NetworkX.ByJSONLD(jsonld=result["jsonld"], validateGraph=False, printReport=False)
        assert graph.number_of_nodes() == 15
        assert graph.number_of_edges() == 14        # every node but the building has a parent
        assert NetworkX.IsolatedNodes(graph) == []

    def test_records_into_a_shared_meter(self, monkeypatch, document):
        self._stub(monkeypatch, document)
        meter = CostMeter()
        Cycle.JSONLDCreateByPrompt("a building", llm=object(), meter=meter)
        assert meter.Total()["calls"] == 0   # the stub bypasses LLM.Complete, nothing is charged

    def test_missing_prompt_raises(self):
        with pytest.raises(ValueError):
            Cycle.JSONLDCreateByPrompt("")


class TestJSONLDAgentInputValidation:
    def test_write_needs_a_request(self):
        with pytest.raises(ValueError):
            Tool.JSONLDWrite(object(), "VOCAB", "NOTATION", "")

    def test_repair_needs_a_reason(self):
        with pytest.raises(ValueError):
            Tool.JSONLDRepair(object(), "VOCAB", "NOTATION", "req", "{}", "")


# --- Cycle 3: a PDF into a Document, a PropertySet and the node it belongs to -----------

CANDIDATE_OBJECTS = [
    {"@id": "FRV9", "@type": "bot:Site", "name": "Lotto"},
    {"@id": "FRV9-APT", "@type": "brick:Zone", "name": "Appartamento"},
    {"@id": "DOC-1", "@type": "btwin:Document", "name": "2022-06-01_APE.pdf"},
]

GOOD_REPLY = json.dumps({
    "name": "Catasto dei Fabbricati - Foglio 44",
    "linkTo": "FRV9-APT",
    "pset": {
        "name": "Dati catastali",
        "properties": [
            {"name": "Foglio", "value": 44, "quantity": "IfcInteger"},
            {"name": "Comune", "value": "PIANORO", "quantity": "IfcLabel"},
            {"name": "Superficie", "value": 78.5, "quantity": "IfcReal", "unit": "m2"},
        ],
    },
})


def replyWith(**changes):
    """GOOD_REPLY with one thing altered, so each test names its own defect."""
    data = json.loads(GOOD_REPLY)
    for key, value in changes.items():
        if key.startswith("pset_"):
            data["pset"][key[5:]] = value
        else:
            data[key] = value
    return json.dumps(data)


@pytest.fixture
def candidates():
    return Tool.DocumentCandidates(CANDIDATE_OBJECTS)


class TestDocumentCandidates:
    def test_lists_every_object(self, candidates):
        text, lookup = candidates
        assert set(lookup) == {"FRV9", "FRV9-APT", "DOC-1"}
        assert "FRV9-APT" in text and "Appartamento" in text and "brick:Zone" in text

    def test_skips_entries_without_an_id(self):
        text, lookup = Tool.DocumentCandidates(CANDIDATE_OBJECTS + [{"name": "orphan"}, "junk"])
        assert set(lookup) == {"FRV9", "FRV9-APT", "DOC-1"}

    def test_no_usable_object_raises(self):
        with pytest.raises(ValueError):
            Tool.DocumentCandidates([])


class TestDocumentValidate:
    def test_accepts_a_good_reply(self, candidates):
        data, error = Tool.DocumentValidate(GOOD_REPLY, candidates[1])
        assert error == "" and data["linkTo"] == "FRV9-APT"

    def test_accepts_fences_and_prose(self, candidates):
        assert Tool.DocumentValidate(f"Sure!\n```json\n{GOOD_REPLY}\n```", candidates[1])[0]

    def test_rejects_prose_only(self, candidates):
        data, error = Tool.DocumentValidate("I could not read it.", candidates[1])
        assert data is None and "no JSON" in error

    def test_rejects_a_truncated_reply(self, candidates):
        # The token ceiling hit mid-object: there is no closing brace to find
        data, error = Tool.DocumentValidate(GOOD_REPLY[:40], candidates[1])
        assert data is None and "no JSON" in error

    def test_rejects_malformed_json(self, candidates):
        data, error = Tool.DocumentValidate('{"name": "x", }', candidates[1])
        assert data is None and "not valid JSON" in error

    def test_rejects_a_missing_name(self, candidates):
        assert Tool.DocumentValidate(replyWith(name=""), candidates[1])[0] is None

    def test_rejects_a_name_copied_from_the_candidates(self, candidates):
        # The model handed a list of existing nodes will sometimes name the document after one
        # of them instead of after what it read, and that is silently wrong
        data, error = Tool.DocumentValidate(replyWith(name="2022-06-01_APE.pdf"), candidates[1])
        assert data is None and "existing node" in error

    def test_name_check_ignores_case_and_padding(self, candidates):
        assert Tool.DocumentValidate(replyWith(name="  appartamento  "), candidates[1])[0] is None

    def test_rejects_an_invented_link(self, candidates):
        data, error = Tool.DocumentValidate(replyWith(linkTo="NOPE-1"), candidates[1])
        assert data is None and "not one of the CANDIDATES" in error

    def test_rejects_a_missing_pset(self, candidates):
        assert Tool.DocumentValidate(replyWith(pset={}), candidates[1])[0] is None

    def test_rejects_an_empty_property_list(self, candidates):
        assert Tool.DocumentValidate(replyWith(pset_properties=[]), candidates[1])[0] is None

    def test_rejects_a_property_without_a_value(self, candidates):
        reply = replyWith(pset_properties=[{"name": "Foglio", "value": None}])
        data, error = Tool.DocumentValidate(reply, candidates[1])
        assert data is None and "no value" in error

    def test_rejects_a_duplicate_property(self, candidates):
        reply = replyWith(pset_properties=[{"name": "Foglio", "value": 1},
                                           {"name": "Foglio", "value": 2}])
        data, error = Tool.DocumentValidate(reply, candidates[1])
        assert data is None and "more than once" in error

    def test_rejects_an_unknown_quantity(self, candidates):
        # The first live run produced exactly this: 'IfcDate', which Property would not know
        reply = replyWith(pset_properties=[{"name": "Data", "value": "x", "quantity": "IfcDate"}])
        data, error = Tool.DocumentValidate(reply, candidates[1])
        assert data is None and "IfcDate" in error

    def test_quantity_is_optional(self, candidates):
        reply = replyWith(pset_properties=[{"name": "Foglio", "value": "44"}])
        assert Tool.DocumentValidate(reply, candidates[1])[0] is not None

    def test_without_candidates_only_the_shape_is_checked(self):
        assert Tool.DocumentValidate(replyWith(linkTo="ANYTHING"))[0] is not None


class TestDocumentInferValidation:
    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            Tool.DocumentInfer(object(), "text", "cands", mode="clever")

    def test_manual_mode_needs_a_request(self):
        with pytest.raises(ValueError):
            Tool.DocumentInfer(object(), "text", "cands", request="", mode="manual")

    def test_no_content_and_no_images_raises(self):
        with pytest.raises(ValueError):
            Tool.DocumentInfer(object(), "", "cands")

    def test_repair_needs_a_reason(self):
        with pytest.raises(ValueError):
            Tool.DocumentRepair(object(), "text", "cands", "{}", "")


class TestDocumentCreateByPrompt:
    """The two model calls are stubbed, so no network and no key."""

    @staticmethod
    def _stub(monkeypatch, text, reply, repaired=None, images=None):
        monkeypatch.setattr(Tool, "DocumentText", staticmethod(lambda p: text))
        monkeypatch.setattr(Tool, "DocumentImages",
                            staticmethod(lambda p, maxPages=4, dpi=150: images or ["data:x"]))
        monkeypatch.setattr(Tool, "DocumentInfer", staticmethod(
            lambda llm, content, cands, request="", mode="auto", meter=None, images=None: reply))
        monkeypatch.setattr(Tool, "DocumentRepair", staticmethod(
            lambda llm, content, cands, reply, reason, request="", meter=None, images=None: repaired))

    def test_builds_the_document_and_the_pset(self, monkeypatch, tmp_path):
        self._stub(monkeypatch, "some text", GOOD_REPLY)
        pdf = tmp_path / "plan.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = Cycle.DocumentCreateByPrompt(pdf, objects=CANDIDATE_OBJECTS, llm=object())

        assert result["document"]["@type"] == "btwin:Document"
        assert result["document"]["@id"] == "plan"          # the file stem
        assert result["document"]["name"] == "Catasto dei Fabbricati - Foglio 44"
        assert result["pset"]["name"] == "Dati catastali"
        assert len(result["pset"]["ifc:HasProperties"]) == 3

    def test_keeps_units_and_quantities(self, monkeypatch, tmp_path):
        self._stub(monkeypatch, "some text", GOOD_REPLY)
        pdf = tmp_path / "plan.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = Cycle.DocumentCreateByPrompt(pdf, objects=CANDIDATE_OBJECTS, llm=object())
        surface = next(p for p in result["pset"]["ifc:HasProperties"] if p["name"] == "Superficie")
        assert surface["nominalValue"] == {"type": "IfcReal", "value": 78.5, "unit": "m2"}

    def test_names_the_owning_node_without_wiring_it(self, monkeypatch, tmp_path):
        self._stub(monkeypatch, "some text", GOOD_REPLY)
        pdf = tmp_path / "plan.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = Cycle.DocumentCreateByPrompt(pdf, objects=CANDIDATE_OBJECTS, llm=object())
        assert result["linkTo"] == "FRV9-APT"
        assert result["linkToObject"]["name"] == "Appartamento"
        # nothing was attached: the caller decides whether the inference is good enough
        assert result["linkToObject"].get("relationships", {}) == {}
        assert result["document"]["relationships"] == {}

    def test_explicit_uid_wins_over_the_file_name(self, monkeypatch, tmp_path):
        self._stub(monkeypatch, "some text", GOOD_REPLY)
        pdf = tmp_path / "plan.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = Cycle.DocumentCreateByPrompt(pdf, objects=CANDIDATE_OBJECTS, llm=object(),
                                              documentUID="CAT-1")
        assert result["document"]["@id"] == "CAT-1"

    def test_text_layer_is_preferred(self, monkeypatch, tmp_path):
        self._stub(monkeypatch, "readable text", GOOD_REPLY)
        pdf = tmp_path / "plan.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        assert Cycle.DocumentCreateByPrompt(pdf, objects=CANDIDATE_OBJECTS,
                                            llm=object())["source"] == "text"

    def test_a_scan_falls_back_to_page_images(self, monkeypatch, tmp_path):
        # No text layer at all is what a scan looks like, and the only reliable tell
        self._stub(monkeypatch, "   ", GOOD_REPLY)
        pdf = tmp_path / "scan.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        assert Cycle.DocumentCreateByPrompt(pdf, objects=CANDIDATE_OBJECTS,
                                            llm=object())["source"] == "images"

    def test_a_rejected_reply_is_repaired(self, monkeypatch, tmp_path):
        self._stub(monkeypatch, "text", replyWith(linkTo="NOPE"), repaired=GOOD_REPLY)
        pdf = tmp_path / "plan.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = Cycle.DocumentCreateByPrompt(pdf, objects=CANDIDATE_OBJECTS, llm=object())
        assert result["attempts"] == 2 and result["linkTo"] == "FRV9-APT"

    def test_gives_up_after_the_repair_budget(self, monkeypatch, tmp_path):
        self._stub(monkeypatch, "text", "not json", repaired="still not json")
        pdf = tmp_path / "plan.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with pytest.raises(ValueError):
            Cycle.DocumentCreateByPrompt(pdf, objects=CANDIDATE_OBJECTS, llm=object(),
                                         maxRepairs=1)

    def test_reports_usage(self, monkeypatch, tmp_path):
        self._stub(monkeypatch, "text", GOOD_REPLY)
        pdf = tmp_path / "plan.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = Cycle.DocumentCreateByPrompt(pdf, objects=CANDIDATE_OBJECTS, llm=object())
        assert set(result["usage"]) >= {"calls", "cost", "promptTokens"}

    def test_missing_inputs_raise(self):
        with pytest.raises(ValueError):
            Cycle.DocumentCreateByPrompt(None, objects=CANDIDATE_OBJECTS)

    def test_unknown_mode_raises(self, tmp_path):
        with pytest.raises(ValueError):
            Cycle.DocumentCreateByPrompt(tmp_path / "x.pdf", objects=CANDIDATE_OBJECTS,
                                         mode="clever")


class TestDocumentReaders:
    """The PDF readers, against files made on the spot."""

    def test_text_is_extracted(self, tmp_path):
        pymupdf = pytest.importorskip("pymupdf")
        pytest.importorskip("pypdf")
        path = tmp_path / "text.pdf"
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 72), "Foglio 44 Particella 1115")
        doc.save(str(path))
        doc.close()
        assert "Particella 1115" in Tool.DocumentText(path)

    def test_a_page_without_text_reads_as_empty(self, tmp_path):
        pymupdf = pytest.importorskip("pymupdf")
        pytest.importorskip("pypdf")
        path = tmp_path / "blank.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(path))
        doc.close()
        assert Tool.DocumentText(path).strip() == ""

    def test_pages_render_to_data_uris(self, tmp_path):
        pymupdf = pytest.importorskip("pymupdf")
        path = tmp_path / "blank.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.new_page()
        doc.save(str(path))
        doc.close()
        images = Tool.DocumentImages(path, maxPages=1, dpi=72)
        assert len(images) == 1 and images[0].startswith("data:image/png;base64,")

    def test_missing_file_raises(self, tmp_path):
        pytest.importorskip("pypdf")
        with pytest.raises(OSError):
            Tool.DocumentText(tmp_path / "nope.pdf")


# --- Cycle 4: an instruction into a patch, and the patch into an edited document --------

SENSOR_PATCH = {
    "addNodes": [node("BLDG-F1-S1-C1", "brick:CO2_Sensor", "CO2 sensor",
                      {"brick:hasLocation": link("BLDG-F1-S1", "bot:Space")})],
}


@pytest.fixture
def edited():
    """The document of cycle 2, as a dict rather than as a reply."""
    return buildDocument()


class TestJSONLDDocumentBlock:
    def test_lists_every_node_and_edge(self, edited):
        block = Tool.JSONLDDocumentBlock(edited)
        assert "NODES (15)" in block and "RELATIONSHIPS (14)" in block
        assert "BLDG-F1  a bot:Storey  'Floor 1'" in block
        assert "BLDG-F1 -brick:hasLocation-> BLDG" in block

    def test_a_document_without_a_graph_raises(self):
        with pytest.raises(ValueError):
            Tool.JSONLDDocumentBlock({"@context": {}})


class TestJSONLDEditPatch:
    def test_reads_a_patch(self):
        patch, error = Tool.JSONLDEditPatch(json.dumps(SENSOR_PATCH))
        assert error == "" and len(patch["addNodes"]) == 1

    def test_accepts_a_fenced_reply(self):
        assert Tool.JSONLDEditPatch("```json\n" + json.dumps(SENSOR_PATCH) + "\n```")[0] is not None

    def test_rejects_prose_only(self):
        assert Tool.JSONLDEditPatch("I cannot do that.")[0] is None

    def test_rejects_an_invented_operation(self):
        patch, error = Tool.JSONLDEditPatch('{"deleteEverything": ["BLDG"]}')
        assert patch is None and "deleteEverything" in error

    def test_rejects_an_operation_that_is_not_a_list(self):
        assert Tool.JSONLDEditPatch('{"addNodes": {"@id": "X"}}')[0] is None

    def test_rejects_a_patch_that_changes_nothing(self):
        # Every operation empty is the model declining without saying so
        patch, error = Tool.JSONLDEditPatch('{"addNodes": [], "removeNodes": []}')
        assert patch is None and "empty" in error


class TestJSONLDApplyEdit:
    def test_adds_a_node(self, edited):
        document, error = Tool.JSONLDApplyEdit(edited, SENSOR_PATCH)
        assert error == "" and len(document["@graph"]) == 16

    def test_leaves_the_original_alone(self, edited):
        Tool.JSONLDApplyEdit(edited, SENSOR_PATCH)
        assert len(edited["@graph"]) == 15

    def test_adds_a_relationship_with_the_target_type(self, edited):
        patch = {"addRelationships": [{"subject": "BLDG-F1-S1", "relationship": "brick:isPartOf",
                                       "object": "BLDG"}]}
        document, _ = Tool.JSONLDApplyEdit(edited, patch)
        space = next(n for n in document["@graph"] if n["@id"] == "BLDG-F1-S1")
        assert space["relationships"]["brick:isPartOf"] == link("BLDG", "bot:Building")

    def test_adding_a_relationship_twice_is_not_an_error(self, edited):
        patch = {"addRelationships": [{"subject": "BLDG-F1", "relationship": "brick:hasLocation",
                                       "object": "BLDG"}]}
        document, error = Tool.JSONLDApplyEdit(edited, patch)
        storey = next(n for n in document["@graph"] if n["@id"] == "BLDG-F1")
        assert error == "" and len(storey["relationships"]["brick:hasLocation"]) == 1

    def test_a_new_node_may_be_pointed_at_in_the_same_patch(self, edited):
        patch = {
            "addNodes": [node("ZONE", "brick:Zone", "Zone")],
            "addRelationships": [{"subject": "BLDG-F1-S1", "relationship": "brick:hasLocation",
                                  "object": "ZONE"}],
        }
        document, error = Tool.JSONLDApplyEdit(edited, patch)
        assert error == "" and len(document["@graph"]) == 16

    def test_removes_a_relationship(self, edited):
        patch = {"removeRelationships": [{"subject": "BLDG-F1", "relationship": "brick:hasLocation",
                                          "object": "BLDG"}]}
        document, _ = Tool.JSONLDApplyEdit(edited, patch)
        storey = next(n for n in document["@graph"] if n["@id"] == "BLDG-F1")
        assert storey["relationships"] == {}

    def test_removing_a_node_takes_the_relationships_aimed_at_it(self, edited):
        document, _ = Tool.JSONLDApplyEdit(edited, {"removeNodes": ["BLDG-F1-S1"]})
        assert len(document["@graph"]) == 14
        # The two sensors of that space now point at nothing, so they cannot keep the link
        assert all("brick:hasLocation" not in n["relationships"]
                   for n in document["@graph"] if n["@id"].startswith("BLDG-F1-S1-"))

    def test_renames_a_node(self, edited):
        document, _ = Tool.JSONLDApplyEdit(edited, {"renameNodes": [{"@id": "BLDG",
                                                                     "name": "Head office"}]})
        assert document["@graph"][0]["name"] == "Head office"

    def test_rejects_an_id_that_is_already_taken(self, edited):
        patch = {"addNodes": [node("BLDG", "bot:Building", "Another building")]}
        document, error = Tool.JSONLDApplyEdit(edited, patch)
        assert document is None and "already in the document" in error

    def test_rejects_an_unknown_node(self, edited):
        document, error = Tool.JSONLDApplyEdit(edited, {"removeNodes": ["GHOST"]})
        assert document is None and "not in the document" in error

    def test_rejects_a_relationship_end_that_does_not_exist(self, edited):
        patch = {"addRelationships": [{"subject": "BLDG", "relationship": "brick:hasLocation",
                                       "object": "GHOST"}]}
        document, error = Tool.JSONLDApplyEdit(edited, patch)
        assert document is None and "GHOST" in error

    def test_rejects_removing_a_relationship_that_is_not_there(self, edited):
        patch = {"removeRelationships": [{"subject": "BLDG", "relationship": "brick:hasLocation",
                                          "object": "BLDG-F1"}]}
        document, error = Tool.JSONLDApplyEdit(edited, patch)
        assert document is None and "not in the document" in error

    def test_rejects_a_patch_that_empties_the_document(self, edited):
        patch = {"removeNodes": [n["@id"] for n in edited["@graph"]]}
        document, error = Tool.JSONLDApplyEdit(edited, patch)
        assert document is None and "no nodes left" in error

    def test_nothing_is_applied_when_one_operation_fails(self, edited):
        # The rename holds, the removal does not: neither may reach the caller
        patch = {"renameNodes": [{"@id": "BLDG", "name": "Head office"}],
                 "removeNodes": ["GHOST"]}
        assert Tool.JSONLDApplyEdit(edited, patch)[0] is None
        assert edited["@graph"][0]["name"] == "Building"


class TestJSONLDEditByPrompt:
    @staticmethod
    def _stub(monkeypatch, written, repaired=None):
        monkeypatch.setattr(Tool, "JSONLDEdit", staticmethod(
            lambda llm, vocabulary, document, request, meter=None: written))
        monkeypatch.setattr(Tool, "JSONLDEditRepair", staticmethod(
            lambda llm, vocabulary, document, request, patch, reason, meter=None: repaired))

    def test_applies_the_patch(self, monkeypatch, edited):
        self._stub(monkeypatch, json.dumps(SENSOR_PATCH))
        result = Cycle.JSONLDEditByPrompt(edited, "add a CO2 sensor", llm=object())
        assert len(result["jsonld"]["@graph"]) == 16
        assert result["attempts"] == 1 and result["changes"]["addNodes"] == 1

    def test_leaves_the_caller_document_alone(self, monkeypatch, edited):
        self._stub(monkeypatch, json.dumps(SENSOR_PATCH))
        Cycle.JSONLDEditByPrompt(edited, "add a CO2 sensor", llm=object())
        assert len(edited["@graph"]) == 15

    def test_result_builds_a_graph(self, monkeypatch, edited):
        self._stub(monkeypatch, json.dumps(SENSOR_PATCH))
        result = Cycle.JSONLDEditByPrompt(edited, "add a CO2 sensor", llm=object())
        graph, _ = NetworkX.ByJSONLD(jsonld=result["jsonld"], validateGraph=False, printReport=False)
        assert graph.number_of_nodes() == 16 and NetworkX.IsolatedNodes(graph) == []

    def test_repairs_a_rejected_patch(self, monkeypatch, edited):
        self._stub(monkeypatch, "not JSON at all", repaired=json.dumps(SENSOR_PATCH))
        result = Cycle.JSONLDEditByPrompt(edited, "add a CO2 sensor", llm=object())
        assert result["attempts"] == 2 and len(result["jsonld"]["@graph"]) == 16

    def test_an_illegal_pair_is_caught_after_the_patch_is_applied(self, monkeypatch, edited):
        # The patch applies cleanly; it is the edited document that does not hold
        illegal = {"addNodes": [node("SITE", "bot:Site", "Site")],
                   "addRelationships": [{"subject": "BLDG-F1-S1",
                                         "relationship": "brick:hasLocation", "object": "SITE"}]}
        self._stub(monkeypatch, json.dumps(illegal), repaired=json.dumps(SENSOR_PATCH))
        result = Cycle.JSONLDEditByPrompt(edited, "put the space on the site", llm=object())
        assert result["attempts"] == 2

    def test_gives_up_after_the_repair_budget(self, monkeypatch, edited):
        self._stub(monkeypatch, "not JSON", repaired="still not JSON")
        with pytest.raises(ValueError):
            Cycle.JSONLDEditByPrompt(edited, "add a CO2 sensor", llm=object(), maxRepairs=1)

    def test_reports_usage(self, monkeypatch, edited):
        self._stub(monkeypatch, json.dumps(SENSOR_PATCH))
        result = Cycle.JSONLDEditByPrompt(edited, "add a CO2 sensor", llm=object())
        assert set(result["usage"]) >= {"calls", "cost", "promptTokens"}

    def test_missing_inputs_raise(self, edited):
        with pytest.raises(ValueError):
            Cycle.JSONLDEditByPrompt(edited, "")
        with pytest.raises(ValueError):
            Cycle.JSONLDEditByPrompt({"@context": {}}, "add a sensor")
        with pytest.raises(ValueError):
            Cycle.JSONLDEditByPrompt({"@graph": []}, "add a sensor")


class TestJSONLDEditAgentInputValidation:
    def test_edit_needs_a_request(self):
        with pytest.raises(ValueError):
            Tool.JSONLDEdit(object(), "VOCAB", "DOCUMENT", "")

    def test_repair_needs_a_reason(self):
        with pytest.raises(ValueError):
            Tool.JSONLDEditRepair(object(), "VOCAB", "DOCUMENT", "req", "{}", "")


# --- Cycle 5: an instruction into a SPARQL update ---------------------------------------

U_INSERT = PREFIXES + """INSERT DATA {
  <https://example.org/test/space-02> a bot:Space ; rdfs:label "Cucina" ;
      brick:hasLocation <https://example.org/test/storey-01> . }"""
U_DELETE = PREFIXES + """DELETE WHERE {
  <https://example.org/test/space-01> brick:hasLocation <https://example.org/test/zone-01> }"""
# Legal vocabulary, clean parse, a pattern the graph does not hold: changes nothing
U_NOOP = PREFIXES + "DELETE WHERE { <https://example.org/test/ghost-01> ?p ?o }"


@pytest.fixture
def stubEditAgents(monkeypatch):
    """Replace the two model-calling agents of cycle 5: no network, no key."""
    def apply(written, repaired=None):
        monkeypatch.setattr(Tool, "RDFWriteUpdate", staticmethod(
            lambda llm, grounding, request, meter=None: written))
        monkeypatch.setattr(Tool, "RDFRepairUpdate", staticmethod(
            lambda llm, grounding, request, sparql, reason, meter=None: repaired))
    return apply


class TestValidateUpdate:
    def test_accepts_an_insert(self, rdf_schema):
        checked, error = SPARQL.ValidateUpdate(U_INSERT, rdf_schema["terms"])
        assert checked is not None and error == ""

    def test_accepts_a_delete(self, rdf_schema):
        assert SPARQL.ValidateUpdate(U_DELETE, rdf_schema["terms"])[0] is not None

    def test_refuses_a_select(self, rdf_schema):
        checked, error = SPARQL.ValidateUpdate("SELECT * WHERE { ?s ?p ?o }", rdf_schema["terms"])
        assert checked is None and "SELECT is not allowed" in error

    def test_refuses_to_drop_a_graph(self, rdf_schema):
        assert SPARQL.ValidateUpdate("DROP ALL", rdf_schema["terms"])[0] is None

    def test_refuses_to_name_a_graph(self, rdf_schema):
        update = "INSERT DATA { GRAPH <https://x> { <https://a> <https://b> <https://c> } }"
        checked, error = SPARQL.ValidateUpdate(update, rdf_schema["terms"])
        assert checked is None and "GRAPH" in error

    def test_refuses_to_reach_the_network(self, rdf_schema):
        update = "DELETE { ?s ?p ?o } WHERE { SERVICE <https://evil> { ?s ?p ?o } }"
        assert SPARQL.ValidateUpdate(update, rdf_schema["terms"])[0] is None

    def test_refuses_a_syntax_error(self, rdf_schema):
        checked, error = SPARQL.ValidateUpdate("INSERT DATA { <a> ", rdf_schema["terms"])
        assert checked is None and "Syntax error" in error

    def test_refuses_an_invented_term(self, rdf_schema):
        update = PREFIXES + "INSERT DATA { <https://example.org/test/x> a brick:Invented }"
        checked, error = SPARQL.ValidateUpdate(update, rdf_schema["terms"])
        assert checked is None and "brick:Invented" in error

    def test_refuses_an_empty_update(self):
        pytest.importorskip("rdflib")
        assert SPARQL.ValidateUpdate("")[0] is None

    def test_a_class_the_graph_lacks_is_legal_in_an_edit(self, rdf_schema):
        # An edit may introduce vocabulary a query could never have asked about
        update = PREFIXES + ("INSERT DATA { <https://example.org/test/t-01> "
                             "a brick:Temperature_Sensor }")
        assert SPARQL.ValidateUpdate(update, rdf_schema["terms"])[0] is None
        assert SPARQL.ValidateUpdate(update, Tool.RDFEditTerms(rdf_schema))[0] is not None


class TestRDFEditTerms:
    def test_covers_both_vocabularies(self, rdf_schema):
        terms = Tool.RDFEditTerms(rdf_schema)
        assert "brick:Temperature_Sensor" in terms     # BTwin vocabulary, not in the graph
        assert "btwin:hasDocument" in terms            # graph vocabulary

    def test_works_without_a_schema(self):
        assert "bot:Space" in Tool.RDFEditTerms()

    def test_block_lists_what_may_be_introduced(self):
        block = Tool.RDFEditVocabularyBlock()
        assert "ADDITIONAL VOCABULARY" in block and "brick:Temperature_Sensor" in block


class TestRDFApplyUpdate:
    def test_reports_what_it_added(self, rdf_graph):
        edited, added, removed, error = Tool.RDFApplyUpdate(rdf_graph, U_INSERT)
        assert error == "" and len(added) == 3 and removed == []
        assert len(edited) == len(rdf_graph) + 3

    def test_leaves_the_caller_graph_alone(self, rdf_graph):
        before = len(rdf_graph)
        Tool.RDFApplyUpdate(rdf_graph, U_INSERT)
        assert len(rdf_graph) == before

    def test_keeps_the_namespace_bindings(self, rdf_graph):
        edited, _, _, _ = Tool.RDFApplyUpdate(rdf_graph, U_INSERT)
        assert dict(rdf_graph.namespaces()).keys() <= dict(edited.namespaces()).keys()

    def test_an_update_that_cannot_run_is_a_reason_not_a_crash(self, rdf_graph):
        edited, _, _, error = Tool.RDFApplyUpdate(rdf_graph, "INSERT DATA { not sparql }")
        assert edited is None and error != ""


class TestRDFEditByPrompt:
    def test_applies_the_update(self, stubEditAgents, rdf_graph, rdf_schema):
        stubEditAgents(U_INSERT)
        result = Cycle.RDFEditByPrompt(rdf_graph, "add a kitchen", llm=object(), schema=rdf_schema)
        assert len(result["added"]) == 3 and result["removed"] == []
        assert result["attempts"] == 1

    def test_renders_the_change_compactly(self, stubEditAgents, rdf_graph, rdf_schema):
        stubEditAgents(U_INSERT)
        result = Cycle.RDFEditByPrompt(rdf_graph, "add a kitchen", llm=object(), schema=rdf_schema)
        assert ("https://example.org/test/space-02", "rdf:type", "bot:Space") in result["added"]

    def test_the_caller_graph_is_untouched_by_default(self, stubEditAgents, rdf_graph, rdf_schema):
        before = len(rdf_graph)
        stubEditAgents(U_INSERT)
        result = Cycle.RDFEditByPrompt(rdf_graph, "add a kitchen", llm=object(), schema=rdf_schema)
        assert len(rdf_graph) == before and len(result["graph"]) == before + 3

    def test_in_place_commits_to_the_caller_graph(self, stubEditAgents, rdf_graph, rdf_schema):
        before = len(rdf_graph)
        stubEditAgents(U_INSERT)
        result = Cycle.RDFEditByPrompt(rdf_graph, "add a kitchen", llm=object(),
                                       schema=rdf_schema, inPlace=True)
        assert len(rdf_graph) == before + 3 and result["graph"] is rdf_graph

    def test_deletes(self, stubEditAgents, rdf_graph, rdf_schema):
        stubEditAgents(U_DELETE)
        result = Cycle.RDFEditByPrompt(rdf_graph, "unlink the room from the flat",
                                       llm=object(), schema=rdf_schema)
        assert len(result["removed"]) == 1 and result["added"] == []

    def test_an_update_that_changes_nothing_is_rewritten_and_adopted(
            self, stubEditAgents, rdf_graph, rdf_schema):
        stubEditAgents(U_NOOP, repaired=U_INSERT)
        result = Cycle.RDFEditByPrompt(rdf_graph, "add a kitchen", llm=object(), schema=rdf_schema)
        assert len(result["added"]) == 3

    def test_rewrite_kept_only_when_it_changes_something(
            self, stubEditAgents, rdf_graph, rdf_schema):
        stubEditAgents(U_NOOP, repaired=U_NOOP)
        result = Cycle.RDFEditByPrompt(rdf_graph, "remove the ghost", llm=object(),
                                       schema=rdf_schema)
        assert result["added"] == [] and result["removed"] == []
        assert result["sparql"] == U_NOOP

    def test_an_invalid_rewrite_keeps_the_unchanged_graph(
            self, stubEditAgents, rdf_graph, rdf_schema):
        stubEditAgents(U_NOOP, repaired="DROP ALL")
        result = Cycle.RDFEditByPrompt(rdf_graph, "remove the ghost", llm=object(),
                                       schema=rdf_schema)
        assert result["added"] == [] and result["sparql"] == U_NOOP

    def test_nothing_is_committed_when_nothing_changed(
            self, stubEditAgents, rdf_graph, rdf_schema):
        before = set(rdf_graph)
        stubEditAgents(U_NOOP, repaired=U_NOOP)
        Cycle.RDFEditByPrompt(rdf_graph, "remove the ghost", llm=object(),
                              schema=rdf_schema, inPlace=True)
        assert set(rdf_graph) == before

    def test_a_rejected_update_is_repaired(self, stubEditAgents, rdf_graph, rdf_schema):
        stubEditAgents("SELECT * WHERE { ?s ?p ?o }", repaired=U_INSERT)
        result = Cycle.RDFEditByPrompt(rdf_graph, "add a kitchen", llm=object(), schema=rdf_schema)
        assert result["attempts"] == 2 and len(result["added"]) == 3

    def test_gives_up_after_the_repair_budget(self, stubEditAgents, rdf_graph, rdf_schema):
        stubEditAgents("DROP ALL", repaired="DROP ALL")
        with pytest.raises(ValueError):
            Cycle.RDFEditByPrompt(rdf_graph, "wipe it", llm=object(), schema=rdf_schema,
                                  maxRepairs=1)

    def test_builds_the_schema_when_not_supplied(self, stubEditAgents, rdf_graph):
        stubEditAgents(U_INSERT)
        assert len(Cycle.RDFEditByPrompt(rdf_graph, "add a kitchen", llm=object())["added"]) == 3

    def test_reports_usage(self, stubEditAgents, rdf_graph, rdf_schema):
        stubEditAgents(U_INSERT)
        result = Cycle.RDFEditByPrompt(rdf_graph, "add a kitchen", llm=object(), schema=rdf_schema)
        assert set(result["usage"]) >= {"calls", "cost", "promptTokens"}

    def test_missing_inputs_raise(self, rdf_graph):
        with pytest.raises(ValueError):
            Cycle.RDFEditByPrompt(rdf_graph, "")
        with pytest.raises(ValueError):
            Cycle.RDFEditByPrompt(None, "add a kitchen")


class TestRDFEditAgentInputValidation:
    def test_write_needs_grounding(self):
        with pytest.raises(ValueError):
            Tool.RDFWriteUpdate(object(), "", "add a kitchen")

    def test_write_needs_a_request(self):
        with pytest.raises(ValueError):
            Tool.RDFWriteUpdate(object(), "SCHEMA", "")

    def test_repair_needs_a_reason(self):
        with pytest.raises(ValueError):
            Tool.RDFRepairUpdate(object(), "SCHEMA", "req", U_INSERT, "")

    def test_apply_needs_a_graph(self):
        pytest.importorskip("rdflib")
        with pytest.raises(ValueError):
            Tool.RDFApplyUpdate(None, U_INSERT)
