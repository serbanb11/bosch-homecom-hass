"""Test climate platform."""

from unittest.mock import AsyncMock, MagicMock

from homecom_alt import BHCDeviceK40

from custom_components.bosch_homecom.climate import BoschComK40Climate


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


async def test_set_temperature_no_temperature_is_noop():
    """Calling without a temperature does nothing."""
    coordinator = _make_k40_coordinator(suwi="cooling", heatcool="cooling")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature()

    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_not_awaited()
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()
    coordinator.async_request_refresh.assert_not_awaited()
