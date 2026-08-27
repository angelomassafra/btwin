# Tutorial: Building a Spatial Model

In this tutorial you will create a complete building model with a spatial hierarchy, serialize it to JSON-LD, and build a NetworkX graph.

## Step 1: Create Spatial Elements

```python
from btwin import SpatialElement

# Site
site = SpatialElement.Constructor("site-01", "bot:Site", name="University Campus")

# Building
building = SpatialElement.Constructor("bldg-01", "bot:Building", name="Engineering Block")

# Storeys
ground = SpatialElement.Constructor("storey-gf", "bot:Storey", name="Ground Floor")
first = SpatialElement.Constructor("storey-1f", "bot:Storey", name="First Floor")

# Spaces
lab = SpatialElement.Constructor("space-lab", "bot:Space", name="Electronics Lab")
office = SpatialElement.Constructor("space-office", "bot:Space", name="Staff Office")
lecture = SpatialElement.Constructor("space-lecture", "bot:Space", name="Lecture Hall")
```

## Step 2: Set Location Relationships

Each element declares where it is located (child → parent):

```python
SpatialElement.SetLocationRelationship(building, linkedObject=site)
SpatialElement.SetLocationRelationship(ground, linkedObject=building)
SpatialElement.SetLocationRelationship(first, linkedObject=building)
SpatialElement.SetLocationRelationship(lab, linkedObject=ground)
SpatialElement.SetLocationRelationship(office, linkedObject=ground)
SpatialElement.SetLocationRelationship(lecture, linkedObject=first)
```

## Step 3: Add Adjacency Relationships

Mark which spaces are adjacent:

```python
SpatialElement.SetRelationship(
    lab,
    relationshipName="btwin:isAdjacentTo",
    linkedObjectUID="space-office",
    linkedObjectType="bot:Space"
)
```

## Step 4: Export to JSON-LD

```python
from btwin import Serialization

all_objects = [site, building, ground, first, lab, office, lecture]

jsonld = Serialization.JSONLDByObjects(
    all_objects,
    savePath="campus_model.json"
)

print(f"Exported {len(jsonld['@graph'])} nodes")
```

## Step 5: Build a NetworkX Graph

```python
import networkx as nx
from btwin import NetworkX

G = nx.DiGraph()
for obj in all_objects:
    NetworkX.AddEdgesByObject(G, obj)

print(f"Nodes: {G.number_of_nodes()}")
print(f"Edges: {G.number_of_edges()}")
```

## Step 6: Validate the Graph

```python
is_valid = NetworkX.Validate(G)
print(f"Graph valid: {is_valid}")
```

## Step 7: Extract a Subgraph

Get only the spaces and storeys:

```python
sub = NetworkX.SubgraphByObjectTypes(G, objectTypes=["bot:Space", "bot:Storey"])
print(f"Subgraph nodes: {sub.number_of_nodes()}")
```

## Result

You now have:

- A spatial hierarchy with 7 elements
- Location relationships linking every element to its parent
- An adjacency relationship between two spaces
- A JSON-LD file (`campus_model.json`) with full ontology context
- A NetworkX graph ready for analysis or visualization
