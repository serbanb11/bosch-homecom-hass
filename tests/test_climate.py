"""Test climate platform."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.climate import ClimateEntityFeature
from homecom_alt import BHCDeviceIcom, BHCDeviceK40, BHCDeviceRac

from custom_components.bosch_homecom.climate import (
    BoschComK40Climate,
    BoschComRacClimate,
)
from custom_components.bosch_homecom.coordinator import BoschComModuleCoordinatorIcom


def _rac_ref(name: str, value: str) -> dict:
    """Build a RAC standard-function reference, e.g. airFlowHorizontal=swing."""
    return {"id": f"/airConditioning/{name}", "value": value}


def _make_rac_coordinator(standard_functions):
    """Create a mock RAC coordinator with the given standard functions."""
    coordinator = MagicMock()
    coordinator.unique_id = "rac329"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "rac329")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.device = {"deviceId": "rac329", "deviceType": "rac"}
    coordinator.data = BHCDeviceRac(
        device="rac329",
        firmware=[],
        notifications=[],
        stardard_functions=standard_functions,
        advanced_functions=[],
        switch_programs=[],
    )
    return coordinator


# A unit that reports fan speed and both airflow louvers.
_FULL_RAC_FUNCTIONS = [
    _rac_ref("operationMode", "cool"),
    _rac_ref("fanSpeed", "auto"),
    _rac_ref("airFlowHorizontal", "swing"),
    _rac_ref("airFlowVertical", "off"),
    _rac_ref("temperatureSetpoint", "21"),
    _rac_ref("roomTemperature", "22"),
]


def test_rac_without_horizontal_airflow_does_not_crash():
    """A unit with no airFlowHorizontal renders without AttributeError (#167)."""
    functions = [
        ref for ref in _FULL_RAC_FUNCTIONS if "airFlowHorizontal" not in ref["id"]
    ]
    climate = BoschComRacClimate(
        coordinator=_make_rac_coordinator(functions), field="clima"
    )

    # The value the failing state write used to read is now a safe default.
    assert climate.swing_horizontal_mode is None
    # And the horizontal axis is not advertised, so HA never reads it.
    assert ClimateEntityFeature.SWING_HORIZONTAL_MODE not in climate.supported_features
    assert ClimateEntityFeature.SWING_MODE in climate.supported_features


def test_rac_with_both_airflows_advertises_both_axes():
    """A fully-featured unit keeps both swing axes and their values."""
    climate = BoschComRacClimate(
        coordinator=_make_rac_coordinator(list(_FULL_RAC_FUNCTIONS)), field="clima"
    )
    features = climate.supported_features
    assert ClimateEntityFeature.SWING_HORIZONTAL_MODE in features
    assert ClimateEntityFeature.SWING_MODE in features
    assert ClimateEntityFeature.FAN_MODE in features
    assert climate.swing_horizontal_mode == "on"
    assert climate.swing_mode == "off"


def test_rac_without_vertical_or_fan_gates_those_features():
    """Vertical swing and fan mode are gated the same way (sibling of #167)."""
    functions = [
        ref
        for ref in _FULL_RAC_FUNCTIONS
        if not any(k in ref["id"] for k in ("airFlowVertical", "fanSpeed"))
    ]
    climate = BoschComRacClimate(
        coordinator=_make_rac_coordinator(functions), field="clima"
    )
    features = climate.supported_features
    assert ClimateEntityFeature.SWING_MODE not in features
    assert ClimateEntityFeature.FAN_MODE not in features
    assert climate.swing_mode is None
    assert climate.fan_mode is None


def _make_k40_coordinator(suwi=None, heatcool=None):
    """Create a mock K40 coordinator with a single hc1 circuit."""
    hc1 = {
        "id": "/heatingCircuits/hc1",
        "operationMode": {"value": "auto"},
        "currentSuWiMode": {"value": suwi},
        "heatCoolMode": {"value": heatcool},
        "currentRoomSetpoint": {"value": 21, "unitOfMeasure": "C"},
    }
    coordinator = MagicMock()
    coordinator.unique_id = "k40123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "k40123")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.device = {"deviceId": "k40123", "deviceType": "k40"}
    coordinator.data = BHCDeviceK40(
        device="k40123",
        firmware=[],
        notifications=[],
        holiday_mode=None,
        away_mode=None,
        power_limitation=None,
        outdoor_temp=None,
        heat_sources=None,
        dhw_circuits=None,
        heating_circuits=[hc1],
        ventilation=None,
        zones=None,
        flame_indication=None,
        energy_history=None,
        hourly_energy_history=None,
        indoor_humidity=None,
        devices=None,
    )
    return coordinator


def _make_icom_coordinator(suwi=None):
    """Create a mock icom coordinator with a single hc1 circuit.

    Built on the real class (not MagicMock) so the isinstance check in
    async_set_temperature and the real async_set_temporary_room_setpoint
    delegation are exercised. Icom data has no heatCoolMode field.
    """
    hc1 = {
        "id": "/heatingCircuits/hc1",
        "operationMode": {"value": "auto"},
        "currentSuWiMode": {"value": suwi},
        "currentRoomSetpoint": {"value": 21, "unitOfMeasure": "C"},
    }
    coordinator = object.__new__(BoschComModuleCoordinatorIcom)
    coordinator.unique_id = "icom123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "icom123")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.device = {"deviceId": "icom123", "deviceType": "icom"}
    coordinator.data = BHCDeviceIcom(
        device="icom123",
        firmware=[],
        notifications=[],
        holiday_mode=None,
        heat_sources=None,
        dhw_circuits=None,
        heating_circuits=[hc1],
        solar_circuits=None,
        ventilation=None,
        system_info=None,
        system_bus=None,
    )
    return coordinator


def _make_climate(coordinator):
    """Build the climate entity, stubbing HA state writes."""
    climate = BoschComK40Climate(coordinator=coordinator, field="hc1")
    climate.async_write_ha_state = MagicMock()
    return climate


async def test_set_temperature_heating_uses_manual_setpoint():
    """In heating mode the manual room setpoint endpoint is used."""
    coordinator = _make_k40_coordinator(suwi="forced", heatcool="heating")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=21)

    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_awaited_once_with(
        "k40123", "hc1", 21
    )
    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_not_awaited()
    assert climate._attr_target_temperature == 21
    coordinator.async_request_refresh.assert_awaited_once()


async def test_set_temperature_cooling_uses_cooling_setpoint():
    """In cooling mode the cooling room temp setpoint endpoint is used."""
    coordinator = _make_k40_coordinator(suwi="cooling", heatcool="cooling")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=23)

    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_awaited_once_with(
        "k40123", "hc1", 23
    )
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()
    assert climate._attr_target_temperature == 23
    coordinator.async_request_refresh.assert_awaited_once()


async def test_set_temperature_cooling_season_while_idle():
    """Cooling configured but compressor idle still writes cooling setpoint."""
    coordinator = _make_k40_coordinator(suwi="off", heatcool="cooling")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=22)

    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_awaited_once_with(
        "k40123", "hc1", 22
    )
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()


async def test_set_temperature_icom_cooling_uses_cooling_setpoint():
    """Icom in cooling mode writes coolingRoomTempSetpoint, not temporary.

    Regression test for the branch order fixed in #173: the icom-specific
    temporaryRoomSetpoint path must not shadow the cooling path (404s).
    """
    coordinator = _make_icom_coordinator(suwi="cooling")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=24)

    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_awaited_once_with(
        "icom123", "hc1", 24
    )
    coordinator.bhc.async_set_hc_temporary_room_setpoint.assert_not_awaited()
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()
    assert climate._attr_target_temperature == 24
    coordinator.async_request_refresh.assert_awaited_once()


async def test_set_temperature_icom_heating_uses_temporary_setpoint():
    """Icom in heating mode still uses the temporaryRoomSetpoint path."""
    coordinator = _make_icom_coordinator(suwi="forced")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=21)

    coordinator.bhc.async_set_hc_temporary_room_setpoint.assert_awaited_once_with(
        "icom123", "hc1", 21
    )
    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_not_awaited()
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()


async def test_set_temperature_no_temperature_is_noop():
    """Calling without a temperature does nothing."""
    coordinator = _make_k40_coordinator(suwi="cooling", heatcool="cooling")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature()

    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_not_awaited()
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()
    coordinator.async_request_refresh.assert_not_awaited()
