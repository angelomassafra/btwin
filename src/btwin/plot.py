"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

PLOT MODULE
This module defines the functions to plot data, graphs, and models via the BTWIN toolkit.

© Angelo Massafra, 2025
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

