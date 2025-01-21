"""Bosch HomeCom Custom Component."""

import asyncio
import logging

from homeassistant import config_entries, core
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr
from aiohttp import ClientSession
from homeassistant.const import Platform

from .const import *
from .coordinator import BoschComModuleCoordinator

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.TEXT,
    Platform.SWITCH,
]

_LOGGER = logging.getLogger(__name__)


async def get_token(config: list, session: ClientSession) -> None:
    """Get token using refresh_token."""
    code = config["refresh_token"]
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        async with session.post(
            OATUH_DOMAIN + OATUH_ENDPOINT,
            data="refresh_token=" + code + "&" + OATUH_PARAMS_REFRESH,
            headers=headers,
        ) as response:
            # Ensure the request was successful
            if response.status == 200:
                try:
                    response_json = await response.json()
                    return response_json
                except ValueError:
                    _LOGGER.error("Response is not JSON")
            else:
                _LOGGER.error(f"{response.url} returned {response.status}")
                return
    except ValueError:
        _LOGGER.error(f"{response.url} exception")


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
                    return response_json
                except ValueError:
                    _LOGGER.error(f"Response is not JSON")
            elif response.status == 401:
                try:
                    response_json = await get_token(config, session)
                    for entry in hass.config_entries.async_entries(DOMAIN):
                        hass.config_entries.async_update_entry(
                            entry, data=response_json
                        )

                    return await get_devices(hass, response_json)
                except ValueError:
                    _LOGGER.error(f"Response is not JSON")
            else:
                _LOGGER.error(f"{response.url} returned {response.status}")
                return
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

    coordinators: list[BoschComModuleCoordinator] = [
        BoschComModuleCoordinator(hass, device, config)
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
    entry.token = token
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


async def async_setup(hass: core.HomeAssistant, config: dict) -> bool:
    """Set up the Bosch HomeCom component."""
    hass.data.setdefault(DOMAIN, {})
    return True
