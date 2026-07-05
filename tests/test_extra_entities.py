"""Tests for extra K40 endpoint entities (sensor, select, button, number)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homecom_alt import BHCDeviceK40
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom.button import BoschComK40DhwChargeButton
from custom_components.bosch_homecom.const import CONF_DEVICES, CONF_REFRESH, DOMAIN
from custom_components.bosch_homecom.coordinator import (
    BoschComModuleCoordinatorIcom,
    BoschComModuleCoordinatorK40,
)
from custom_components.bosch_homecom.number import BoschComK40DhwChargeDurationNumber
from custom_components.bosch_homecom.select import BoschComK40ExtraSelect
from custom_components.bosch_homecom.sensor import (
    BoschComK40ExtraSensor,
    BoschComK40HeatDemandSensor,
    BoschComK40StartCountsSensor,
)


@pytest.fixture
def device():
    """Fixture for K40 device data."""
    return {"deviceId": "102128202", "deviceType": "k40"}


@pytest.fixture
def firmware():
    """Fixture for firmware data."""
    return {"value": "14.00.03"}


@pytest.fixture
def entry():
    """Fixture for config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        unique_id="test-user",
        data={
            CONF_DEVICES: {"102128202_k40": True},
            CONF_REFRESH: "mock_refresh",
            "token": "mock_token",
            "username": "test-user",
            "code": "valid_code",
        },
    )


def _make_k40_data():
    """Create a minimal BHCDeviceK40."""
    fields = BHCDeviceK40.__dataclass_fields__
    kwargs = {
        "device": "102128202",
        "firmware": [],
        "notifications": [],
        "holiday_mode": {},
        "away_mode": {},
        "power_limitation": {},
        "outdoor_temp": {},
        "heat_sources": {},
        "dhw_circuits": {},
        "heating_circuits": {},
        "ventilation": {},
        "zones": {},
        "flame_indication": {},
        "energy_history": {},
        "indoor_humidity": {},
        "devices": {},
    }
    for optional in ("hourly_energy_history", "energy_gas_unit"):
        if optional in fields:
            kwargs[optional] = {}
    return BHCDeviceK40(**kwargs)


SAMPLE_EXTRA_DATA = {
    "additional_heater": {
        "id": "/heatSources/additionalHeater/operationMode",
        "type": "stringValue",
        "writeable": 1,
        "value": "auto",
        "allowedValues": ["off", "manual", "auto"],
    },
    "silent_mode": {
        "id": "/system/silentMode/enabled",
        "type": "stringValue",
        "writeable": 1,
        "value": "off",
        "allowedValues": ["off", "auto", "on"],
    },
    "dhw_charge": {
        "id": "/dhwCircuits/dhw1/charge",
        "type": "stringValue",
        "writeable": 1,
        "value": "stop",
        "allowedValues": ["start", "stop"],
    },
    "dhw_charge_duration": {
        "id": "/dhwCircuits/dhw1/chargeDuration",
        "type": "floatValue",
        "writeable": 1,
        "value": 60.0,
        "unitOfMeasure": "mins",
        "minValue": 60.0,
        "maxValue": 2880.0,
    },
    "heat_demand": {
        "id": "/heatSources/actualHeatDemand",
        "type": "arrayData",
        "writeable": 0,
        "allowedValues": ["", "ch", "dhw", "frost"],
        "values": ["dhw"],
    },
    "modulation": {
        "id": "/heatSources/actualModulation",
        "type": "floatValue",
        "writeable": 0,
        "value": 45.0,
        "unitOfMeasure": "%",
    },
    "supply_temp": {
        "id": "/heatSources/actualSupplyTemperature",
        "type": "floatValue",
        "writeable": 0,
        "value": 41.8,
        "unitOfMeasure": "C",
    },
    "return_temp": {
        "id": "/heatSources/returnTemperature",
        "type": "floatValue",
        "writeable": 0,
        "value": 40.0,
        "unitOfMeasure": "C",
    },
    "system_pressure": {
        "id": "/heatSources/systemPressure",
        "type": "floatValue",
        "writeable": 0,
        "value": 1.8,
        "unitOfMeasure": "bar",
    },
    "working_time": {
        "id": "/heatSources/workingTime/totalSystem",
        "type": "floatValue",
        "writeable": 0,
        "value": 6677759.0,
        "unitOfMeasure": "s",
    },
    "number_of_starts": {
        "id": "/heatSources/hs1/numberOfStarts",
        "type": "emonValue",
        "writeable": 0,
        "values": [{"ch": 149.0}, {"dhw": 47.0}, {"cooling": 0.0}, {"total": 196.0}],
    },
}


SAMPLE_HEAT_SOURCES = {
    "actualModulation": {"value": 45.0, "unitOfMeasure": "%"},
    "actualSupplyTemperature": {"value": 41.8, "unitOfMeasure": "C"},
    "returnTemperature": {"value": 40.0, "unitOfMeasure": "C"},
    "systemPressure": {"value": 1.8, "unitOfMeasure": "bar"},
    "totalWorkingTime": {"value": 6677759.0, "unitOfMeasure": "s"},
    "actualHeatDemand": {
        "allowedValues": ["", "ch", "dhw", "frost"],
        "values": ["dhw"],
    },
    "starts": {
        "values": [{"ch": 149.0}, {"dhw": 47.0}, {"cooling": 0.0}, {"total": 196.0}],
    },
}


def _mock_coordinator(extra_data=None, heat_sources=None):
    """Create a mock K40 coordinator with heat_sources and extra_data."""

    class _Data:
        def __init__(self, hs, dhw):
            self.heat_sources = hs
            self.device = {"deviceId": "102128202", "deviceType": "k40"}
            self.dhw_circuits = dhw

    coordinator = MagicMock()
    coordinator.unique_id = "102128202"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "102128202")}}
    coordinator.extra_data = extra_data if extra_data is not None else SAMPLE_EXTRA_DATA
    coordinator.data = _Data(
        hs=heat_sources if heat_sources is not None else SAMPLE_HEAT_SOURCES,
        dhw=[{"id": "/dhwCircuits/dhw1", "chargeDuration": {"value": 60.0}}],
    )
    coordinator.bhc = MagicMock()
    coordinator.bhc.async_set_dhw_charge = AsyncMock()
    coordinator.bhc.async_set_dhw_charge_duration = AsyncMock()
    coordinator.bhc.async_put_additional_heater_mode = AsyncMock()
    coordinator.bhc.async_put_silent_mode = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


# ===================================================================
# Coordinator tests
# ===================================================================


@pytest.mark.asyncio
async def test_k40_coordinator_fetches_extra_endpoints(hass, entry, device, firmware):
    """K40 coordinator fetches all extra endpoints via public library getters."""
    entry.add_to_hass(hass)
    bhc = MagicMock()
    bhc.get_token = AsyncMock()
    bhc.async_update = AsyncMock(return_value=_make_k40_data())
    bhc.async_get_additional_heater_mode = AsyncMock(return_value={"value": "auto"})
    bhc.async_get_silent_mode = AsyncMock(return_value={"value": "off"})
    bhc.async_get_dhw_charge_duration = AsyncMock(return_value={"value": 60.0})

    coordinator = BoschComModuleCoordinatorK40(
        hass, bhc, device, firmware, entry, auth_provider=False
    )
    await coordinator._async_update_data()

    bhc.async_get_additional_heater_mode.assert_awaited_once()
    bhc.async_get_silent_mode.assert_awaited_once()
    bhc.async_get_dhw_charge_duration.assert_awaited_once()
    for key in BoschComModuleCoordinatorK40.EXTRA_KEYS:
        assert coordinator.extra_data.get(key) is not None


@pytest.mark.asyncio
async def test_k40_coordinator_extra_endpoint_failure_graceful(
    hass, entry, device, firmware
):
    """A failing endpoint doesn't crash the update; its value becomes None."""
    from homecom_alt import ApiError

    entry.add_to_hass(hass)
    bhc = MagicMock()
    bhc.get_token = AsyncMock()
    bhc.async_update = AsyncMock(return_value=_make_k40_data())
    bhc.async_get_additional_heater_mode = AsyncMock(side_effect=ApiError("boom"))
    bhc.async_get_silent_mode = AsyncMock(side_effect=ApiError("boom"))
    bhc.async_get_dhw_charge_duration = AsyncMock(side_effect=ApiError("boom"))

    coordinator = BoschComModuleCoordinatorK40(
        hass, bhc, device, firmware, entry, auth_provider=False
    )
    data = await coordinator._async_update_data()

    assert data is not None
    for key in BoschComModuleCoordinatorK40.EXTRA_KEYS:
        assert coordinator.extra_data[key] is None


@pytest.mark.asyncio
async def test_icom_coordinator_shares_extra_endpoints(hass, entry, firmware):
    """ICOM coordinator shares the extra-endpoint mixin, so ICOM is supported."""
    entry.add_to_hass(hass)
    icom_device = {"deviceId": "102128202", "deviceType": "icom"}
    bhc = MagicMock()
    bhc.get_token = AsyncMock()
    bhc.async_get_additional_heater_mode = AsyncMock(
        return_value={"value": "auto", "allowedValues": ["off", "auto"]}
    )
    bhc.async_get_silent_mode = AsyncMock(return_value={"value": "off"})
    bhc.async_get_dhw_charge_duration = AsyncMock(return_value={"value": 60.0})

    coordinator = BoschComModuleCoordinatorIcom(
        hass, bhc, icom_device, firmware, entry, auth_provider=False
    )
    assert hasattr(coordinator, "extra_data")
    await coordinator._fetch_extra_endpoints()

    for key in BoschComModuleCoordinatorIcom.EXTRA_KEYS:
        assert coordinator.extra_data.get(key) is not None


# ===================================================================
# Sensor entity tests
# ===================================================================


def test_float_sensor_value():
    """Test BoschComK40ExtraSensor returns correct value."""
    coordinator = _mock_coordinator()
    sensor = BoschComK40ExtraSensor(
        coordinator,
        "actualModulation",
        "compressor_modulation",
        "compressor_modulation",
    )
    assert sensor.native_value == 45.0


def test_float_sensor_none_when_no_data():
    """Test BoschComK40ExtraSensor returns None when no data."""
    coordinator = _mock_coordinator(heat_sources={"actualModulation": None})
    sensor = BoschComK40ExtraSensor(
        coordinator,
        "actualModulation",
        "compressor_modulation",
        "compressor_modulation",
    )
    assert sensor.native_value is None


def test_heat_demand_sensor_active():
    """Test heat demand sensor shows active demand."""
    coordinator = _mock_coordinator()
    sensor = BoschComK40HeatDemandSensor(coordinator)
    assert sensor.native_value == "dhw"


def test_heat_demand_sensor_idle():
    """Test heat demand sensor shows idle when no demand."""
    hs = dict(SAMPLE_HEAT_SOURCES)
    hs["actualHeatDemand"] = {"values": [""]}
    coordinator = _mock_coordinator(heat_sources=hs)
    sensor = BoschComK40HeatDemandSensor(coordinator)
    assert sensor.native_value == "idle"


def test_start_counts_sensor():
    """Test start counts sensor returns total."""
    coordinator = _mock_coordinator()
    sensor = BoschComK40StartCountsSensor(coordinator)
    assert sensor.native_value == 196.0


def test_start_counts_attributes():
    """Test start counts sensor has per-domain attributes."""
    coordinator = _mock_coordinator()
    sensor = BoschComK40StartCountsSensor(coordinator)
    attrs = sensor.extra_state_attributes
    assert attrs["ch"] == 149.0
    assert attrs["dhw"] == 47.0
    assert attrs["total"] == 196.0


# ===================================================================
# Select entity tests
# ===================================================================


def test_extra_select_current_option():
    """Test BoschComK40ExtraSelect returns current value."""
    coordinator = _mock_coordinator()
    select = BoschComK40ExtraSelect(
        coordinator,
        "silent_mode",
        "silent_mode",
        "silent_mode",
        ["off", "auto", "on"],
        "async_put_silent_mode",
    )
    assert select.current_option == "off"


@pytest.mark.asyncio
async def test_extra_select_set_option():
    """BoschComK40ExtraSelect writes via the public library setter."""
    coordinator = _mock_coordinator()
    select = BoschComK40ExtraSelect(
        coordinator,
        "silent_mode",
        "silent_mode",
        "silent_mode",
        ["off", "auto", "on"],
        "async_put_silent_mode",
    )
    await select.async_select_option("on")

    coordinator.bhc.async_put_silent_mode.assert_awaited_once_with("102128202", "on")
    coordinator.async_request_refresh.assert_awaited_once()


# ===================================================================
# Button entity tests
# ===================================================================


@pytest.mark.asyncio
async def test_dhw_charge_button_press():
    """Test DHW charge button sends start command."""
    coordinator = _mock_coordinator()
    button = BoschComK40DhwChargeButton(coordinator)
    await button.async_press()

    coordinator.bhc.async_set_dhw_charge.assert_awaited_once_with(
        "102128202", "dhw1", "start"
    )
    coordinator.async_request_refresh.assert_awaited_once()


# ===================================================================
# Number entity tests
# ===================================================================


def test_dhw_charge_duration_value():
    """Test DHW charge duration number returns correct value."""
    coordinator = _mock_coordinator()
    number = BoschComK40DhwChargeDurationNumber(coordinator)
    assert number.native_value == 60.0


@pytest.mark.asyncio
async def test_dhw_charge_duration_set_value():
    """Test DHW charge duration number sets value via library method."""
    coordinator = _mock_coordinator()
    number = BoschComK40DhwChargeDurationNumber(coordinator)
    await number.async_set_native_value(120.0)

    coordinator.bhc.async_set_dhw_charge_duration.assert_awaited_once_with(
        "102128202", "dhw1", "120"
    )
    coordinator.async_request_refresh.assert_awaited_once()


def test_dhw_charge_duration_limits():
    """Test DHW charge duration has correct min/max."""
    coordinator = _mock_coordinator()
    number = BoschComK40DhwChargeDurationNumber(coordinator)
    assert number._attr_native_min_value == 60
    assert number._attr_native_max_value == 2880
