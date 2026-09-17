# KPISet & KPI

A `KPISet` groups key performance indicators evaluated over one time interval, for one object
and, optionally, under one [`Scenario`](scenario.md). Each `KPI` carries a value, a unit and
its own interval; timestamps are normalised to ISO-8601 UTC.

```python
from btwin import KPISet, KPI, Scenario

kpis = KPISet.Constructor("kpis-bldg-01-2025-01", name="January energy",
                          hasBeginning="2025-01-01T00:00:00Z", hasEnd="2025-01-31T23:59:59Z")
KPISet.SetAssociatedObject(kpis, linkedObjectUID="bldg-01", linkedObjectType="bot:Building")

baseline = Scenario.Constructor("scenario-baseline", name="Baseline")
KPISet.SetScenario(kpis, scenarioObject=baseline)

energy = KPI.Constructor("kpi-energy", kpiName="Total energy", kpiValue=15230.5, kpiUnit="kWh")
KPISet.SetKPI(kpis, energy)
KPISet.SetKPIsTimestep(kpis)        # copy the set's interval onto every KPI it holds

KPI.Value(energy), KPI.Timestep(energy)
```

The set's interval is stored under the `eko:hasEvaluationTimestep` relationship, and its KPIs
in `btwin:hasKPIs`. When the graph is built, [`NetworkX.CompactKPISets`](graph.md) can fold
the KPI values into the node they describe.

## KPISet

::: btwin.kpi_set.KPISet
    options:
      members_order: source
      show_source: true

## KPI

::: btwin.kpi_set.KPI
    options:
      members_order: source
      show_source: true
