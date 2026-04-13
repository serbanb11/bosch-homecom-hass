import asyncio
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import CONF_CODE, CONF_TOKEN, CONF_USERNAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed
from homecom_alt import (
    ApiError,
    AuthFailedError,
    BHCDeviceCommodule,
    BHCDeviceGeneric,
    BHCDeviceK40,
    BHCDeviceRac,
    BHCDeviceWddw2,
    InvalidSensorDataError,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from tenacity import RetryError

from custom_components.bosch_homecom.const import (
    CONF_DEVICES,
    CONF_REFRESH,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MANUFACTURER,
)
from custom_components.bosch_homecom.coordinator import (
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
    for optional in ("hourly_energy_history", "energy_gas_unit"):
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
