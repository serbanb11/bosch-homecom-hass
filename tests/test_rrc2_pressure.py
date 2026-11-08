"""RRC2 boiler water pressure (#230)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfPressure
import pytest

from custom_components.bosch_homecom.coordinator import BoschComModuleCoordinatorRrc2
from custom_components.bosch_homecom.sensor import (
    BoschComRrc2Sensor,
    _add_or_defer,
    _add_pending_sensors_later,
    _rrc2_pressure_candidate,
)


def _coordinator(pressure=None):
    coordinator = object.__new__(BoschComModuleCoordinatorRrc2)
    coordinator.unique_id = "rrc2123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "rrc2123")}}
    heat_sources = {"supplyTemperature": {"value": 55.0}}
    if pressure is not None:
        heat_sources["systemPressure"] = pressure
    coordinator.data = SimpleNamespace(heat_sources=heat_sources)
    coordinator.listeners = []
    coordinator.async_add_listener = lambda listener: (
        coordinator.listeners.append(listener) or (lambda: None)
    )
    return coordinator


def test_pressure_sensor_reads_bar_with_the_translated_name():
    coordinator = _coordinator({"value": 1.8, "unitOfMeasure": "bar"})
    entities, pending = [], []

    _add_or_defer(_rrc2_pressure_candidate(coordinator), entities, pending)

    (sensor,) = entities
    assert pending == []
    assert isinstance(sensor, BoschComRrc2Sensor)
    assert sensor.native_value == 1.8
    assert sensor.unique_id == "rrc2123-hs-system-pressure"
    assert sensor.translation_key == "system_pressure"
    assert sensor.device_class == SensorDeviceClass.PRESSURE
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    assert sensor.native_unit_of_measurement == UnitOfPressure.BAR


@pytest.mark.parametrize("node", [None, {}, {"value": None}])
def test_no_pressure_sensor_until_the_gateway_reports_it(node):
    coordinator = _coordinator(node)
    entities, pending = [], []

    _add_or_defer(_rrc2_pressure_candidate(coordinator), entities, pending)

    assert entities == []
    assert len(pending) == 1


def test_pressure_sensor_is_added_on_a_later_update():
    coordinator = _coordinator()
    entities, pending, added = [], [], []
    _add_or_defer(_rrc2_pressure_candidate(coordinator), entities, pending)
    entry = MagicMock()
    _add_pending_sensors_later(coordinator, entry, pending, added.extend)

    coordinator.data.heat_sources["systemPressure"] = {"value": 1.5}
    for listener in coordinator.listeners:
        listener()
    for listener in coordinator.listeners:
        listener()

    assert [sensor.native_value for sensor in added] == [1.5]


def test_pressure_marker_is_no_reading():
    """A failed sensor's marker must not trip a low or high pressure alert."""
    coordinator = _coordinator(
        {"value": 255, "unitOfMeasure": "bar", "state": [{"invalid": 255}]}
    )
    entities, pending = [], []
    _add_or_defer(_rrc2_pressure_candidate(coordinator), entities, pending)

    assert entities[0].native_value is None

    coordinator.data.heat_sources["systemPressure"] = {
        "value": 1.7,
        "state": [{"invalid": 255}],
    }
    assert entities[0].native_value == 1.7


def test_other_rrc2_sensors_keep_their_names_and_raw_values():
    """The new options are opt-in: existing RRC2 entities are unchanged."""
    coordinator = _coordinator()
    coordinator.data.heat_sources["supplyTemperature"] = {
        "value": 255,
        "state": [{"invalid": 255}],
    }
    sensor = BoschComRrc2Sensor(
        coordinator,
        scope="heat_sources",
        circuit_id=None,
        field="supplyTemperature",
        name_suffix="hs_supply_temperature",
        unique_suffix="hs-supply-temperature",
    )

    assert sensor.name == "hs_supply_temperature"
    assert sensor.native_value == 255
