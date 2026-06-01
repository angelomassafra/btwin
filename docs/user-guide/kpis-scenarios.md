# KPIs & Scenarios

BTwin supports key performance indicators (KPIs) grouped into KPI sets, optionally linked to evaluation scenarios.

## KPI Sets

A KPI set groups related KPIs with a shared evaluation time interval:

```python
from btwin import KPISet

kpiset = KPISet.Constructor(
    "kpiset-01",
    name="Monthly Energy KPIs",
    hasBeginning="2025-01-01T00:00:00Z",
    hasEnd="2025-01-31T23:59:59Z"
)
```

### Updating the Timestep

```python
KPISet.SetTimestep(
    kpiset,
    hasBeginning="2025-02-01T00:00:00Z",
    hasEnd="2025-02-28T23:59:59Z"
)
```

### Linking to Spatial Elements

```python
KPISet.SetAssociatedObject(
    kpiset,
    linkedObjectUID="bldg-01",
    linkedObjectType="bot:Building"
)
```

## KPIs

Individual KPIs carry a name, value, unit, and optional evaluation timestep:

```python
from btwin import KPI

kpi = KPI.Constructor(
    kpiUID="kpi-energy",
    kpiName="Total Energy Consumption",
    kpiValue=15230.5,
    kpiUnit="kWh",
    hasBeginning="2025-01-01T00:00:00Z",
    hasEnd="2025-01-31T23:59:59Z"
)
```

### Adding KPIs to a Set

```python
KPISet.SetKPI(kpiset, kpi)

# Overwrite an existing KPI with the same @id
KPISet.SetKPI(kpiset, updated_kpi, overwrite=True)
```

### Aligning Timesteps

Propagate the KPI set's timestep to all contained KPIs:

```python
KPISet.SetKPIsTimestep(kpiset)
```

### KPI Accessors

```python
KPI.UID(kpi)        # "kpi-energy"
KPI.Name(kpi)       # "Total Energy Consumption"
KPI.Value(kpi)      # 15230.5
KPI.Timestep(kpi)   # {"time:hasBeginning": "...", "time:hasEnd": "..."}
```

## Scenarios

Scenarios represent hypothetical situations (e.g., a renovation, a control strategy change):

```python
from btwin import Scenario

scenario = Scenario.Constructor(
    "scenario-baseline",
    name="Baseline",
    description="Current building operation without changes"
)
```

### Linking KPI Sets to Scenarios

```python
KPISet.SetScenario(kpiset, scenarioObject=scenario)
```

### Scenario Accessors

```python
Scenario.UID(scenario)            # "scenario-baseline"
Scenario.Name(scenario)           # "Baseline"
Scenario.Description(scenario)    # "Current building operation without changes"
Scenario.Relationships(scenario)  # {}
```
