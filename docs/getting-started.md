# Getting Started

## Installation

Install BTwin from PyPI:

```bash
pip install btwin
```

### Optional extras

=== "Visualization"

    ```bash
    pip install btwin[viz]
    ```

    Adds `matplotlib`, `plotly`, and `kaleido` for graph plotting.

=== "Neo4j"

    ```bash
    pip install btwin[neo4j]
    ```

    Adds the `neo4j` driver for graph database export.

=== "Development"

    ```bash
    pip install btwin[dev]
    ```

    Adds `pytest`, `pytest-cov`, and `ruff` for testing and linting.

=== "Documentation"

    ```bash
    pip install btwin[docs]
    ```

    Adds MkDocs, Material theme, and mkdocstrings for building these docs.

## Quick Start

### 1. Create a spatial hierarchy

```python
from btwin import SpatialElement

site = SpatialElement.Constructor("site-01", "bot:Site", name="Campus")
building = SpatialElement.Constructor("bldg-01", "bot:Building", name="Main Hall")
storey = SpatialElement.Constructor("storey-01", "bot:Storey", name="Ground Floor")
space = SpatialElement.Constructor("space-01", "bot:Space", name="Room 101")
```

### 2. Set location relationships

```python
SpatialElement.SetLocationRelationship(building, linkedObject=site)
SpatialElement.SetLocationRelationship(storey, linkedObject=building)
SpatialElement.SetLocationRelationship(space, linkedObject=storey)
```

### 3. Add equipment

```python
from btwin import Equipment

ahu = Equipment.Constructor("ahu-01", "brick:Air_Handling_Unit", name="AHU 1")
Equipment.SetLocationRelationship(ahu, linkedObject=space)
```

### 4. Build a NetworkX graph

```python
import networkx as nx
from btwin import NetworkX

G = nx.DiGraph()
for obj in [site, building, storey, space, ahu]:
    NetworkX.AddEdgesByObject(G, obj)

print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")
```

### 5. Export to JSON-LD

```python
from btwin import Serialization

jsonld = Serialization.JSONLODByObjects(
    [site, building, storey, space, ahu],
    savePath="my_building.json"
)
```

## Next Steps

- [Ontologies](user-guide/ontologies.md) — understand the Brick/BOT/IFC foundations
- [Spatial Elements](user-guide/spatial-elements.md) — deep dive into spatial modeling
- [Equipment](user-guide/equipment.md) — modeling building equipment
- [Tutorials](tutorials/index.md) — hands-on walkthroughs
