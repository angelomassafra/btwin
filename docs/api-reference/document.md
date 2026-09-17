# Document

Documents are the files a twin refers to rather than contains: manuals, drawings, IFC models,
timeseries databases. A `Document` is linked to what it describes, to a
[scenario](scenario.md) when it belongs to one, and to its own metadata through a
[property set](property-set.md).

```python
from btwin import Document, PropertySet, Property

manual = Document.Constructor("doc-ahu-manual", name="AHU 1 operation manual")
Document.SetRelationship(manual, "btwin:isDocumentOf",
                         linkedObjectUID="bldg-01", linkedObjectType="bot:Building")

meta = PropertySet.Constructor("pset-doc-ahu-manual", "Pset_DocumentInformation")
PropertySet.SetProperty(meta, Property.Constructor("Location", "docs/ahu-1.pdf", propertyQuantity="IfcLabel"))
Document.SetPSet(manual, pset=meta)
```

A graph can also point at a timeseries database through a document — the link
[`Cycle.TwinQueryByPrompt`](llm.md) follows from a graph node to the readings behind it — and
[`Cycle.DocumentCreateByPrompt`](llm.md) builds a document and its property set from a PDF.

::: btwin.document.Document
    options:
      members_order: source
      show_source: true
