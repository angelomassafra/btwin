
import json
import re

import pytest

from btwin import GraphPlot, NetworkX, SpatialElement


def payloadOf(html):
    """The JSON the page carries, read back the way the page itself reads it."""
    raw = re.search(r'<script id="graph-data" type="application/json">(.*?)</script>',
                    html, re.S).group(1)
    return json.loads(raw.replace("<\\/", "</"))


@pytest.fixture
def graph():
    site = SpatialElement.Constructor("site-01", "bot:Site", "Site")
    building = SpatialElement.Constructor("bldg-01", "bot:Building", "Building")
    storey = SpatialElement.Constructor("storey-01", "bot:Storey", "Ground Floor")
    space = SpatialElement.Constructor("space-01", "bot:Space", "Room 101")
    SpatialElement.SetLocationRelationship(building, linkedObject=site)
    SpatialElement.SetLocationRelationship(storey, linkedObject=building)
    SpatialElement.SetLocationRelationship(space, linkedObject=storey)

    G = NetworkX.Constructor()
    for obj in (site, building, storey, space):
        NetworkX.AddNodeByObject(G, obj)
    for obj in (building, storey, space):
        NetworkX.AddEdgesByObject(G, obj)
    return G


class TestNetworkXByHTMLPayload:
    def test_every_node_and_edge_is_carried(self, graph):
        data = payloadOf(GraphPlot.NetworkXByHTML(graph))
        assert len(data["nodes"]) == graph.number_of_nodes()
        assert len(data["edges"]) == graph.number_of_edges()

    def test_edge_endpoints_are_valid_indices(self, graph):
        data = payloadOf(GraphPlot.NetworkXByHTML(graph))
        count = len(data["nodes"])
        assert all(0 <= e["s"] < count and 0 <= e["t"] < count for e in data["edges"])

    def test_nodes_are_grouped_by_class(self, graph):
        data = payloadOf(GraphPlot.NetworkXByHTML(graph))
        assert set(data["nodeGroups"]) == {"bot:Site", "bot:Building", "bot:Storey", "bot:Space"}
        assert all(data["nodeGroups"][n["g"]] == n["group"] for n in data["nodes"])

    def test_edges_are_grouped_by_class(self, graph):
        data = payloadOf(GraphPlot.NetworkXByHTML(graph))
        assert data["edgeGroups"] == ["brick:hasLocation"]

    def test_every_node_carries_its_metadata(self, graph):
        # This is what the click panel reads, so an empty one would make the page useless
        data = payloadOf(GraphPlot.NetworkXByHTML(graph))
        node = next(n for n in data["nodes"] if n["id"] == "space-01")
        assert node["meta"]["type"] == "bot:Space"
        assert node["meta"]["name"] == "Room 101"

    def test_labels_fall_back_through_the_key_list(self, graph):
        graph.add_node("bare-01", type="bot:Space")          # no name
        data = payloadOf(GraphPlot.NetworkXByHTML(graph))
        assert next(n for n in data["nodes"] if n["id"] == "bare-01")["label"] == "bare-01"

    def test_missing_class_becomes_unknown(self, graph):
        graph.add_node("untyped-01", name="No class")
        data = payloadOf(GraphPlot.NetworkXByHTML(graph))
        assert next(n for n in data["nodes"] if n["id"] == "untyped-01")["group"] == "Unknown"

    def test_positions_are_spread_out(self, graph):
        # The force layout starts from NetworkX, so nodes must not all sit on the origin
        data = payloadOf(GraphPlot.NetworkXByHTML(graph))
        assert max(n["x"] for n in data["nodes"]) > min(n["x"] for n in data["nodes"])

    def test_same_seed_gives_the_same_page(self, graph):
        assert GraphPlot.NetworkXByHTML(graph) == GraphPlot.NetworkXByHTML(graph)

    def test_non_serialisable_attributes_are_kept_as_text(self, graph):
        graph.add_node("odd-01", type="bot:Space", when=object())
        node = next(n for n in payloadOf(GraphPlot.NetworkXByHTML(graph))["nodes"]
                    if n["id"] == "odd-01")
        assert isinstance(node["meta"]["when"], str)

    def test_nested_attributes_survive(self, graph):
        graph.add_node("nested-01", type="bot:Space", rel={"brick:hasLocation": [{"@id": "x"}]})
        node = next(n for n in payloadOf(GraphPlot.NetworkXByHTML(graph))["nodes"]
                    if n["id"] == "nested-01")
        assert node["meta"]["rel"]["brick:hasLocation"][0]["@id"] == "x"


class TestNetworkXByHTMLDocument:
    def test_is_self_contained(self, graph):
        html = GraphPlot.NetworkXByHTML(graph)
        external = [u for u in re.findall(r'(?:src|href)="([^"]+)"', html)
                    if u.startswith(("http", "//"))]
        assert external == []

    def test_carries_its_own_script_and_style(self, graph):
        html = GraphPlot.NetworkXByHTML(graph)
        assert "<canvas" in html and "<style>" in html
        assert "requestAnimationFrame" in html          # the force simulation runs in the page

    def test_markup_in_metadata_cannot_close_the_script(self, graph):
        # A node named '</script><script>alert(1)</script>' must stay data, not become markup
        graph.add_node("evil-01", type="bot:Space", name="</script><script>alert(1)</script>")
        html = GraphPlot.NetworkXByHTML(graph)
        data = payloadOf(html)                           # parses, so the element never closed early
        node = next(n for n in data["nodes"] if n["id"] == "evil-01")
        assert node["label"] == "</script><script>alert(1)</script>"
        assert html.count('<script id="graph-data"') == 1

    def test_title_is_escaped_in_the_markup(self, graph):
        # The raw title also travels inside the JSON payload, where it is inert data; what
        # must not happen is markup reaching the document itself
        html = GraphPlot.NetworkXByHTML(graph, title='Fer<b>rovia</b> "9"')
        heading = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        assert heading == "Fer&lt;b&gt;rovia&lt;/b&gt; &quot;9&quot;"
        assert "<b>rovia" not in re.sub(
            r'<script id="graph-data".*?</script>', "", html, flags=re.S)

    def test_labels_hidden_above_the_threshold(self, graph):
        assert payloadOf(GraphPlot.NetworkXByHTML(graph))["showLabels"] is True
        assert payloadOf(GraphPlot.NetworkXByHTML(graph, showLabelsUpTo=2))["showLabels"] is False


class TestNetworkXByHTMLFile:
    def test_writes_the_file(self, tmp_path, graph):
        out = tmp_path / "graph.html"
        html = GraphPlot.NetworkXByHTML(graph, savePath=str(out))
        assert out.read_text(encoding="utf-8") == html

    def test_adds_the_html_suffix(self, tmp_path, graph):
        GraphPlot.NetworkXByHTML(graph, savePath=str(tmp_path / "graph"))
        assert (tmp_path / "graph.html").exists()

    def test_returns_html_without_a_path(self, graph):
        assert GraphPlot.NetworkXByHTML(graph).startswith("<!doctype html>")


class TestNetworkXByHTMLValidation:
    def test_missing_graph_raises(self):
        with pytest.raises(ValueError):
            GraphPlot.NetworkXByHTML(None)

    def test_non_graph_raises(self):
        with pytest.raises(ValueError):
            GraphPlot.NetworkXByHTML("not a graph")

    def test_bad_node_size_raises(self, graph):
        with pytest.raises(ValueError):
            GraphPlot.NetworkXByHTML(graph, nodeSize=0)

    def test_negative_relax_steps_raises(self, graph):
        with pytest.raises(ValueError):
            GraphPlot.NetworkXByHTML(graph, relaxSteps=-1)

    def test_empty_palette_raises(self, graph):
        with pytest.raises(ValueError):
            GraphPlot.NetworkXByHTML(graph, palette=())

    def test_empty_graph_still_renders(self):
        data = payloadOf(GraphPlot.NetworkXByHTML(NetworkX.Constructor()))
        assert data["nodes"] == [] and data["edges"] == []
