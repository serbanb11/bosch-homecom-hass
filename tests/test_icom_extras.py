"""Tests for icom data the library fetched but nothing showed (item 4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homecom_alt import BHCDeviceIcom

from custom_components.bosch_homecom.binary_sensor import (
    BoschComIcomHolidayActiveSensor,
    async_setup_entry as binary_sensor_async_setup_entry,
)
from custom_components.bosch_homecom.coordinator import BoschComModuleCoordinatorIcom
from custom_components.bosch_homecom.number import (
    BoschComIcomHcLevelNumber,
    _build_icom_hc_level_numbers,
)
from custom_components.bosch_homecom.select import (
    BoschComSelectHcSwitchProgram,
    async_setup_entry as select_async_setup_entry,
)
from custom_components.bosch_homecom.sensor import _build_icom_extra_sensors

HC1 = {
    "id": "/heatingCircuits/hc1",
    "operationMode": {"value": "auto", "allowedValues": ["manual", "auto"]},
    "holidayActivated": {"value": "hm2"},
    "activeSwitchProgram": {"value": "A", "allowedValues": ["A", "B"]},
    "switchProgramMode": {"value": "levels"},
    "temperatureLevelComfort2": {
        "value": 21.0,
        "minValue": 10.0,
        "maxValue": 30.0,
        "stepSize": 0.5,
    },
    "temperatureLevelEco": {"value": 17.0},
}
HC2 = {
    "id": "/heatingCircuits/hc2",
    "holidayActivated": {"value": "off"},
    "activeSwitchProgram": None,
    "temperatureLevelComfort2": None,
    "temperatureLevelEco": {"value": None},
}
DHW1 = {"id": "/dhwCircuits/dhw1", "holidayActivated": {"value": "hm2"}}
HOLIDAYS = [
    {"id": "/system/holidayModes/hm1", "startStop": {"value": "2026-12-20/2027-01-03"}},
    {
        "id": "/system/holidayModes/hm2",
        "startStop": {"value": "2026-11-01/2026-11-08"},
        "hcMode": {"value": "FIX_TEMPERATURE"},
        "dhwMode": {"value": "OFF"},
        "fixTemperature": {"value": 17.0},
    },
]


def _coordinator(heating_circuits=None, dhw_circuits=None, holidays=None, bus="EMS2_0"):
    coordinator = object.__new__(BoschComModuleCoordinatorIcom)
    coordinator.unique_id = "icom123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "icom123")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.extra_data = {}
    coordinator.local_first = None
    coordinator.device = {"deviceId": "icom123", "deviceType": "icom"}
    coordinator.data = BHCDeviceIcom(
        device={"deviceId": "icom123", "deviceType": "icom"},
        firmware=[],
        notifications=[],
        holiday_mode=HOLIDAYS if holidays is None else holidays,
        heat_sources={},
        dhw_circuits=[DHW1] if dhw_circuits is None else dhw_circuits,
        heating_circuits=[HC1, HC2] if heating_circuits is None else heating_circuits,
        solar_circuits=None,
        ventilation=None,
        system_info=None,
        system_bus={"value": bus} if bus else None,
    )
    return coordinator


async def _setup(hass, setup, coordinator):
    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]
    added: list = []
    await setup(hass, config_entry, added.extend)
    return added


# --- holiday periods ----------------------------------------------------------


async def test_holiday_sensor_per_circuit_that_reports_the_node(hass):
    added = await _setup(hass, binary_sensor_async_setup_entry, _coordinator())
    holidays = {
        e.unique_id: e for e in added if isinstance(e, BoschComIcomHolidayActiveSensor)
    }
    assert set(holidays) == {
        "icom123-hc1-holiday_active",
        "icom123-hc2-holiday_active",
        "icom123-dhw1-holiday_active",
    }
    assert holidays["icom123-hc1-holiday_active"].translation_placeholders == {
        "circuit": "hc1"
    }


def test_active_period_is_described():
    sensor = BoschComIcomHolidayActiveSensor(_coordinator(), "heating_circuits", "hc1")
    assert sensor.is_on is True
    assert sensor.extra_state_attributes == {
        "period": "hm2",
        "start": "2026-11-01",
        "end": "2026-11-08",
        "heating_mode": "FIX_TEMPERATURE",
        "dhw_mode": "OFF",
        "fixed_temperature": 17.0,
    }
    dhw = BoschComIcomHolidayActiveSensor(_coordinator(), "dhw_circuits", "dhw1")
    assert dhw.is_on is True
    assert dhw.extra_state_attributes["period"] == "hm2"


def test_inactive_and_unknown_periods():
    sensor = BoschComIcomHolidayActiveSensor(_coordinator(), "heating_circuits", "hc2")
    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {}

    # The period is active but its details were not fetched: id only.
    sensor = BoschComIcomHolidayActiveSensor(
        _coordinator(holidays=[]), "heating_circuits", "hc1"
    )
    assert sensor.is_on is True
    assert sensor.extra_state_attributes["period"] == "hm2"
    assert sensor.extra_state_attributes["start"] is None

    missing = BoschComIcomHolidayActiveSensor(
        _coordinator(heating_circuits=[{"id": "/heatingCircuits/hc1"}]),
        "heating_circuits",
        "hc1",
    )
    assert missing.is_on is None


# --- switch program select ----------------------------------------------------


async def test_switch_program_select_only_where_served(hass):
    added = await _setup(hass, select_async_setup_entry, _coordinator())
    selects = [e for e in added if isinstance(e, BoschComSelectHcSwitchProgram)]
    assert [e.unique_id for e in selects] == ["icom123-hc1-switch_program"]


async def test_switch_program_select_reads_and_writes():
    coordinator = _coordinator()
    select = BoschComSelectHcSwitchProgram(coordinator=coordinator, field="hc1")
    assert select.options == ["A", "B"]
    assert select.current_option == "A"
    assert select.extra_state_attributes == {"switch_program_mode": "levels"}

    await select.async_select_option("B")

    coordinator.bhc.async_set_hc_active_switch_program.assert_awaited_once_with(
        "icom123", "hc1", "B"
    )
    coordinator.async_request_refresh.assert_awaited_once()


def test_switch_program_select_defaults_without_allowed_values():
    hc1 = {**HC1, "activeSwitchProgram": {"value": "B"}, "switchProgramMode": None}
    select = BoschComSelectHcSwitchProgram(
        coordinator=_coordinator(heating_circuits=[hc1]), field="hc1"
    )
    assert select.options == ["A", "B"]
    assert select.current_option == "B"
    assert select.extra_state_attributes == {}


# --- temperature levels -------------------------------------------------------


def test_level_numbers_only_for_levels_with_a_value():
    numbers = _build_icom_hc_level_numbers(_coordinator())
    assert [n.unique_id for n in numbers] == [
        "icom123-hc1-comfort2",
        "icom123-hc1-eco",
    ]
    comfort = numbers[0]
    assert comfort.translation_key == "hc_comfort2"
    assert comfort.translation_placeholders == {"circuit": "hc1"}
    assert (comfort.native_min_value, comfort.native_max_value) == (10.0, 30.0)
    assert comfort.native_step == 0.5
    assert comfort.native_value == 21.0
    eco = numbers[1]
    assert (eco.native_min_value, eco.native_max_value, eco.native_step) == (5, 30, 0.5)
    assert eco.native_value == 17.0


async def test_level_number_writes_through_the_library_setter():
    coordinator = _coordinator()
    number = BoschComIcomHcLevelNumber(
        coordinator,
        hc_id="hc1",
        field="temperatureLevelEco",
        min_value=5,
        max_value=30,
        step=0.5,
    )
    await number.async_set_native_value(16.5)
    coordinator.bhc.async_set_hc_temp_level_eco.assert_awaited_once_with(
        "icom123", "hc1", 16.5
    )
    coordinator.bhc.async_set_hc_temp_level_comfort2.assert_not_awaited()


# --- system bus ---------------------------------------------------------------


def test_system_bus_sensor_only_when_reported():
    sensors = {e.unique_id: e for e in _build_icom_extra_sensors(_coordinator())}
    assert "icom123-system-bus" in sensors
    assert sensors["icom123-system-bus"].native_value == "EMS2_0"

    sensors = {e.unique_id for e in _build_icom_extra_sensors(_coordinator(bus=None))}
    assert "icom123-system-bus" not in sensors
