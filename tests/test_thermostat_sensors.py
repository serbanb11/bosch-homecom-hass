"""Tests for the sensors of the room units behind a K30/K40 gateway."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass
import pytest

from custom_components.bosch_homecom.sensor import (
    THERMOSTAT_BATTERY_STATES,
    BoschComThermostatBatterySensor,
)


def _battery_sensor(battery: dict | None) -> BoschComThermostatBatterySensor:
    device = {"id": "/devices/device1"}
    if battery is not None:
        device["battery"] = battery
    coordinator = MagicMock()
    coordinator.unique_id = "102011489"
    coordinator.data = SimpleNamespace(devices=[device])
    return BoschComThermostatBatterySensor(coordinator, None, "device1")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("BAT_NORMAL", "normal"),
        ("BAT_LOW", "low"),
        ("BAT_TOO_LOW", "too_low"),
        ("BAT_FOTA_FORBIDDEN", "fota_forbidden"),
        ("NO_BAT", "no_battery"),
    ],
)
def test_battery_state(value, expected):
    """The gateway's battery string maps to an enum state, not a percentage."""
    sensor = _battery_sensor(
        {
            "id": "/devices/device1/battery",
            "type": "stringValue",
            "value": value,
            "allowedValues": list(THERMOSTAT_BATTERY_STATES),
        }
    )
    assert sensor.native_value == expected
    assert sensor.native_value in sensor.options


@pytest.mark.parametrize("battery", [None, {}, {"value": "BAT_SOMETHING_NEW"}])
def test_battery_state_unknown(battery):
    """A missing or unknown battery value is None, not an invalid enum state."""
    assert _battery_sensor(battery).native_value is None


def test_battery_is_enum_without_unit():
    """The sensor is an enum; a battery device class would require a percentage."""
    sensor = _battery_sensor({"value": "BAT_LOW"})
    assert sensor.device_class == SensorDeviceClass.ENUM
    assert sensor.native_unit_of_measurement is None


def test_room_unit_reports_its_zone_and_circuit():
    """zoneId and assignedHC were read with the device but never shown."""
    sensor = _battery_sensor({"value": "BAT_NORMAL"})
    device = sensor.coordinator.data.devices[0]
    device["zoneId"] = {"value": 1}
    device["assignedHC"] = {"value": "hc1"}

    assert sensor.extra_state_attributes == {"zone_id": 1, "heating_circuit": "hc1"}

    del device["zoneId"]
    assert sensor.extra_state_attributes == {"heating_circuit": "hc1"}
