import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import CONF_CODE, CONF_TOKEN, CONF_USERNAME
from homeassistant.data_entry_flow import UnknownFlow
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from homecom_alt import (
    ApiError,
    AuthFailedError,
    BHCDeviceBaconRac,
    BHCDeviceCommodule,
    BHCDeviceGeneric,
    BHCDeviceK40,
    BHCDeviceRac,
    BHCDeviceWddw2,
    InvalidSensorDataError,
    MqttNotAuthorizedError,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from tenacity import RetryError

from custom_components.bosch_homecom.const import (
    CONF_BACON_TITLES,
    CONF_DEVICES,
    CONF_REFRESH,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MANUFACTURER,
)
from custom_components.bosch_homecom.coordinator import (
    BACON_RECONNECT_MARGIN,
    BACON_RECONNECT_MIN_DELAY,
    BoschComModuleCoordinatorBaconRac,
    BoschComModuleCoordinatorCommodule,
    BoschComModuleCoordinatorGeneric,
    BoschComModuleCoordinatorK40,
    BoschComModuleCoordinatorRac,
    BoschComModuleCoordinatorWddw2,
)

"""Tests for the BoschComModuleCoordinator."""


@pytest.fixture
def bhc():
    """Fixture for HomeComAlt instance."""
    return Mock()


@pytest.fixture
def device():
    """Fixture for device data."""
    return {"deviceId": "12345", "deviceType": "Thermostat"}


@pytest.fixture
def firmware():
    """Fixture for firmware data."""
    return {"value": "1.0.0"}


@pytest.fixture
def entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        unique_id="test-user",
        data={
            "123_rac": True,
            CONF_DEVICES: {"123_rac": True},
            CONF_REFRESH: "mock_refresh",
            CONF_TOKEN: "mock_token",
            CONF_USERNAME: "test-user",
            CONF_CODE: "valid_code",
        },
    )


def _make_rac_data(device, firmware):
    """Create a BHCDeviceRac for test assertions."""
    return BHCDeviceRac(
        device=device,
        firmware=firmware,
        notifications=[],
        stardard_functions=[],
        advanced_functions=[],
        switch_programs=[],
    )


def _make_k40_data(device, firmware):
    """Create a BHCDeviceK40 compatible with any homecom_alt version."""
    fields = BHCDeviceK40.__dataclass_fields__
    kwargs = {
        "device": device,
        "firmware": firmware,
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
    # Optional fields added in newer homecom_alt versions
    for optional in ("hourly_energy_history", "energy_gas_unit", "pool"):
        if optional in fields:
            kwargs[optional] = {}
    return BHCDeviceK40(**kwargs)


def _make_wddw2_data(device, firmware):
    """Create a BHCDeviceWddw2 for test assertions."""
    return BHCDeviceWddw2(
        device=device,
        firmware=firmware,
        notifications=[],
        dhw_circuits={},
    )


def _make_commodule_data(device, firmware):
    """Create a BHCDeviceCommodule compatible with any homecom_alt version."""
    fields = BHCDeviceCommodule.__dataclass_fields__
    kwargs = {
        "device": device,
        "firmware": firmware,
        "notifications": [],
        "charge_points": {},
        "eth0_state": {},
    }
    if "wifi_state" in fields:
        kwargs["wifi_state"] = {}
    return BHCDeviceCommodule(**kwargs)


def _make_generic_data(device, firmware):
    """Create a BHCDeviceGeneric for test assertions."""
    return BHCDeviceGeneric(
        device=device,
        firmware=firmware,
        notifications=[],
    )


# ===================================================================
# Existing unit tests
# ===================================================================


def _make_bacon_client(expires_in=timedelta(minutes=60), connected=False):
    """Mock BaconMqttClient with a predictable session expiry."""
    client = Mock()
    client.is_connected = connected
    client.token_expires_at = (
        None if expires_in is None else dt_util.utcnow() + expires_in
    )
    client.async_connect = AsyncMock()
    return client


def _make_token_manager(token="fresh_token", refresh="fresh_refresh"):
    """Mock HomeComAlt token owner."""
    token_manager = Mock()
    token_manager.token = token
    token_manager.refresh_token = refresh
    token_manager.get_token = AsyncMock(return_value=None)
    return token_manager


def _make_bacon_coordinator(
    hass,
    entry,
    firmware,
    *,
    client=None,
    token_manager=None,
    lock=None,
    auth_provider=False,
):
    """Construct a bacon coordinator with mocked transport dependencies."""
    return BoschComModuleCoordinatorBaconRac(
        hass,
        Mock(),  # bhc (HomeComBaconRac)
        {"deviceId": "86DM-1", "deviceType": "bacon_rac"},
        firmware,
        entry,
        client if client is not None else _make_bacon_client(),
        token_manager if token_manager is not None else _make_token_manager(),
        lock if lock is not None else asyncio.Lock(),
        auth_provider,
    )


def test_bacon_coordinator_seeds_name_from_persisted_title(hass, entry, firmware):
    """A reload seeds device_info name from the persisted title, not the fallback."""
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_BACON_TITLES: {"86DM-1": "Living Room AC"}}
    )

    coordinator = _make_bacon_coordinator(hass, entry, firmware)

    assert coordinator.device_info["name"] == "Living Room AC"


def test_bacon_coordinator_falls_back_when_no_persisted_title(hass, entry, firmware):
    """With no persisted title the name is the Boschcom_ fallback."""
    entry.add_to_hass(hass)

    coordinator = _make_bacon_coordinator(hass, entry, firmware)

    assert coordinator.device_info["name"] == "Boschcom_bacon_rac_86DM-1"


def test_bacon_coordinator_persists_title_from_shadow(hass, entry, firmware):
    """A customTitle in the shadow is cleaned, applied and persisted on the entry."""
    entry.add_to_hass(hass)
    coordinator = _make_bacon_coordinator(hass, entry, firmware)

    coordinator._build({"reported": {"customTitle": "Kitchen%|$?*junk"}})

    assert coordinator.device_info["name"] == "Kitchen"
    assert entry.data[CONF_BACON_TITLES]["86DM-1"] == "Kitchen"


def test_init_coordinator(hass, entry, bhc, device, firmware):
    """Test the initialization of the coordinator."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(
        hass, bhc, device, firmware, entry, False
    )

    assert coordinator.hass == hass
    assert coordinator.bhc == bhc
    assert coordinator.unique_id == device["deviceId"]
    assert coordinator.device == device
    assert coordinator.device_info == DeviceInfo(
        serial_number=device["deviceId"],
        identifiers={(DOMAIN, device["deviceId"])},
        name=f"Boschcom_{device['deviceType']}_{device['deviceId']}",
        sw_version=firmware["value"],
        manufacturer=MANUFACTURER,
    )
    assert coordinator.update_interval == DEFAULT_UPDATE_INTERVAL
    assert coordinator.always_update is True


@pytest.mark.asyncio
async def test_async_update_data_success(hass, entry, bhc, device, firmware):
    """Test successful data update."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(
        hass, bhc, device, firmware, entry, False
    )
    bhc.async_update = AsyncMock(return_value=_make_rac_data(device, firmware))

    data = await coordinator._async_update_data()
    assert data.device == device
    assert data.firmware == {}
    assert data.notifications == []
    assert data.stardard_functions == []
    assert data.advanced_functions == []
    assert data.switch_programs == []


@pytest.mark.asyncio
async def test_async_update_data_api_error(hass, entry, bhc, device, firmware):
    """Test data update with ApiError."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(
        hass, bhc, device, firmware, entry, False
    )
    bhc.async_update = Mock(side_effect=ApiError("error_status"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_async_update_data_invalid_sensor_data_error(
    hass, entry, bhc, device, firmware
):
    """Test data update with InvalidSensorDataError."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(
        hass, bhc, device, firmware, entry, False
    )
    bhc.async_update = Mock(side_effect=InvalidSensorDataError("error_status"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_async_update_data_retry_error(hass, entry, bhc, device, firmware):
    """Test data update with RetryError."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(
        hass, bhc, device, firmware, entry, False
    )
    bhc.async_update = Mock(side_effect=RetryError("error_status"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_async_update_data_auth_failed_error_propagates(
    hass, entry, bhc, device, firmware
):
    """Test async_update AuthFailedError propagates without triggering reauth.

    AuthFailedError from async_update() is transient (race condition, server
    hiccup).  It must NOT trigger reauth — HA's DataUpdateCoordinator treats
    the unhandled exception as a temporary failure and retries next interval.
    """
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(
        hass, bhc, device, firmware, entry, False
    )
    bhc.async_update = AsyncMock(side_effect=AuthFailedError("error_status"))
    entry.async_start_reauth = Mock()

    with pytest.raises(AuthFailedError):
        await coordinator._async_update_data()

    entry.async_start_reauth.assert_not_called()


@pytest.mark.asyncio
async def test_async_update_data_refresh_auth_failed(
    hass, entry, bhc, device, firmware
):
    """Test refresh auth failure starts reauth and stops the update."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(hass, bhc, device, firmware, entry, True)
    bhc.token = "mock_token"
    bhc.refresh_token = "mock_refresh"
    bhc.get_token = AsyncMock(side_effect=AuthFailedError("error_status"))
    bhc.async_update = AsyncMock()
    entry.async_start_reauth = Mock()

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    entry.async_start_reauth.assert_called_once_with(hass)
    bhc.async_update.assert_not_called()


@pytest.mark.asyncio
async def test_async_update_data_persists_rotated_tokens(
    hass, entry, bhc, device, firmware
):
    """Test auth refresh persists changed tokens."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(hass, bhc, device, firmware, entry, True)
    bhc.token = "mock_token"
    bhc.refresh_token = "mock_refresh"

    async def mutate_tokens():
        bhc.token = "new_token"
        bhc.refresh_token = "new_refresh"

    bhc.get_token = AsyncMock(side_effect=mutate_tokens)
    bhc.async_update = AsyncMock(return_value=_make_rac_data(device, firmware))

    assert entry.data[CONF_TOKEN] == "mock_token"
    assert entry.data[CONF_REFRESH] == "mock_refresh"

    await coordinator._async_update_data()

    assert entry.data[CONF_TOKEN] == "new_token"
    assert entry.data[CONF_REFRESH] == "new_refresh"


@pytest.mark.asyncio
async def test_async_update_data_persists_access_token_only_change(
    hass, entry, bhc, device, firmware
):
    """Test persistence when only access token changes (refresh stays same)."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(hass, bhc, device, firmware, entry, True)
    bhc.token = "mock_token"
    bhc.refresh_token = "mock_refresh"

    async def mutate_access_token():
        bhc.token = "new_token"

    bhc.get_token = AsyncMock(side_effect=mutate_access_token)
    bhc.async_update = AsyncMock(return_value=_make_rac_data(device, firmware))

    await coordinator._async_update_data()

    assert entry.data[CONF_TOKEN] == "new_token"
    assert entry.data[CONF_REFRESH] == "mock_refresh"


@pytest.mark.asyncio
async def test_async_update_data_no_persist_when_unchanged(
    hass, entry, bhc, device, firmware
):
    """Test no persistence write when tokens match stored values."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(hass, bhc, device, firmware, entry, True)
    bhc.token = "mock_token"
    bhc.refresh_token = "mock_refresh"
    bhc.get_token = AsyncMock(return_value=None)
    bhc.async_update = AsyncMock(return_value=_make_rac_data(device, firmware))

    with patch(
        "custom_components.bosch_homecom.coordinator."
        "BoschComModuleCoordinatorBase._async_update_data",
        wraps=coordinator._async_update_data,
    ):
        await coordinator._async_update_data()

    # Tokens unchanged, so entry data should still be the original
    assert entry.data[CONF_TOKEN] == "mock_token"
    assert entry.data[CONF_REFRESH] == "mock_refresh"


# ===================================================================
# Regression tests for issue #112: AuthFailedError from async_update()
#
# In v1.3.31 AuthFailedError from async_update() was NOT caught —
# it propagated to DataUpdateCoordinator which treated it as a
# transient failure (retry next interval, self-healing).
#
# Commit 6ebfa8f (v1.3.32) added an `except AuthFailedError` block
# that converted these into hard reauth requirements.  The fix
# removes that block, restoring v1.3.31 behaviour.
#
# These tests verify the FIXED behaviour: AuthFailedError from
# async_update() propagates without triggering reauth.
# ===================================================================


# --- Path 2a: non-auth-provider, transient 401 from async_update ------
# Multi-device setups: only the first coordinator refreshes tokens.
# If a non-auth-provider polls while the shared token is momentarily
# expired, async_update() returns 401.  Must NOT trigger reauth.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "coordinator_cls",
    [
        BoschComModuleCoordinatorRac,
        BoschComModuleCoordinatorK40,
        BoschComModuleCoordinatorWddw2,
        BoschComModuleCoordinatorCommodule,
        BoschComModuleCoordinatorGeneric,
    ],
    ids=["rac", "k40", "wddw2", "commodule", "generic"],
)
async def test_non_auth_provider_transient_401_no_reauth(
    hass, entry, bhc, device, firmware, coordinator_cls
):
    """Non-auth-provider: transient 401 propagates, no reauth triggered."""
    entry.add_to_hass(hass)
    coordinator = coordinator_cls(
        hass, bhc, device, firmware, entry, auth_provider=False
    )
    bhc.async_update = AsyncMock(
        side_effect=AuthFailedError("Authorization has failed")
    )
    entry.async_start_reauth = Mock()

    with pytest.raises(AuthFailedError):
        await coordinator._async_update_data()

    entry.async_start_reauth.assert_not_called()


# --- Path 2b: auth-provider, get_token succeeds, transient 401 --------
# Even the auth-provider can hit a transient 401 during async_update()
# after get_token() succeeds.  Must NOT trigger reauth.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "coordinator_cls",
    [
        BoschComModuleCoordinatorRac,
        BoschComModuleCoordinatorK40,
        BoschComModuleCoordinatorWddw2,
        BoschComModuleCoordinatorCommodule,
        BoschComModuleCoordinatorGeneric,
    ],
    ids=["rac", "k40", "wddw2", "commodule", "generic"],
)
async def test_auth_provider_transient_401_after_successful_get_token_no_reauth(
    hass, entry, bhc, device, firmware, coordinator_cls
):
    """Auth-provider: get_token succeeds but async_update gets 401 — no reauth."""
    entry.add_to_hass(hass)
    coordinator = coordinator_cls(
        hass, bhc, device, firmware, entry, auth_provider=True
    )
    bhc.token = "mock_token"
    bhc.refresh_token = "mock_refresh"
    bhc.get_token = AsyncMock(return_value=None)  # token still valid
    bhc.async_update = AsyncMock(
        side_effect=AuthFailedError("Authorization has failed")
    )
    entry.async_start_reauth = Mock()

    with pytest.raises(AuthFailedError):
        await coordinator._async_update_data()

    entry.async_start_reauth.assert_not_called()


# --- Path 2c: auth-provider, token refreshed then immediately invalid --
# get_token() refreshes the token, but the Bosch API rejects it.
# Tokens should be persisted, but reauth must NOT be triggered.


@pytest.mark.asyncio
async def test_auth_provider_token_refreshed_but_immediately_rejected(
    hass, entry, bhc, device, firmware
):
    """Auth-provider: get_token refreshes, API rejects new token — no reauth."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(
        hass, bhc, device, firmware, entry, auth_provider=True
    )
    bhc.token = "mock_token"
    bhc.refresh_token = "mock_refresh"

    async def refresh_tokens():
        bhc.token = "new_token"
        bhc.refresh_token = "new_refresh"

    bhc.get_token = AsyncMock(side_effect=refresh_tokens)
    bhc.async_update = AsyncMock(
        side_effect=AuthFailedError("Authorization has failed")
    )
    entry.async_start_reauth = Mock()

    with pytest.raises(AuthFailedError):
        await coordinator._async_update_data()

    # Tokens were persisted (refresh succeeded)
    assert entry.data[CONF_TOKEN] == "new_token"
    assert entry.data[CONF_REFRESH] == "new_refresh"
    # No reauth — the 401 is transient, next poll will retry
    entry.async_start_reauth.assert_not_called()


# --- Multi-device race condition simulation ----------------------------
# Two coordinators share one config entry.  The auth-provider's
# get_token() takes time.  The non-auth-provider fires async_update()
# with the stale token before the auth-provider finishes refreshing.
# Must NOT trigger reauth.


@pytest.mark.asyncio
async def test_multi_device_race_non_auth_provider_hits_401_before_refresh(
    hass, entry, firmware
):
    """Simulate multi-device race: non-auth 401 does not trigger reauth."""
    entry.add_to_hass(hass)

    device_1 = {"deviceId": "auth-device", "deviceType": "rac"}
    device_2 = {"deviceId": "secondary-device", "deviceType": "rac"}

    bhc_auth = Mock()
    bhc_secondary = Mock()

    coordinator_auth = BoschComModuleCoordinatorRac(
        hass, bhc_auth, device_1, firmware, entry, auth_provider=True
    )
    coordinator_secondary = BoschComModuleCoordinatorRac(
        hass, bhc_secondary, device_2, firmware, entry, auth_provider=False
    )

    refresh_done = asyncio.Event()

    async def slow_get_token():
        """Simulate a token refresh that takes time (network round-trip)."""
        await refresh_done.wait()
        bhc_auth.token = "fresh_token"
        bhc_auth.refresh_token = "fresh_refresh"

    bhc_auth.token = "expired_token"
    bhc_auth.refresh_token = "old_refresh"
    bhc_auth.get_token = AsyncMock(side_effect=slow_get_token)
    bhc_auth.async_update = AsyncMock(return_value=_make_rac_data(device_1, firmware))

    # Secondary gets 401 on first call (expired token), succeeds after refresh
    bhc_secondary.async_update = AsyncMock(
        side_effect=[
            AuthFailedError("Authorization has failed"),
            _make_rac_data(device_2, firmware),
        ]
    )
    entry.async_start_reauth = Mock()

    async def run_secondary():
        """Non-auth-provider runs immediately — no get_token() guard."""
        return await coordinator_secondary._async_update_data()

    async def run_auth():
        """Auth-provider: get_token() blocks until refresh completes."""
        await asyncio.sleep(0)  # yield to let secondary start first
        refresh_done.set()
        return await coordinator_auth._async_update_data()

    secondary_task = asyncio.create_task(run_secondary())
    auth_task = asyncio.create_task(run_auth())

    # Secondary fails with AuthFailedError — but NO reauth
    with pytest.raises(AuthFailedError):
        await secondary_task

    entry.async_start_reauth.assert_not_called()

    # Auth-provider succeeds (it refreshed first)
    auth_result = await auth_task
    assert auth_result.device == device_1

    # Prove the secondary error was transient: next poll succeeds
    data = await coordinator_secondary._async_update_data()
    assert data.device == device_2


# --- Path 1 (legitimate): get_token fails permanently ------------------
# This is the CORRECT reauth path that existed in v1.3.31 too.
# Refresh token is permanently invalid — reauth IS warranted.


@pytest.mark.asyncio
async def test_get_token_permanent_auth_failure_is_legitimate_reauth(
    hass, entry, bhc, device, firmware
):
    """get_token() AuthFailedError is a real auth failure — reauth is correct."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(
        hass, bhc, device, firmware, entry, auth_provider=True
    )
    bhc.token = "mock_token"
    bhc.refresh_token = "mock_refresh"
    bhc.get_token = AsyncMock(side_effect=AuthFailedError("Failed to refresh"))
    bhc.async_update = AsyncMock()
    entry.async_start_reauth = Mock()

    with pytest.raises(UpdateFailed, match="Re-authentication required"):
        await coordinator._async_update_data()

    # Reauth is correct here — refresh token is dead
    entry.async_start_reauth.assert_called_once_with(hass)
    # async_update should NOT have been called
    bhc.async_update.assert_not_called()


# ===================================================================
# Phase 1: bacon (MQTT) auth — proactive reconnect, no false reauth
#
# The MQTT password *is* the OAuth access token, so the broker drops
# the session when the token expires and refuses a reconnect that
# replays it.  That is a transport failure: it must never surface as
# a re-authentication request.  Only a failed refresh-token exchange
# may do that.
# ===================================================================

_TRACKER = "custom_components.bosch_homecom.coordinator.async_track_point_in_utc_time"
_DECODE_SUB = "custom_components.bosch_homecom.coordinator.decode_jwt_sub"
_DECODE_EXP = "custom_components.bosch_homecom.coordinator.decode_jwt_exp"
_DELETE_ISSUE = "custom_components.bosch_homecom.coordinator.ir.async_delete_issue"


def _shadow_state():
    """Minimal shadow payload accepted by _build()."""
    return {"reported": {"airFlowHorizontal": "on"}, "desired": {}}


# --- Scheduling --------------------------------------------------------


def test_bacon_schedule_reconnect_uses_margin_before_expiry(hass, entry, firmware):
    """The reconnect is armed BACON_RECONNECT_MARGIN before the token expires."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(expires_in=timedelta(minutes=60))
    coordinator = _make_bacon_coordinator(hass, entry, firmware, client=client)

    with patch(_TRACKER, return_value=Mock()) as tracker:
        coordinator._schedule_reconnect()

    when = tracker.call_args[0][2]
    assert when == client.token_expires_at - BACON_RECONNECT_MARGIN
    # Well before expiry, so the session is replaced instead of refused.
    assert when < client.token_expires_at
    assert coordinator._unsub_reconnect is not None


def test_bacon_schedule_reconnect_floors_short_lived_token(hass, entry, firmware):
    """A token already inside the margin is floored to the minimum delay."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(expires_in=timedelta(minutes=2))
    coordinator = _make_bacon_coordinator(hass, entry, firmware, client=client)

    before = dt_util.utcnow()
    with patch(_TRACKER, return_value=Mock()) as tracker:
        coordinator._schedule_reconnect()
    after = dt_util.utcnow()

    when = tracker.call_args[0][2]
    # Not "immediately", which would spin: at least the floor from now.
    assert before + BACON_RECONNECT_MIN_DELAY <= when
    assert when <= after + BACON_RECONNECT_MIN_DELAY


def test_bacon_schedule_reconnect_noop_without_expiry(hass, entry, firmware):
    """Nothing is armed when the session has no decodable expiry."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(expires_in=None)
    coordinator = _make_bacon_coordinator(hass, entry, firmware, client=client)

    with patch(_TRACKER, return_value=Mock()) as tracker:
        coordinator._schedule_reconnect()

    tracker.assert_not_called()
    assert coordinator._unsub_reconnect is None


def test_bacon_schedule_reconnect_replaces_previous_timer(hass, entry, firmware):
    """Re-arming cancels the timer it replaces (no timer pile-up)."""
    entry.add_to_hass(hass)
    coordinator = _make_bacon_coordinator(hass, entry, firmware)
    first = Mock()

    with patch(_TRACKER, side_effect=[first, Mock()]):
        coordinator._schedule_reconnect()
        coordinator._schedule_reconnect()

    first.assert_called_once_with()


def test_bacon_cancel_scheduled_reconnect_is_idempotent(hass, entry, firmware):
    """Cancelling twice, or with nothing armed, is safe.

    Regression: the coordinator referenced _cancel_scheduled_reconnect as an
    unload hook before it existed, so constructing it raised AttributeError.
    """
    entry.add_to_hass(hass)
    coordinator = _make_bacon_coordinator(hass, entry, firmware)
    unsub = Mock()

    coordinator._cancel_scheduled_reconnect()  # nothing armed

    with patch(_TRACKER, return_value=unsub):
        coordinator._schedule_reconnect()
    coordinator._cancel_scheduled_reconnect()
    coordinator._cancel_scheduled_reconnect()

    unsub.assert_called_once_with()
    assert coordinator._unsub_reconnect is None


def test_bacon_unload_cancels_scheduled_reconnect(hass, entry, firmware):
    """The pending reconnect is cancelled when the entry unloads."""
    entry.add_to_hass(hass)
    coordinator = _make_bacon_coordinator(hass, entry, firmware)

    assert coordinator._cancel_scheduled_reconnect in entry._on_unload


@pytest.mark.asyncio
async def test_bacon_ensure_connected_arms_schedule_for_setup_session(
    hass, entry, firmware
):
    """An already-connected session (opened at setup) still gets a timer."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(connected=True)
    coordinator = _make_bacon_coordinator(hass, entry, firmware, client=client)

    with patch(_TRACKER, return_value=Mock()) as tracker:
        await coordinator._ensure_connected()

    tracker.assert_called_once()
    client.async_connect.assert_not_called()


@pytest.mark.asyncio
async def test_bacon_connect_reschedules_on_success(hass, entry, firmware):
    """Every successful connect re-arms the pre-expiry reconnect."""
    entry.add_to_hass(hass)
    client = _make_bacon_client()
    coordinator = _make_bacon_coordinator(hass, entry, firmware, client=client)

    with (
        patch(_TRACKER, return_value=Mock()) as tracker,
        patch(_DECODE_SUB, return_value="sub-1"),
    ):
        await coordinator._ensure_connected()

    client.async_connect.assert_awaited_once_with("mock_token", "sub-1")
    tracker.assert_called_once()


# --- _ensure_connected: refusal handling -------------------------------


@pytest.mark.asyncio
async def test_bacon_ensure_connected_forces_refresh_and_retries_once(
    hass, entry, firmware
):
    """A refused CONNACK forces a token rotation and retries the connect once."""
    entry.add_to_hass(hass)
    client = _make_bacon_client()
    client.async_connect = AsyncMock(
        side_effect=[MqttNotAuthorizedError("Not authorized"), None]
    )
    token_manager = _make_token_manager(token="rotated_token")
    coordinator = _make_bacon_coordinator(
        hass,
        entry,
        firmware,
        client=client,
        token_manager=token_manager,
        auth_provider=True,
    )
    entry.async_start_reauth = Mock()

    with patch(_TRACKER, return_value=Mock()), patch(_DECODE_SUB, return_value="sub-1"):
        await coordinator._ensure_connected()

    # Exactly one forced rotation, exactly one retry.
    assert token_manager.get_token.await_count == 2
    assert token_manager.get_token.await_args_list[0].kwargs == {"force": False}
    assert token_manager.get_token.await_args_list[1].kwargs == {"force": True}
    assert client.async_connect.await_count == 2
    # A stale MQTT password is never a reauth.
    entry.async_start_reauth.assert_not_called()
    # The rotated token is handed to the other coordinators.
    assert entry.data[CONF_TOKEN] == "rotated_token"


@pytest.mark.asyncio
async def test_bacon_ensure_connected_second_refusal_is_not_reauth(
    hass, entry, firmware
):
    """A refusal that survives the forced rotation fails the update, not the user."""
    entry.add_to_hass(hass)
    client = _make_bacon_client()
    client.async_connect = AsyncMock(
        side_effect=MqttNotAuthorizedError("Not authorized")
    )
    coordinator = _make_bacon_coordinator(
        hass,
        entry,
        firmware,
        client=client,
        token_manager=_make_token_manager(),
        auth_provider=True,
    )
    entry.async_start_reauth = Mock()

    with (
        patch(_TRACKER, return_value=Mock()),
        patch(_DECODE_SUB, return_value="sub-1"),
        pytest.raises(UpdateFailed, match="rejected the refreshed access token"),
    ):
        await coordinator._ensure_connected()

    assert client.async_connect.await_count == 2  # once, then one retry — no storm
    entry.async_start_reauth.assert_not_called()


@pytest.mark.asyncio
async def test_bacon_ensure_connected_reauth_only_when_rotation_fails(
    hass, entry, firmware
):
    """A dead refresh token is the one failure that warrants a reauth."""
    entry.add_to_hass(hass)
    client = _make_bacon_client()
    client.async_connect = AsyncMock(
        side_effect=MqttNotAuthorizedError("Not authorized")
    )
    token_manager = _make_token_manager()
    token_manager.get_token = AsyncMock(
        side_effect=[None, AuthFailedError("Failed to refresh")]
    )
    coordinator = _make_bacon_coordinator(
        hass,
        entry,
        firmware,
        client=client,
        token_manager=token_manager,
        auth_provider=True,
    )
    entry.async_start_reauth = Mock()

    with (
        patch(_TRACKER, return_value=Mock()),
        patch(_DECODE_SUB, return_value="sub-1"),
        pytest.raises(UpdateFailed, match="Re-authentication required"),
    ):
        await coordinator._ensure_connected()

    entry.async_start_reauth.assert_called_once_with(hass)
    client.async_connect.assert_awaited_once()  # no retry after a dead refresh token


@pytest.mark.asyncio
async def test_bacon_ensure_connected_non_owner_never_rotates(hass, entry, firmware):
    """Only the auth_provider rotates: refresh tokens are single-use."""
    entry.add_to_hass(hass)
    client = _make_bacon_client()
    client.async_connect = AsyncMock(
        side_effect=[MqttNotAuthorizedError("Not authorized"), None]
    )
    token_manager = _make_token_manager()
    coordinator = _make_bacon_coordinator(
        hass,
        entry,
        firmware,
        client=client,
        token_manager=token_manager,
        auth_provider=False,
    )
    entry.async_start_reauth = Mock()

    with patch(_TRACKER, return_value=Mock()), patch(_DECODE_SUB, return_value="sub-1"):
        await coordinator._ensure_connected()

    token_manager.get_token.assert_not_awaited()
    # Both attempts use the entry token the owner keeps fresh.
    assert client.async_connect.await_args_list == [
        (("mock_token", "sub-1"),),
        (("mock_token", "sub-1"),),
    ]
    entry.async_start_reauth.assert_not_called()


@pytest.mark.asyncio
async def test_bacon_ensure_connected_holds_the_shared_lock(hass, entry, firmware):
    """The connect happens under the shared token lock."""
    entry.add_to_hass(hass)
    lock = asyncio.Lock()
    client = _make_bacon_client()
    coordinator = _make_bacon_coordinator(
        hass, entry, firmware, client=client, lock=lock
    )

    await lock.acquire()
    with patch(_TRACKER, return_value=Mock()), patch(_DECODE_SUB, return_value="sub-1"):
        task = asyncio.create_task(coordinator._ensure_connected())
        await asyncio.sleep(0)
        client.async_connect.assert_not_called()
        lock.release()
        await task

    client.async_connect.assert_awaited_once()


# --- The scheduled job -------------------------------------------------


@pytest.mark.asyncio
async def test_bacon_scheduled_reconnect_rotates_and_rearms(hass, entry, firmware):
    """The scheduled job forces a rotation, reconnects and re-arms itself."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(expires_in=BACON_RECONNECT_MARGIN / 2, connected=True)
    token_manager = _make_token_manager(token="rotated_token")
    coordinator = _make_bacon_coordinator(
        hass,
        entry,
        firmware,
        client=client,
        token_manager=token_manager,
        auth_provider=True,
    )

    with (
        patch(_TRACKER, return_value=Mock()) as tracker,
        patch(_DECODE_SUB, return_value="sub-1"),
        patch(_DECODE_EXP, return_value=dt_util.utcnow() + timedelta(minutes=60)),
    ):
        await coordinator._async_scheduled_reconnect()

    token_manager.get_token.assert_awaited_once_with(force=True)
    client.async_connect.assert_awaited_once_with("rotated_token", "sub-1")
    assert tracker.call_count >= 1
    assert coordinator._unsub_reconnect is not None


@pytest.mark.asyncio
async def test_bacon_scheduled_reconnect_skips_when_already_renewed(
    hass, entry, firmware
):
    """Every coordinator arms a timer, but only one renews the shared session."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(expires_in=timedelta(minutes=55), connected=True)
    token_manager = _make_token_manager()
    coordinator = _make_bacon_coordinator(
        hass,
        entry,
        firmware,
        client=client,
        token_manager=token_manager,
        auth_provider=True,
    )

    with patch(_TRACKER, return_value=Mock()) as tracker:
        await coordinator._async_scheduled_reconnect()

    client.async_connect.assert_not_called()
    token_manager.get_token.assert_not_awaited()
    tracker.assert_called_once()  # still re-armed for the real expiry


@pytest.mark.asyncio
async def test_bacon_scheduled_reconnect_skips_stale_token_for_non_owner(
    hass, entry, firmware
):
    """A non-owner with nothing fresher to present does not churn the session."""
    entry.add_to_hass(hass)
    session_expiry = dt_util.utcnow() + BACON_RECONNECT_MARGIN / 2
    client = _make_bacon_client(connected=True)
    client.token_expires_at = session_expiry
    coordinator = _make_bacon_coordinator(
        hass, entry, firmware, client=client, auth_provider=False
    )

    with (
        patch(_TRACKER, return_value=Mock()),
        patch(_DECODE_EXP, return_value=session_expiry),
    ):
        await coordinator._async_scheduled_reconnect()

    client.async_connect.assert_not_called()
    assert coordinator._unsub_reconnect is not None  # tries again after the floor


@pytest.mark.asyncio
async def test_bacon_scheduled_reconnect_rearms_after_failure(hass, entry, firmware):
    """A failed scheduled reconnect is swallowed and retried later."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(expires_in=BACON_RECONNECT_MARGIN / 2, connected=True)
    client.async_connect = AsyncMock(side_effect=ApiError("broker down"))
    coordinator = _make_bacon_coordinator(
        hass,
        entry,
        firmware,
        client=client,
        token_manager=_make_token_manager(),
        auth_provider=True,
    )

    with (
        patch(_TRACKER, return_value=Mock()) as tracker,
        patch(_DECODE_SUB, return_value="sub-1"),
        patch(_DECODE_EXP, return_value=dt_util.utcnow() + timedelta(minutes=60)),
    ):
        await coordinator._async_scheduled_reconnect()  # must not raise

    assert coordinator._unsub_reconnect is not None
    assert tracker.call_count >= 1


@pytest.mark.asyncio
async def test_bacon_scheduled_reconnect_respects_the_shared_lock(
    hass, entry, firmware
):
    """The scheduled job serialises with the poller on the same lock."""
    entry.add_to_hass(hass)
    lock = asyncio.Lock()
    client = _make_bacon_client(expires_in=BACON_RECONNECT_MARGIN / 2, connected=True)
    coordinator = _make_bacon_coordinator(
        hass,
        entry,
        firmware,
        client=client,
        token_manager=_make_token_manager(),
        lock=lock,
        auth_provider=True,
    )

    await lock.acquire()
    with (
        patch(_TRACKER, return_value=Mock()),
        patch(_DECODE_SUB, return_value="sub-1"),
        patch(_DECODE_EXP, return_value=dt_util.utcnow() + timedelta(minutes=60)),
    ):
        task = asyncio.create_task(coordinator._async_scheduled_reconnect())
        await asyncio.sleep(0)
        client.async_connect.assert_not_called()
        lock.release()
        await task

    client.async_connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_bacon_handle_scheduled_reconnect_runs_the_job(hass, entry, firmware):
    """The timer callback hands the reconnect to a task."""
    entry.add_to_hass(hass)
    coordinator = _make_bacon_coordinator(hass, entry, firmware)
    ran = asyncio.Event()

    async def _job():
        ran.set()

    with patch.object(coordinator, "_async_scheduled_reconnect", side_effect=_job):
        coordinator._handle_scheduled_reconnect(dt_util.utcnow())
        await asyncio.wait_for(ran.wait(), timeout=1)

    assert coordinator._unsub_reconnect is None


# --- _async_update_data ------------------------------------------------


@pytest.mark.asyncio
async def test_bacon_update_mqtt_refusal_is_update_failed_not_reauth(
    hass, entry, firmware
):
    """THE regression: a stale MQTT password never asks for re-authentication."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(connected=True)
    coordinator = _make_bacon_coordinator(hass, entry, firmware, client=client)
    coordinator.bhc.async_update = AsyncMock(
        side_effect=MqttNotAuthorizedError("Not authorized")
    )
    entry.async_start_reauth = Mock()

    with patch(_TRACKER, return_value=Mock()), pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    entry.async_start_reauth.assert_not_called()


@pytest.mark.asyncio
async def test_bacon_update_auth_failed_still_triggers_reauth(hass, entry, firmware):
    """A genuine OAuth failure keeps its reauth."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(connected=True)
    coordinator = _make_bacon_coordinator(hass, entry, firmware, client=client)
    coordinator.bhc.async_update = AsyncMock(
        side_effect=AuthFailedError("Authorization has failed")
    )
    entry.async_start_reauth = Mock()

    with (
        patch(_TRACKER, return_value=Mock()),
        pytest.raises(UpdateFailed, match="Re-authentication required"),
    ):
        await coordinator._async_update_data()

    entry.async_start_reauth.assert_called_once_with(hass)


@pytest.mark.asyncio
async def test_bacon_update_withdraws_stale_reauth_on_success(hass, entry, firmware):
    """A successful update aborts the reauth flow and drops its repair issue."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(connected=True)
    coordinator = _make_bacon_coordinator(hass, entry, firmware, client=client)
    coordinator.bhc.async_update = AsyncMock(return_value=_shadow_state())

    with (
        patch(_TRACKER, return_value=Mock()),
        patch.object(
            hass.config_entries.flow,
            "async_progress_by_handler",
            return_value=[{"flow_id": "flow-1"}],
        ) as progress,
        patch.object(hass.config_entries.flow, "async_abort") as abort,
        patch(_DELETE_ISSUE) as delete_issue,
    ):
        data = await coordinator._async_update_data()

    assert isinstance(data, BHCDeviceBaconRac)
    # Only this entry's reauth flows are considered.
    assert progress.call_args.kwargs["match_context"] == {
        "source": SOURCE_REAUTH,
        "entry_id": entry.entry_id,
    }
    abort.assert_called_once_with("flow-1")
    delete_issue.assert_called_once_with(
        hass, "homeassistant", f"config_entry_reauth_{DOMAIN}_{entry.entry_id}"
    )


@pytest.mark.asyncio
async def test_bacon_update_withdraw_survives_unknown_flow(hass, entry, firmware):
    """A flow that vanished between listing and aborting is not fatal."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(connected=True)
    coordinator = _make_bacon_coordinator(hass, entry, firmware, client=client)
    coordinator.bhc.async_update = AsyncMock(return_value=_shadow_state())

    with (
        patch(_TRACKER, return_value=Mock()),
        patch.object(
            hass.config_entries.flow,
            "async_progress_by_handler",
            return_value=[{"flow_id": "gone"}],
        ),
        patch.object(hass.config_entries.flow, "async_abort", side_effect=UnknownFlow),
        patch(_DELETE_ISSUE) as delete_issue,
    ):
        data = await coordinator._async_update_data()

    assert isinstance(data, BHCDeviceBaconRac)
    delete_issue.assert_not_called()


@pytest.mark.asyncio
async def test_bacon_update_withdraw_noop_without_reauth(hass, entry, firmware):
    """With no reauth in progress a successful update changes nothing."""
    entry.add_to_hass(hass)
    client = _make_bacon_client(connected=True)
    coordinator = _make_bacon_coordinator(hass, entry, firmware, client=client)
    coordinator.bhc.async_update = AsyncMock(return_value=_shadow_state())

    with (
        patch(_TRACKER, return_value=Mock()),
        patch.object(hass.config_entries.flow, "async_abort") as abort,
        patch(_DELETE_ISSUE) as delete_issue,
    ):
        await coordinator._async_update_data()

    abort.assert_not_called()
    delete_issue.assert_not_called()
