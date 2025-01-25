"""Bosch HomeCom Custom Component."""

import asyncio
import logging

from homeassistant import config_entries, core
from homeassistant.const import Platform
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .config_flow import check_jwt, get_token
from .const import BOSCHCOM_DOMAIN, BOSCHCOM_ENDPOINT_GATEWAYS, DOMAIN
from .coordinator import BoschComModuleCoordinator

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.TEXT,
]

_LOGGER = logging.getLogger(__name__)


async def get_devices(hass: core.HomeAssistant, config: list) -> None:
    """Get devices."""
    session = async_get_clientsession(hass)

    headers = {
        "Authorization": f"Bearer {config['access_token']}"  # Set Bearer token
    }
    try:
        async with session.get(
            BOSCHCOM_DOMAIN + BOSCHCOM_ENDPOINT_GATEWAYS,
            headers=headers,
        ) as response:
            # Ensure the request was successful
            if response.status == 200:
                try:
                    response_json = await response.json()
                except ValueError:
                    _LOGGER.error("Authentication error")
                    return None
                return response_json
            _LOGGER.error(f"{response.url} returned {response.status}")
            return None
    except ValueError:
        _LOGGER.error(f"{response.url} exception")


async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up platform from a ConfigEntry."""
    hass.data.setdefault(DOMAIN, {})
    hass_data = dict(entry.data)
    hass.data[DOMAIN][entry.entry_id] = hass_data
    config = hass.data[DOMAIN][entry.entry_id]

    token = config["access_token"]
    if not check_jwt(token):
        response_json = await get_token(hass, config["refresh_token"], entry.entry_id)
        hass.config_entries.async_update_entry(entry, data=config | response_json)

    coordinators: list[BoschComModuleCoordinator] = [
        BoschComModuleCoordinator(hass, device, entry.entry_id)
        for device in await get_devices(hass, config)
    ]

    await asyncio.gather(
        *[
            coordinator.async_config_entry_first_refresh()
            for coordinator in coordinators
        ]
    )

    device_registry = dr.async_get(hass)

    # Create a new Device for each coorodinator to represent each module
    for c in coordinators:
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, c.device["deviceId"])},
            name="Bosch_" + c.device["deviceType"] + "_" + c.device["deviceId"],
            manufacturer="Bosch",
            model=c.device["deviceType"],
            sw_version=c.data.firmware,
        )

    entry.runtime_data = coordinators
    # Forward the setup to the sensor platform.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Remove config entry from domain.
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
