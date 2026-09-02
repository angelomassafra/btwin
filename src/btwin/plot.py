"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

PLOT MODULE
This module defines the functions to plot data, graphs, and models via the BTWIN toolkit.

© Angelo Massafra, 2026
"""

# Dependencies
from __future__ import annotations


# Functions
class Color():

    @staticmethod
    def Dark():

        """Return BTwin's dark color as rgb()"""

        return 'rgb(89,89,89)'

    @staticmethod
    def Light():

        """Return BTwin's light color as rgb()"""

        return 'rgb(237,237,237)'

    @staticmethod
    def Orange():

        """Return BTwin's orange as rgb()"""

        return 'rgb(250,160,120)'

    @staticmethod
    def Purple():

        """Return BTwin's purple as rgb()"""

        return 'rgb(160,30,120)'

    @staticmethod
    def Red():

        """Return BTwin's red as rgb()"""

        return 'rgb(230,80,110)'

    @staticmethod
    def Sunsetdark():

        """Return a matplotlib colormap based on Plotly's 'Sunsetdark' color sequence."""

        # Dependencies
        import plotly.express as px
        from matplotlib.colors import LinearSegmentedColormap

        # Create the colormap
        sunsetdarkColors=[tuple(int(num) / 255 for num in color.strip("rgb()").split(",")) for color in px.colors.sequential.Sunsetdark]
        colormap=LinearSegmentedColormap.from_list("Sunsetdark", sunsetdarkColors
                                                   )
        return colormap

class GraphPlot():

    @staticmethod
    def NetworkXByMatplotlib(
        nxGraph=None,
        *,
        showNodeLabels: bool = True,
        showEdgeLabels: bool = False,
        nodeColorMap: str = "turbo",
        nodeSize: int = 50,
        nodeOpacity: float = 1.0,
        edgeColorMap: str = "turbo",
        edgeWidth: float = 1.0,
        savePath: str | None = None,
        figsize: tuple[int, int] = (10, 10),
        showLegend: bool = True,
        layout: str = "spring",
        layoutSeed: int | None = 42,
        dpi: int = 300,
    ):
        """
        Draw a NetworkX graph with Matplotlib, coloring nodes/edges by their type/label.

        Node color groups are determined from node attributes (priority order: 'label', 'type', '@type').
        Edge color groups are determined from edge attributes (priority order: 'label', 'type', 'relationship', 'relation', 'name').
        If attributes are missing, sensible fallbacks are used.
        """

        # --- Imports & validation -------------------------------------------------
        try:
            import re  # ADDITION

            import matplotlib as mpl
            import matplotlib.pyplot as plt
            import networkx as nx
        except Exception as exc:
            raise ImportError("This function requires matplotlib and networkx.") from exc

        # --- ADDITION: helper functions ------------------------------------------
        def _is_hex_color(s: str) -> bool:
            if not isinstance(s, str):
                return False
            s = s.strip()
            return re.fullmatch(r"#?[0-9A-Fa-f]{3}|#?[0-9A-Fa-f]{6}|#?[0-9A-Fa-f]{8}", s) is not None

        def _normalize_hex(s: str) -> str:
            s = s.strip()
            return s if s.startswith("#") else f"#{s}"

        # --- Validation -----------------------------------------------------------
        if nxGraph is None or not hasattr(nxGraph, "nodes"):
            raise ValueError("`nxGraph` must be a valid NetworkX graph instance.")

        if not isinstance(nodeSize, (int, float)) or nodeSize <= 0:
            raise ValueError("`nodeSize` must be a positive number.")
        if not (0 <= float(nodeOpacity) <= 1):
            raise ValueError("`nodeOpacity` must be in [0, 1].")
        if not isinstance(edgeWidth, (int, float)) or edgeWidth < 0:
            raise ValueError("`edgeWidth` must be a non-negative number.")
        if not isinstance(figsize, (tuple, list)) or len(figsize) != 2:
            raise ValueError("`figsize` must be a (width, height) tuple.")

        # --- Choose layout --------------------------------------------------------
        if layout == "spring":
            pos = nx.spring_layout(nxGraph, seed=layoutSeed)
        elif layout == "kamada_kawai":
            pos = nx.kamada_kawai_layout(nxGraph)
        elif layout == "circular":
            pos = nx.circular_layout(nxGraph)
        elif layout == "random":
            pos = nx.random_layout(nxGraph, seed=layoutSeed)
        elif layout == "shell":
            pos = nx.shell_layout(nxGraph)
        elif layout == "spectral":
            pos = nx.spectral_layout(nxGraph)
        else:
            raise ValueError(f"Unsupported layout '{layout}'.")

        # --- Node attributes: group labels, colors, and display labels ------------
        nodeGroupAttr = {}
        for n, data in nxGraph.nodes(data=True):
            if isinstance(data, dict):
                group = data.get("label") or data.get("type") or data.get("@type") or "Unknown"
            else:
                group = "Unknown"
            nodeGroupAttr[n] = str(group)

        nodeList = list(nxGraph.nodes())
        nodeGroupsOrdered = [nodeGroupAttr.get(n, "Unknown") for n in nodeList]
        uniqueNodeGroups = sorted(set(nodeGroupsOrdered))

        try:
            nodeCmap = mpl.cm.get_cmap(nodeColorMap, len(uniqueNodeGroups) or 1)
        except Exception:
            nodeCmap = mpl.cm.get_cmap("viridis", len(uniqueNodeGroups) or 1)
        nodePalette = {g: nodeCmap(i) for i, g in enumerate(uniqueNodeGroups)}
        nodeColors = [nodePalette[g] for g in nodeGroupsOrdered]

        # --- ADDITION: solid hex node color override ------------------------------
        if _is_hex_color(nodeColorMap):
            nodeColors = [_normalize_hex(nodeColorMap)] * len(nodeList)

        nodeTextLabels = {}
        for n, data in nxGraph.nodes(data=True):
            if not showNodeLabels:
                continue
            labelVal = None
            if isinstance(data, dict):
                labelVal = str(n) or data.get("name") or data.get("id") or data.get("@id")
            nodeTextLabels[n] = str(labelVal if labelVal is not None else n)

        # --- Edge attributes: group labels, colors, and display labels ------------
        edgeLabelAttr = {}
        for u, v, edata in nxGraph.edges(data=True):
            if isinstance(edata, dict):
                eLabel = edata.get("label") or edata.get("type") or edata.get("relationship") or edata.get("relation") or edata.get("name")
            else:
                eLabel = None
            edgeLabelAttr[(u, v)] = str(eLabel) if eLabel is not None else "Unknown"

        uniqueEdgeGroups = sorted(set(edgeLabelAttr.values()))
        try:
            edgeCmap = mpl.cm.get_cmap(edgeColorMap, len(uniqueEdgeGroups) or 1)
        except Exception:
            edgeCmap = mpl.cm.get_cmap("viridis", len(uniqueEdgeGroups) or 1)
        edgePalette = {g: edgeCmap(i) for i, g in enumerate(uniqueEdgeGroups)}

        edgeList = list(nxGraph.edges())
        edgeColors = [edgePalette[edgeLabelAttr[(u, v)]] for (u, v) in edgeList]

        # --- ADDITION: solid hex edge color override ------------------------------
        if _is_hex_color(edgeColorMap):
            edgeColors = [_normalize_hex(edgeColorMap)] * len(edgeList)

        # --- Create figure/axes ---------------------------------------------------
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
        ax.set_axis_off()

        # --- Draw graph -----------------------------------------------------------
        nx.draw_networkx_nodes(
            nxGraph, pos, nodelist=nodeList,
            node_color=nodeColors, node_size=nodeSize, alpha=nodeOpacity, ax=ax
        )
        nx.draw_networkx_edges(
            nxGraph, pos, edgelist=edgeList,
            edge_color=edgeColors, width=edgeWidth, ax=ax
        )

        if showNodeLabels and nodeTextLabels:
            nx.draw_networkx_labels(nxGraph, pos, labels=nodeTextLabels, font_size=10, font_color="black", ax=ax)

        if showEdgeLabels and edgeLabelAttr:
            nx.draw_networkx_edge_labels(nxGraph, pos, edge_labels=edgeLabelAttr, font_size=8, ax=ax)

        # --- Legend ---------------------------------------------------------------
        if showLegend:
            legendHandles = []
            legendHandles.append(mpl.lines.Line2D([], [], linestyle='None', label='Nodes:'))
            for g in uniqueNodeGroups:
                legendHandles.append(
                    mpl.lines.Line2D([], [], marker='o', linestyle='None', markersize=8, label=str(g), color=nodePalette[g])
                )
            legendHandles.append(mpl.lines.Line2D([], [], linestyle='None', label='Edges:'))
            for g in uniqueEdgeGroups:
                legendHandles.append(
                    mpl.lines.Line2D([], [], marker='_', linestyle='None', markersize=12, label=str(g), color=edgePalette[g])
                )
            ax.legend(
                handles=legendHandles,
                loc="upper left",
                bbox_to_anchor=(1.02, 1),
                borderaxespad=0.,
                frameon=True
            )

        # --- Save (optional) ------------------------------------------------------
        if savePath is not None:
            fig.savefig(savePath, format="png", dpi=dpi, bbox_inches="tight")

        # --- Display & return -----------------------------------------------------
        print(f"Drawn graph with {nxGraph.number_of_nodes()} nodes and {nxGraph.number_of_edges()} edges.")
        plt.tight_layout()
        plt.show()
        return fig, ax


    @staticmethod
    def NetworkXByPlotly(
        nxGraph=None,
        *,
        showNodeLabels: bool = True,
        showEdgeLabels: bool = False,
        nodeColorMap: str = "Turbo",      # Plotly colorscale name
        nodeSize: int = 12,               # in px; here it is the marker diameter
        nodeOpacity: float = 1.0,
        edgeColorMap: str = "Turbo",
        edgeWidth: float = 1.0,
        savePath: str | None = None,      # ".html" -> write_html; otherwise -> write_image (requires kaleido)
        figsize: tuple[int, int] = (1000, 800),  # (w,h) in px for Plotly
        showLegend: bool = True,
        layout: str = "spring",
        layoutSeed: int | None = 42,
        legendOutside: bool = True,       # place the legend outside the plotting area
    ):
        """
        Draw a NetworkX graph with Plotly, coloring nodes/edges by their type/label.

        Args:
            nxGraph: (networkx.Graph | DiGraph | MultiGraph | MultiDiGraph) Graph to draw.
            showNodeLabels: If True, show node labels (priority: 'name' → 'id' → '@id' → node key).
            showEdgeLabels: If True, show edge labels near edge midpoints.
            nodeColorMap: Plotly colorscale name for nodes (e.g., 'Turbo', 'Viridis').
            nodeSize: Marker size (pixels).
            nodeOpacity: Marker opacity [0..1].
            edgeColorMap: Plotly colorscale name for edges.
            edgeWidth: Edge line width (pixels).
            savePath: If provided, saves the figure (.html via write_html, else try write_image).
            figsize: (width, height) in pixels for the figure.
            showLegend: Show legend for node and edge groups.
            layout: {'spring','kamada_kawai','circular','random','shell','spectral'} NetworkX layout.
            layoutSeed: Seed for deterministic layouts when applicable.
            legendOutside: Place legend outside the plotting area on the right.

        Returns:
            plotly.graph_objs.Figure: Interactive Plotly figure.

        Raises:
            ValueError: On invalid inputs/parameters.
            ImportError: If plotly or networkx are not available.
        """
        # --- Imports & validation
        try:
            import networkx as nx
            import plotly.graph_objects as go
            from plotly.colors import sample_colorscale
        except Exception as exc:
            raise ImportError("This function requires plotly and networkx.") from exc

        if nxGraph is None or not hasattr(nxGraph, "nodes"):
            raise ValueError("`nxGraph` must be a valid NetworkX graph instance.")
        if not isinstance(nodeSize, (int, float)) or nodeSize <= 0:
            raise ValueError("`nodeSize` must be a positive number.")
        if not (0 <= float(nodeOpacity) <= 1):
            raise ValueError("`nodeOpacity` must be in [0, 1].")
        if not isinstance(edgeWidth, (int, float)) or edgeWidth < 0:
            raise ValueError("`edgeWidth` must be a non-negative number.")
        if not isinstance(figsize, (tuple, list)) or len(figsize) != 2:
            raise ValueError("`figsize` must be a (width, height) tuple in pixels.")

        # --- Layout positions via NetworkX
        if layout == "spring":
            pos = nx.spring_layout(nxGraph, seed=layoutSeed)
        elif layout == "kamada_kawai":
            pos = nx.kamada_kawai_layout(nxGraph)
        elif layout == "circular":
            pos = nx.circular_layout(nxGraph)
        elif layout == "random":
            pos = nx.random_layout(nxGraph, seed=layoutSeed)
        elif layout == "shell":
            pos = nx.shell_layout(nxGraph)
        elif layout == "spectral":
            pos = nx.spectral_layout(nxGraph)
        else:
            raise ValueError(f"Unsupported layout '{layout}'.")

        # --- Node grouping (label/type/@type → 'Unknown')
        def node_group(data):
            if not isinstance(data, dict):
                return "Unknown"
            return str(data.get("label") or data.get("type") or data.get("@type") or "Unknown")

        nodeList = list(nxGraph.nodes())
        nodeGroupsOrdered = [node_group(nxGraph.nodes[n]) for n in nodeList]
        uniqueNodeGroups = sorted(set(nodeGroupsOrdered)) or ["Unknown"]

        # --- Build node palette using Plotly colorscale
        if len(uniqueNodeGroups) == 1:
            nodePalette = {uniqueNodeGroups[0]: sample_colorscale(nodeColorMap, [0.5])[0]}
        else:
            fractions = [i / (len(uniqueNodeGroups)-1 or 1) for i in range(len(uniqueNodeGroups))]
            colors = sample_colorscale(nodeColorMap, fractions)
            nodePalette = {g: colors[i] for i, g in enumerate(uniqueNodeGroups)}

        # Node label text (name → id → @id → key)
        def node_text(n, data):
            if not isinstance(data, dict):
                return str(n)
            return str(n) or str(data.get("name") or data.get("id") or data.get("@id") or n)

        # --- Edge grouping
        def edge_label(edata):
            elabel = edata.get("label") or edata.get("type") or edata.get("relationship") or edata.get("relation") or edata.get("name")
            return elabel

        edgeList = list(nxGraph.edges())
        edgeGroupsOrdered = [edge_label(nxGraph.get_edge_data(u, v)) for (u, v) in edgeList]
        uniqueEdgeGroups = sorted(set(edgeGroupsOrdered)) or ["Unknown"]

        # Edge palette
        if len(uniqueEdgeGroups) == 1:
            edgePalette = {uniqueEdgeGroups[0]: sample_colorscale(edgeColorMap, [0.5])[0]}
        else:
            fractions = [i / (len(uniqueEdgeGroups)-1 or 1) for i in range(len(uniqueEdgeGroups))]
            ecolors = sample_colorscale(edgeColorMap, fractions)
            edgePalette = {g: ecolors[i] for i, g in enumerate(uniqueEdgeGroups)}

        # --- Create Plotly traces
        fig = go.Figure()

        # Edges: create one Scatter trace per edge group (lines)
        # Build coordinates for each group
        edgesByGroup = {g: [] for g in uniqueEdgeGroups}
        for (u, v), g in zip(edgeList, edgeGroupsOrdered):
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edgesByGroup[g].append((x0, y0, x1, y1))

        for g, segs in edgesByGroup.items():
            if not segs:
                continue
            xs, ys = [], []
            for x0, y0, x1, y1 in segs:
                xs += [x0, x1, None]
                ys += [y0, y1, None]
            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                mode="lines",
                line=dict(color=edgePalette[g], width=edgeWidth),
                hoverinfo="skip",
                name=f"Edge: {g}",
                showlegend=showLegend,
            ))

        # Edge labels (optional): one Scatter text for all edges with their label near midpoint
        if showEdgeLabels and edgeList:
            ex, ey, etext = [], [], []
            for (u, v), g in zip(edgeList, edgeGroupsOrdered):
                x0, y0 = pos[u]
                x1, y1 = pos[v]
                ex.append((x0 + x1) / 2)
                ey.append((y0 + y1) / 2)
                etext.append(g)
            fig.add_trace(go.Scatter(
                x=ex, y=ey,
                mode="text",
                text=etext,
                textposition="middle center",
                textfont=dict(size=10),
                hoverinfo="skip",
                showlegend=False
            ))

        # Nodes: one Scatter per node group (for legend grouping)
        nodesByGroup = {g: [] for g in uniqueNodeGroups}
        for n, g in zip(nodeList, nodeGroupsOrdered):
            x, y = pos[n]
            nodesByGroup[g].append((n, x, y))

        for g, items in nodesByGroup.items():
            if not items:
                continue
            xs, ys, texts, hovertexts = [], [], [], []
            for (n, x, y) in items:
                xs.append(x); ys.append(y)
                data = nxGraph.nodes[n]
                texts.append(node_text(n, data) if showNodeLabels else "")
                # build hovertext with some common fields
                if isinstance(data, dict):
                    hname = data.get("name") or n
                    htype = data.get("label") or data.get("type") or data.get("@type") or "Unknown"
                    hovertexts.append(f"<b>{hname}</b><br>type: {htype}<br>id: {data.get('id', n)}")
                else:
                    hovertexts.append(str(n))

            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                mode="markers+text" if showNodeLabels else "markers",
                text=texts if showNodeLabels else None,
                textposition="top center",
                marker=dict(
                    size=nodeSize,
                    color=nodePalette[g],
                    opacity=nodeOpacity,
                    line=dict(width=0.5, color="rgba(0,0,0,0.4)")
                ),
                hovertext=hovertexts,
                hoverinfo="text",
                name=f"Node: {g}",
                showlegend=showLegend
            ))

        # --- Layout & legend
        fig.update_layout(
            width=figsize[0],
            height=figsize[1],
            template="plotly_white",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            margin=dict(l=20, r=220 if (showLegend and legendOutside) else 20, t=20, b=20),
            legend=dict(
                orientation="v",
                x=1.02 if legendOutside else 0.01,
                y=1.0,
                xanchor="left" if legendOutside else "left",
                yanchor="top",
                bgcolor="rgba(255,255,255,0.7)",
                bordercolor="rgba(0,0,0,0.15)",
                borderwidth=1
            ),
            hovermode="closest",
        )

        # Keep aspect
        fig.update_yaxes(scaleanchor="x", scaleratio=1)

        # --- Save if requested
        if savePath:
            if str(savePath).lower().endswith(".html"):
                fig.write_html(savePath, include_plotlyjs="cdn")
            else:
                # Requires 'kaleido' package for static image export
                try:
                    fig.write_image(savePath, scale=2)
                except Exception as e:
                    print(f"Warning: could not save static image ({e}). Try savePath with .html or install 'kaleido'.")

        return fig

    # Tableau 10: distinct at small marker sizes and readable for the common colour
    # deficiencies, which a sampled continuous colormap is not.
    CATEGORICAL_PALETTE = (
        "#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#B07AA1",
        "#76B7B2", "#EDC948", "#FF9DA7", "#9C755F", "#BAB0AC",
    )

    @staticmethod
    def NetworkXByHTML(
        nxGraph=None,
        *,
        savePath: str | None = None,
        title: str = "BTwin graph",
        nodeGroupBy: str = "type",
        edgeGroupBy: str = "type",
        nodeLabelKeys: tuple[str, ...] = ("name", "label", "id", "@id"),
        nodeSize: int = 9,
        layoutSeed: int | None = 42,
        relaxSteps: int = 400,
        showLabelsUpTo: int = 80,
        palette: tuple[str, ...] | None = None,
    ) -> str:
        """
        Draw a NetworkX graph as one self-contained interactive HTML page.

        The page needs no network to open: the force simulation, the rendering and the
        interactions are plain JavaScript written into the file, so there is no CDN to reach
        and nothing for the viewer to install.

        What the page does:
          - lays the graph out with a force simulation, seeded from NetworkX's spring layout
            so the first frame is already sensible and the same graph always opens the same;
          - colours nodes by `nodeGroupBy` and edges by `edgeGroupBy`, one colour per class,
            with a legend whose entries toggle a class on and off;
          - shows every attribute of a node in a side panel when the node is clicked, along
            with the edges that touch it;
          - supports wheel zoom, background drag to pan, node drag to reposition (a dragged
            node stays pinned), and double click on a node to release it.

        Args:
            nxGraph: (networkx.Graph | DiGraph | MultiGraph | MultiDiGraph) Graph to draw.
            savePath: Where to write the page. '.html' is appended when missing. The HTML is
                returned either way.
            title: Heading shown on the page and used as the document title.
            nodeGroupBy: Node attribute that decides a node's colour. Falls back to 'Unknown'.
            edgeGroupBy: Edge attribute that decides an edge's colour.
            nodeLabelKeys: Attributes tried in order for a node's visible label, before
                falling back to the node key itself.
            nodeSize: Node radius in pixels at 100% zoom.
            layoutSeed: Seed for the initial NetworkX spring layout. None for a random start.
            relaxSteps: Force-simulation steps run when the page opens. 0 keeps the layout
                exactly as NetworkX computed it.
            showLabelsUpTo: Labels start visible while the graph has at most this many nodes;
                above it they would be an unreadable smear, so they start hidden and the page
                offers a toggle.
            palette: Colours to cycle through, one per class. Defaults to Tableau 10.

        Returns:
            str: The complete HTML document.

        Raises:
            ValueError:  If `nxGraph` is missing or a parameter is out of range.
            ImportError: If `networkx` is not available.
            OSError:     If `savePath` cannot be written.
        """
        try:
            import networkx as nx
        except Exception as exc:
            raise ImportError("networkx is required. Install with `pip install networkx`.") from exc

        import json
        from pathlib import Path

        if nxGraph is None or not hasattr(nxGraph, "nodes"):
            raise ValueError("`nxGraph` must be a valid NetworkX graph instance.")
        if not isinstance(nodeSize, (int, float)) or nodeSize <= 0:
            raise ValueError("`nodeSize` must be a positive number.")
        if not isinstance(relaxSteps, int) or relaxSteps < 0:
            raise ValueError("`relaxSteps` must be a non-negative integer.")

        # A single colour string is the one wrong argument that fails silently: tuple() takes
        # it apart character by character, every character is an invalid CSS colour, and the
        # page renders every node black with no error anywhere. Color.Purple() and its
        # siblings return exactly that - one colour, for the matplotlib and plotly renderers -
        # so the mistake is an easy one to make.
        if isinstance(palette, str):
            raise ValueError(
                "`palette` must be a sequence of colours, not one colour string: a str is "
                "iterated character by character and every node would render black. Pass a "
                "tuple such as ('#4E79A7', '#F28E2B'), or None for the default. Note that "
                "Color.Purple() and its siblings return a single colour for the matplotlib "
                "and plotly renderers, not a categorical palette for this one.")

        # None means "use the default"; an empty palette is a request for no colours at all,
        # which cannot be honoured, so it is an error rather than a silent fallback.
        colors = GraphPlot.CATEGORICAL_PALETTE if palette is None else tuple(palette)
        if not colors:
            raise ValueError("`palette` must contain at least one colour.")

        # --- Initial positions -------------------------------------------------------
        # NetworkX does the first layout: it is well tested and seedable, so the page opens
        # the same way every time. The JavaScript only refines it and reacts to dragging.
        positions = nx.spring_layout(nxGraph, seed=layoutSeed) if nxGraph.number_of_nodes() else {}

        def jsonSafe(value):
            """Anything not already JSON becomes its string form, so no attribute is dropped."""
            if value is None or isinstance(value, (bool, int, float, str)):
                return value
            if isinstance(value, dict):
                return {str(k): jsonSafe(v) for k, v in value.items()}
            if isinstance(value, (list, tuple, set)):
                return [jsonSafe(v) for v in value]
            return str(value)

        def labelOf(key, data):
            for candidate in nodeLabelKeys:
                text = data.get(candidate)
                if isinstance(text, str) and text.strip():
                    return text
            return str(key)

        groups: list[str] = []

        def groupIndex(name):
            if name not in groups:
                groups.append(name)
            return groups.index(name)

        nodes = []
        for key, data in nxGraph.nodes(data=True):
            group = str(data.get(nodeGroupBy) or "Unknown")
            x, y = positions.get(key, (0.0, 0.0))
            nodes.append({
                "id": str(key),
                "label": labelOf(key, data),
                "group": group,
                "g": groupIndex(group),
                "x": float(x) * 400.0,
                "y": float(y) * 400.0,
                "meta": {str(k): jsonSafe(v) for k, v in data.items()},
            })

        indexByID = {node["id"]: position for position, node in enumerate(nodes)}
        edgeGroups: list[str] = []
        edges = []
        for source, target, data in nxGraph.edges(data=True):
            source, target = str(source), str(target)
            if source not in indexByID or target not in indexByID:
                continue
            group = str(data.get(edgeGroupBy) or "Unknown")
            if group not in edgeGroups:
                edgeGroups.append(group)
            edges.append({
                "s": indexByID[source],
                "t": indexByID[target],
                "group": group,
                "g": edgeGroups.index(group),
            })

        payload = {
            "title": title,
            "nodes": nodes,
            "edges": edges,
            "nodeGroups": groups,
            "edgeGroups": edgeGroups,
            "palette": list(colors),
            "nodeSize": float(nodeSize),
            "relaxSteps": int(relaxSteps),
            "showLabels": len(nodes) <= showLabelsUpTo,
            "directed": bool(nxGraph.is_directed()),
        }

        # '</' would close the script element early, wherever it appears inside the JSON
        data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        html = _HTML_TEMPLATE.replace("__TITLE__", _EscapeHTML(title)).replace("__DATA__", data)

        if savePath:
            path = Path(savePath)
            if path.suffix.lower() != ".html":
                path = path.with_suffix(".html")
            try:
                path.write_text(html, encoding="utf-8")
            except Exception as exc:
                raise OSError(f"Could not write '{path}'.") from exc

        return html


def _EscapeHTML(text: str) -> str:
    """Escape the five characters that can break out of markup or an attribute."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


# The page written by GraphPlot.NetworkXByHTML. Kept as one template rather than assembled
# from pieces so that what ships is exactly what can be read here. Two placeholders:
# __TITLE__ (already HTML-escaped) and __DATA__ (a JSON object).
_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #ffffff; --panel: #f7f7f8; --line: #e3e3e6;
    --ink: #1c1c1e; --muted: #6b6b70; --accent: #1c1c1e;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font: 13px/1.5 ui-sans-serif, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: var(--ink); background: var(--bg); display: flex; flex-direction: column;
  }
  header {
    padding: 10px 16px; border-bottom: 1px solid var(--line);
    display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap;
  }
  header h1 { font-size: 15px; font-weight: 600; margin: 0; }
  header .stats { color: var(--muted); }
  header .actions { margin-left: auto; display: flex; gap: 8px; }
  button {
    font: inherit; color: var(--ink); background: var(--bg);
    border: 1px solid var(--line); border-radius: 6px; padding: 4px 10px; cursor: pointer;
  }
  button:hover { background: var(--panel); }
  button[aria-pressed="true"] { background: var(--ink); color: var(--bg); border-color: var(--ink); }
  main { flex: 1; display: flex; min-height: 0; }
  #stage { flex: 1; position: relative; min-width: 0; }
  canvas { display: block; width: 100%; height: 100%; cursor: grab; }
  canvas.dragging { cursor: grabbing; }
  #hint {
    position: absolute; left: 12px; bottom: 10px; color: var(--muted);
    background: rgba(255,255,255,.85); padding: 4px 8px; border-radius: 6px;
    border: 1px solid var(--line); pointer-events: none;
  }
  aside {
    width: 320px; flex: none; border-left: 1px solid var(--line);
    background: var(--panel); overflow-y: auto; padding: 14px 16px;
  }
  aside h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em;
             color: var(--muted); margin: 0 0 8px; font-weight: 600; }
  aside section + section { margin-top: 22px; }
  .legend-item {
    display: flex; align-items: center; gap: 8px; padding: 3px 0;
    cursor: pointer; user-select: none;
  }
  .legend-item.off { opacity: .35; }
  .swatch { width: 11px; height: 11px; border-radius: 3px; flex: none; }
  .legend-item .count { margin-left: auto; color: var(--muted); font-variant-numeric: tabular-nums; }
  .empty { color: var(--muted); }
  .node-title { font-size: 15px; font-weight: 600; margin: 0 0 2px; word-break: break-word; }
  .node-class { display: inline-block; padding: 1px 7px; border-radius: 999px;
                color: #fff; font-size: 11px; margin-bottom: 10px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; vertical-align: top; padding: 4px 0; border-top: 1px solid var(--line); }
  th { width: 38%; font-weight: 500; color: var(--muted); padding-right: 8px; }
  td { word-break: break-word; }
  td pre { margin: 0; font: 11px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
           white-space: pre-wrap; word-break: break-word; }
  ul.edges { list-style: none; margin: 0; padding: 0; }
  ul.edges li { padding: 4px 0; border-top: 1px solid var(--line); }
  ul.edges .rel { color: var(--muted); }
  ul.edges button { border: 0; background: none; padding: 0; text-align: left;
                    text-decoration: underline; text-underline-offset: 2px; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <span class="stats" id="stats"></span>
  <span class="actions">
    <button id="toggleLabels" aria-pressed="false">Labels</button>
    <button id="relax">Re-run layout</button>
    <button id="reset">Reset view</button>
  </span>
</header>
<main>
  <div id="stage">
    <canvas id="canvas"></canvas>
    <div id="hint">Wheel to zoom &middot; drag background to pan &middot; drag a node to pin it &middot; double click to release &middot; click for details</div>
  </div>
  <aside>
    <section>
      <h2>Node classes</h2>
      <div id="nodeLegend"></div>
    </section>
    <section>
      <h2>Edge classes</h2>
      <div id="edgeLegend"></div>
    </section>
    <section>
      <h2>Selection</h2>
      <div id="details"><p class="empty">Click a node to read its metadata.</p></div>
    </section>
  </aside>
</main>

<script id="graph-data" type="application/json">__DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("graph-data").textContent);
const nodes = DATA.nodes, edges = DATA.edges;
const colorOf = i => DATA.palette[i % DATA.palette.length];

// Every node carries its own simulation state; x/y arrive already laid out by NetworkX
for (const n of nodes) { n.vx = 0; n.vy = 0; n.pinned = false; n.hidden = false; }
for (const e of edges) { e.hidden = false; }

// ---------------------------------------------------------------- force simulation
// Plain O(n^2) repulsion. NetworkX has already done the hard part, so this only needs to
// relax the result and answer dragging; at a few hundred nodes the cost is not worth a
// quadtree, and above that the layout is unreadable anyway.
const REPULSION = 9000, SPRING = 0.006, REST = 60, DAMPING = 0.82, GRAVITY = 0.002;
let alpha = 0;

function step() {
  const n = nodes.length;
  for (let i = 0; i < n; i++) {
    const a = nodes[i];
    if (a.hidden) continue;
    for (let j = i + 1; j < n; j++) {
      const b = nodes[j];
      if (b.hidden) continue;
      let dx = a.x - b.x, dy = a.y - b.y;
      let d2 = dx * dx + dy * dy;
      if (d2 < 1e-4) { dx = (Math.random() - 0.5) * 0.1; dy = (Math.random() - 0.5) * 0.1; d2 = 1e-4; }
      const f = REPULSION / d2, d = Math.sqrt(d2);
      const fx = f * dx / d, fy = f * dy / d;
      a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
    }
  }
  for (const e of edges) {
    const a = nodes[e.s], b = nodes[e.t];
    if (e.hidden || a.hidden || b.hidden) continue;
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.hypot(dx, dy) || 1e-4;
    const f = SPRING * (d - REST);
    const fx = f * dx / d, fy = f * dy / d;
    a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
  }
  for (const a of nodes) {
    if (a.hidden) continue;
    a.vx -= a.x * GRAVITY; a.vy -= a.y * GRAVITY;
    if (a.pinned || a === dragNode) { a.vx = 0; a.vy = 0; continue; }
    a.vx *= DAMPING; a.vy *= DAMPING;
    a.x += a.vx * alpha; a.y += a.vy * alpha;
  }
}

// ------------------------------------------------------------------------ rendering
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
let view = { x: 0, y: 0, k: 1 }, dpr = 1, width = 0, height = 0;
let selected = null, hovered = null, dragNode = null, showLabels = DATA.showLabels;

function resize() {
  dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  width = rect.width; height = rect.height;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  draw();
}

function toScreen(p) { return { x: (p.x + view.x) * view.k + width / 2, y: (p.y + view.y) * view.k + height / 2 }; }
function toWorld(sx, sy) { return { x: (sx - width / 2) / view.k - view.x, y: (sy - height / 2) / view.k - view.y }; }

function fit() {
  const shown = nodes.filter(n => !n.hidden);
  if (!shown.length) { view = { x: 0, y: 0, k: 1 }; return; }
  const xs = shown.map(n => n.x), ys = shown.map(n => n.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const pad = 60;
  const k = Math.min((width - pad * 2) / Math.max(maxX - minX, 1), (height - pad * 2) / Math.max(maxY - minY, 1));
  view.k = Math.max(0.05, Math.min(4, k));
  view.x = -(minX + maxX) / 2;
  view.y = -(minY + maxY) / 2;
}

function neighboursOf(node) {
  const set = new Set();
  for (const e of edges) {
    if (nodes[e.s] === node) set.add(nodes[e.t]);
    if (nodes[e.t] === node) set.add(nodes[e.s]);
  }
  return set;
}

function draw() {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const focus = selected || hovered;
  const near = focus ? neighboursOf(focus) : null;

  for (const e of edges) {
    const a = nodes[e.s], b = nodes[e.t];
    if (e.hidden || a.hidden || b.hidden) continue;
    const p = toScreen(a), q = toScreen(b);
    const lit = !focus || a === focus || b === focus;
    ctx.globalAlpha = lit ? 0.85 : 0.12;
    ctx.strokeStyle = colorOf(e.g);
    ctx.lineWidth = lit && focus ? 2 : 1;
    ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
    if (DATA.directed) {
      const ang = Math.atan2(q.y - p.y, q.x - p.x);
      const r = DATA.nodeSize * Math.max(0.6, Math.min(1.6, view.k));
      const tipX = q.x - Math.cos(ang) * r, tipY = q.y - Math.sin(ang) * r, h = 7;
      ctx.beginPath();
      ctx.moveTo(tipX, tipY);
      ctx.lineTo(tipX - h * Math.cos(ang - 0.4), tipY - h * Math.sin(ang - 0.4));
      ctx.lineTo(tipX - h * Math.cos(ang + 0.4), tipY - h * Math.sin(ang + 0.4));
      ctx.closePath(); ctx.fillStyle = colorOf(e.g); ctx.fill();
    }
  }

  const r = DATA.nodeSize * Math.max(0.6, Math.min(1.6, view.k));
  for (const n of nodes) {
    if (n.hidden) continue;
    const p = toScreen(n);
    const lit = !focus || n === focus || (near && near.has(n));
    ctx.globalAlpha = lit ? 1 : 0.15;
    ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fillStyle = colorOf(n.g); ctx.fill();
    if (n === selected) { ctx.lineWidth = 3; ctx.strokeStyle = "#1c1c1e"; ctx.stroke(); }
    else if (n.pinned) { ctx.lineWidth = 2; ctx.strokeStyle = "#ffffff"; ctx.stroke(); }
  }

  if (showLabels || focus) {
    ctx.globalAlpha = 1;
    ctx.font = "11px ui-sans-serif, -apple-system, 'Segoe UI', Roboto, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    for (const n of nodes) {
      if (n.hidden) continue;
      if (!showLabels && !(n === focus || (near && near.has(n)))) continue;
      const p = toScreen(n);
      const text = n.label;
      const w = ctx.measureText(text).width;
      ctx.fillStyle = "rgba(255,255,255,.82)";
      ctx.fillRect(p.x - w / 2 - 2, p.y + r + 2, w + 4, 14);
      ctx.fillStyle = "#1c1c1e";
      ctx.fillText(text, p.x, p.y + r + 3);
    }
  }
  ctx.globalAlpha = 1;
}

let running = 0;
function run(steps) {
  running = steps; alpha = 0.5;
  if (running > 0) requestAnimationFrame(tick);
}
function tick() {
  for (let i = 0; i < 3 && running > 0; i++, running--) step();
  alpha *= 0.995;
  draw();
  if (running > 0) requestAnimationFrame(tick);
}

// --------------------------------------------------------------------- interactions
function nodeAt(sx, sy) {
  const w = toWorld(sx, sy);
  const r = (DATA.nodeSize + 4) / view.k;
  let best = null, bestD = r * r;
  for (const n of nodes) {
    if (n.hidden) continue;
    const dx = n.x - w.x, dy = n.y - w.y, d = dx * dx + dy * dy;
    if (d <= bestD) { best = n; bestD = d; }
  }
  return best;
}

let pointer = null, moved = false;
canvas.addEventListener("pointerdown", ev => {
  canvas.setPointerCapture(ev.pointerId);
  pointer = { x: ev.offsetX, y: ev.offsetY }; moved = false;
  dragNode = nodeAt(ev.offsetX, ev.offsetY);
  canvas.classList.add("dragging");
});
canvas.addEventListener("pointermove", ev => {
  if (!pointer) {
    const over = nodeAt(ev.offsetX, ev.offsetY);
    if (over !== hovered) { hovered = over; draw(); }
    return;
  }
  const dx = ev.offsetX - pointer.x, dy = ev.offsetY - pointer.y;
  if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
  if (dragNode) { dragNode.x += dx / view.k; dragNode.y += dy / view.k; }
  else { view.x += dx / view.k; view.y += dy / view.k; }
  pointer = { x: ev.offsetX, y: ev.offsetY };
  draw();
});
canvas.addEventListener("pointerup", ev => {
  canvas.classList.remove("dragging");
  if (dragNode && moved) { dragNode.pinned = true; run(120); }
  else if (!moved) { select(nodeAt(ev.offsetX, ev.offsetY)); }
  dragNode = null; pointer = null;
});
canvas.addEventListener("dblclick", ev => {
  const n = nodeAt(ev.offsetX, ev.offsetY);
  if (n) { n.pinned = false; run(200); }
});
canvas.addEventListener("wheel", ev => {
  ev.preventDefault();
  const before = toWorld(ev.offsetX, ev.offsetY);
  view.k = Math.max(0.05, Math.min(6, view.k * (ev.deltaY < 0 ? 1.12 : 1 / 1.12)));
  const after = toWorld(ev.offsetX, ev.offsetY);
  view.x += after.x - before.x; view.y += after.y - before.y;
  draw();
}, { passive: false });

// ------------------------------------------------------------------------- details
function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function renderValue(value) {
  if (value === null || value === undefined) return '<span class="empty">-</span>';
  if (typeof value === "object") return "<pre>" + escapeHTML(JSON.stringify(value, null, 2)) + "</pre>";
  return escapeHTML(value);
}

function select(node) {
  selected = node || null;
  const box = document.getElementById("details");
  if (!selected) {
    box.innerHTML = '<p class="empty">Click a node to read its metadata.</p>';
    draw(); return;
  }
  const rows = Object.keys(selected.meta).sort()
    .map(k => "<tr><th>" + escapeHTML(k) + "</th><td>" + renderValue(selected.meta[k]) + "</td></tr>")
    .join("");

  const links = [];
  edges.forEach(e => {
    if (nodes[e.s] === selected) links.push({ dir: "→", rel: e.group, other: nodes[e.t] });
    else if (nodes[e.t] === selected) links.push({ dir: "←", rel: e.group, other: nodes[e.s] });
  });
  const linkHTML = links.length
    ? '<ul class="edges">' + links.map((l, i) =>
        "<li>" + l.dir + ' <span class="rel">' + escapeHTML(l.rel) + "</span> " +
        '<button type="button" data-link="' + i + '">' + escapeHTML(l.other.label) + "</button></li>").join("") + "</ul>"
    : '<p class="empty">No edges.</p>';

  box.innerHTML =
    '<p class="node-title">' + escapeHTML(selected.label) + "</p>" +
    '<span class="node-class" style="background:' + colorOf(selected.g) + '">' + escapeHTML(selected.group) + "</span>" +
    "<table>" + rows + "</table>" +
    '<h2 style="margin-top:18px">Edges (' + links.length + ")</h2>" + linkHTML;

  box.querySelectorAll("button[data-link]").forEach(button => {
    button.addEventListener("click", () => select(links[+button.dataset.link].other));
  });
  draw();
}

// -------------------------------------------------------------------------- legends
function buildLegend(container, names, counts, onToggle) {
  container.innerHTML = "";
  if (!names.length) { container.innerHTML = '<p class="empty">None.</p>'; return; }
  names.forEach((name, i) => {
    const row = document.createElement("div");
    row.className = "legend-item";
    row.innerHTML = '<span class="swatch" style="background:' + colorOf(i) + '"></span>' +
                    "<span>" + escapeHTML(name) + '</span><span class="count">' + counts[i] + "</span>";
    row.addEventListener("click", () => { row.classList.toggle("off"); onToggle(i, !row.classList.contains("off")); });
    container.appendChild(row);
  });
}

const nodeCounts = DATA.nodeGroups.map((_, i) => nodes.filter(n => n.g === i).length);
const edgeCounts = DATA.edgeGroups.map((_, i) => edges.filter(e => e.g === i).length);

buildLegend(document.getElementById("nodeLegend"), DATA.nodeGroups, nodeCounts, (i, on) => {
  nodes.forEach(n => { if (n.g === i) n.hidden = !on; });
  if (selected && selected.hidden) select(null);
  draw();
});
buildLegend(document.getElementById("edgeLegend"), DATA.edgeGroups, edgeCounts, (i, on) => {
  edges.forEach(e => { if (e.g === i) e.hidden = !on; });
  draw();
});

// --------------------------------------------------------------------------- chrome
document.getElementById("stats").textContent =
  nodes.length + " nodes · " + edges.length + " edges · " +
  DATA.nodeGroups.length + " node classes";

const labelButton = document.getElementById("toggleLabels");
labelButton.setAttribute("aria-pressed", String(showLabels));
labelButton.addEventListener("click", () => {
  showLabels = !showLabels;
  labelButton.setAttribute("aria-pressed", String(showLabels));
  draw();
});
document.getElementById("relax").addEventListener("click", () => {
  nodes.forEach(n => { n.pinned = false; });
  run(DATA.relaxSteps || 300);
});
document.getElementById("reset").addEventListener("click", () => { fit(); draw(); });

window.addEventListener("resize", resize);
resize();
fit();
draw();
if (DATA.relaxSteps > 0) { run(DATA.relaxSteps); setTimeout(() => { fit(); draw(); }, 60); }
</script>
</body>
</html>
"""
