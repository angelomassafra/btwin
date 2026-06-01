import pytest

from btwin import (
    Document,
    Equipment,
    KPISet,
    Point,
    PropertySet,
    Scenario,
    SpatialElement,
)


@pytest.fixture
def site_obj():
    return SpatialElement.Constructor("site-01", "bot:Site", "Test Site")


@pytest.fixture
def building_obj():
    return SpatialElement.Constructor("bldg-01", "bot:Building", "Test Building")


@pytest.fixture
def storey_obj():
    return SpatialElement.Constructor("storey-01", "bot:Storey", "Ground Floor")


@pytest.fixture
def space_obj():
    return SpatialElement.Constructor("space-01", "bot:Space", "Room 101")


@pytest.fixture
def equipment_obj():
    return Equipment.Constructor("equip-01", "brick:Equipment", "AHU-1")


@pytest.fixture
def point_obj():
    return Point.Constructor("point-01", "brick:Temperature_Sensor", "Temp Sensor")


@pytest.fixture
def pset_obj():
    return PropertySet.Constructor("pset-01", "Thermal Properties")


@pytest.fixture
def scenario_obj():
    return Scenario.Constructor("scenario-01")


@pytest.fixture
def document_obj():
    return Document.Constructor("doc-01", "Energy Model")


@pytest.fixture
def kpiset_obj():
    return KPISet.Constructor("kpiset-01", "Energy KPIs")
