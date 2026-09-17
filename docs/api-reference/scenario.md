# Scenario

A scenario names the conditions a set of KPIs was evaluated under — the building as it
operates today, after a retrofit, under a new control strategy. [KPI sets](kpi-set.md) and
[documents](document.md) point at it through `kpi:relatedScenario`, so two sets measuring the
same building under different scenarios can be told apart and compared.

```python
from btwin import Scenario, KPISet

baseline = Scenario.Constructor("scenario-baseline", name="Baseline",
                                description="Current operation, no interventions")
retrofit = Scenario.Constructor("scenario-retrofit", name="Envelope retrofit",
                                description="External insulation and new glazing")

before = KPISet.Constructor("kpis-before", name="Annual energy",
                            hasBeginning="2024-01-01T00:00:00Z", hasEnd="2024-12-31T23:59:59Z")
KPISet.SetScenario(before, scenarioObject=baseline)

Scenario.Name(retrofit), Scenario.Description(retrofit)
```

::: btwin.scenario.Scenario
    options:
      members_order: source
      show_source: true
