import pytest

from btwin import Property, PropertySet


class TestPropertySetConstructor:
    def test_happy_path(self, pset_obj):
        assert pset_obj["@id"] == "pset-01"
        assert pset_obj["@type"] == "ifc:IfcPropertySet"
        assert pset_obj["name"] == "Thermal Properties"
        assert pset_obj["ifc:HasProperties"] == []

    def test_missing_uid_raises(self):
        with pytest.raises(ValueError):
            PropertySet.Constructor(None, "Name")

    def test_empty_uid_raises(self):
        with pytest.raises(ValueError):
            PropertySet.Constructor("", "Name")

    def test_missing_name_raises(self):
        with pytest.raises(ValueError):
            PropertySet.Constructor("pset-01", None)


class TestSetProperty:
    def test_add_property(self, pset_obj):
        prop = Property.Constructor("U-Value", propertyValue=0.25, propertyQuantity="IfcReal")
        PropertySet.SetProperty(pset=pset_obj, property=prop)
        assert len(pset_obj["ifc:HasProperties"]) == 1

    def test_overwrite_false_skips_existing(self, pset_obj):
        prop1 = Property.Constructor("U-Value", propertyValue=0.25, propertyQuantity="IfcReal")
        prop2 = Property.Constructor("U-Value", propertyValue=0.50, propertyQuantity="IfcReal")
        PropertySet.SetProperty(pset=pset_obj, property=prop1)
        PropertySet.SetProperty(pset=pset_obj, property=prop2, overwrite=False)
        assert Property.Value(pset_obj["ifc:HasProperties"][0]) == 0.25

    def test_overwrite_true_replaces(self, pset_obj):
        prop1 = Property.Constructor("U-Value", propertyValue=0.25, propertyQuantity="IfcReal")
        prop2 = Property.Constructor("U-Value", propertyValue=0.50, propertyQuantity="IfcReal")
        PropertySet.SetProperty(pset=pset_obj, property=prop1)
        PropertySet.SetProperty(pset=pset_obj, property=prop2, overwrite=True)
        assert Property.Value(pset_obj["ifc:HasProperties"][0]) == 0.50


class TestSetProperties:
    def test_batch_add(self, pset_obj):
        props = [
            Property.Constructor("U-Value", propertyValue=0.25, propertyQuantity="IfcReal"),
            Property.Constructor("R-Value", propertyValue=4.0, propertyQuantity="IfcReal"),
        ]
        PropertySet.SetProperties(pset=pset_obj, properties=props)
        assert len(pset_obj["ifc:HasProperties"]) == 2

    def test_none_properties_returns_pset(self, pset_obj):
        result = PropertySet.SetProperties(pset=pset_obj, properties=None)
        assert result is pset_obj


class TestPropertyQuery:
    def test_get_by_name(self, pset_obj):
        prop = Property.Constructor("U-Value", propertyValue=0.25, propertyQuantity="IfcReal")
        PropertySet.SetProperty(pset=pset_obj, property=prop)
        found = PropertySet.Property(pset=pset_obj, propertyName="U-Value")
        assert found is not None
        assert found["name"] == "U-Value"

    def test_missing_returns_none(self, pset_obj):
        assert PropertySet.Property(pset=pset_obj, propertyName="Nonexistent") is None


class TestProperties:
    def test_returns_list(self, pset_obj):
        props = PropertySet.Properties(pset=pset_obj)
        assert isinstance(props, list)


class TestPropertyConstructor:
    def test_single_value(self):
        prop = Property.Constructor("U-Value", propertyValue=0.25, propertyQuantity="IfcReal")
        assert prop["@type"] == "IfcPropertySingleValue"
        assert prop["name"] == "U-Value"
        assert prop["nominalValue"]["value"] == 0.25

    def test_enumerated_values(self):
        prop = Property.Constructor(
            "Materials", propertyValues=["Brick", "Concrete"],
            propertyQuantity="IfcLabel",
            propertyType="IfcPropertyEnumeratedValue",
        )
        assert prop["@type"] == "IfcPropertyEnumeratedValue"
        assert len(prop["enumeratedValues"]) == 2

    def test_with_unit(self):
        prop = Property.Constructor("U-Value", propertyValue=0.25, propertyQuantity="IfcReal", propertyUnit="W/(m²·K)")
        assert prop["nominalValue"]["unit"] == "W/(m²·K)"

    def test_missing_name_raises(self):
        with pytest.raises(ValueError):
            Property.Constructor(None, propertyValue=1, propertyQuantity="IfcReal")


class TestPropertyAccessors:
    def test_value_single(self):
        prop = Property.Constructor("X", propertyValue=42, propertyQuantity="IfcInteger")
        assert Property.Value(prop) == 42

    def test_value_enumerated(self):
        prop = Property.Constructor(
            "X", propertyValues=["a", "b"],
            propertyQuantity="IfcLabel",
            propertyType="IfcPropertyEnumeratedValue",
        )
        assert Property.Value(prop) == ["a", "b"]

    def test_quantity_type(self):
        prop = Property.Constructor("X", propertyValue=1, propertyQuantity="IfcReal")
        assert Property.QuantityType(prop) == "IfcReal"

    def test_unit(self):
        prop = Property.Constructor("X", propertyValue=1, propertyQuantity="IfcReal", propertyUnit="m")
        assert Property.Unit(prop) == "m"

    def test_unit_none(self):
        prop = Property.Constructor("X", propertyValue=1, propertyQuantity="IfcReal")
        assert Property.Unit(prop) is None


class TestPropertySetValue:
    def test_set_value(self):
        prop = Property.Constructor("X", propertyValue=1, propertyQuantity="IfcReal")
        Property.SetValue(prop, propertyValue=99, propertyQuantity="IfcReal")
        assert Property.Value(prop) == 99

    def test_set_enumerated_value(self):
        prop = Property.Constructor("X", propertyValue=1, propertyQuantity="IfcReal")
        Property.SetValue(prop, propertyValue=["a", "b"],
                          propertyType="IfcPropertyEnumeratedValue",
                          propertyQuantity="IfcLabel")
        assert prop["@type"] == "IfcPropertyEnumeratedValue"
        assert len(prop["enumeratedValues"]) == 2
        assert "nominalValue" not in prop

    def test_switch_from_enum_to_single(self):
        prop = Property.Constructor(
            "X", propertyValues=["a"], propertyQuantity="IfcLabel",
            propertyType="IfcPropertyEnumeratedValue",
        )
        Property.SetValue(prop, propertyValue=42, propertyQuantity="IfcReal")
        assert prop["@type"] == "IfcPropertySingleValue"
        assert "enumeratedValues" not in prop

    def test_set_value_with_unit(self):
        prop = Property.Constructor("X", propertyValue=1, propertyQuantity="IfcReal")
        Property.SetValue(prop, propertyValue=100, propertyQuantity="IfcReal", propertyUnit="kWh")
        assert prop["nominalValue"]["unit"] == "kWh"

    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            Property.SetValue("bad", propertyValue=1, propertyQuantity="IfcReal")

    def test_missing_name_raises(self):
        with pytest.raises(ValueError):
            Property.SetValue({}, propertyValue=1, propertyQuantity="IfcReal")

    def test_invalid_property_type_raises(self):
        prop = Property.Constructor("X", propertyValue=1, propertyQuantity="IfcReal")
        with pytest.raises(ValueError):
            Property.SetValue(prop, propertyValue=1, propertyType="Invalid")

    def test_missing_quantity_single_raises(self):
        prop = Property.Constructor("X", propertyValue=1, propertyQuantity="IfcReal")
        with pytest.raises(ValueError):
            Property.SetValue(prop, propertyValue=1, propertyQuantity=None)

    def test_missing_quantity_enum_raises(self):
        prop = Property.Constructor("X", propertyValue=1, propertyQuantity="IfcReal")
        with pytest.raises(ValueError):
            Property.SetValue(prop, propertyValue=["a"],
                              propertyType="IfcPropertyEnumeratedValue",
                              propertyQuantity=None)

    def test_non_list_enum_value_raises(self):
        prop = Property.Constructor("X", propertyValue=1, propertyQuantity="IfcReal")
        with pytest.raises(ValueError):
            Property.SetValue(prop, propertyValue="not_list",
                              propertyType="IfcPropertyEnumeratedValue",
                              propertyQuantity="IfcLabel")


class TestPropertyConstructorErrors:
    def test_empty_name_raises(self):
        with pytest.raises(ValueError):
            Property.Constructor("", propertyValue=1, propertyQuantity="IfcReal")

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            Property.Constructor("X", propertyType=123)

    def test_invalid_type_value_raises(self):
        with pytest.raises(ValueError):
            Property.Constructor("X", propertyType="InvalidType")

    def test_missing_quantity_single_raises(self):
        with pytest.raises(ValueError):
            Property.Constructor("X", propertyValue=1, propertyQuantity=None)

    def test_enumerated_non_list_raises(self):
        with pytest.raises(TypeError):
            Property.Constructor("X", propertyValues="not_list",
                                 propertyQuantity="IfcLabel",
                                 propertyType="IfcPropertyEnumeratedValue")

    def test_enumerated_missing_quantity_raises(self):
        with pytest.raises(ValueError):
            Property.Constructor("X", propertyValues=["a"],
                                 propertyType="IfcPropertyEnumeratedValue")

    def test_enumerated_with_unit(self):
        prop = Property.Constructor("X", propertyValues=["a", "b"],
                                    propertyQuantity="IfcLabel",
                                    propertyType="IfcPropertyEnumeratedValue",
                                    propertyUnit="m")
        assert prop["enumeratedValues"][0]["unit"] == "m"


class TestQuantityTypeAdvanced:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            Property.QuantityType("bad")

    def test_enumerated_quantity(self):
        prop = Property.Constructor("X", propertyValues=["a", "b"],
                                    propertyQuantity="IfcLabel",
                                    propertyType="IfcPropertyEnumeratedValue")
        assert Property.QuantityType(prop) == "IfcLabel"

    def test_enumerated_empty_values(self):
        prop = {"@type": "IfcPropertyEnumeratedValue", "enumeratedValues": []}
        assert Property.QuantityType(prop) is None

    def test_unknown_type_with_nominal(self):
        prop = {"@type": "Unknown", "nominalValue": {"type": "IfcReal"}}
        assert Property.QuantityType(prop) == "IfcReal"

    def test_unknown_type_no_nominal(self):
        prop = {"@type": "Unknown"}
        assert Property.QuantityType(prop) is None

    def test_single_empty_type(self):
        prop = {"@type": "IfcPropertySingleValue", "nominalValue": {"type": ""}}
        assert Property.QuantityType(prop) is None

    def test_single_no_nominal(self):
        prop = {"@type": "IfcPropertySingleValue"}
        assert Property.QuantityType(prop) is None

    def test_unknown_type_nominal_empty(self):
        prop = {"@type": "Unknown", "nominalValue": {"type": ""}}
        assert Property.QuantityType(prop) is None


class TestUnitAdvanced:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            Property.Unit("bad")

    def test_enumerated_unit(self):
        prop = Property.Constructor("X", propertyValues=["a", "b"],
                                    propertyQuantity="IfcLabel",
                                    propertyType="IfcPropertyEnumeratedValue",
                                    propertyUnit="m")
        assert Property.Unit(prop) == "m"

    def test_enumerated_no_unit(self):
        prop = Property.Constructor("X", propertyValues=["a"],
                                    propertyQuantity="IfcLabel",
                                    propertyType="IfcPropertyEnumeratedValue")
        assert Property.Unit(prop) is None

    def test_unknown_type_with_nominal_unit(self):
        prop = {"@type": "Unknown", "nominalValue": {"unit": "kg"}}
        assert Property.Unit(prop) == "kg"

    def test_unknown_type_no_nominal(self):
        prop = {"@type": "Unknown"}
        assert Property.Unit(prop) is None


class TestValueAdvanced:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            Property.Value("bad")

    def test_unknown_type_with_nominal(self):
        prop = {"@type": "Unknown", "nominalValue": {"value": 42}}
        assert Property.Value(prop) == 42

    def test_unknown_type_no_nominal(self):
        prop = {"@type": "Unknown"}
        assert Property.Value(prop) is None

    def test_single_value_missing_nominal(self):
        prop = {"@type": "IfcPropertySingleValue"}
        assert Property.Value(prop) is None


class TestPropertySetConstructorErrors:
    def test_non_string_uid_raises(self):
        with pytest.raises(TypeError):
            PropertySet.Constructor(123, "Name")

    def test_non_string_name_raises(self):
        with pytest.raises(TypeError):
            PropertySet.Constructor("uid", 123)

    def test_empty_name_raises(self):
        with pytest.raises(ValueError):
            PropertySet.Constructor("uid", "")


class TestPropertySetSetPropertyErrors:
    def test_non_dict_pset_raises(self):
        with pytest.raises(TypeError):
            PropertySet.SetProperty(pset="bad", property={"name": "X"})

    def test_non_dict_property_raises(self, pset_obj):
        with pytest.raises(TypeError):
            PropertySet.SetProperty(pset=pset_obj, property="bad")

    def test_missing_name_raises(self, pset_obj):
        with pytest.raises(ValueError):
            PropertySet.SetProperty(pset=pset_obj, property={"value": 1})

    def test_empty_name_raises(self, pset_obj):
        with pytest.raises(ValueError):
            PropertySet.SetProperty(pset=pset_obj, property={"name": ""})

    def test_creates_properties_list(self):
        pset = {"@id": "p1"}
        prop = {"name": "X", "value": 1}
        PropertySet.SetProperty(pset=pset, property=prop)
        assert len(pset["ifc:HasProperties"]) == 1

    def test_non_list_has_properties_raises(self):
        pset = {"@id": "p1", "ifc:HasProperties": "bad"}
        with pytest.raises(TypeError):
            PropertySet.SetProperty(pset=pset, property={"name": "X"})


class TestPropertySetSetPropertiesErrors:
    def test_non_dict_pset_raises(self):
        with pytest.raises(TypeError):
            PropertySet.SetProperties(pset="bad", properties=[])

    def test_non_iterable_raises(self, pset_obj):
        with pytest.raises(TypeError):
            PropertySet.SetProperties(pset=pset_obj, properties=123)

    def test_non_dict_element_raises(self, pset_obj):
        with pytest.raises(TypeError):
            PropertySet.SetProperties(pset=pset_obj, properties=["bad"])

    def test_missing_name_in_element_raises(self, pset_obj):
        with pytest.raises(ValueError):
            PropertySet.SetProperties(pset=pset_obj, properties=[{"value": 1}])

    def test_overwrite_replaces(self, pset_obj):
        props1 = [{"name": "X", "value": 1}]
        props2 = [{"name": "X", "value": 2}]
        PropertySet.SetProperties(pset=pset_obj, properties=props1)
        PropertySet.SetProperties(pset=pset_obj, properties=props2, overwrite=True)
        assert pset_obj["ifc:HasProperties"][0]["value"] == 2

    def test_overwrite_false_skips(self, pset_obj):
        props1 = [{"name": "X", "value": 1}]
        props2 = [{"name": "X", "value": 2}]
        PropertySet.SetProperties(pset=pset_obj, properties=props1)
        PropertySet.SetProperties(pset=pset_obj, properties=props2, overwrite=False)
        assert pset_obj["ifc:HasProperties"][0]["value"] == 1

    def test_creates_properties_key(self):
        pset = {"@id": "p1"}
        PropertySet.SetProperties(pset=pset, properties=[{"name": "X", "value": 1}])
        assert "ifc:HasProperties" in pset

    def test_non_list_has_properties_raises(self):
        pset = {"@id": "p1", "ifc:HasProperties": "bad"}
        with pytest.raises(TypeError):
            PropertySet.SetProperties(pset=pset, properties=[{"name": "X"}])


class TestPropertySetPropertyErrors:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            PropertySet.Property(pset="bad", propertyName="X")

    def test_empty_name_raises(self, pset_obj):
        with pytest.raises(ValueError):
            PropertySet.Property(pset=pset_obj, propertyName="")

    def test_none_name_raises(self, pset_obj):
        with pytest.raises(ValueError):
            PropertySet.Property(pset=pset_obj, propertyName=None)


class TestPropertySetPropertiesErrors:
    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            PropertySet.Properties(pset="bad")

    def test_missing_key_returns_empty(self):
        result = PropertySet.Properties(pset={"@id": "p1"})
        assert result == []


class TestPropertySetUID:
    def test_returns_id(self, pset_obj):
        assert PropertySet.UID(pset_obj) == "pset-01"
