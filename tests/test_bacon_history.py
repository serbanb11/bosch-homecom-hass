"""Bacon AC energy totals and extended readings from the history service (#202)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONF_TOKEN, CONF_USERNAME
from homeassistant.util import dt as dt_util
from homecom_alt import ApiError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom.const import (
    BACON_HISTORY_INTERVAL,
    CONF_BACON_REGION,
    CONF_DEVICES,
    CONF_REFRESH,
    DOMAIN,
)
from custom_components.bosch_homecom.coordinator import (
    BoschComModuleCoordinatorBaconRac,
)
from custom_components.bosch_homecom.sensor import (
    BACON_HISTORY_SENSORS,
    BoschComBaconHistorySensor,
    _add_or_defer,
    _add_pending_sensors_later,
    _bacon_history_sensor_candidate,
)

_FETCH = "custom_components.bosch_homecom.coordinator.async_get_rac_history"
_TRACKER = "custom_components.bosch_homecom.coordinator.async_track_point_in_utc_time"

EMON = {
    "timestamp": 1763251200,
    "totalElectricalEnergyConsumptionHeat": 12.5,
    "totalElectricalEnergyConsumptionCool": 71.4,
    "totalElectricalEnergyConsumptionDry": 0.3,
    "totalElectricalEnergyConsumptionFan": 0.1,
    "totalThermalEnergyOutputHeat": 40.2,
    "totalThermalEnergyOutputCool": 387.4,
}
EXTENDED = {
    "timestamp": 1763291800,
    "currentRealTimePower": 515.0,
    "outdoorTemp": 6.5,
    "compFreq": 42,
}
HISTORY = {"emon": EMON, "extended": EXTENDED}


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        unique_id="test-user",
        data={
            CONF_DEVICES: {"86DM-1_bacon_rac": True},
            CONF_REFRESH: "entry_refresh",
            CONF_TOKEN: "entry_token",
            CONF_USERNAME: "test-user",
        },
    )
    entry.add_to_hass(hass)
    return entry


def _coordinator(hass, entry, device_type="bacon_rac", token="owner_token"):
    client = Mock()
    client.is_connected = True
    client.token_expires_at = dt_util.utcnow() + timedelta(minutes=60)
    token_manager = Mock()
    token_manager.token = token
    token_manager.refresh_token = "owner_refresh"
    token_manager.get_token = AsyncMock(return_value=None)
    coordinator = BoschComModuleCoordinatorBaconRac(
        hass,
        Mock(),
        {"deviceId": "86DM-1", "deviceType": device_type},
        {"value": "1.0.0"},
        entry,
        client,
        token_manager,
        asyncio.Lock(),
        True,
    )
    coordinator.bhc.async_update = AsyncMock(
        return_value={"reported": {"powerEnabled": True}, "desired": {}}
    )
    return coordinator


async def _update(hass, coordinator):
    """One poll, the way the coordinator runs it, plus its background read."""
    with patch(_TRACKER, return_value=Mock()):
        coordinator.data = await coordinator._async_update_data()
    await hass.async_block_till_done()


async def test_history_is_read_in_the_background_and_lands_in_the_data(hass, entry):
    coordinator = _coordinator(hass, entry)
    with patch(_FETCH, AsyncMock(return_value=HISTORY)) as fetch:
        await _update(hass, coordinator)

    assert coordinator.data.history == HISTORY
    # The token the MQTT session and the heartbeat use; never a refresh.
    _, token, serial, region = fetch.call_args.args
    assert (token, serial, region) == ("owner_token", "86DM-1", "euc1")
    coordinator.token_manager.get_token.assert_not_called()


async def test_history_uses_the_entry_region(hass, entry):
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_BACON_REGION: "use1"}
    )
    coordinator = _coordinator(hass, entry)
    with patch(_FETCH, AsyncMock(return_value=HISTORY)) as fetch:
        await _update(hass, coordinator)

    assert fetch.call_args.args[3] == "use1"


async def test_history_falls_back_to_the_entry_token(hass, entry):
    coordinator = _coordinator(hass, entry, token=None)
    with patch(_FETCH, AsyncMock(return_value=HISTORY)) as fetch:
        await _update(hass, coordinator)

    assert fetch.call_args.args[1] == "entry_token"


async def test_history_is_read_once_per_interval(hass, entry):
    coordinator = _coordinator(hass, entry)
    start = dt_util.utcnow()
    with patch(_FETCH, AsyncMock(return_value=HISTORY)) as fetch:
        with patch("homeassistant.util.dt.utcnow", return_value=start):
            await _update(hass, coordinator)
            await _update(hass, coordinator)
        assert fetch.call_count == 1

        later = start + BACON_HISTORY_INTERVAL + timedelta(seconds=1)
        with patch("homeassistant.util.dt.utcnow", return_value=later):
            await _update(hass, coordinator)
        assert fetch.call_count == 2


async def test_a_failed_read_keeps_the_last_answer_and_never_reauths(hass, entry):
    coordinator = _coordinator(hass, entry)
    start = dt_util.utcnow()
    with patch(_FETCH, AsyncMock(return_value=HISTORY)):
        with patch("homeassistant.util.dt.utcnow", return_value=start):
            await _update(hass, coordinator)

    later = start + BACON_HISTORY_INTERVAL + timedelta(seconds=1)
    with (
        patch(_FETCH, AsyncMock(side_effect=ApiError("Bacon history: 401"))),
        patch("homeassistant.util.dt.utcnow", return_value=later),
        patch.object(entry, "async_start_reauth") as reauth,
    ):
        await _update(hass, coordinator)

    assert coordinator.data.history == HISTORY
    reauth.assert_not_called()


async def test_the_poll_does_not_wait_for_the_history_read(hass, entry):
    coordinator = _coordinator(hass, entry)
    release = asyncio.Event()

    async def slow_fetch(*args):
        await release.wait()
        return HISTORY

    with patch(_FETCH, side_effect=slow_fetch), patch(_TRACKER, return_value=Mock()):
        coordinator.data = await coordinator._async_update_data()
        assert coordinator.data.history is None
        release.set()
        await hass.async_block_till_done()

    assert coordinator.data.history == HISTORY


async def test_an_air_purifier_never_reads_history(hass, entry):
    coordinator = _coordinator(hass, entry, device_type="bacon_ap")
    with patch(_FETCH, AsyncMock(return_value=HISTORY)) as fetch:
        await _update(hass, coordinator)

    fetch.assert_not_called()
    assert coordinator.data.history is None


# --- Sensors -------------------------------------------------------------


def _sensor_coordinator(history):
    coordinator = Mock()
    coordinator.unique_id = "86DM-1"
    coordinator.device_info = {"identifiers": {(DOMAIN, "86DM-1")}}
    coordinator.data = Mock(history=history)
    listeners = []
    coordinator.listeners = listeners
    coordinator.async_add_listener = lambda listener: (
        listeners.append(listener) or (lambda: None)
    )
    return coordinator


def _build(coordinator):
    entities, pending = [], []
    for description in BACON_HISTORY_SENSORS:
        _add_or_defer(
            _bacon_history_sensor_candidate(coordinator, Mock(), description),
            entities,
            pending,
        )
    return {entity.unique_id: entity for entity in entities}, pending


def test_energy_totals_are_total_increasing_kwh():
    entities, pending = _build(_sensor_coordinator(HISTORY))

    assert pending == []
    cool = entities["86DM-1-energy-consumption-cool"]
    assert isinstance(cool, BoschComBaconHistorySensor)
    assert cool.native_value == 71.4
    assert cool.device_class == SensorDeviceClass.ENERGY
    assert cool.state_class == SensorStateClass.TOTAL_INCREASING
    assert cool.native_unit_of_measurement == "kWh"
    assert cool.extra_state_attributes == {}
    assert entities["86DM-1-thermal-energy-cool"].native_value == 387.4


def test_extended_readings_carry_their_time():
    entities, _ = _build(_sensor_coordinator(HISTORY))

    power = entities["86DM-1-power"]
    assert power.native_value == 515.0
    assert power.device_class == SensorDeviceClass.POWER
    assert power.native_unit_of_measurement == "W"
    assert power.extra_state_attributes == {"measured_at": "2025-11-16T11:16:40+00:00"}
    assert entities["86DM-1-outdoor-temperature"].native_value == 6.5
    assert entities["86DM-1-compressor-frequency"].native_value == 42


@pytest.mark.parametrize(
    "history",
    [None, {"emon": None, "extended": None}, {"emon": {}, "extended": {}}],
)
def test_no_sensor_until_the_service_serves_the_field(history):
    entities, pending = _build(_sensor_coordinator(history))

    assert entities == {}
    assert len(pending) == len(BACON_HISTORY_SENSORS)


def test_sensors_are_added_when_the_history_arrives():
    coordinator = _sensor_coordinator(None)
    _, pending = _build(coordinator)
    added = []
    _add_pending_sensors_later(coordinator, Mock(), pending, added.extend)

    coordinator.data = Mock(history={"emon": EMON, "extended": None})
    for listener in coordinator.listeners:
        listener()
    assert len(added) == 6

    coordinator.data = Mock(history=HISTORY)
    for listener in coordinator.listeners:
        listener()
    assert len(added) == len(BACON_HISTORY_SENSORS)


def test_a_stale_extended_row_goes_unknown_but_totals_stay():
    coordinator = _sensor_coordinator(HISTORY)
    entities, _ = _build(coordinator)

    coordinator.data = Mock(history={"emon": EMON, "extended": None})

    assert entities["86DM-1-power"].native_value is None
    assert entities["86DM-1-power"].extra_state_attributes == {}
    assert entities["86DM-1-energy-consumption-heat"].native_value == 12.5


async def test_a_failed_read_logs_a_masked_serial(hass, entry, caplog):
    caplog.set_level("DEBUG", logger="custom_components.bosch_homecom")
    coordinator = _coordinator(hass, entry)
    with patch(_FETCH, AsyncMock(side_effect=ApiError("Bacon history: 500"))):
        await _update(hass, coordinator)

    assert "86DM***, bacon history read failed" in caplog.text
    assert "86DM-1" not in caplog.text
