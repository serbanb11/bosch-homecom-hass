"""Tests for the K40 heat source status tiles and lifetime energy counters.

Gap analysis items 5 and 6 (#58, #161, #206).
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homecom_alt import BHCDeviceK40
import pytest

from custom_components.bosch_homecom.binary_sensor import (
    BoschComK40HeatSourceFlagSensor,
    async_setup_entry as binary_sensor_async_setup_entry,
)
from custom_components.bosch_homecom.coordinator import BoschComModuleCoordinatorK40
from custom_components.bosch_homecom.sensor import (
    BoschComK40EHeaterStatusSensor,
    BoschComK40LifetimeEnergySensor,
    async_setup_entry as sensor_async_setup_entry,
)


def _emon(output, eheater, compressor):
    return {
        "type": "emonValue",
        "unit": "kWh",
        "values": [
            {"outputProduced": output},
            {"eheater": eheater},
            {"compressor": compressor},
        ],
    }


# A Compress 5800i AW with heating, hot water and a pool, no cooling.
HEAT_SOURCES = {
    "pumpType": {"value": "air_water"},
    "eHeaterStatus": {
        "value": "off",
        "allowedValues": ["off", "heating", "dhw", "alarm"],
    },
    "emergencyMode": {"value": "off"},
    "standbyMode": {"value": "off"},
    "chStatus": {"value": "heating"},
    "pvContactState": {"value": "on"},
    "consumption": _emon(23307.0, 401.0, 6346.0),
    "chConsumption": _emon(15000.0, 300.0, 4000.0),
    "dhwConsumption": _emon(8307.0, 101.0, 2346.0),
    "coolingConsumption": {},
    "poolConsumption": _emon(0.0, 0.0, 0.0),
}


def _coordinator(heat_sources=None):
    coordinator = object.__new__(BoschComModuleCoordinatorK40)
    coordinator.unique_id = "k40123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "k40123")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_add_listener = MagicMock(return_value=lambda: None)
    coordinator.extra_data = {}
    coordinator.recordings = {}
    coordinator.local_first = None
    coordinator.device = {"deviceId": "k40123", "deviceType": "k40"}
    coordinator.data = BHCDeviceK40(
        device={"deviceId": "k40123", "deviceType": "k40"},
        firmware=[],
        notifications=[],
        holiday_mode=None,
        away_mode=None,
        power_limitation=None,
        outdoor_temp=None,
        heat_sources=dict(HEAT_SOURCES) if heat_sources is None else heat_sources,
        dhw_circuits=None,
        heating_circuits=None,
        ventilation=None,
        zones=None,
        flame_indication=None,
        energy_history=None,
        hourly_energy_history=None,
        indoor_humidity=None,
        devices=None,
    )
    return coordinator


async def _setup(hass, setup, coordinator):
    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]
    added: list = []
    await setup(hass, config_entry, added.extend)
    # Several pending groups may each register a listener; fire them all.
    listeners = [call.args[0] for call in coordinator.async_add_listener.call_args_list]

    def listener() -> None:
        for callback in listeners:
            callback()

    return added, listener


# --- status tiles --------------------------------------------------------------


async def test_flags_only_for_tiles_the_device_serves(hass):
    hs = {**HEAT_SOURCES, "pvContactState": {}}
    added, listener = await _setup(
        hass, binary_sensor_async_setup_entry, _coordinator(hs)
    )
    flags = {
        e.unique_id: e for e in added if isinstance(e, BoschComK40HeatSourceFlagSensor)
    }
    assert set(flags) == {
        "k40123-hs_ch_status",
        "k40123-hs_standby_mode",
        "k40123-hs_emergency_mode",
    }
    assert flags["k40123-hs_ch_status"].device_class is BinarySensorDeviceClass.HEAT
    assert (
        flags["k40123-hs_emergency_mode"].device_class
        is BinarySensorDeviceClass.PROBLEM
    )

    # A tile hidden at setup appears once the bulk carries it.
    coordinator = flags["k40123-hs_ch_status"].coordinator
    coordinator.data = replace(coordinator.data, heat_sources=dict(HEAT_SOURCES))
    listener()
    assert any(e.unique_id == "k40123-hs_pv_contact" for e in added)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("chStatus", "heating", True),
        ("chStatus", "off", False),
        ("chStatus", "OFF", False),
        ("standbyMode", "on", True),
        ("standbyMode", "off", False),
        ("emergencyMode", "on", True),
        ("emergencyMode", "off", False),
        ("pvContactState", "on", True),
        ("pvContactState", "off", False),
        ("pvContactState", None, None),
    ],
)
def test_flag_semantics_follow_the_app(key, value, expected):
    """chStatus is active unless "off"; the others are active when "on"."""
    hs = {**HEAT_SOURCES, key: {"value": value} if value is not None else {}}
    sensor = BoschComK40HeatSourceFlagSensor(_coordinator(hs), key)
    assert sensor.is_on is expected
    if value is None:
        assert sensor.extra_state_attributes == {}
    else:
        assert sensor.extra_state_attributes == {"raw_value": value}


# --- electric heater status ----------------------------------------------------


async def test_eheater_status_sensor_created_when_served(hass):
    added, _ = await _setup(hass, sensor_async_setup_entry, _coordinator())
    sensors = [e for e in added if isinstance(e, BoschComK40EHeaterStatusSensor)]
    assert [e.unique_id for e in sensors] == ["k40123-eheater_status"]

    added, _ = await _setup(
        hass,
        sensor_async_setup_entry,
        _coordinator({**HEAT_SOURCES, "eHeaterStatus": {}}),
    )
    assert not [e for e in added if isinstance(e, BoschComK40EHeaterStatusSensor)]


def test_eheater_status_options_and_value():
    sensor = BoschComK40EHeaterStatusSensor(_coordinator())
    assert sensor.device_class is SensorDeviceClass.ENUM
    assert sensor.options == ["off", "heating", "dhw", "alarm"]
    assert sensor.native_value == "off"

    hs = {**HEAT_SOURCES, "eHeaterStatus": {"value": "pool_heat"}}
    sensor = BoschComK40EHeaterStatusSensor(_coordinator(hs))
    assert "pool_heat" in sensor.options  # compressor vocabulary without allowedValues
    assert sensor.native_value == "pool_heat"

    hs = {
        **HEAT_SOURCES,
        "eHeaterStatus": {"value": "something_new", "allowedValues": ["off"]},
    }
    assert BoschComK40EHeaterStatusSensor(_coordinator(hs)).native_value is None


# --- lifetime energy -----------------------------------------------------------


async def test_lifetime_sensors_per_mode_the_device_reports(hass):
    added, listener = await _setup(hass, sensor_async_setup_entry, _coordinator())
    lifetime = {
        e.unique_id: e for e in added if isinstance(e, BoschComK40LifetimeEnergySensor)
    }
    # total, ch, dhw and pool: three parts each; cooling answered 404.
    assert len(lifetime) == 12
    assert not any("cooling" in uid for uid in lifetime)

    total = lifetime["k40123-lifetime_compressor_total"]
    assert total.native_value == 6346.0
    assert total.device_class is SensorDeviceClass.ENERGY
    assert total.state_class is SensorStateClass.TOTAL_INCREASING
    assert total.native_unit_of_measurement == "kWh"
    assert total.entity_registry_enabled_default is True
    assert lifetime["k40123-lifetime_heat_produced_total"].native_value == 23307.0
    assert lifetime["k40123-lifetime_eheater_dhw"].native_value == 101.0
    # Per-mode counters are diagnostics users enable themselves.
    assert (
        lifetime["k40123-lifetime_compressor_ch"].entity_registry_enabled_default
        is False
    )

    # Cooling appears once the device starts serving it.
    coordinator = total.coordinator
    coordinator.data = replace(
        coordinator.data,
        heat_sources={**HEAT_SOURCES, "coolingConsumption": _emon(10.0, 0.0, 5.0)},
    )
    listener()
    ids = [e.unique_id for e in added]
    assert "k40123-lifetime_compressor_cooling" in ids
    assert ids.count("k40123-lifetime_compressor_cooling") == 1


def test_lifetime_sensor_reads_none_for_a_malformed_counter():
    hs = {**HEAT_SOURCES, "consumption": {"values": [{"compressor": "n/a"}, "x"]}}
    sensor = BoschComK40LifetimeEnergySensor(
        _coordinator(hs), "consumption", "compressor", enabled_default=True
    )
    assert sensor.native_value is None
    assert sensor.translation_key == "lifetime_compressor_total"
