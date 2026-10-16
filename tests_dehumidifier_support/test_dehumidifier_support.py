"""Check 6000i/8000i dehumidifier mapping and entity-ID migration.

Uses real Home Assistant 2026.9.1 entity classes and homecom_alt 1.8.2.
Only the network transport is mocked; no Bosch account is used.
The fixture is a 6000i capture; 8000i cases simulate the shared capability schema.
"""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.humidifier import HumidifierAction, HumidifierDeviceClass
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry, entity_registry
from homecom_alt import BaconMqttClient

from custom_components.bosch_homecom.dehumidifier import (
    BoschComDehumidifier,
    BoschComDehumidifierHumidity,
    _async_migrate_dehumidifier_ids,
    async_setup_dehumidifier_entities,
    dehumidifier_status_entities,
    is_dehumidifier_device,
)


def make_coordinator(model="6000i"):
    payload = json.loads(
        (Path(__file__).parent / "dehumidifier_sample.json").read_text()
    )
    payload["info"]["appliance"]["type"] = f"dry_{model}_v2"
    coordinator = MagicMock()
    coordinator.unique_id = "TEST-DEHUMIDIFIER-001"
    coordinator.device_info = {
        "identifiers": {("bosch_homecom", "TEST-DEHUMIDIFIER-001")}
    }
    coordinator.data = SimpleNamespace(**payload)
    coordinator.last_update_success = True
    coordinator.async_request_refresh = AsyncMock()
    coordinator.client.async_set_desired = AsyncMock()
    return coordinator


@pytest.fixture
async def registry_hass(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    device_registry.async_setup(hass)
    await device_registry.async_load(hass)
    await entity_registry.async_load(hass)
    try:
        yield hass
    finally:
        await hass.async_stop(force=True)


@pytest.mark.parametrize("model", ["6000i", "8000i"])
def test_payload_mapping_and_modes(model):
    coordinator = make_coordinator(model)
    control = BoschComDehumidifier(coordinator)
    humidity = BoschComDehumidifierHumidity(coordinator)
    assert is_dehumidifier_device(coordinator)
    assert control.device_class == HumidifierDeviceClass.DEHUMIDIFIER
    assert control.is_on is True
    assert control.target_humidity == 40
    assert control.current_humidity == humidity.native_value == 42
    assert (
        control.min_humidity,
        control.max_humidity,
        control.target_humidity_step,
    ) == (40, 70, 5)
    assert control.available_modes == ["auto", "night", "laundry"]
    assert control.mode == "auto"
    assert control.action == HumidifierAction.DRYING
    assert control.available is True
    assert all(
        status.is_on is False for status in dehumidifier_status_entities(coordinator)
    )
    assert "measured_at" in humidity.extra_state_attributes


def test_missing_data_is_unknown_and_offline_is_unavailable():
    coordinator = make_coordinator()
    coordinator.data.sensor = None
    coordinator.data.reported = {}
    control = BoschComDehumidifier(coordinator)
    assert control.current_humidity is None
    assert control.target_humidity is None
    assert control.is_on is None
    assert control.action is None
    assert all(
        status.is_on is None for status in dehumidifier_status_entities(coordinator)
    )
    coordinator.data.info = {"online": False}
    assert control.available is False
    coordinator.data = None
    assert control.target_humidity is None
    assert control.current_humidity is None


def test_blocked_or_idle_device_does_not_report_drying():
    coordinator = make_coordinator()
    control = BoschComDehumidifier(coordinator)
    for flag in ("idleState", "waterTankFull", "defrostingActive"):
        coordinator.data.sensor[flag] = True
        assert control.action == HumidifierAction.IDLE
        coordinator.data.sensor[flag] = False
    coordinator.data.reported["powerEnabled"] = False
    assert control.action == HumidifierAction.OFF


@pytest.mark.parametrize("model", ["6000i", "8000i"])
@pytest.mark.asyncio
async def test_exact_mqtt_commands_and_reported_confirmation(model):
    coordinator = make_coordinator(model)
    control = BoschComDehumidifier(coordinator)
    await control.async_turn_off()
    await control.async_turn_on()
    await control.async_set_mode("night")
    await control.async_set_humidity(55)
    assert [
        call.args for call in coordinator.client.async_set_desired.await_args_list
    ] == [
        ("TEST-DEHUMIDIFIER-001", {"powerEnabled": False}),
        ("TEST-DEHUMIDIFIER-001", {"powerEnabled": True}),
        ("TEST-DEHUMIDIFIER-001", {"opMode": "night"}),
        ("TEST-DEHUMIDIFIER-001", {"humiditySetpoint": 55}),
    ]
    # Publishing desired settings must not pretend the device confirmed them.
    assert control.target_humidity == 40
    assert control.mode == "auto"
    coordinator.data.reported.update(humiditySetpoint=55, opMode="night")
    assert control.target_humidity == 55
    assert control.mode == "night"


@pytest.mark.parametrize(
    "target", [39, 71, 42, -1, True, "50", float("nan"), float("inf")]
)
@pytest.mark.asyncio
async def test_invalid_humidity_never_publishes(target):
    coordinator = make_coordinator()
    with pytest.raises(ServiceValidationError):
        await BoschComDehumidifier(coordinator).async_set_humidity(target)
    coordinator.client.async_set_desired.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_ac_modes_and_read_only_fields_never_publish():
    coordinator = make_coordinator()
    control = BoschComDehumidifier(coordinator)
    for mode in ("heat", "cool", "dry", "fan"):
        with pytest.raises(ServiceValidationError):
            await control.async_set_mode(mode)
    coordinator.data.metadata["shadows"]["state"]["powerEnabled"]["ro"] = True
    with pytest.raises(ServiceValidationError):
        await control.async_turn_on()
    coordinator.client.async_set_desired.assert_not_awaited()


@pytest.mark.asyncio
async def test_laundry_to_auto_when_setting_humidity():
    coordinator = make_coordinator()
    coordinator.data.reported["opMode"] = "laundry"
    await BoschComDehumidifier(coordinator).async_set_humidity(50)
    coordinator.client.async_set_desired.assert_awaited_once_with(
        "TEST-DEHUMIDIFIER-001", {"humiditySetpoint": 50, "opMode": "auto"}
    )


@pytest.mark.asyncio
async def test_real_library_builds_the_expected_shadow_message():
    coordinator = make_coordinator()
    client = BaconMqttClient("dehumidifier-test-client")
    client._sub = "dehumidifier-test-user"
    client._client = MagicMock()
    coordinator.client = client
    await BoschComDehumidifier(coordinator).async_set_humidity(50)
    topic, raw = client._client.publish.call_args.args
    assert (
        topic
        == "users/dehumidifier-test-user/devices/TEST-DEHUMIDIFIER-001/shadows/state/update"
    )
    assert json.loads(raw) == {"state": {"desired": {"humiditySetpoint": 50}}}


@pytest.mark.asyncio
async def test_discovery_waits_for_device_information_and_adds_only_once(registry_hass):
    coordinator = make_coordinator()
    saved = deepcopy(coordinator.data)
    coordinator.data.info = None
    coordinator.data.metadata = None
    coordinator.data.reported = {"powerEnabled": True}
    entry = MagicMock(runtime_data=[coordinator])
    added = []
    async_setup_dehumidifier_entities(
        registry_hass, entry, added.extend, lambda c: [BoschComDehumidifier(c)]
    )
    assert added == []
    discover = coordinator.async_add_listener.call_args.args[0]
    coordinator.data = saved
    discover()
    discover()
    assert len(added) == 1
    entry.async_on_unload.assert_called_once()


@pytest.mark.asyncio
async def test_real_air_conditioner_gets_no_dehumidifier_entities(registry_hass):
    coordinator = make_coordinator()
    coordinator.data.info = {"appliance": {"type": "climate_6000i"}}
    coordinator.data.reported = {"powerEnabled": True, "tempSetpoint": 23}
    coordinator.data.metadata = {"shadows": {"state": {"tempSetpoint": {"min": 16}}}}
    assert not is_dehumidifier_device(coordinator)
    added = []
    entry = MagicMock(runtime_data=[coordinator])
    async_setup_dehumidifier_entities(
        registry_hass, entry, added.extend, lambda c: [BoschComDehumidifier(c)]
    )
    assert added == []


@pytest.mark.parametrize("model", ["6000i", "8000i"])
@pytest.mark.asyncio
async def test_entity_and_setpoint_service_in_real_home_assistant(tmp_path, model):
    """Exercise actual HA entity registration and its set_humidity service."""
    from homeassistant.components.humidifier import DATA_COMPONENT, async_setup
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import device_registry, entity_registry

    hass = HomeAssistant(str(tmp_path))
    try:
        device_registry.async_setup(hass)
        await device_registry.async_load(hass)
        await entity_registry.async_load(hass)
        await async_setup(hass, {})
        coordinator = make_coordinator(model)
        control = BoschComDehumidifier(coordinator)
        # This isolated HA component has no config entry/device registry owner.
        # Device linking is exercised by the normal integration at installation.
        control._attr_device_info = None
        await hass.data[DATA_COMPONENT].async_add_entities([control])
        await hass.async_block_till_done()
        state = hass.states.get(control.entity_id)
        assert state.state == "on"
        assert state.attributes["device_class"] == "dehumidifier"
        assert state.attributes["humidity"] == 40
        assert state.attributes["current_humidity"] == 42
        await hass.services.async_call(
            "humidifier",
            "set_humidity",
            {"entity_id": control.entity_id, "humidity": 55},
            blocking=True,
        )
        coordinator.client.async_set_desired.assert_awaited_once_with(
            "TEST-DEHUMIDIFIER-001", {"humiditySetpoint": 55}
        )
    finally:
        await hass.async_stop(force=True)


@pytest.mark.parametrize("model", ["6000i", "8000i"])
def test_humidity_limits_and_modes_follow_each_devices_metadata(model):
    coordinator = make_coordinator(model)
    metadata = coordinator.data.metadata["shadows"]["state"]
    metadata["humiditySetpoint"].update(min=35, max=75, step=10)
    metadata["opMode"]["enum"] = ["auto", "night"]
    control = BoschComDehumidifier(coordinator)
    assert (
        control.min_humidity,
        control.max_humidity,
        control.target_humidity_step,
    ) == (35, 75, 10)
    assert control.available_modes == ["auto", "night"]


def test_known_air_conditioner_with_humidity_feature_is_not_misidentified():
    coordinator = make_coordinator()
    coordinator.data.info["appliance"]["type"] = "climate_6000i"
    assert not is_dehumidifier_device(coordinator)


def test_humidity_capability_identifies_device_before_identity_arrives():
    coordinator = make_coordinator()
    coordinator.data.info = None
    assert is_dehumidifier_device(coordinator)
    coordinator.data.metadata["shadows"]["state"]["tempSetpoint"] = {"min": 16}
    assert not is_dehumidifier_device(coordinator)


@pytest.mark.asyncio
async def test_legacy_unique_ids_migrate_without_changing_entity_ids_or_names(
    registry_hass,
):
    registry = entity_registry.async_get(registry_hass)
    coordinator = make_coordinator()
    entry = SimpleNamespace(
        entry_id="dehumidifier-test-entry",
        pref_disable_new_entities=False,
        runtime_data=[coordinator],
    )
    created = []
    with patch.object(
        registry_hass.config_entries, "async_get_entry", return_value=entry
    ):
        for domain, suffix in [
            ("humidifier", "control"),
            ("sensor", "humidity"),
            ("binary_sensor", "waterTankFull"),
            ("binary_sensor", "defrostingActive"),
            ("binary_sensor", "condensatePumpRunning"),
            ("binary_sensor", "idleState"),
        ]:
            registered = registry.async_get_or_create(
                domain,
                "bosch_homecom",
                f"{coordinator.unique_id}-dry-{suffix}",
                config_entry=entry,
            )
            registered = registry.async_update_entity(
                registered.entity_id, name=f"My {suffix}"
            )
            created.append((registered.entity_id, domain, suffix))
        unrelated = registry.async_get_or_create(
            "sensor", "bosch_homecom", "OTHER-DEVICE-dry-humidity", config_entry=entry
        )
        _async_migrate_dehumidifier_ids(registry_hass, entry)
        _async_migrate_dehumidifier_ids(registry_hass, entry)
    for entity_id, domain, suffix in created:
        current = registry.async_get(entity_id)
        assert current.name == f"My {suffix}"
        assert current.unique_id == f"{coordinator.unique_id}-dehumidifier-{suffix}"
        assert (
            registry.async_get_entity_id(domain, "bosch_homecom", current.unique_id)
            == entity_id
        )
    assert (
        registry.async_get(unrelated.entity_id).unique_id == "OTHER-DEVICE-dry-humidity"
    )
    assert len(registry.entities) == 7


@pytest.mark.asyncio
async def test_migration_does_not_overwrite_an_existing_new_entity(registry_hass):
    registry = entity_registry.async_get(registry_hass)
    coordinator = make_coordinator()
    entry = SimpleNamespace(
        entry_id="dehumidifier-test-entry",
        pref_disable_new_entities=False,
        runtime_data=[coordinator],
    )
    with patch.object(
        registry_hass.config_entries, "async_get_entry", return_value=entry
    ):
        old = registry.async_get_or_create(
            "sensor",
            "bosch_homecom",
            f"{coordinator.unique_id}-dry-humidity",
            config_entry=entry,
        )
        current = registry.async_get_or_create(
            "sensor",
            "bosch_homecom",
            f"{coordinator.unique_id}-dehumidifier-humidity",
            config_entry=entry,
        )
        _async_migrate_dehumidifier_ids(registry_hass, entry)
    assert registry.async_get(old.entity_id).unique_id.endswith("-dry-humidity")
    assert registry.async_get(current.entity_id).unique_id.endswith(
        "-dehumidifier-humidity"
    )
    assert len(registry.entities) == 2
