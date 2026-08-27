# Plot (GraphPlot & Color)

Visualization helpers for rendering graphs, plus the BTwin color palette. Three backends:

| method | output | when |
| --- | --- | --- |
| `NetworkXByMatplotlib` | PNG | a static picture for a report or a paper |
| `NetworkXByPlotly` | Plotly figure, HTML | a figure to embed in an existing Plotly page |
| `NetworkXByHTML` | one self-contained HTML file | **exploring a graph**: force layout, colours by class, metadata on click |

`NetworkXByHTML` writes the force simulation, the rendering and the interactions into the
page as plain JavaScript, so the file opens with no network and nothing installed:

```python
from btwin import GraphPlot, NetworkX

graph = NetworkX.ByJSONLD(jsonPath="spatialHierarchy.json")
GraphPlot.NetworkXByHTML(graph, title="Ferrovia 9", savePath="spatialHierarchy.html")
```

In the page: wheel zooms, dragging the background pans, dragging a node pins it where you
drop it, double clicking releases it, and clicking a node opens every attribute it carries in
the side panel together with the edges that touch it. The legend entries switch a class off.

## GraphPlot

::: btwin.plot.GraphPlot
    options:
      members_order: source
      show_source: true

## Color

::: btwin.plot.Color
    options:
      members_order: source
      show_source: true
