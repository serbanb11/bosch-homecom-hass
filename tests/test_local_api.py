"""Tests for the optional K 40 RF Local API support.

Covers the options-flow steps where the user enters the gateway details, the
coordinator's local-first behaviour, and the local-only sensors.
"""

import dataclasses
from dataclasses import replace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN, CONF_USERNAME
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from homecom_alt import (
    ApiError,
    AuthFailedError,
    BHCDeviceK40,
    BHCDeviceK40Local,
    K40Update,
    NotRespondingError,
    ProximityRequiredError,
    TokenStoreFullError,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
)

from custom_components.bosch_homecom import _local_only_devices
from custom_components.bosch_homecom.binary_sensor import (
    BoschComK40LocalPumpStatusSensor,
    async_setup_entry as binary_sensor_async_setup_entry,
)
from custom_components.bosch_homecom.const import (
    CONF_DEVICES,
    CONF_LOCAL,
    CONF_LOCAL_GATEWAY,
    CONF_LOCAL_HOST,
    CONF_LOCAL_LOGIN,
    CONF_LOCAL_PASSWORD,
    CONF_LOCAL_REMOVE,
    CONF_LOCAL_TOKEN,
    CONF_LOCAL_TOKEN_ID,
    CONF_REFRESH,
    DOMAIN,
    MAX_CLOUD_FAILURES_WITH_LOCAL,
)
from custom_components.bosch_homecom.coordinator import (
    HC_TUNE_ENDPOINTS,
    BoschComModuleCoordinatorK40,
    _overlay_local,
)
from custom_components.bosch_homecom.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.bosch_homecom.local_sensor import (
    LOCAL_SENSORS,
    BoschComLocalSensor,
    BoschComLocalSourceSensor,
    _emon_field,
)

_FLOW_CLIENT = "custom_components.bosch_homecom.config_flow.HomeComK40Local"
HOST = "192.0.2.10"
GATEWAY = "102128202"
LOCAL_TOKEN = "local-token"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entry():
    """Config entry with one k40 gateway selected."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user",
            CONF_TOKEN: "cloud-token",
            CONF_DEVICES: {f"{GATEWAY}_k40": True, "999_rac": True},
        },
    )


@pytest.fixture
def device():
    """K40 device description."""
    return {"deviceId": GATEWAY, "deviceType": "k40"}


@pytest.fixture
def firmware():
    """Firmware payload."""
    return {"value": "15.00.01"}


def _local_device(**overrides):
    """Build a local payload with a couple of representative resources."""
    resources = {
        "/heatSources/compressor/powerElecActual": {
            "type": "floatValue",
            "value": 25.0,
            "unitOfMeasure": "W",
        },
        "/heatSources/hs1/numberOfStarts": {
            "type": "emonValue",
            "values": [{"ch": 149}, {"dhw": 129}, {"cooling": 0}, {"total": 278}],
        },
    }
    resources.update(overrides.pop("resources", {}))
    return BHCDeviceK40Local(
        device=GATEWAY,
        firmware="15.00.01",
        resources=resources,
        **overrides,
    )


def _cloud_device():
    """Minimal cloud payload; the coordinator only re-wraps it."""
    return BHCDeviceK40(
        device={"deviceId": GATEWAY, "deviceType": "k40"},
        firmware="15.00.01",
        notifications=None,
        holiday_mode=None,
        away_mode=None,
        power_limitation=None,
        outdoor_temp=None,
        heat_sources=None,
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


def _coordinator(hass, entry, device, firmware, *, local=True):
    """Build a K40 coordinator with or without a local transport."""
    bhc = Mock()
    bhc.token = "cloud-token"
    bhc.refresh_token = "cloud-refresh"
    bhc.get_token = AsyncMock()
    bhc.async_update = AsyncMock(return_value=_cloud_device())
    # The K40 coordinator also pulls these standalone endpoints via the
    # _K40ExtraEndpointsMixin.
    bhc.async_get_additional_heater_mode = AsyncMock(return_value={"value": "off"})
    bhc.async_get_silent_mode = AsyncMock(return_value={"value": "off"})
    bhc.async_get_dhw_charge_duration = AsyncMock(return_value={"value": 60})
    for getter, _setter in HC_TUNE_ENDPOINTS.values():
        setattr(bhc, getter, AsyncMock(return_value=None))
    bhc.async_request_bulk = AsyncMock(return_value={})
    local_client = Mock() if local else None
    coordinator = BoschComModuleCoordinatorK40(
        hass, bhc, device, firmware, entry, False, local_client
    )
    return coordinator, bhc


# ---------------------------------------------------------------------------
# Options flow: entering the gateway details
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_options_menu_offers_general_and_local(hass, entry):
    """The options flow opens on a menu, not straight into the old form."""
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == "menu"
    assert set(result["menu_options"]) == {"general", "local"}


@pytest.mark.asyncio
async def test_options_general_still_saves_interval(hass, entry):
    """The pre-existing settings remain reachable and still save."""
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "general"}
    )
    assert result["step_id"] == "general"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"update_seconds": 120, "brand_buderus": False, "wb_label": "Wallbox"},
    )
    assert result["type"] == "create_entry"
    assert result["data"]["update_seconds"] == 120


@pytest.mark.asyncio
async def test_local_single_gateway_skips_selection(hass, entry):
    """With one k40 the gateway picker is skipped and credentials asked directly."""
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )

    assert result["step_id"] == "local_credentials"
    # The gateway id is surfaced so the user knows which appliance this is for.
    assert result["description_placeholders"]["gateway"] == GATEWAY


@pytest.mark.asyncio
async def test_local_multiple_gateways_asks_which(hass):
    """With two k40 gateways the user picks one first."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user",
            CONF_DEVICES: {f"{GATEWAY}_k40": True, "555_k40": True},
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )
    assert result["step_id"] == "local"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCAL_GATEWAY: "555"}
    )
    assert result["step_id"] == "local_credentials"


@pytest.mark.asyncio
@pytest.mark.parametrize("devices", [{"999_rac": True}, {"888_k30": True}])
async def test_local_aborts_without_a_k40(hass, devices):
    """Only a K 40 RF can be configured locally.

    A K 30 RF has no Local API (no buttons, no token port, not in Bosch's list
    of applicable variants), so offering it only produced "not reachable" (#186).
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_DEVICES: devices},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )

    assert result["type"] == "abort"
    assert result["reason"] == "no_k40_gateway"


@pytest.mark.asyncio
async def test_local_credentials_success_stores_token(hass, entry):
    """A successful token request persists host and token against the gateway."""
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )

    async def fake_create(self, login, password, client_name):
        self.token = LOCAL_TOKEN
        return {"access_token": LOCAL_TOKEN}

    tokens = [
        {"token_id": "1", "client_name": "eu-dataact", "created_at": "2026-01-01"},
        {"token_id": "4", "client_name": "home-assistant", "created_at": "2026-09-01"},
        {"token_id": "7", "client_name": "home-assistant", "created_at": "2026-09-20"},
    ]
    with (
        patch(f"{_FLOW_CLIENT}.async_create_token", new=fake_create),
        patch(f"{_FLOW_CLIENT}.async_list_tokens", new=AsyncMock(return_value=tokens)),
        patch(f"{_FLOW_CLIENT}.async_revoke_token", new=AsyncMock()) as revoke,
        patch.object(hass.config_entries, "async_schedule_reload") as reload,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_LOCAL_HOST: f"  {HOST}  ",
                CONF_LOCAL_LOGIN: "login",
                CONF_LOCAL_PASSWORD: "abcd-efgh",
                CONF_LOCAL_REMOVE: False,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    stored = entry.data[CONF_LOCAL][GATEWAY]
    # Whitespace trimmed so a copy-pasted address still works.
    assert stored[CONF_LOCAL_HOST] == HOST
    assert stored[CONF_LOCAL_TOKEN] == LOCAL_TOKEN
    # The newest token under our client name is the one just issued.
    assert stored[CONF_LOCAL_TOKEN_ID] == "7"
    # First provisioning: nothing of ours to revoke.
    revoke.assert_not_awaited()
    # The options are unchanged, so OptionsFlowWithReload would not reload and
    # the coordinator would never see the new token.
    reload.assert_called_once_with(entry.entry_id)


async def _configure_local(hass, entry, user_input):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    await hass.async_block_till_done()
    return result


def _with_local(hass, entry, local_conf):
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_LOCAL: {GATEWAY: local_conf}}
    )


@pytest.mark.asyncio
async def test_reprovisioning_revokes_the_replaced_token(hass, entry):
    """A new token replaces the old one on the gateway too, not just in HA."""
    _with_local(
        hass,
        entry,
        {CONF_LOCAL_HOST: HOST, CONF_LOCAL_TOKEN: "old", CONF_LOCAL_TOKEN_ID: "4"},
    )

    async def fake_create(self, login, password, client_name):
        self.token = LOCAL_TOKEN
        return {"access_token": LOCAL_TOKEN}

    tokens = [
        {"token_id": "4", "client_name": "home-assistant", "created_at": 1775134322},
        {"token_id": "9", "client_name": "home-assistant", "created_at": 1790000000},
    ]
    with (
        patch(f"{_FLOW_CLIENT}.async_create_token", new=fake_create),
        patch(f"{_FLOW_CLIENT}.async_list_tokens", new=AsyncMock(return_value=tokens)),
        patch(f"{_FLOW_CLIENT}.async_revoke_token", new=AsyncMock()) as revoke,
        patch.object(hass.config_entries, "async_schedule_reload"),
    ):
        await _configure_local(
            hass,
            entry,
            {
                CONF_LOCAL_HOST: HOST,
                CONF_LOCAL_LOGIN: "login",
                CONF_LOCAL_PASSWORD: "pass",
                CONF_LOCAL_REMOVE: False,
            },
        )

    revoke.assert_awaited_once_with("4")
    stored = entry.data[CONF_LOCAL][GATEWAY]
    assert stored[CONF_LOCAL_TOKEN] == LOCAL_TOKEN
    assert stored[CONF_LOCAL_TOKEN_ID] == "9"


@pytest.mark.asyncio
async def test_token_listing_failure_does_not_block_provisioning(hass, entry):
    """Without an id the token still works; it just cannot be revoked later."""
    entry.add_to_hass(hass)

    async def fake_create(self, login, password, client_name):
        self.token = LOCAL_TOKEN
        return {"access_token": LOCAL_TOKEN}

    with (
        patch(f"{_FLOW_CLIENT}.async_create_token", new=fake_create),
        patch(
            f"{_FLOW_CLIENT}.async_list_tokens",
            new=AsyncMock(side_effect=NotRespondingError("timeout")),
        ),
        patch.object(hass.config_entries, "async_schedule_reload"),
    ):
        result = await _configure_local(
            hass,
            entry,
            {
                CONF_LOCAL_HOST: HOST,
                CONF_LOCAL_LOGIN: "login",
                CONF_LOCAL_PASSWORD: "pass",
                CONF_LOCAL_REMOVE: False,
            },
        )

    assert result["type"] == "create_entry"
    stored = entry.data[CONF_LOCAL][GATEWAY]
    assert stored[CONF_LOCAL_TOKEN] == LOCAL_TOKEN
    assert CONF_LOCAL_TOKEN_ID not in stored


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke_error", [None, NotRespondingError("gateway gone")])
async def test_removal_revokes_the_token_and_reloads(hass, entry, revoke_error):
    """Removing local access frees the gateway's token slot, best effort."""
    _with_local(
        hass,
        entry,
        {CONF_LOCAL_HOST: HOST, CONF_LOCAL_TOKEN: "old", CONF_LOCAL_TOKEN_ID: "4"},
    )

    with (
        patch(
            f"{_FLOW_CLIENT}.async_revoke_token",
            new=AsyncMock(side_effect=revoke_error),
        ) as revoke,
        patch.object(hass.config_entries, "async_schedule_reload") as reload,
    ):
        result = await _configure_local(
            hass,
            entry,
            {
                CONF_LOCAL_HOST: HOST,
                CONF_LOCAL_LOGIN: "",
                CONF_LOCAL_PASSWORD: "",
                CONF_LOCAL_REMOVE: True,
            },
        )

    revoke.assert_awaited_once_with("4")
    # An unreachable gateway must not stop the user from removing local access.
    assert result["type"] == "create_entry"
    assert GATEWAY not in entry.data[CONF_LOCAL]
    reload.assert_called_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_diagnostics_redact_local_credentials(hass, entry):
    """The never-expiring LAN token must not reach a dump pasted into an issue."""
    _with_local(
        hass,
        entry,
        {
            CONF_LOCAL_HOST: HOST,
            CONF_LOCAL_TOKEN: LOCAL_TOKEN,
            CONF_LOCAL_TOKEN_ID: "4",
        },
    )
    entry.runtime_data = []

    dump = await async_get_config_entry_diagnostics(hass, entry)

    local = dump["info"][CONF_LOCAL][GATEWAY]
    assert local[CONF_LOCAL_TOKEN] == "**REDACTED**"
    assert local[CONF_LOCAL_HOST] == "**REDACTED**"
    assert LOCAL_TOKEN not in str(dump)
    assert HOST not in str(dump)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "expected_error"),
    [
        (ProximityRequiredError("412"), "local_proximity_required"),
        (TokenStoreFullError("507"), "local_token_store_full"),
        (AuthFailedError("401"), "local_invalid_auth"),
        (ApiError("400 invalid_grant"), "local_invalid_auth"),
        (NotRespondingError("timeout"), "local_cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
    ids=["proximity", "store_full", "401", "bad_credentials", "unreachable", "other"],
)
async def test_local_credentials_error_mapping(hass, entry, exc, expected_error):
    """Each failure mode gets its own actionable message."""
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )

    with patch(
        "custom_components.bosch_homecom.config_flow.HomeComK40Local.async_create_token",
        new=AsyncMock(side_effect=exc),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_LOCAL_HOST: HOST,
                CONF_LOCAL_LOGIN: "login",
                CONF_LOCAL_PASSWORD: "pass",
                CONF_LOCAL_REMOVE: False,
            },
        )

    assert result["step_id"] == "local_credentials"
    assert result["errors"]["base"] == expected_error
    # Nothing is persisted on failure.
    assert not entry.data.get(CONF_LOCAL)


def _basic_info(gateway_id=GATEWAY):
    return {"id": "/system/basicInfo", "gatewayId": gateway_id, "values": []}


@pytest.mark.asyncio
async def test_pasted_token_is_verified_and_stored(hass, entry):
    """A pasted token skips Login/Pass and the button press entirely."""
    entry.add_to_hass(hass)
    seen = {}

    async def fake_get(self, path):
        seen[path] = self.token
        return _basic_info()

    with (
        patch(f"{_FLOW_CLIENT}.async_get_resource", new=fake_get),
        patch(f"{_FLOW_CLIENT}.async_create_token", new=AsyncMock()) as create,
        patch.object(hass.config_entries, "async_schedule_reload") as reload,
    ):
        result = await _configure_local(
            hass,
            entry,
            {
                CONF_LOCAL_HOST: f" {HOST} ",
                CONF_LOCAL_LOGIN: "",
                CONF_LOCAL_PASSWORD: "",
                CONF_LOCAL_TOKEN: f"  {LOCAL_TOKEN}\n",
                CONF_LOCAL_REMOVE: False,
            },
        )

    assert result["type"] == "create_entry"
    # Proven against the gateway with the pasted token before it is stored.
    assert seen == {"/system/basicInfo": LOCAL_TOKEN}
    create.assert_not_awaited()
    stored = entry.data[CONF_LOCAL][GATEWAY]
    assert stored == {CONF_LOCAL_HOST: HOST, CONF_LOCAL_TOKEN: LOCAL_TOKEN}
    reload.assert_called_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_pasted_token_accepted_when_basic_info_is_absent(hass, entry):
    """A 403/404 comes after authentication, so it still proves the token."""
    entry.add_to_hass(hass)
    with (
        patch(f"{_FLOW_CLIENT}.async_get_resource", new=AsyncMock(return_value=None)),
        patch.object(hass.config_entries, "async_schedule_reload"),
    ):
        result = await _configure_local(
            hass,
            entry,
            {CONF_LOCAL_HOST: HOST, CONF_LOCAL_TOKEN: LOCAL_TOKEN},
        )

    assert result["type"] == "create_entry"
    assert entry.data[CONF_LOCAL][GATEWAY][CONF_LOCAL_TOKEN] == LOCAL_TOKEN


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("get_resource", "expected_error"),
    [
        (AsyncMock(side_effect=AuthFailedError("401")), "local_invalid_token"),
        (AsyncMock(side_effect=NotRespondingError("timeout")), "local_cannot_connect"),
        (AsyncMock(side_effect=RuntimeError("boom")), "unknown"),
        (AsyncMock(return_value=_basic_info("999999999")), "local_wrong_gateway"),
    ],
    ids=["401", "unreachable", "other", "other_gateway"],
)
async def test_pasted_token_error_mapping(hass, entry, get_resource, expected_error):
    """A token that does not open this gateway is never stored."""
    entry.add_to_hass(hass)
    with patch(f"{_FLOW_CLIENT}.async_get_resource", new=get_resource):
        result = await _configure_local(
            hass,
            entry,
            {CONF_LOCAL_HOST: HOST, CONF_LOCAL_TOKEN: LOCAL_TOKEN},
        )

    assert result["step_id"] == "local_credentials"
    assert result["errors"]["base"] == expected_error
    assert not entry.data.get(CONF_LOCAL)


@pytest.mark.asyncio
async def test_pasted_token_replaces_and_revokes_the_old_one(hass, entry):
    """A different pasted token frees the slot of the one it replaces."""
    _with_local(
        hass,
        entry,
        {CONF_LOCAL_HOST: HOST, CONF_LOCAL_TOKEN: "old", CONF_LOCAL_TOKEN_ID: "4"},
    )
    with (
        patch(
            f"{_FLOW_CLIENT}.async_get_resource",
            new=AsyncMock(return_value=_basic_info()),
        ),
        patch(f"{_FLOW_CLIENT}.async_revoke_token", new=AsyncMock()) as revoke,
        patch.object(hass.config_entries, "async_schedule_reload"),
    ):
        await _configure_local(
            hass,
            entry,
            {CONF_LOCAL_HOST: HOST, CONF_LOCAL_TOKEN: LOCAL_TOKEN},
        )

    revoke.assert_awaited_once_with("4")
    stored = entry.data[CONF_LOCAL][GATEWAY]
    assert stored == {CONF_LOCAL_HOST: HOST, CONF_LOCAL_TOKEN: LOCAL_TOKEN}


@pytest.mark.asyncio
async def test_re_entering_the_same_token_keeps_it(hass, entry):
    """Changing only the address must not revoke the token being kept."""
    _with_local(
        hass,
        entry,
        {
            CONF_LOCAL_HOST: HOST,
            CONF_LOCAL_TOKEN: LOCAL_TOKEN,
            CONF_LOCAL_TOKEN_ID: "4",
        },
    )
    with (
        patch(
            f"{_FLOW_CLIENT}.async_get_resource",
            new=AsyncMock(return_value=_basic_info()),
        ),
        patch(f"{_FLOW_CLIENT}.async_revoke_token", new=AsyncMock()) as revoke,
        patch.object(hass.config_entries, "async_schedule_reload"),
    ):
        await _configure_local(
            hass,
            entry,
            {CONF_LOCAL_HOST: "192.0.2.20", CONF_LOCAL_TOKEN: LOCAL_TOKEN},
        )

    revoke.assert_not_awaited()
    stored = entry.data[CONF_LOCAL][GATEWAY]
    assert stored == {
        CONF_LOCAL_HOST: "192.0.2.20",
        CONF_LOCAL_TOKEN: LOCAL_TOKEN,
        CONF_LOCAL_TOKEN_ID: "4",
    }


@pytest.mark.asyncio
async def test_local_removal_clears_config(hass, entry):
    """Ticking the removal box deletes the stored local config."""
    (
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_LOCAL: {GATEWAY: {CONF_LOCAL_HOST: HOST}}}
        )
        if entry.entry_id in hass.config_entries._entries
        else None
    )
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_LOCAL: {GATEWAY: {CONF_LOCAL_HOST: HOST, CONF_LOCAL_TOKEN: "t"}},
        },
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "local"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_LOCAL_HOST: HOST,
            CONF_LOCAL_LOGIN: "",
            CONF_LOCAL_PASSWORD: "",
            CONF_LOCAL_REMOVE: True,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert GATEWAY not in entry.data[CONF_LOCAL]


# ---------------------------------------------------------------------------
# Coordinator: local-first behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_without_local_uses_cloud_path(hass, entry, device, firmware):
    """No local config -> the original cloud-only code path, unchanged."""
    entry.add_to_hass(hass)
    coordinator, bhc = _coordinator(hass, entry, device, firmware, local=False)

    assert coordinator.local_first is None
    data = await coordinator._async_update_data()

    assert data.device == device
    bhc.async_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_both_transports_ok(hass, entry, device, firmware):
    """Cloud data is returned and the local payload is exposed alongside it."""
    entry.add_to_hass(hass)
    coordinator, bhc = _coordinator(hass, entry, device, firmware)
    local = _local_device()
    coordinator.local_first.async_update = AsyncMock(
        return_value=K40Update(
            local=local, cloud=_cloud_device(), source="both", local_healthy=True
        )
    )

    data = await coordinator._async_update_data()

    assert data.device == device
    assert coordinator.local_data is local
    assert coordinator.local_source == "both"
    assert coordinator.local_healthy is True
    # The local path bypasses the mixin, so it must fetch the HC settings too.
    bhc.async_get_hc_max_flow_temp.assert_awaited_once_with(device["deviceId"], "hc1")


@pytest.mark.asyncio
async def test_cloud_outage_holds_last_data_while_local_alive(
    hass, entry, device, firmware
):
    """A cloud failure with a reachable gateway must not drop every entity."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    previous = _cloud_device()
    coordinator.data = previous

    coordinator.local_first.async_update = AsyncMock(
        return_value=K40Update(
            local=_local_device(),
            cloud=None,
            source="local",
            local_healthy=True,
            cloud_error="504",
        )
    )

    data = await coordinator._async_update_data()

    # The held cloud data, with the gateway's readings laid over it.
    assert data.device == previous.device
    assert data.firmware == previous.firmware
    assert coordinator.local_source == "local"


@pytest.mark.asyncio
async def test_long_cloud_outage_keeps_serving_local_readings(
    hass, entry, device, firmware
):
    """However long the cloud is down, the gateway keeps the shared values live."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.data = _cloud_device()
    for outdoor in (7.0, 6.5, 6.0, 5.5, 5.0, 4.5, 4.0):
        coordinator.local_first.async_update = AsyncMock(
            return_value=K40Update(
                local=_local_device(resources=_resource(OUTDOOR, outdoor)),
                cloud=None,
                source="local",
                local_healthy=True,
                cloud_error="504",
            )
        )
        coordinator.data = await coordinator._async_update_data()

    assert coordinator.data.outdoor_temp["value"] == 4.0


@pytest.mark.asyncio
async def test_listeners_notified_on_every_failed_refresh(
    hass, entry, device, firmware
):
    """Local-only sensors must hear about every failed refresh, not just the first.

    DataUpdateCoordinator notifies listeners only on the first of a run of failed
    refreshes, so the local sensors used to keep presenting a stale reading.
    """
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_first.async_update = AsyncMock(side_effect=ApiError("down"))
    listener = Mock()
    coordinator.async_add_listener(listener)

    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    notified = listener.call_count

    await coordinator.async_refresh()
    await coordinator.async_refresh()

    assert listener.call_count == notified + 2

    await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_both_transports_failing_marks_local_unhealthy(
    hass, entry, device, firmware
):
    """With no payload at all the local sensors must stop presenting as live."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.data = _cloud_device()
    coordinator.local_healthy = True
    coordinator.local_first = Mock()
    coordinator.local_first.local_healthy = False
    coordinator.local_first.async_update = AsyncMock(
        side_effect=NotRespondingError("both down")
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert coordinator.local_healthy is False


@pytest.mark.asyncio
async def test_cloud_recovery_resets_the_failure_count(hass, entry, device, firmware):
    """One good cloud poll clears the held-data budget."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.data = _cloud_device()

    failing = K40Update(
        local=_local_device(),
        cloud=None,
        source="local",
        local_healthy=True,
        cloud_error="504",
    )
    ok = K40Update(
        local=_local_device(),
        cloud=_cloud_device(),
        source="both",
        local_healthy=True,
    )
    coordinator.local_first.async_update = AsyncMock(side_effect=[failing, ok, failing])

    await coordinator._async_update_data()
    assert coordinator._cloud_failures == 1
    await coordinator._async_update_data()
    assert coordinator._cloud_failures == 0
    await coordinator._async_update_data()
    assert coordinator._cloud_failures == 1


@pytest.mark.asyncio
async def test_no_previous_cloud_data_serves_the_gateway_alone(
    hass, entry, device, firmware
):
    """At startup without the cloud there is nothing to hold: local values only."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_first.async_update = AsyncMock(
        return_value=K40Update(
            local=_local_device(
                resources={
                    **_resource(OUTDOOR, 7.1),
                    **_resource("/dhwCircuits/dhw1/actualTemp", 36.5),
                    **_resource("/heatingCircuits/hc1/currentRoomSetpoint", 21.0),
                }
            ),
            cloud=None,
            source="local",
            local_healthy=True,
            cloud_error="504",
        )
    )

    data = await coordinator._async_update_data()

    assert data.device == device
    assert data.outdoor_temp["value"] == 7.1
    assert data.dhw_circuits[0]["id"] == "/dhwCircuits/dhw1"
    assert data.dhw_circuits[0]["actualTemp"]["value"] == 36.5
    assert data.heating_circuits[0]["id"] == "/heatingCircuits/hc1"
    assert data.notifications is None


@pytest.mark.asyncio
async def test_both_transports_failing_raises_update_failed(
    hass, entry, device, firmware
):
    """Nothing reachable at all is a normal failed refresh."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_first.async_update = AsyncMock(
        side_effect=NotRespondingError("both down")
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_transient_cloud_401_does_not_trigger_reauth(
    hass, entry, device, firmware
):
    """Mirrors the cloud-only contract: a 401 from the update propagates.

    On a multi-device setup a non-auth-provider can see a transient 401 while the
    shared token rotates; turning that into a reauth flow would be wrong.
    """
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_first.async_update = AsyncMock(side_effect=AuthFailedError("401"))
    entry.async_start_reauth = Mock()

    with pytest.raises(AuthFailedError):
        await coordinator._async_update_data()

    entry.async_start_reauth.assert_not_called()


# ---------------------------------------------------------------------------
# Local-only sensors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_circuit_pump_status_distinguishes_off_from_missing(
    hass, entry, device, firmware
):
    """A stopped pump is off; a missing local resource is unavailable."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_data = _local_device(
        resources={
            "/heatingCircuits/hc1/pumpStatus": {"value": "on"},
            "/heatingCircuits/hc2/pumpStatus": {"value": "off"},
        }
    )
    coordinator.local_healthy = True
    hc1 = BoschComK40LocalPumpStatusSensor(coordinator, "hc1")
    hc2 = BoschComK40LocalPumpStatusSensor(coordinator, "hc2")
    hc3 = BoschComK40LocalPumpStatusSensor(coordinator, "hc3")

    assert hc1.is_on is True and hc1.available
    assert hc2.is_on is False and hc2.available
    assert hc3.is_on is None and not hc3.available
    coordinator.local_data = _local_device(
        resources={"/heatingCircuits/hc1/pumpStatus": {"value": 1}}
    )
    hc1 = BoschComK40LocalPumpStatusSensor(coordinator, "hc1")
    assert hc1.is_on is None and not hc1.available
    coordinator.local_healthy = False
    assert not hc1.available


@pytest.mark.asyncio
async def test_local_pump_entities_wait_for_served_circuit(
    hass, entry, device, firmware
):
    """Unsupported circuits stay absent; a later local read can add one."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.async_set_updated_data(
        replace(
            _cloud_device(),
            heating_circuits=[
                {"id": f"/heatingCircuits/hc{number}"} for number in range(1, 4)
            ],
        )
    )
    coordinator.local_data = _local_device(
        resources={"/heatingCircuits/hc1/pumpStatus": {"value": "on"}}
    )
    coordinator.local_healthy = True
    entry.runtime_data = [coordinator]
    entities = []

    await binary_sensor_async_setup_entry(hass, entry, entities.extend)
    assert [e._resource for e in entities] == ["/heatingCircuits/hc1/pumpStatus"]

    coordinator.local_data = _local_device(
        resources={
            "/heatingCircuits/hc1/pumpStatus": {"value": "on"},
            "/heatingCircuits/hc2/pumpStatus": {"value": "off"},
        }
    )
    coordinator.async_update_listeners()
    coordinator.async_update_listeners()
    assert [e._resource for e in entities] == [
        "/heatingCircuits/hc1/pumpStatus",
        "/heatingCircuits/hc2/pumpStatus",
    ]


@pytest.mark.asyncio
async def test_local_circuit_pump_status_adds_to_platform(
    hass, entry, device, firmware, caplog
):
    """A live local status becomes a running binary sensor in HA."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_data = _local_device(
        resources={"/heatingCircuits/hc1/pumpStatus": {"value": "on"}}
    )
    coordinator.local_healthy = True
    pump = BoschComK40LocalPumpStatusSensor(coordinator, "hc1")

    platform = MockEntityPlatform(hass, domain="binary_sensor", platform_name=DOMAIN)
    await platform.async_add_entities([pump])

    assert "Error adding entity" not in caplog.text
    state = hass.states.get(pump.entity_id)
    assert state.state == "on"
    assert state.attributes["device_class"] == "running"

    coordinator.local_data = _local_device(
        resources={"/heatingCircuits/hc1/pumpStatus": {"value": "off"}}
    )
    coordinator.async_update_listeners()
    assert hass.states.get(pump.entity_id).state == "off"

    coordinator.local_healthy = False
    coordinator.async_update_listeners()
    assert hass.states.get(pump.entity_id).state == "unavailable"


def test_emon_field_extraction() -> None:
    """Named keys are pulled out of the gateway's list-of-dicts shape."""
    values = [{"ch": 149}, {"dhw": 129}, {"total": 278}]
    assert _emon_field(values, "ch") == 149
    assert _emon_field(values, "dhw") == 129
    assert _emon_field(values, "missing") is None
    assert _emon_field(None, "ch") is None
    assert _emon_field("not a list", "ch") is None


@pytest.mark.asyncio
async def test_local_sensor_reads_scalar_and_emon_values(hass, entry, device, firmware):
    """A scalar resource and an emon field both resolve to native values."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_data = _local_device()
    coordinator.local_healthy = True

    by_key = {d.key: d for d in LOCAL_SENSORS}
    power = BoschComLocalSensor(coordinator, entry, by_key["local_compressor_power"])
    starts = BoschComLocalSensor(coordinator, entry, by_key["local_starts_dhw"])

    assert power.native_value == 25.0
    assert starts.native_value == 129
    assert power.available is True


@pytest.mark.asyncio
async def test_local_sensors_add_to_the_platform(hass, entry, device, firmware, caplog):
    """Every local sensor survives being added by Home Assistant (issue #184).

    Adding reads fields such as ``suggested_unit_of_measurement`` from the
    entity description, which a plain dataclass description lacks. Building the
    entity directly, as the other tests do, never gets that far.
    """
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_data = _local_device()
    coordinator.local_healthy = True
    sensors = [BoschComLocalSensor(coordinator, entry, d) for d in LOCAL_SENSORS]

    platform = MockEntityPlatform(hass, domain="sensor", platform_name=DOMAIN)
    await platform.async_add_entities(sensors)

    assert "Error adding entity" not in caplog.text
    registry = er.async_get(hass)
    entries = {
        sensor.entity_description.key: registry.async_get(sensor.entity_id)
        for sensor in sensors
    }
    assert all(entries.values())
    disabled = {key for key, reg in entries.items() if reg.disabled_by}
    assert disabled == {
        d.key for d in LOCAL_SENSORS if not d.entity_registry_enabled_default
    }
    assert len(disabled) == 5

    power = hass.states.get(entries["local_compressor_power"].entity_id)
    assert power.state == "25.0"
    assert power.attributes["unit_of_measurement"] == "W"
    assert power.attributes["device_class"] == "power"
    assert power.attributes["state_class"] == "measurement"


@pytest.mark.asyncio
async def test_local_sensor_unavailable_when_local_unhealthy(
    hass, entry, device, firmware
):
    """These entities follow the gateway, not the cloud."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_data = _local_device()
    coordinator.local_healthy = False

    by_key = {d.key: d for d in LOCAL_SENSORS}
    sensor = BoschComLocalSensor(coordinator, entry, by_key["local_compressor_power"])

    assert sensor.available is False


@pytest.mark.asyncio
async def test_local_sensor_missing_resource_is_none(hass, entry, device, firmware):
    """A resource this appliance does not provide yields no value."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_data = _local_device()
    coordinator.local_healthy = True

    by_key = {d.key: d for d in LOCAL_SENSORS}
    sensor = BoschComLocalSensor(coordinator, entry, by_key["local_hot_gas_temp"])

    assert sensor.native_value is None
    assert sensor.available is False


@pytest.mark.asyncio
async def test_local_source_sensor_reports_transport(hass, entry, device, firmware):
    """The diagnostic sensor exposes which transport served the last update."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_source = "local"

    sensor = BoschComLocalSourceSensor(coordinator, entry)
    assert sensor.native_value == "local"

    coordinator.local_source = "both"
    sensor.set_attr()
    assert sensor.native_value == "both"


@pytest.mark.asyncio
async def test_local_sensors_absent_without_local_config(hass, entry, device, firmware):
    """Cloud-only installs must not gain any new entities."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware, local=False)

    assert getattr(coordinator, "local_first", None) is None


def test_every_local_sensor_has_a_unique_key() -> None:
    """Duplicate keys would collide in the entity registry."""
    keys = [d.key for d in LOCAL_SENSORS]
    assert len(keys) == len(set(keys))


@pytest.mark.asyncio
async def test_local_path_still_fetches_extra_endpoints(hass, entry, device, firmware):
    """Enabling local access must not silently stop the mixin's endpoints.

    The local path bypasses _K40ExtraEndpointsMixin._async_update_data, so it has
    to invoke the extra-endpoint and recordings fetches itself. Without this the
    additionalHeater / silentMode / dhwChargeDuration entities would quietly
    freeze for anyone who turns local access on.
    """
    entry.add_to_hass(hass)
    coordinator, bhc = _coordinator(hass, entry, device, firmware)
    coordinator.local_first.async_update = AsyncMock(
        return_value=K40Update(
            local=_local_device(),
            cloud=_cloud_device(),
            source="both",
            local_healthy=True,
        )
    )

    await coordinator._async_update_data()

    bhc.async_get_additional_heater_mode.assert_awaited_once()
    bhc.async_get_silent_mode.assert_awaited_once()
    bhc.async_get_dhw_charge_duration.assert_awaited_once()
    assert coordinator.extra_data["additional_heater"] == {"value": "off"}


# ---------------------------------------------------------------------------
# Local readings in the existing (cloud) entities
# ---------------------------------------------------------------------------

OUTDOOR = "/system/sensors/temperatures/outdoor_t1"


def _resource(path, value, **extra):
    return {path: {"id": path, "type": "floatValue", "value": value, **extra}}


def _cloud_with_circuits():
    """Cloud payload with the nodes the overlay touches."""
    return dataclasses.replace(
        _cloud_device(),
        outdoor_temp={"value": 9.0, "unitOfMeasure": "C"},
        heat_sources={
            "actualSupplyTemperature": {"value": 30.0, "unitOfMeasure": "C"},
            "pumpType": {"value": "air_water"},
        },
        dhw_circuits=[
            {
                "id": "/dhwCircuits/dhw1",
                "actualTemp": {"value": 40.0},
                "currentTemperatureLevel": {
                    "value": "eco",
                    "allowedValues": ["off", "eco", "low", "high"],
                },
                "operationMode": {"value": "ownprogram"},
            }
        ],
        heating_circuits=[
            {"id": "/heatingCircuits/hc1", "currentSuWiMode": {"value": "off"}}
        ],
    )


def test_overlay_replaces_shared_values_and_keeps_cloud_only_ones() -> None:
    """Same entities, one value each: the gateway's where it has one."""
    local = _local_device(
        resources={
            **_resource(OUTDOOR, 7.1, unitOfMeasure="C"),
            **_resource("/heatSources/actualSupplyTemperature", 28.8),
            **_resource("/heatSources/systemPressure", 1.7),
            **_resource("/dhwCircuits/dhw1/actualTemp", 36.5),
            "/dhwCircuits/dhw1/currentTemperatureLevel": {"value": "off"},
            "/heatingCircuits/hc1/currentSuWiMode": {"value": "forced"},
        }
    )

    data = _overlay_local(_cloud_with_circuits(), local)

    assert data.outdoor_temp == {
        "id": OUTDOOR,
        "type": "floatValue",
        "value": 7.1,
        "unitOfMeasure": "C",
    }
    assert data.heat_sources["actualSupplyTemperature"]["value"] == 28.8
    # Cloud lacked it, the gateway has it: now available.
    assert data.heat_sources["systemPressure"]["value"] == 1.7
    # Only the cloud has it: untouched.
    assert data.heat_sources["pumpType"] == {"value": "air_water"}
    dhw = data.dhw_circuits[0]
    assert dhw["actualTemp"]["value"] == 36.5
    # Merged, not swapped: the cloud's allowedValues survive.
    assert dhw["currentTemperatureLevel"] == {
        "value": "off",
        "allowedValues": ["off", "eco", "low", "high"],
    }
    assert dhw["operationMode"] == {"value": "ownprogram"}
    assert data.heating_circuits[0]["currentSuWiMode"]["value"] == "forced"


def test_overlay_does_not_mutate_the_cloud_payload() -> None:
    """The held cloud data is reused each cycle, so it must stay pristine."""
    cloud = _cloud_with_circuits()
    _overlay_local(
        cloud, _local_device(resources=_resource("/dhwCircuits/dhw1/actualTemp", 1.0))
    )
    assert cloud.dhw_circuits[0]["actualTemp"] == {"value": 40.0}


def test_overlay_without_local_data_is_a_no_op() -> None:
    """No gateway payload, no change."""
    cloud = _cloud_with_circuits()
    assert _overlay_local(cloud, None) is cloud


@pytest.mark.asyncio
async def test_both_transports_ok_prefers_the_gateway_values(
    hass, entry, device, firmware
):
    """With both answering, a shared value comes from the gateway."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_first.async_update = AsyncMock(
        return_value=K40Update(
            local=_local_device(resources=_resource(OUTDOOR, 7.1)),
            cloud=_cloud_device(),
            source="both",
            local_healthy=True,
        )
    )

    data = await coordinator._async_update_data()

    assert data.outdoor_temp["value"] == 7.1


def _token_owner(hass, entry, device, firmware, token_error):
    """A local-enabled coordinator that owns the token and fails to refresh it."""
    coordinator, bhc = _coordinator(hass, entry, device, firmware)
    coordinator.auth_provider = True
    coordinator.data = _cloud_with_circuits()
    bhc.get_token = AsyncMock(side_effect=token_error)
    coordinator.local_first.async_update = AsyncMock()
    coordinator.local_client.async_update = AsyncMock(
        return_value=_local_device(resources=_resource(OUTDOOR, 7.1))
    )
    return coordinator, bhc


@pytest.mark.asyncio
async def test_rejected_token_keeps_the_entities_live_and_starts_reauth(
    hass, entry, device, firmware
):
    """A dead refresh token must not take the gateway readings down with it."""
    entry.add_to_hass(hass)
    coordinator, bhc = _token_owner(
        hass, entry, device, firmware, AuthFailedError("Failed to refresh")
    )
    entry.async_start_reauth = Mock()

    data = await coordinator._async_update_data()

    entry.async_start_reauth.assert_called_once()
    assert data.outdoor_temp["value"] == 7.1
    assert data.heat_sources["actualSupplyTemperature"]["value"] == 30.0
    # The cloud is not asked again: its own token check would only fail.
    coordinator.local_first.async_update.assert_not_awaited()
    bhc.async_get_additional_heater_mode.assert_not_awaited()
    assert coordinator.local_source == "local"
    assert coordinator.local_healthy is True


@pytest.mark.asyncio
async def test_unreachable_token_endpoint_serves_local_without_reauth(
    hass, entry, device, firmware
):
    """A DNS timeout on the token endpoint is no reason to bother the user."""
    entry.add_to_hass(hass)
    coordinator, _ = _token_owner(
        hass,
        entry,
        device,
        firmware,
        NotRespondingError("https://singlekey-id.com/auth/connect/token"),
    )
    entry.async_start_reauth = Mock()

    data = await coordinator._async_update_data()

    entry.async_start_reauth.assert_not_called()
    assert data.outdoor_temp["value"] == 7.1


@pytest.mark.asyncio
async def test_unusable_token_and_unreachable_gateway_fails(
    hass, entry, device, firmware
):
    """With both down there is nothing current to show."""
    entry.add_to_hass(hass)
    coordinator, _ = _token_owner(
        hass, entry, device, firmware, AuthFailedError("Failed to refresh")
    )
    coordinator.local_healthy = True
    coordinator.local_client.async_update = AsyncMock(
        side_effect=NotRespondingError("gateway")
    )
    entry.async_start_reauth = Mock()

    with pytest.raises(UpdateFailed, match="No usable cloud token"):
        await coordinator._async_update_data()

    assert coordinator.local_healthy is False


@pytest.mark.asyncio
async def test_unusable_token_skips_a_parked_local_transport(
    hass, entry, device, firmware
):
    """A gateway token that was already rejected is not retried here either."""
    entry.add_to_hass(hass)
    coordinator, _ = _token_owner(
        hass, entry, device, firmware, AuthFailedError("Failed to refresh")
    )
    coordinator.local_first._local_disabled = True
    entry.async_start_reauth = Mock()

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    coordinator.local_client.async_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_token_refresh_dns_timeout_without_local_is_update_failed(
    hass, entry, device, firmware
):
    """Cloud-only: an unreachable token endpoint is a plain UpdateFailed."""
    entry.add_to_hass(hass)
    coordinator, bhc = _coordinator(hass, entry, device, firmware, local=False)
    coordinator.auth_provider = True
    bhc.get_token = AsyncMock(side_effect=NotRespondingError("token endpoint"))

    with pytest.raises(UpdateFailed, match="Token refresh failed"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_cloud_only_values_go_empty_after_the_bound(
    hass, entry, device, firmware
):
    """Shared values stay live; cloud-only ones are held briefly, then cleared."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.data = dataclasses.replace(
        _cloud_with_circuits(), notifications=[{"code": "A01"}]
    )
    coordinator.local_first.async_update = AsyncMock(
        return_value=K40Update(
            local=_local_device(resources=_resource(OUTDOOR, 7.1)),
            cloud=None,
            source="local",
            local_healthy=True,
            cloud_error="504",
        )
    )

    for _ in range(MAX_CLOUD_FAILURES_WITH_LOCAL):
        coordinator.data = await coordinator._async_update_data()
    assert coordinator.data.notifications == [{"code": "A01"}]
    assert coordinator.data.dhw_circuits[0]["operationMode"] == {"value": "ownprogram"}

    coordinator.data = await coordinator._async_update_data()

    assert coordinator.data.notifications is None
    assert "operationMode" not in coordinator.data.dhw_circuits[0]
    assert coordinator.data.outdoor_temp["value"] == 7.1


@pytest.mark.asyncio
async def test_cloud_back_reloads_an_entry_set_up_without_it(
    hass, entry, device, firmware
):
    """Cloud-only entities were never created, so reload once the cloud answers."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.cloud_setup_pending = True
    coordinator.local_first.async_update = AsyncMock(
        return_value=K40Update(
            local=_local_device(),
            cloud=_cloud_device(),
            source="both",
            local_healthy=True,
        )
    )

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        await coordinator._async_update_data()
        await coordinator._async_update_data()

    reload.assert_called_once_with(entry.entry_id)
    assert coordinator.cloud_setup_pending is False


def _local_entry(**data):
    return MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        unique_id="test-user",
        data={
            CONF_DEVICES: {f"{GATEWAY}_k40": True, "555_rac": True},
            CONF_LOCAL: {
                GATEWAY: {CONF_LOCAL_HOST: "192.0.2.10", CONF_LOCAL_TOKEN: LOCAL_TOKEN}
            },
            CONF_REFRESH: "refresh",
            CONF_TOKEN: "token",
            CONF_USERNAME: "test-user",
            **data,
        },
    )


def test_local_only_devices_come_from_the_entry() -> None:
    """Only selected gateways with local access can be set up without the cloud."""
    assert _local_only_devices(_local_entry()) == [
        {"deviceId": GATEWAY, "deviceType": "k40"}
    ]
    assert _local_only_devices(_local_entry(**{CONF_LOCAL: {}})) == []
    assert (
        _local_only_devices(_local_entry(**{CONF_DEVICES: {f"{GATEWAY}_k40": False}}))
        == []
    )


@pytest.mark.parametrize(
    ("cloud_error", "reauth"),
    [(AuthFailedError("Failed to refresh"), True), (ApiError("504"), False)],
)
async def test_setup_without_the_cloud_uses_the_gateway(hass, cloud_error, reauth):
    """An expired login or a cloud outage at startup still sets up the gateway."""
    entry = _local_entry()
    entry.add_to_hass(hass)
    local = _local_device(
        resources={
            **_resource(OUTDOOR, 7.1, unitOfMeasure="C"),
            **_resource("/heatSources/actualSupplyTemperature", 28.8),
            **_resource("/dhwCircuits/dhw1/actualTemp", 36.5),
        }
    )
    bhc = AsyncMock()
    bhc.token = "token"
    bhc.refresh_token = "refresh"
    bhc.async_get_devices.side_effect = cloud_error

    with (
        patch(
            "custom_components.bosch_homecom.HomeComAlt.create",
            new=AsyncMock(return_value=bhc),
        ),
        patch(
            "custom_components.bosch_homecom.HomeComK40.get_token",
            new=AsyncMock(side_effect=cloud_error),
        ),
        patch(
            "custom_components.bosch_homecom.HomeComK40.async_update",
            new=AsyncMock(side_effect=ApiError("504")),
        ),
        patch(
            "custom_components.bosch_homecom.HomeComK40Local.async_update",
            new=AsyncMock(return_value=local),
        ),
        patch.object(entry, "async_start_reauth") as start_reauth,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert bool(start_reauth.call_count) is reauth
        (coordinator,) = entry.runtime_data
        assert coordinator.cloud_setup_pending is True
        assert coordinator.data.outdoor_temp["value"] == 7.1

        outdoor = [
            state for state in hass.states.async_all("sensor") if state.state == "7.1"
        ]
        assert outdoor, "outdoor temperature entity not served from the gateway"

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_setup_without_cloud_or_local_access_still_fails(hass):
    """Nothing to read locally: keep the old behaviour (reauth / retry)."""
    entry = _local_entry(**{CONF_LOCAL: {}})
    entry.add_to_hass(hass)
    bhc = AsyncMock()
    bhc.async_get_devices.side_effect = AuthFailedError("Failed to refresh")

    with patch(
        "custom_components.bosch_homecom.HomeComAlt.create",
        new=AsyncMock(return_value=bhc),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR


def test_overlay_derives_the_operation_modes_from_the_status() -> None:
    """No operationMode resource locally: it comes from overallStatus."""
    cloud = dataclasses.replace(
        _cloud_with_circuits(),
        heating_circuits=[
            {
                "id": "/heatingCircuits/hc1",
                "operationMode": {
                    "value": "auto",
                    "allowedValues": ["off", "manual", "auto"],
                },
            }
        ],
    )
    local = _local_device(hc_status="heating_manual_on", dhw_mode="eco")

    data = _overlay_local(cloud, local)

    assert data.heating_circuits[0]["operationMode"] == {
        "value": "manual",
        "allowedValues": ["off", "manual", "auto"],
    }
    assert data.dhw_circuits[0]["operationMode"]["value"] == "eco"


def test_overlay_keeps_the_mode_for_statuses_without_one() -> None:
    """Away, holiday and the like say nothing about the mode."""
    cloud = _cloud_with_circuits()
    data = _overlay_local(cloud, _local_device(hc_status="away", dhw_mode=None))

    assert "operationMode" not in data.heating_circuits[0]
    assert data.dhw_circuits[0]["operationMode"] == {"value": "ownprogram"}
