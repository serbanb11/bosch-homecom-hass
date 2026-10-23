"""Tests for the DHW custom actions (#200).

The target is resolved through the entity and device registries, so a renamed
device or entity, the default K40 naming and a wddw2 circuit all work, and an
entity the integration does not own raises instead of silently succeeding.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.const import CONF_USERNAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
