
import pytest

from btwin import RDF, SPARQL, NetworkX, Serialization, SpatialElement

# --- RDF fixtures ---------------------------------------------------------------------
# A miniature of the graph main.py builds: a spatial hierarchy, two spaces sharing a label,
# and an energy index reachable only through blank nodes.
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
<space-02> a bot:Space ; rdfs:label "Camera" ; brick:hasLocation <storey-01>, <zone-01> .
<space-03> a bot:Space ; rdfs:label "Cucina" ; brick:hasLocation <storey-01>, <zone-01> .
<zone-01> a brick:Zone ; rdfs:label "Appartamento" ;
    brick:hasLocation <bldg-01>, <storey-01> ; btwin:hasDocument <doc-01> .
<doc-01> a btwin:Document ; rdfs:label "APE.pdf" ; ifc:HasPropertySets <pset-01> .
<pset-01> a ifc:IfcPropertySet ; rdfs:label "Indici" ;
    ifc:HasProperties [ a ifc:IfcPropertySingleValue ;
        rdfs:label "EPgl,nren" ; ifc:NominalValue 66.98 ; ifc:Unit "kWh/m2 anno" ] .
"""

RDF_PREFIXES = """PREFIX bot: <https://w3id.org/bot#>
PREFIX brick: <https://brickschema.org/schema/Brick#>
PREFIX btwin: <https://example.org/test/btwin#>
PREFIX ifc: <https://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2_TC1/OWL#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

Q_SPACES = RDF_PREFIXES + "SELECT ?s ?name WHERE { ?s a bot:Space ; rdfs:label ?name . }"
Q_ASK = RDF_PREFIXES + "ASK { <https://example.org/test/site-01> a bot:Site }"
Q_INDEX = RDF_PREFIXES + """SELECT ?label ?value ?unit WHERE {
  <https://example.org/test/zone-01> btwin:hasDocument ?doc .
  ?doc ifc:HasPropertySets ?pset . ?pset ifc:HasProperties ?p .
  ?p rdfs:label ?label ; ifc:NominalValue ?value ; ifc:Unit ?unit . } LIMIT 100"""
# Legal vocabulary, clean parse, invented hop: matches nothing
Q_WRONG = RDF_PREFIXES + """SELECT ?label WHERE {
  <https://example.org/test/zone-01> btwin:hasDocument ?doc .
  ?doc btwin:hasDocument ?other . ?other rdfs:label ?label . } LIMIT 100"""


@pytest.fixture
def rdf_graph(tmp_path):
    pytest.importorskip("rdflib")
    ttl = tmp_path / "test.ttl"
    ttl.write_text(RDF_TURTLE, encoding="utf-8")
    return RDF.ByTTL(ttl, baseIRI=RDF_BASE_IRI)


@pytest.fixture
def rdf_schema(rdf_graph):
    return RDF.SchemaSummary(rdf_graph)


class TestConstructor:
    def test_default_is_multidigraph(self):
        import networkx as nx
        G = NetworkX.Constructor()
        assert isinstance(G, nx.MultiDiGraph)

    def test_digraph(self):
        import networkx as nx
        G = NetworkX.Constructor(graphType="DiGraph")
        assert isinstance(G, nx.DiGraph)

    def test_with_name(self):
        G = NetworkX.Constructor(name="Test Graph")
        assert G.graph["name"] == "Test Graph"

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            NetworkX.Constructor(graphType="InvalidType")


class TestAddNodeByObject:
    def test_adds_node(self, site_obj):
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, site_obj)
        assert "site-01" in G.nodes

    def test_node_has_type_attr(self, site_obj):
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, site_obj)
        assert G.nodes["site-01"]["type"] == "bot:Site"


class TestAddEdgesByObject:
    def test_adds_edges(self, space_obj, storey_obj):
        G = NetworkX.Constructor()
        SpatialElement.SetLocationRelationship(
            spatialElementObject=space_obj,
            linkedObject=storey_obj,
        )
        NetworkX.AddNodeByObject(G, space_obj)
        NetworkX.AddNodeByObject(G, storey_obj)
        NetworkX.AddEdgesByObject(G, space_obj)
        assert G.number_of_edges() > 0

    def test_skips_missing_target(self, space_obj):
        G = NetworkX.Constructor()
        SpatialElement.SetRelationship(
            spatialElementObject=space_obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="nonexistent",
            linkedObjectType="bot:Storey",
            validate=False,
        )
        NetworkX.AddNodeByObject(G, space_obj)
        NetworkX.AddEdgesByObject(G, space_obj)
        assert G.number_of_edges() == 0


class TestByJSONLD:
    def test_full_round_trip(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(
            spatialElementObject=building_obj,
            linkedObject=site_obj,
        )
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj],
            strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        assert "site-01" in G.nodes
        assert "bldg-01" in G.nodes
        assert G.number_of_edges() >= 1


class TestToJSONAndByJSON:
    def test_save_and_reload(self, tmp_path, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(
            spatialElementObject=building_obj,
            linkedObject=site_obj,
        )
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj],
            strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)

        out = tmp_path / "graph.json"
        NetworkX.ToJSON(G, savePath=str(out))
        assert out.exists()

        G2 = NetworkX.ByJSON(source=str(out))
        assert set(G.nodes) == set(G2.nodes)


class TestSubgraphByObjectTypes:
    def test_filter_by_type(self, site_obj, building_obj, storey_obj):
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj, storey_obj],
            strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        sub = NetworkX.SubgraphByObjectTypes(G, objectTypes=["bot:Site"])
        assert "site-01" in sub.nodes
        assert "bldg-01" not in sub.nodes


class TestSubgraphByObjectUID:
    def test_subgraph_extraction(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(
            spatialElementObject=building_obj,
            linkedObject=site_obj,
        )
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj],
            strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        sub = NetworkX.SubgraphByObjectUID(G, objectUID="bldg-01", nodeDegree=1)
        assert "bldg-01" in sub.nodes


class TestIsolatedNodes:
    def test_detects_isolated(self, site_obj, building_obj):
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj],
            strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        isolated = NetworkX.IsolatedNodes(G)
        # Both nodes have no edges between them in this setup
        assert isinstance(isolated, list)

    def test_no_isolated_when_connected(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(
            spatialElementObject=building_obj,
            linkedObject=site_obj,
        )
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj],
            strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        isolated = NetworkX.IsolatedNodes(G)
        assert len(isolated) == 0


class TestValidate:
    def test_valid_graph_returns_graph(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(
            spatialElementObject=building_obj,
            linkedObject=site_obj,
        )
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj],
            strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        import networkx as nx
        result = NetworkX.Validate(G, printReport=False)
        # Validate returns the graph itself
        assert isinstance(result, (nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph))

    def test_validate_does_not_raise_on_valid(self, site_obj):
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj],
            strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        # Should not raise
        result = NetworkX.Validate(G, printReport=False)
        assert result is G


class TestConstructorAdvanced:
    def test_graph_type(self):
        import networkx as nx
        G = NetworkX.Constructor(graphType="Graph")
        assert isinstance(G, nx.Graph)

    def test_multigraph_type(self):
        import networkx as nx
        G = NetworkX.Constructor(graphType="MultiGraph")
        assert isinstance(G, nx.MultiGraph)

    def test_with_graph_attrs(self):
        G = NetworkX.Constructor(graphAttrs={"version": "1.0", "author": "test"})
        assert G.graph["version"] == "1.0"
        assert G.graph["author"] == "test"

    def test_with_node_defaults(self):
        G = NetworkX.Constructor(nodeDefaults={"color": "blue"})
        assert G.graph["node_defaults"] == {"color": "blue"}

    def test_with_edge_defaults(self):
        G = NetworkX.Constructor(edgeDefaults={"weight": 1.0})
        assert G.graph["edge_defaults"] == {"weight": 1.0}

    def test_invalid_graph_attrs_raises(self):
        with pytest.raises(TypeError):
            NetworkX.Constructor(graphAttrs="bad")

    def test_invalid_node_defaults_raises(self):
        with pytest.raises(TypeError):
            NetworkX.Constructor(nodeDefaults="bad")

    def test_invalid_edge_defaults_raises(self):
        with pytest.raises(TypeError):
            NetworkX.Constructor(edgeDefaults="bad")


class TestAddNodeByObjectAdvanced:
    def test_node_with_name(self, site_obj):
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, site_obj)
        assert G.nodes["site-01"].get("name") == "Test Site"

    def test_multiple_nodes(self, site_obj, building_obj, storey_obj, space_obj):
        G = NetworkX.Constructor()
        for obj in [site_obj, building_obj, storey_obj, space_obj]:
            NetworkX.AddNodeByObject(G, obj)
        assert G.number_of_nodes() == 4

    def test_non_dict_raises(self):
        G = NetworkX.Constructor()
        with pytest.raises(TypeError):
            NetworkX.AddNodeByObject(G, "not_dict")


class TestAddEdgesByObjectAdvanced:
    def test_non_dict_raises(self):
        G = NetworkX.Constructor()
        with pytest.raises(TypeError):
            NetworkX.AddEdgesByObject(G, "not_dict")

    def test_source_not_in_graph(self, space_obj):
        G = NetworkX.Constructor()
        # source not added to graph
        SpatialElement.SetRelationship(
            spatialElementObject=space_obj,
            relationshipName="brick:hasLocation",
            linkedObjectUID="x", linkedObjectType="bot:Storey",
            validate=False,
        )
        # Should not raise, just print error and skip
        result = NetworkX.AddEdgesByObject(G, space_obj)
        assert result is G

    def test_deduplication(self, space_obj, storey_obj):
        G = NetworkX.Constructor()
        SpatialElement.SetLocationRelationship(space_obj, linkedObject=storey_obj)
        NetworkX.AddNodeByObject(G, space_obj)
        NetworkX.AddNodeByObject(G, storey_obj)
        NetworkX.AddEdgesByObject(G, space_obj)
        initial_edges = G.number_of_edges()
        NetworkX.AddEdgesByObject(G, space_obj, deduplicate=True)
        assert G.number_of_edges() == initial_edges


class TestByJSONLDAdvanced:
    def test_with_validation(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(building_obj, linkedObject=site_obj)
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj], strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=True, printReport=False)
        assert G.number_of_nodes() == 2

    def test_missing_input_raises(self):
        with pytest.raises(ValueError):
            NetworkX.ByJSONLD(jsonld=None, jsonPath=None)

    def test_invalid_jsonld_raises(self):
        with pytest.raises(ValueError):
            NetworkX.ByJSONLD(jsonld={"no_graph": []})

    def test_from_file(self, tmp_path, site_obj):
        import json
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj], strictValidation=False,
        )
        p = tmp_path / "test.json"
        p.write_text(json.dumps(jsonld))
        G = NetworkX.ByJSONLD(jsonPath=str(p), validateGraph=False, printReport=False)
        assert "site-01" in G.nodes

    def test_digraph_type(self, site_obj):
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj], strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, graphType="DiGraph", validateGraph=False, printReport=False)
        import networkx as nx
        assert isinstance(G, nx.DiGraph)


class TestToJSONAdvanced:
    def test_returns_json_string(self, site_obj):
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, site_obj)
        result = NetworkX.ToJSON(G)
        assert isinstance(result, str)
        import json
        data = json.loads(result)
        assert "nodes" in data or "links" in data

    def test_none_graph_raises(self):
        with pytest.raises(TypeError):
            NetworkX.ToJSON(None)


class TestByJSONAdvanced:
    def test_invalid_source_raises(self):
        with pytest.raises(ValueError):
            NetworkX.ByJSON(source=123)

    def test_missing_file_raises(self):
        with pytest.raises(OSError):
            NetworkX.ByJSON(source="nonexistent_file.json")

    def test_invalid_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{}")
        with pytest.raises(ValueError):
            NetworkX.ByJSON(source=str(p))


class TestSubgraphByObjectTypesAdvanced:
    def test_no_match_returns_empty(self, site_obj):
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj], strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        sub = NetworkX.SubgraphByObjectTypes(G, objectTypes=["bot:Storey"])
        assert sub.number_of_nodes() == 0

    def test_none_types_raises(self, site_obj):
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, site_obj)
        with pytest.raises(ValueError):
            NetworkX.SubgraphByObjectTypes(G, objectTypes=None)

    def test_empty_types_raises(self, site_obj):
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, site_obj)
        with pytest.raises(ValueError):
            NetworkX.SubgraphByObjectTypes(G, objectTypes=[])

    def test_keep_isolates_false(self, site_obj, building_obj):
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj], strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        sub = NetworkX.SubgraphByObjectTypes(
            G, objectTypes=["bot:Site", "bot:Building"], keepIsolates=False,
        )
        # Both are isolated (no edges between them), so should be empty
        assert sub.number_of_nodes() == 0


class TestIsolatedNodesAdvanced:
    def test_non_graph_raises(self):
        with pytest.raises(TypeError):
            NetworkX.IsolatedNodes("not_a_graph")

    def test_empty_graph(self):
        G = NetworkX.Constructor()
        assert NetworkX.IsolatedNodes(G) == []


class TestValidateAdvanced:
    def test_non_graph_raises(self):
        with pytest.raises(TypeError):
            NetworkX.Validate("not_a_graph")

    def test_with_print_report(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(building_obj, linkedObject=site_obj)
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj], strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        # Should not raise
        NetworkX.Validate(G, printReport=True)


class TestAddNodeByObjectPSet:
    """Test AddNodeByObject with PSet objects to cover PSet flattening paths."""

    def test_pset_node_flattened(self):
        from btwin import Property, PropertySet
        pset = PropertySet.Constructor("pset-01", "Thermal")
        prop = Property.Constructor("U-Value", propertyValue=0.25, propertyQuantity="IfcReal")
        PropertySet.SetProperty(pset=pset, property=prop)
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, pset)
        assert "pset-01" in G.nodes
        # flattened property should appear as attribute
        data = G.nodes["pset-01"]
        assert data.get("U-Value") == 0.25

    def test_pset_with_enumerated_values(self):
        from btwin import Property, PropertySet
        pset = PropertySet.Constructor("pset-02", "Materials")
        prop = Property.Constructor(
            "Materials", propertyValues=["Brick", "Concrete"],
            propertyQuantity="IfcLabel",
            propertyType="IfcPropertyEnumeratedValue",
        )
        PropertySet.SetProperty(pset=pset, property=prop)
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, pset)
        data = G.nodes["pset-02"]
        assert isinstance(data.get("Materials"), list)


class TestAddNodeByObjectKPISet:
    """Test AddNodeByObject with KPISet objects to cover KPISet compression paths."""

    def test_kpiset_node(self):
        from btwin import KPI, KPISet
        ks = KPISet.Constructor("ks-01", "Test KPIs")
        kpi = KPI.Constructor("kpi-01", kpiName="Energy", kpiValue=100.0, kpiUnit="kWh")
        KPISet.SetKPI(ks, kpi)
        KPISet.SetTimestep(ks, hasBeginning="2025-01-01T00:00:00Z", hasEnd="2025-12-31T23:59:59Z")
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, ks)
        assert "ks-01" in G.nodes
        data = G.nodes["ks-01"]
        assert data.get("type") == "btwin:KPISet"

    def test_kpiset_with_associated_object(self):
        from btwin import KPISet
        ks = KPISet.Constructor("ks-02", "Test")
        KPISet.SetAssociatedObject(ks, linkedObjectUID="bldg-01", linkedObjectType="bot:Building")
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, ks)
        data = G.nodes["ks-02"]
        assert data.get("associatedObjectId") == "bldg-01"


class TestAddNodeByObjectGeneral:
    """Test AddNodeByObject general paths."""

    def test_upsert_false_raises(self, site_obj):
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, site_obj)
        with pytest.raises(ValueError):
            NetworkX.AddNodeByObject(G, site_obj, upsert=False)

    def test_upsert_true_updates(self, site_obj):
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, site_obj)
        site_obj["name"] = "Updated Site"
        NetworkX.AddNodeByObject(G, site_obj, upsert=True)
        assert G.nodes["site-01"]["name"] == "Updated Site"

    def test_extra_attrs(self, site_obj):
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, site_obj, extraAttrs={"custom": "value"})
        assert G.nodes["site-01"]["custom"] == "value"

    def test_extra_attrs_non_dict_raises(self, site_obj):
        G = NetworkX.Constructor()
        with pytest.raises(TypeError):
            NetworkX.AddNodeByObject(G, site_obj, extraAttrs="bad")

    def test_apply_defaults(self, site_obj):
        G = NetworkX.Constructor(nodeDefaults={"color": "blue"})
        NetworkX.AddNodeByObject(G, site_obj, applyDefaults=True)
        assert G.nodes["site-01"]["color"] == "blue"

    def test_missing_id_raises(self):
        G = NetworkX.Constructor()
        with pytest.raises(ValueError):
            NetworkX.AddNodeByObject(G, {"name": "no id"})


class TestAddEdgesByObjectDetailed:
    """Cover more edge-adding paths."""

    def test_none_relationships_skips(self, site_obj):
        G = NetworkX.Constructor()
        site_obj["relationships"] = None
        NetworkX.AddNodeByObject(G, site_obj)
        NetworkX.AddEdgesByObject(G, site_obj)
        assert G.number_of_edges() == 0

    def test_non_dict_relationships_raises(self, site_obj):
        G = NetworkX.Constructor()
        site_obj["relationships"] = "bad"
        NetworkX.AddNodeByObject(G, site_obj)
        with pytest.raises(ValueError):
            NetworkX.AddEdgesByObject(G, site_obj)

    def test_empty_rel_name_raises(self, site_obj):
        G = NetworkX.Constructor()
        site_obj["relationships"] = {"": [{"@id": "x", "@type": "t"}]}
        NetworkX.AddNodeByObject(G, site_obj)
        with pytest.raises(ValueError):
            NetworkX.AddEdgesByObject(G, site_obj)


class TestToJSONSavePath:
    def test_save_without_extension(self, tmp_path, site_obj):
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, site_obj)
        out = tmp_path / "graph"
        NetworkX.ToJSON(G, savePath=str(out))
        assert (tmp_path / "graph.json").exists()


class TestSubgraphByObjectUIDAdvanced:
    def test_missing_inputs_raises(self):
        with pytest.raises(ValueError):
            NetworkX.SubgraphByObjectUID(nxGraph=None, objectUID="x")

    def test_non_graph_raises(self):
        with pytest.raises(TypeError):
            NetworkX.SubgraphByObjectUID(nxGraph="bad", objectUID="x")

    def test_missing_node_raises(self):
        G = NetworkX.Constructor()
        with pytest.raises(ValueError):
            NetworkX.SubgraphByObjectUID(G, objectUID="nonexistent")

    def test_resolve_by_attribute(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(building_obj, linkedObject=site_obj)
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj], strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        sub = NetworkX.SubgraphByObjectUID(G, objectUID="bldg-01", nodeDegree=2)
        assert "bldg-01" in sub.nodes


class TestNodeLinkedPSets:
    def test_missing_inputs_raises(self):
        with pytest.raises(ValueError):
            NetworkX.NodeLinkedPSets(nxGraph=None, nodeObjectUID="x")

    def test_non_graph_raises(self):
        with pytest.raises(TypeError):
            NetworkX.NodeLinkedPSets(nxGraph="bad", nodeObjectUID="x")

    def test_node_not_found_raises(self):
        G = NetworkX.Constructor()
        with pytest.raises(ValueError):
            NetworkX.NodeLinkedPSets(G, nodeObjectUID="nonexistent")

    def test_pset_linked_to_node(self):
        from btwin import Property, PropertySet
        G = NetworkX.Constructor()
        # Add a space node
        space = SpatialElement.Constructor("space-01", "bot:Space", "Room")
        pset = PropertySet.Constructor("pset-01", "Thermal")
        prop = Property.Constructor("U-Value", propertyValue=0.25, propertyQuantity="IfcReal")
        PropertySet.SetProperty(pset=pset, property=prop)
        SpatialElement.SetPSetRelationship(space, pset=pset)

        NetworkX.AddNodeByObject(G, space)
        NetworkX.AddNodeByObject(G, pset)
        NetworkX.AddEdgesByObject(G, space)
        psets = NetworkX.NodeLinkedPSets(G, nodeObjectUID="space-01")
        assert len(psets) >= 1
        assert psets[0][0] == "pset-01"

    def test_no_psets_returns_empty(self, site_obj):
        G = NetworkX.Constructor()
        NetworkX.AddNodeByObject(G, site_obj)
        psets = NetworkX.NodeLinkedPSets(G, nodeObjectUID="site-01")
        assert psets == []


class TestValidateDetailed:
    def test_invalid_node_types_reported(self):
        import networkx as nx
        G = nx.MultiDiGraph()
        G.add_node("n1", type="invalid:Type")
        result = NetworkX.Validate(G, printReport=False)
        # result is the graph itself
        assert isinstance(result, nx.MultiDiGraph)

    def test_missing_node_type_reported(self):
        import networkx as nx
        G = nx.MultiDiGraph()
        G.add_node("n1")  # no type attribute
        result = NetworkX.Validate(G, printReport=True)
        assert isinstance(result, nx.MultiDiGraph)

    def test_invalid_edge_types_multigraph(self):
        import networkx as nx
        G = nx.MultiDiGraph()
        G.add_node("n1", type="bot:Site")
        G.add_node("n2", type="bot:Building")
        G.add_edge("n1", "n2", type="invalid:rel")
        result = NetworkX.Validate(G, printReport=True)
        assert isinstance(result, nx.MultiDiGraph)

    def test_digraph_edge_validation(self):
        import networkx as nx
        G = nx.DiGraph()
        G.add_node("n1", type="bot:Site")
        G.add_node("n2", type="bot:Building")
        G.add_edge("n1", "n2", type="invalid:rel")
        result = NetworkX.Validate(G, printReport=False)
        assert isinstance(result, nx.DiGraph)

    def test_missing_edge_type_reported(self):
        import networkx as nx
        G = nx.DiGraph()
        G.add_node("n1", type="bot:Site")
        G.add_node("n2", type="bot:Building")
        G.add_edge("n1", "n2")  # no type
        result = NetworkX.Validate(G, printReport=False)
        assert isinstance(result, nx.DiGraph)

    def test_valid_graph_prints_success(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(building_obj, linkedObject=site_obj)
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj], strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        result = NetworkX.Validate(G, printReport=True)
        assert result is G


class TestCompactPSets:
    """Test CompactPSets function to flatten PSet nodes into owners."""

    def _build_graph_with_pset(self):
        import networkx as nx
        G = nx.MultiDiGraph()
        # Add owner node
        G.add_node("space-01", type="bot:Space", name="Room 101")
        # Add PSet node
        G.add_node("pset-01", type="ifc:IfcPropertySet", name="Thermal",
                    **{"U-Value": 0.25, "R-Value": 4.0})
        # Add edge linking owner to PSet
        G.add_edge("space-01", "pset-01", type="ifc:HasPropertySets")
        return G

    def test_compacts_pset_into_owner(self):
        G = self._build_graph_with_pset()
        result = NetworkX.CompactPSets(G)
        assert result is G
        # PSet node should be removed
        assert "pset-01" not in G.nodes
        # Properties should appear on owner
        assert G.nodes["space-01"].get("U-Value") == 0.25

    def test_none_graph_raises(self):
        with pytest.raises(ValueError):
            NetworkX.CompactPSets(None)

    def test_non_graph_raises(self):
        with pytest.raises(TypeError):
            NetworkX.CompactPSets("bad")

    def test_orphan_pset_not_deleted_by_default(self):
        import networkx as nx
        G = nx.MultiDiGraph()
        G.add_node("pset-01", type="ifc:IfcPropertySet", name="Orphan")
        NetworkX.CompactPSets(G, deleteOrphanPSets=False)
        assert "pset-01" in G.nodes

    def test_orphan_pset_deleted_when_flagged(self):
        import networkx as nx
        G = nx.MultiDiGraph()
        G.add_node("pset-01", type="ifc:IfcPropertySet", name="Orphan")
        NetworkX.CompactPSets(G, deleteOrphanPSets=True)
        assert "pset-01" not in G.nodes

    def test_overwrite_false_keeps_existing(self):
        import networkx as nx
        G = nx.MultiDiGraph()
        G.add_node("space-01", type="bot:Space", **{"U-Value": 999})
        G.add_node("pset-01", type="ifc:IfcPropertySet", **{"U-Value": 0.25})
        G.add_edge("space-01", "pset-01", type="ifc:HasPropertySets")
        NetworkX.CompactPSets(G, overwriteExisting=False)
        assert G.nodes["space-01"]["U-Value"] == 999


class TestCompactKPISets:
    """Test CompactKPISets function to flatten KPISet nodes into owners."""

    def _build_graph_with_kpiset(self):
        import networkx as nx
        G = nx.MultiDiGraph()
        # Add owner node
        G.add_node("bldg-01", type="bot:Building", name="Building 1")
        # Add KPISet node with nested structure
        G.add_node("ks-01", type="btwin:KPISet", name="Energy KPIs",
                    **{"btwin:hasKPIs": {
                        "kpi-01": {"@id": "kpi-01", "name": "Energy",
                                   "nominalValue": {"value": 100, "unit": "kWh"}},
                    },
                    "relationships": {
                        "eko:hasEvaluationTimestep": [
                            {"time:hasBeginning": "2025-01-01T00:00:00Z",
                             "time:hasEnd": "2025-12-31T23:59:59Z"}
                        ],
                        "eko:hasAssociatedObject": [
                            {"@id": "bldg-01", "@type": "bot:Building"}
                        ],
                    }})
        # Add edge linking KPISet to owner
        G.add_edge("ks-01", "bldg-01", type="eko:hasAssociatedObject")
        return G

    def test_compacts_kpiset_into_owner(self):
        G = self._build_graph_with_kpiset()
        result = NetworkX.CompactKPISets(G)
        assert result is G
        # KPISet node should be removed
        assert "ks-01" not in G.nodes
        # KPI values should appear on owner
        data = G.nodes["bldg-01"]
        assert "Energy" in data or "kpi_Energy" in data or any("Energy" in str(k) for k in data)

    def test_none_graph_raises(self):
        with pytest.raises(ValueError):
            NetworkX.CompactKPISets(None)

    def test_non_graph_raises(self):
        with pytest.raises(TypeError):
            NetworkX.CompactKPISets("bad")

    def test_orphan_kpiset_deleted(self):
        import networkx as nx
        G = nx.MultiDiGraph()
        G.add_node("ks-01", type="btwin:KPISet", name="Orphan",
                    **{"btwin:hasKPIs": {}})
        NetworkX.CompactKPISets(G, deleteOrphanKpiSets=True)
        assert "ks-01" not in G.nodes

    def test_orphan_kpiset_kept(self):
        import networkx as nx
        G = nx.MultiDiGraph()
        G.add_node("ks-01", type="btwin:KPISet", name="Orphan",
                    **{"btwin:hasKPIs": {}})
        NetworkX.CompactKPISets(G, deleteOrphanKpiSets=False)
        assert "ks-01" in G.nodes


class TestNodeLinkedNodes:
    """Test NodeLinkedNodes function."""

    def test_missing_graph_raises(self):
        with pytest.raises(ValueError):
            NetworkX.NodeLinkedNodes(nxGraph=None, nodeObjectUID="x")

    def test_non_graph_raises(self):
        with pytest.raises(TypeError):
            NetworkX.NodeLinkedNodes(nxGraph="bad", nodeObjectUID="x")

    def test_basic_linked_nodes(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(building_obj, linkedObject=site_obj)
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj], strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        linked = NetworkX.NodeLinkedNodes(G, nodeObjectUID="site-01")
        assert isinstance(linked, list)

    def test_by_node_number(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(building_obj, linkedObject=site_obj)
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj], strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        linked = NetworkX.NodeLinkedNodes(G, nodeNumber="site-01")
        assert isinstance(linked, list)

    def test_filter_by_type(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(building_obj, linkedObject=site_obj)
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj], strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        linked = NetworkX.NodeLinkedNodes(G, nodeObjectUID="site-01",
                                          linkedNodesType="bot:Building")
        assert isinstance(linked, list)

    def test_filter_by_relationship(self, site_obj, building_obj):
        SpatialElement.SetLocationRelationship(building_obj, linkedObject=site_obj)
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj], strictValidation=False,
        )
        G = NetworkX.ByJSONLD(jsonld=jsonld, validateGraph=False, printReport=False)
        linked = NetworkX.NodeLinkedNodes(G, nodeObjectUID="site-01",
                                          relationshipName="brick:hasLocation")
        assert isinstance(linked, list)


class TestByJSONLDFromFile:
    def test_from_file_path(self, tmp_path, site_obj):
        import json
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj], strictValidation=False,
        )
        p = tmp_path / "test.json"
        p.write_text(json.dumps(jsonld))
        G = NetworkX.ByJSONLD(jsonPath=str(p), validateGraph=False, printReport=False)
        assert "site-01" in G.nodes

    def test_with_existing_graph(self, site_obj, building_obj):
        import networkx as nx
        jsonld = Serialization.JSONLDByObjects(
            objects=[site_obj, building_obj], strictValidation=False,
        )
        existing = nx.MultiDiGraph()
        G = NetworkX.ByJSONLD(jsonld=jsonld, graph=existing, validateGraph=False, printReport=False)
        assert G is existing
        assert "site-01" in G.nodes


class TestRDFCompact:
    def test_shortens_known_namespace(self, rdf_graph):
        from rdflib import URIRef
        assert RDF.Compact(rdf_graph, URIRef("https://w3id.org/bot#Space")) == "bot:Space"

    def test_leaves_unknown_namespace(self, rdf_graph):
        from rdflib import URIRef
        unknown = "https://unknown.example/Thing"
        assert RDF.Compact(rdf_graph, URIRef(unknown)) == unknown

    def test_none_graph_raises(self):
        with pytest.raises(ValueError):
            RDF.Compact(None, "x")


class TestRDFIndex:
    def test_indexes_named_nodes(self, rdf_graph):
        assert len(RDF.Index(rdf_graph)["nodes"]) == 9

    def test_shared_label_keeps_both_ids(self, rdf_graph):
        # Two rooms are both called 'Camera'; collapsing them would drop one from every answer
        assert len(RDF.Index(rdf_graph)["labelIndex"]["Camera"]) == 2

    def test_label_maps_to_iri(self, rdf_graph):
        assert RDF.Index(rdf_graph)["labelIndex"]["Appartamento"] == [RDF_BASE_IRI + "zone-01"]

    def test_counts_predicates(self, rdf_graph):
        predicates = RDF.Index(rdf_graph)["predicates"]
        # 1 building + 1 storey + 3 spaces x2 + 1 zone x2
        assert predicates["brick:hasLocation"] == 10
        assert predicates["btwin:hasDocument"] == 1

    def test_none_graph_raises(self):
        pytest.importorskip("rdflib")
        with pytest.raises(ValueError):
            RDF.Index(None)


class TestRDFSchemaSummary:
    def test_lists_only_used_prefixes(self, rdf_schema):
        # rdflib binds ~30 namespaces to every graph; dead ones invite the model to use them
        assert set(rdf_schema["prefixes"]) <= {"bot", "brick", "btwin", "ifc", "rdf", "rdfs"}

    def test_relative_prefix_resolved_against_base(self, rdf_schema):
        assert rdf_schema["prefixes"]["btwin"] == RDF_BASE_IRI + "btwin#"

    def test_shapes_expose_the_blank_node_path(self, rdf_schema):
        assert ("ifc:IfcPropertySet -ifc:HasProperties-> [blank node] ifc:IfcPropertySingleValue"
                in rdf_schema["text"])

    def test_entities_carry_full_iris(self, rdf_schema):
        assert f"<{RDF_BASE_IRI}zone-01>" in rdf_schema["text"]

    def test_terms_cover_classes_and_predicates(self, rdf_schema):
        assert {"bot:Space", "brick:Zone", "brick:hasLocation"} <= rdf_schema["terms"]

    def test_accepts_a_prebuilt_index(self, rdf_graph):
        index = RDF.Index(rdf_graph)
        assert RDF.SchemaSummary(rdf_graph, index)["text"] == RDF.SchemaSummary(rdf_graph)["text"]

    def test_none_graph_raises(self):
        pytest.importorskip("rdflib")
        with pytest.raises(ValueError):
            RDF.SchemaSummary(None)


class TestRDFQuery:
    def test_select_returns_rows(self, rdf_graph):
        assert len(RDF.Query(rdf_graph, Q_SPACES)) == 3

    def test_ask_returns_single_boolean_row(self, rdf_graph):
        assert RDF.Query(rdf_graph, Q_ASK) == [{"result": "true"}]

    def test_reaches_values_behind_blank_nodes(self, rdf_graph):
        rows = RDF.Query(rdf_graph, Q_INDEX)
        assert rows == [{"label": "EPgl,nren", "value": "66.98", "unit": "kWh/m2 anno"}]

    def test_empty_result_is_not_an_error(self, rdf_graph):
        assert RDF.Query(rdf_graph, Q_WRONG) == []

    def test_invalid_sparql_raises(self, rdf_graph):
        with pytest.raises(ValueError):
            RDF.Query(rdf_graph, "SELECT ?s WHERE {")

    def test_missing_inputs_raise(self, rdf_graph):
        with pytest.raises(ValueError):
            RDF.Query(rdf_graph, "")
        with pytest.raises(ValueError):
            RDF.Query(None, Q_SPACES)


class TestRDFSourceNodes:
    def test_collects_iris(self, rdf_graph):
        rows = RDF.Query(rdf_graph, Q_SPACES)
        assert len(RDF.SourceNodes(rdf_graph, rows)) == 3

    def test_literals_are_not_nodes(self, rdf_graph):
        # 'Camera' is a value carried by a node, not a node
        rows = RDF.Query(rdf_graph, Q_SPACES)
        assert all(s.startswith("http") for s in RDF.SourceNodes(rdf_graph, rows))

    def test_no_rows_gives_no_sources(self, rdf_graph):
        assert RDF.SourceNodes(rdf_graph, []) == []

    def test_none_graph_raises(self):
        pytest.importorskip("rdflib")
        with pytest.raises(ValueError):
            RDF.SourceNodes(None, [])


class TestSPARQLForm:
    def test_select(self):
        assert SPARQL.Form(Q_SPACES) == "SELECT"

    def test_ask(self):
        assert SPARQL.Form(Q_ASK) == "ASK"

    def test_not_a_query(self):
        assert SPARQL.Form("hello there") == ""

    def test_empty(self):
        assert SPARQL.Form("") == ""


class TestSPARQLValidate:
    def test_accepts_a_good_select(self, rdf_schema):
        checked, error = SPARQL.Validate(Q_SPACES, rdf_schema["terms"])
        assert checked is not None and error == ""

    def test_appends_a_missing_limit(self, rdf_schema):
        assert "LIMIT 100" in SPARQL.Validate(Q_SPACES, rdf_schema["terms"])[0]

    def test_respects_a_custom_limit(self, rdf_schema):
        assert "LIMIT 5" in SPARQL.Validate(Q_SPACES, rdf_schema["terms"], rowLimit=5)[0]

    def test_never_limits_an_ask(self, rdf_schema):
        # LIMIT on an ASK is a syntax error
        assert "LIMIT" not in SPARQL.Validate(Q_ASK, rdf_schema["terms"])[0].upper()

    @pytest.mark.parametrize("name,query", [
        ("drop", RDF_PREFIXES + "DROP GRAPH <https://example.org/test/>"),
        ("service", RDF_PREFIXES + "SELECT ?s WHERE { SERVICE <http://evil.example/> { ?s ?p ?o } }"),
        ("insert", RDF_PREFIXES + 'INSERT DATA { <https://example.org/test/site-01> rdfs:label "x" }'),
        ("delete", RDF_PREFIXES + "DELETE WHERE { ?s ?p ?o }"),
        ("syntax", RDF_PREFIXES + "SELECT ?s WHERE { ?s brick:hasLocation"),
        ("empty", "   "),
        ("prose", "Sure! Here is the query you asked for."),
    ])
    def test_rejects(self, rdf_schema, name, query):
        checked, error = SPARQL.Validate(query, rdf_schema["terms"])
        assert checked is None and error

    def test_rejects_vocabulary_not_in_the_schema(self, rdf_schema):
        # A hallucinated predicate parses perfectly and returns zero rows, which reads like
        # an honest empty answer - this is the pass that catches it
        checked, error = SPARQL.Validate(
            RDF_PREFIXES + "SELECT ?s WHERE { ?s brick:hasSpace ?o }", rdf_schema["terms"])
        assert checked is None and "brick:hasSpace" in error

    def test_allows_utility_prefixes(self, rdf_schema):
        query = (RDF_PREFIXES + "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
                 "SELECT ?s WHERE { ?s a bot:Space . FILTER(?s != xsd:string) }")
        assert SPARQL.Validate(query, rdf_schema["terms"])[0] is not None

    def test_skips_vocabulary_check_without_terms(self):
        pytest.importorskip("rdflib")
        query = RDF_PREFIXES + "SELECT ?s WHERE { ?s brick:hasSpace ?o }"
        assert SPARQL.Validate(query)[0] is not None

    def test_keyword_inside_a_comment_is_inert(self, rdf_schema):
        query = RDF_PREFIXES + "SELECT ?s WHERE { ?s a bot:Site } # DROP GRAPH <x>\nLIMIT 10"
        assert SPARQL.Validate(query, rdf_schema["terms"])[0] is not None

    def test_keyword_inside_a_literal_is_inert(self, rdf_schema):
        query = RDF_PREFIXES + 'SELECT ?s WHERE { ?s rdfs:label "DROP TABLE" } LIMIT 10'
        assert SPARQL.Validate(query, rdf_schema["terms"])[0] is not None

    def test_hash_in_a_namespace_iri_is_not_a_comment(self, rdf_schema):
        # Stripping comments before IRIs would eat the closing '>' of every PREFIX line
        assert SPARQL.Validate(Q_ASK, rdf_schema["terms"])[0] is not None
