"""Tests for the optional K 40 RF Local API support.

Covers the options-flow steps where the user enters the gateway details, the
coordinator's local-first behaviour, and the local-only sensors.
"""

from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import CONF_TOKEN, CONF_USERNAME
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
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom.const import (
    CONF_DEVICES,
    CONF_LOCAL,
    CONF_LOCAL_GATEWAY,
    CONF_LOCAL_HOST,
    CONF_LOCAL_LOGIN,
    CONF_LOCAL_PASSWORD,
    CONF_LOCAL_REMOVE,
    CONF_LOCAL_TOKEN,
    DOMAIN,
    MAX_CLOUD_FAILURES_WITH_LOCAL,
)
from custom_components.bosch_homecom.coordinator import BoschComModuleCoordinatorK40
from custom_components.bosch_homecom.local_sensor import (
    LOCAL_SENSORS,
    BoschComLocalSensor,
    BoschComLocalSourceSensor,
    _emon_field,
)

HOST = "192.0.2.10"
GATEWAY = "102128202"
LOCAL_TOKEN = "local-token"  # noqa: S105 - test fixture


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
        result["flow_id"], {CONF_LOCAL_GATEWAY: "555_k40".split("_")[0]}
    )
    assert result["step_id"] == "local_credentials"


@pytest.mark.asyncio
async def test_local_aborts_without_a_k40(hass):
    """A cloud account with no k40/k30 has nothing to configure locally."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_DEVICES: {"999_rac": True}},
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

    with patch(
        "custom_components.bosch_homecom.config_flow.HomeComK40Local.async_create_token",
        new=fake_create,
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
    coordinator, _ = _coordinator(hass, entry, device, firmware)
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

    assert data is previous
    assert coordinator.local_source == "local"


@pytest.mark.asyncio
async def test_cloud_outage_staleness_is_bounded(hass, entry, device, firmware):
    """Held cloud data expires so a long outage does not look healthy forever."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.data = _cloud_device()
    coordinator.local_first.async_update = AsyncMock(
        return_value=K40Update(
            local=_local_device(),
            cloud=None,
            source="local",
            local_healthy=True,
            cloud_error="504",
        )
    )

    for _ in range(MAX_CLOUD_FAILURES_WITH_LOCAL):
        await coordinator._async_update_data()

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


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
async def test_no_previous_data_fails_instead_of_returning_none(
    hass, entry, device, firmware
):
    """At startup there is nothing to hold, so the refresh must fail properly."""
    entry.add_to_hass(hass)
    coordinator, _ = _coordinator(hass, entry, device, firmware)
    coordinator.local_first.async_update = AsyncMock(
        return_value=K40Update(
            local=_local_device(),
            cloud=None,
            source="local",
            local_healthy=True,
            cloud_error="504",
        )
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


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
