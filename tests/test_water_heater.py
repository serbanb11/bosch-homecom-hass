"""Tests for the K40 water heater entity (regression cases for #174)."""

from unittest.mock import AsyncMock, Mock

from custom_components.bosch_homecom.water_heater import BoschComK40WaterHeater


def _coordinator(dhw_circuits):
    coord = Mock()
    coord.unique_id = "k40-174"
    coord.device_info = Mock()
    coord.data.dhw_circuits = dhw_circuits
    coord.bhc = Mock()
    coord.bhc.async_put_dhw_operation_mode = AsyncMock()
    coord.async_request_refresh = AsyncMock()
    return coord


def test_null_circuit_fields_do_not_crash_setup():
    """A tankless system reports the circuit with null fields (#174).

    set_attr() runs in __init__, so an unguarded access kills the whole
    water_heater platform at setup — construction must survive null values.
    """
    circuits = [
        {
            "id": "/dhwCircuits/dhw1",
            "operationMode": None,
            "actualTemp": None,
        }
    ]
    entity = BoschComK40WaterHeater(coordinator=_coordinator(circuits), field="wh")

    assert entity.current_operation is None
    assert entity.current_temperature is None


def test_non_dict_and_missing_value_fields_are_skipped():
    """Fields that are not dicts or carry a null value are ignored."""
    circuits = [
        {
            "id": "/dhwCircuits/dhw1",
            "operationMode": {"value": None},
            "actualTemp": "bogus",
        }
    ]
    entity = BoschComK40WaterHeater(coordinator=_coordinator(circuits), field="wh")

    assert entity.current_operation is None
    assert entity.current_temperature is None


def test_none_circuits_list_does_not_crash():
    """A transiently missing dhw_circuits list must not raise."""
    entity = BoschComK40WaterHeater(coordinator=_coordinator(None), field="wh")

    assert entity.current_operation is None


def test_valid_circuit_populates_attributes():
    """A healthy circuit still maps operation mode and temperature."""
    circuits = [
        {
            "id": "/dhwCircuits/dhw1",
            "operationMode": {"value": "eco"},
            "actualTemp": {"value": 51.5, "unitOfMeasure": "C"},
        }
    ]
    entity = BoschComK40WaterHeater(coordinator=_coordinator(circuits), field="wh")

    assert entity.current_operation == "Eco+"
    assert entity.current_temperature == 51.5


def test_unknown_operation_mode_does_not_crash():
    """An unmapped mode value yields no current operation instead of KeyError."""
    circuits = [
        {
            "id": "/dhwCircuits/dhw1",
            "operationMode": {"value": "someNewMode"},
        }
    ]
    entity = BoschComK40WaterHeater(coordinator=_coordinator(circuits), field="wh")

    assert entity.current_operation is None
