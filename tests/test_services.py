"""Tests for the DHW custom actions (#200).

The target is resolved through the entity and device registries, so a renamed
device or entity, the default K40 naming and a wddw2 circuit all work, and an
entity the integration does not own raises instead of silently succeeding.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.const import CONF_USERNAME
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homecom_alt import ApiError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.bosch_homecom.const import DOMAIN


def _coordinator(device_id: str, device_type: str, circuits: list[str]):
    return SimpleNamespace(
        device={"deviceId": device_id, "deviceType": device_type},
        unique_id=device_id,
        bhc=AsyncMock(),
        async_request_refresh=AsyncMock(),
        data=SimpleNamespace(
            dhw_circuits=[{"id": f"/dhwCircuits/{c}"} for c in circuits]
        ),
    )


async def _setup(hass, coordinators):
    """Register the services and one entry whose runtime data is given."""
    assert await async_setup_component(hass, DOMAIN, {}) is True
    entry = MockConfigEntry(domain=DOMAIN, title="t", data={CONF_USERNAME: "t"})
    entry.add_to_hass(hass)
    entry.runtime_data = coordinators
    return entry


def _register(hass, entry, device_id: str, unique_id: str, object_id: str) -> str:
    """Create the device and a water heater entity the way HA would, renamed."""
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, device_id)}
    )
    return (
        er.async_get(hass)
        .async_get_or_create(
            "water_heater",
            DOMAIN,
            unique_id,
            suggested_object_id=object_id,
            device_id=device.id,
            config_entry=entry,
        )
        .entity_id
    )


@pytest.mark.asyncio
async def test_extrahot_water_resolves_renamed_entity(hass):
    """A renamed device/entity still reaches the right device and circuit."""
    coordinator = _coordinator("123", "k40", ["dhw1"])
    entry = await _setup(hass, [coordinator])
    entity_id = _register(
        hass, entry, "123", "123-waterheater", "ivt_geo_612_water_heater_dhw1"
    )
    assert entity_id == "water_heater.ivt_geo_612_water_heater_dhw1"

    await hass.services.async_call(
        DOMAIN,
        "set_dhw_extrahot_water",
        {"entity_id": entity_id, "mode": "start", "duration": 60},
        blocking=True,
    )

    coordinator.bhc.async_set_dhw_charge_duration.assert_awaited_once_with(
        "123", "dhw1", 60
    )
    coordinator.bhc.async_set_dhw_charge.assert_awaited_once_with(
        "123", "dhw1", "start"
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_extrahot_water_stop_skips_duration(hass):
    """Stopping writes only the charge mode."""
    coordinator = _coordinator("123", "k40", ["dhw1"])
    entry = await _setup(hass, [coordinator])
    entity_id = _register(
        hass, entry, "123", "123-waterheater", "boschcom_k40_123_waterheater"
    )

    await hass.services.async_call(
        DOMAIN,
        "set_dhw_extrahot_water",
        {"entity_id": [entity_id], "mode": "stop"},
        blocking=True,
    )

    coordinator.bhc.async_set_dhw_charge_duration.assert_not_awaited()
    coordinator.bhc.async_set_dhw_charge.assert_awaited_once_with("123", "dhw1", "stop")


@pytest.mark.asyncio
async def test_dhw_temperature_uses_circuit_from_unique_id(hass):
    """A wddw2 water heater carries its circuit in the unique id."""
    coordinator = _coordinator("456", "wddw2", ["dhw1", "dhw2"])
    entry = await _setup(hass, [coordinator])
    entity_id = _register(hass, entry, "456", "456-dhw2", "boiler_dhw2_waterheater")

    await hass.services.async_call(
        DOMAIN,
        "set_dhw_tempreture",
        {"entity_id": entity_id, "level": "high", "temperature": 50.0},
        blocking=True,
    )

    coordinator.bhc.async_set_dhw_temp_level.assert_awaited_once_with(
        "456", "dhw2", "high", 50.0
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_dhw_service_rejects_foreign_entity(hass):
    """An entity the integration does not own raises instead of succeeding."""
    coordinator = _coordinator("123", "k40", ["dhw1"])
    entry = await _setup(hass, [coordinator])
    er.async_get(hass).async_get_or_create(
        "water_heater", "other", "x-1", suggested_object_id="other_heater"
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_dhw_extrahot_water",
            {"entity_id": "water_heater.other_heater", "mode": "stop"},
            blocking=True,
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_dhw_extrahot_water",
            {"entity_id": "water_heater.does_not_exist", "mode": "stop"},
            blocking=True,
        )

    coordinator.bhc.async_set_dhw_charge.assert_not_awaited()
    assert entry.runtime_data[0] is coordinator


@pytest.mark.asyncio
async def test_dhw_service_rejects_ambiguous_circuit(hass):
    """No dhwN in the unique id and several circuits cannot be guessed."""
    coordinator = _coordinator("789", "k40", ["dhw1", "dhw2"])
    entry = await _setup(hass, [coordinator])
    entity_id = _register(hass, entry, "789", "789-waterheater", "pump_waterheater")

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_dhw_extrahot_water",
            {"entity_id": entity_id, "mode": "stop"},
            blocking=True,
        )

    coordinator.bhc.async_set_dhw_charge.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        {"mode": "halt"},
        {"mode": None},
        {},
        {"mode": "start", "duration": 0},
        {"mode": "start", "duration": "an hour"},
    ],
)
async def test_extrahot_water_rejects_bad_input_before_writing(hass, data):
    """A missing or wrong field is an error, not a null write to the device (#219)."""
    coordinator = _coordinator("123", "k40", ["dhw1"])
    entry = await _setup(hass, [coordinator])
    entity_id = _register(
        hass, entry, "123", "123-waterheater", "boschcom_k40_123_waterheater"
    )

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "set_dhw_extrahot_water",
            {"entity_id": entity_id, **data},
            blocking=True,
        )

    coordinator.bhc.async_set_dhw_charge.assert_not_awaited()
    coordinator.bhc.async_set_dhw_charge_duration.assert_not_awaited()


@pytest.mark.asyncio
async def test_extrahot_water_start_without_duration_keeps_the_device_setting(hass):
    """A start without a duration writes only the charge, not a null duration."""
    coordinator = _coordinator("123", "k40", ["dhw1"])
    entry = await _setup(hass, [coordinator])
    entity_id = _register(
        hass, entry, "123", "123-waterheater", "boschcom_k40_123_waterheater"
    )

    await hass.services.async_call(
        DOMAIN,
        "set_dhw_extrahot_water",
        {"entity_id": entity_id, "mode": "start"},
        blocking=True,
    )

    coordinator.bhc.async_set_dhw_charge_duration.assert_not_awaited()
    coordinator.bhc.async_set_dhw_charge.assert_awaited_once_with(
        "123", "dhw1", "start"
    )


@pytest.mark.asyncio
async def test_extrahot_water_duration_is_coerced_to_an_integer(hass):
    """The UI sends the number as a string or float; the device gets minutes."""
    coordinator = _coordinator("123", "k40", ["dhw1"])
    entry = await _setup(hass, [coordinator])
    entity_id = _register(
        hass, entry, "123", "123-waterheater", "boschcom_k40_123_waterheater"
    )

    await hass.services.async_call(
        DOMAIN,
        "set_dhw_extrahot_water",
        {"entity_id": entity_id, "mode": "start", "duration": "90"},
        blocking=True,
    )

    coordinator.bhc.async_set_dhw_charge_duration.assert_awaited_once_with(
        "123", "dhw1", 90
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [{"level": "high"}, {"temperature": 50}, {"level": "high", "temperature": "warm"}],
)
async def test_dhw_temperature_rejects_bad_input_before_writing(hass, data):
    coordinator = _coordinator("123", "k40", ["dhw1"])
    entry = await _setup(hass, [coordinator])
    entity_id = _register(
        hass, entry, "123", "123-waterheater", "boschcom_k40_123_waterheater"
    )

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "set_dhw_tempreture",
            {"entity_id": entity_id, **data},
            blocking=True,
        )

    coordinator.bhc.async_set_dhw_temp_level.assert_not_awaited()


def _register_sensor(hass, entry, device_id: str, unique_id: str, object_id: str):
    """Create the device and a sensor entity the way HA would."""
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, device_id)}
    )
    return (
        er.async_get(hass)
        .async_get_or_create(
            "sensor",
            DOMAIN,
            unique_id,
            suggested_object_id=object_id,
            device_id=device.id,
            config_entry=entry,
        )
        .entity_id
    )


@pytest.mark.asyncio
async def test_set_date_time_writes_local_time_by_default(hass, freezer):
    """Without a value the gateway gets Home Assistant's local wall-clock time."""
    await hass.config.async_set_time_zone("Europe/Stockholm")
    freezer.move_to("2026-11-15 08:44:26+00:00")
    coordinator = _coordinator("123", "icom", ["dhw1"])
    entry = await _setup(hass, [coordinator])
    entity_id = _register_sensor(hass, entry, "123", "123-dhw1-temp", "pump_dhw1")

    await hass.services.async_call(
        DOMAIN, "set_date_time", {"entity_id": entity_id}, blocking=True
    )

    coordinator.bhc.async_action_universal_put.assert_awaited_once_with(
        "123", "/resource/gateway/DateTime", "2026-11-15T09:44:26"
    )


@pytest.mark.asyncio
async def test_set_date_time_writes_the_given_value(hass):
    """A naive value is written as given, an aware one in local time."""
    await hass.config.async_set_time_zone("Europe/Stockholm")
    coordinator = _coordinator("123", "icom", ["dhw1"])
    entry = await _setup(hass, [coordinator])
    entity_id = _register_sensor(hass, entry, "123", "123-dhw1-temp", "pump_dhw1")

    await hass.services.async_call(
        DOMAIN,
        "set_date_time",
        {"entity_id": entity_id, "date_time": "2026-11-15 09:44:00"},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        "set_date_time",
        {"entity_id": entity_id, "date_time": "2026-07-01T10:00:00+00:00"},
        blocking=True,
    )

    calls = coordinator.bhc.async_action_universal_put.await_args_list
    assert [c.args for c in calls] == [
        ("123", "/resource/gateway/DateTime", "2026-11-15T09:44:00"),
        ("123", "/resource/gateway/DateTime", "2026-07-01T12:00:00"),
    ]


@pytest.mark.asyncio
async def test_set_date_time_rejects_foreign_entity_and_bad_input(hass):
    """Nothing is written for an entity the integration does not own or bad input."""
    coordinator = _coordinator("123", "icom", ["dhw1"])
    entry = await _setup(hass, [coordinator])
    entity_id = _register_sensor(hass, entry, "123", "123-dhw1-temp", "pump_dhw1")
    er.async_get(hass).async_get_or_create(
        "sensor", "other", "x-1", suggested_object_id="other_sensor"
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "set_date_time", {"entity_id": "sensor.other_sensor"}, blocking=True
        )
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "set_date_time",
            {"entity_id": entity_id, "date_time": "tomorrow"},
            blocking=True,
        )

    coordinator.bhc.async_action_universal_put.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_date_time_reports_api_errors(hass):
    """A rejected write surfaces as an error instead of a silent success."""
    coordinator = _coordinator("123", "icom", ["dhw1"])
    coordinator.bhc.async_action_universal_put.side_effect = ApiError("403")
    entry = await _setup(hass, [coordinator])
    entity_id = _register_sensor(hass, entry, "123", "123-dhw1-temp", "pump_dhw1")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "set_date_time", {"entity_id": entity_id}, blocking=True
        )


@pytest.mark.asyncio
async def test_set_date_time_writes_each_device_once(hass):
    """Several entities of one device set its clock once; each device is set."""
    first = _coordinator("123", "icom", ["dhw1"])
    second = _coordinator("456", "k40", ["dhw1"])
    entry = await _setup(hass, [first, second])
    entity_ids = [
        _register_sensor(hass, entry, "123", "123-dhw1-temp", "pump_dhw1"),
        _register_sensor(hass, entry, "123", "123-hc1-temp", "pump_hc1"),
        _register_sensor(hass, entry, "456", "456-dhw1-temp", "boiler_dhw1"),
    ]

    await hass.services.async_call(
        DOMAIN,
        "set_date_time",
        {"entity_id": entity_ids, "date_time": "2026-11-15 09:44:00"},
        blocking=True,
    )

    first.bhc.async_action_universal_put.assert_awaited_once_with(
        "123", "/resource/gateway/DateTime", "2026-11-15T09:44:00"
    )
    second.bhc.async_action_universal_put.assert_awaited_once_with(
        "456", "/resource/gateway/DateTime", "2026-11-15T09:44:00"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("device_type", ["bacon_rac", "bacon_ap"])
async def test_set_date_time_refuses_matter_devices(hass, device_type):
    """A Matter device has no gateway clock: a clear error, and nothing written."""
    gateway = _coordinator("123", "icom", ["dhw1"])
    matter = _coordinator("86DM-577", device_type, [])
    entry = await _setup(hass, [gateway, matter])
    entity_ids = [
        _register_sensor(hass, entry, "123", "123-dhw1-temp", "pump_dhw1"),
        _register_sensor(hass, entry, "86DM-577", "86DM-577-temp", "matter_temp"),
    ]

    with pytest.raises(ServiceValidationError, match="Matter device"):
        await hass.services.async_call(
            DOMAIN, "set_date_time", {"entity_id": entity_ids}, blocking=True
        )

    gateway.bhc.async_action_universal_put.assert_not_awaited()
    matter.bhc.async_action_universal_put.assert_not_awaited()
