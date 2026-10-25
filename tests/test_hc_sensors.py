"""Tests for the per-heating-circuit temperature sensors (#207)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homecom_alt import BHCDeviceK40
import pytest

from custom_components.bosch_homecom.sensor import (
    HC_TEMPERATURE_SENSORS,
    BoschComSensorHc,
    BoschComSensorHcTemperature,
    async_setup_entry as sensor_async_setup_entry,
)

# A K30 with a direct circuit and a mixed underfloor circuit, as in #207: only
# the mixed circuit has a flow sensor, and only the direct one a setpoint.
HC1 = {
    "id": "/heatingCircuits/hc1",
    "operationMode": {"value": "auto"},
    "supplyTemperatureSetpoint": {"value": 35.0, "unitOfMeasure": "C"},
    "actualSupplyTemp": None,
}
HC2 = {
    "id": "/heatingCircuits/hc2",
    "operationMode": {"value": "auto"},
    "supplyTemperatureSetpoint": {"value": None, "unitOfMeasure": "C"},
    "actualSupplyTemp": {
        "id": "/heatingCircuits/hc2/actualSupplyTemp",
        "type": "floatValue",
        "writeable": 0,
        "unitOfMeasure": "C",
        "value": 28.9,
    },
}


def _coordinator(circuits, device_type="k30"):
    coordinator = MagicMock()
    coordinator.unique_id = "k30123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "k30123")}}
    coordinator.bhc = AsyncMock()
    coordinator.extra_data = {}
    coordinator.local_first = None
    coordinator.device = {"deviceId": "k30123", "deviceType": device_type}
    coordinator.data = BHCDeviceK40(
        device={"deviceId": "k30123", "deviceType": device_type},
        firmware=[],
        notifications=[],
        holiday_mode=None,
        away_mode=None,
        power_limitation=None,
        outdoor_temp=None,
        heat_sources=None,
        dhw_circuits=None,
        heating_circuits=circuits,
        ventilation=None,
        zones=None,
        flame_indication=None,
        energy_history=None,
        hourly_energy_history=None,
        indoor_humidity=None,
        devices=None,
    )
    return coordinator


@pytest.mark.parametrize("device_type", ["k30", "k40"])
async def test_setup_creates_only_the_temperatures_each_circuit_serves(
    hass, device_type
):
    """HC2 gets a flow temperature, HC1 a setpoint; nothing for absent nodes."""
    coordinator = _coordinator([HC1, HC2], device_type)
    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]
    added: list = []
    await sensor_async_setup_entry(hass, config_entry, added.extend)

    temps = {
        e.unique_id: e for e in added if isinstance(e, BoschComSensorHcTemperature)
    }
    assert set(temps) == {
        "k30123-hc1-supply-temp-setpoint",
        "k30123-hc2-actual-supply-temp",
    }
    # The status sensors are still there for both circuits.
    assert {e.field for e in added if isinstance(e, BoschComSensorHc)} == {
        "hc1",
        "hc2",
    }

    flow = temps["k30123-hc2-actual-supply-temp"]
    assert flow.native_value == 28.9
    assert flow.native_unit_of_measurement == UnitOfTemperature.CELSIUS
    assert flow.device_class is SensorDeviceClass.TEMPERATURE
    assert flow.state_class is SensorStateClass.MEASUREMENT
    assert flow.translation_key == "hc_actual_supply_temp"
    assert flow._attr_translation_placeholders == {"circuit": "hc2"}
    assert flow._attr_suggested_object_id == "hc2_actual_supply_temp"

    setpoint = temps["k30123-hc1-supply-temp-setpoint"]
    assert setpoint.native_value == 35.0
    assert setpoint.translation_key == "hc_supply_temp_setpoint"


def test_temperature_sensor_tracks_updates_and_units():
    """A later update changes the value; a vanished node reads unknown."""
    coordinator = _coordinator([HC2])
    sensor = BoschComSensorHcTemperature(
        coordinator=coordinator,
        config_entry=MagicMock(),
        hc_id="hc2",
        description=HC_TEMPERATURE_SENSORS[0],
    )
    assert sensor.native_value == 28.9

    hc2 = {**HC2, "actualSupplyTemp": {"value": 86, "unitOfMeasure": "F"}}
    coordinator.data = coordinator.data.__class__(
        **{**coordinator.data.__dict__, "heating_circuits": [hc2]}
    )
    assert sensor.native_value == 86
    assert sensor.native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT

    hc2 = {**HC2, "actualSupplyTemp": None}
    coordinator.data = coordinator.data.__class__(
        **{**coordinator.data.__dict__, "heating_circuits": [hc2]}
    )
    assert sensor.native_value is None
    assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS


def test_status_sensor_exposes_the_flow_temperature_attribute():
    """actualSupplyTemp is also an attribute of the circuit status sensor."""
    coordinator = _coordinator([HC1, HC2])
    hc2 = BoschComSensorHc(
        coordinator=coordinator, config_entry=MagicMock(), field="hc2"
    )
    assert hc2.extra_state_attributes["actualSupplyTemp"] == 28.9
    assert hc2.extra_state_attributes["supplyTemperatureSetpoint"] is None

    hc1 = BoschComSensorHc(
        coordinator=coordinator, config_entry=MagicMock(), field="hc1"
    )
    assert hc1.extra_state_attributes["actualSupplyTemp"] == "unknown"

    orphan = BoschComSensorHc(
        coordinator=coordinator, config_entry=MagicMock(), field="hc9"
    )
    assert orphan.extra_state_attributes["actualSupplyTemp"] == "unknown"
