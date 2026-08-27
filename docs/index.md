# BTwin

**A Python toolkit for graph-based decision support system prototypes in building management.**

BTwin lets you model buildings, spaces, equipment and sensors as knowledge graphs using standard ontologies — [Brick](https://brickschema.org/), [BOT](https://w3id.org/bot), and [IFC](https://www.buildingsmart.org/standards/bsi-standards/industry-foundation-classes/).

---

## Key Features

- **Spatial hierarchy** — model sites, buildings, storeys, spaces and zones
- **Equipment & sensors** — create equipment objects and sensor points with Brick types
- **IFC property sets** — attach structured properties to any spatial element
- **KPIs & scenarios** — define key performance indicators with evaluation timesteps
- **Timeseries storage** — write and query sensor observations via SQLite
- **Knowledge graph** — build NetworkX directed graphs from your objects
- **Serialization** — export to JSON-LD with full ontology context, or convert to RDF

## Quick Example

```python
from btwin import SpatialElement, Equipment, NetworkX, Serialization
import networkx as nx

# Create spatial hierarchy
site = SpatialElement.Constructor("site-01", "bot:Site", name="Campus")
building = SpatialElement.Constructor("bldg-01", "bot:Building", name="Main Hall")
storey = SpatialElement.Constructor("storey-01", "bot:Storey", name="Ground Floor")
space = SpatialElement.Constructor("space-01", "bot:Space", name="Room 101")

# Set location relationships
SpatialElement.SetLocationRelationship(building, linkedObject=site)
SpatialElement.SetLocationRelationship(storey, linkedObject=building)
SpatialElement.SetLocationRelationship(space, linkedObject=storey)

# Add equipment
ahu = Equipment.Constructor("ahu-01", "brick:Air_Handling_Unit", name="AHU 1")
Equipment.SetLocationRelationship(ahu, linkedObject=space)

# Build a NetworkX graph
G = nx.DiGraph()
for obj in [site, building, storey, space, ahu]:
    NetworkX.AddEdgesByObject(G, obj)

print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

# Export to JSON-LD
jsonld = Serialization.JSONLDByObjects([site, building, storey, space, ahu])
```

## Next Steps

- [Getting Started](getting-started.md) — installation and first steps
- [User Guide](user-guide/index.md) — conceptual guides for each module
- [Tutorials](tutorials/index.md) — hands-on walkthroughs
- [API Reference](api-reference/index.md) — auto-generated from docstrings
