# Graphs

BTwin uses NetworkX directed graphs as its primary in-memory graph representation.

## Creating a Graph

```python
import networkx as nx
from btwin import NetworkX

G = nx.DiGraph()
```

## Adding Nodes and Edges

### From Objects

The most common way to populate a graph is from BTwin objects:

```python
from btwin import SpatialElement

site = SpatialElement.Constructor("site-01", "bot:Site", name="Campus")
building = SpatialElement.Constructor("bldg-01", "bot:Building", name="Main Hall")
SpatialElement.SetLocationRelationship(building, linkedObject=site)

# Add edges (and nodes implicitly) from an object's relationships
NetworkX.AddEdgesByObject(G, building)
```

You can also add nodes explicitly:

```python
NetworkX.AddNodeByObject(G, site)
```

### From JSON-LD

Build a graph from an existing JSON-LD document:

```python
import json

with open("my_building.json") as f:
    jsonld = json.load(f)

G = NetworkX.ByJSONLD(jsonld)
```

## Graph Operations

### Validation

Check that all edges reference valid node types against the schema:

```python
is_valid = NetworkX.Validate(G)
```

### Subgraph Extraction

Extract a subgraph containing only specific object types:

```python
sub = NetworkX.SubgraphByObjectTypes(G, objectTypes=["bot:Space", "bot:Storey"])
```

### Compact Property Sets and KPI Sets

Collapse property set and KPI set nodes into their parent node attributes:

```python
NetworkX.CompactPSets(G)
NetworkX.CompactKPISets(G)
```

## JSON Serialization

### Export

```python
NetworkX.ToJSON(G, savePath="graph.json")
```

### Import

```python
G = NetworkX.ByJSON("graph.json")
```

## RDF Conversion

Convert a JSON-LD document to RDF (requires `rdflib`):

```python
from btwin import RDF

rdf_graph = RDF.ByJSONLD(jsonld)
```
