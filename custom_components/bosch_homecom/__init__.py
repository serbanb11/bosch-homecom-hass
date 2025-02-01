"""Bosch HomeCom Custom Component."""

from __future__ import annotations

import asyncio
import logging

from aiohttp.client_exceptions import ClientConnectorError, ClientError
from homecom_alt import ApiError, AuthFailedError, ConnectionOptions, HomeComAlt

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, MODEL
from .coordinator import BoschComModuleCoordinator

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.TEXT,
]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up platform from a ConfigEntry."""
    username: str | None = entry.data.get(CONF_USERNAME)
    password: str | None = entry.data.get(CONF_PASSWORD)

    websession = async_get_clientsession(hass)

    options = ConnectionOptions(username=username, password=password)
    try:
        bhc = await HomeComAlt.create(websession, options)
    except (ApiError, ClientError, ClientConnectorError, TimeoutError) as err:
        raise ConfigEntryNotReady from err
    except AuthFailedError as err:
        raise ConfigEntryAuthFailed from err

    devices = await bhc.async_get_devices()

    coordinators: list[BoschComModuleCoordinator] = [
        BoschComModuleCoordinator(
            hass,
            bhc,
            device,
            await bhc.async_get_firmware(device["deviceId"]),
        )
        for device in devices
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
            name=c.device["deviceId"],
            manufacturer="Bosch",
            model=MODEL[c.device["deviceType"]],
            sw_version=c.data.firmware,
        )

    entry.runtime_data = coordinators
    # Forward the setup to the sensor platform.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
