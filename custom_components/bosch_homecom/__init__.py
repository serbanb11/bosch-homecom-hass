"""Bosch HomeCom Custom Component."""

from __future__ import annotations

import asyncio
import logging

from aiohttp.client_exceptions import ClientConnectorError, ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICES,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_REFRESH, DOMAIN, MODEL
from .coordinator import BoschComModuleCoordinatorK40, BoschComModuleCoordinatorRac
from homecom_alt import (
    ApiError,
    AuthFailedError,
    ConnectionOptions,
    HomeComAlt,
    HomeComK40,
    HomeComRac,
)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up platform from a ConfigEntry."""
    coordinators: list[any] = []
    username: str | None = entry.data.get(CONF_USERNAME)
    password: str | None = entry.data.get(CONF_PASSWORD)
    token: str | None = entry.data.get(CONF_TOKEN)
    refresh: str | None = entry.data.get(CONF_REFRESH)

    if token and refresh:
        options = ConnectionOptions(token=token, refresh_token=refresh)
    elif username and password:
        options = ConnectionOptions(username=username, password=password)
    else:
        _LOGGER.error("No valid credentials provided")
        return False
    websession = async_get_clientsession(hass)
    try:
        bhc = await HomeComAlt.create(websession, options)
    except (ApiError, ClientError, ClientConnectorError, TimeoutError) as err:
        raise ConfigEntryNotReady from err
    except AuthFailedError as err:
        raise ConfigEntryAuthFailed from err

    devices = await bhc.async_get_devices()

    config_devices: dict | None = entry.data.get(CONF_DEVICES)
    filtered_devices = [
        device
        for device in await devices
        if config_devices.get(f"{device['deviceId']}_{device['deviceType']}", False)
    ]

    for device in filtered_devices:
        device_id = device["deviceId"]
        firmware = await bhc.async_get_firmware(device_id)

        if device["deviceType"] == "rac":
            coordinators.append(
                BoschComModuleCoordinatorRac(
                    hass,
                    HomeComRac(websession, options, device_id),
                    device,
                    firmware,
                )
            )
        elif device["deviceType"] == "k40" or device["deviceType"] == "k30":
            coordinators.append(
                BoschComModuleCoordinatorK40(
                    hass,
                    HomeComK40(websession, options, device_id),
                    device,
                    firmware,
                )
            )

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
    hass.data[DOMAIN] = {"coordinators": coordinators}
    # Forward the setup to the sensor platform.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_setup(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Add custom action."""

    async def set_dhw_tempreture_service(call: ServiceCall) -> None:
        """Service to change temperature."""
        for entity in call.data["entity_id"]:
            device_id = entity.split("_")[2]
            coordinator = next(
                (
                    c
                    for c in hass.data.get(DOMAIN).get("coordinators")
                    if c.device["deviceId"] == device_id
                ),
                None,
            )
            if not coordinator:
                _LOGGER.error("Coordinator not found for entity %s", entity)
                return
            await coordinator.bhc.async_set_dhw_temp_level(
                device_id,
                entity.split("_")[3],
                call.data.get("level"),
                call.data.get("temperature"),
            )
            await coordinator.async_request_refresh()

    # Register our service with Home Assistant.
    hass.services.async_register(
        DOMAIN, "set_dhw_tempreture", set_dhw_tempreture_service
    )

    async def set_dhw_extrahot_water_service(call: ServiceCall) -> None:
        """Service to control extrahot water service."""
        for entity in call.data["entity_id"]:
            device_id = entity.split("_")[2]
            coordinator = next(
                (
                    c
                    for c in hass.data.get(DOMAIN).get("coordinators")
                    if c.device["deviceId"] == device_id
                ),
                None,
            )
            if not coordinator:
                _LOGGER.error("Coordinator not found for entity %s", entity)
                return
            if call.data.get("mode") == "start":
                await coordinator.bhc.async_set_dhw_charge_duration(
                    device_id,
                    entity.split("_")[3],
                    call.data.get("duration"),
                )
            await coordinator.bhc.async_set_dhw_charge(
                device_id,
                entity.split("_")[3],
                call.data.get("mode"),
            )
            await coordinator.async_request_refresh()

    # Register our service with Home Assistant.
    hass.services.async_register(
        DOMAIN, "set_dhw_extrahot_water", set_dhw_extrahot_water_service
    )

    async def get_custom_path_service(call: ServiceCall) -> ServiceResponse:
        """Service to query any endpoint."""
        for entity in call.data["entity_id"]:
            device_id = entity.split("_")[2]
            coordinator = next(
                (
                    c
                    for c in hass.data.get(DOMAIN).get("coordinators")
                    if c.device["deviceId"] == device_id
                ),
                None,
            )
            if not coordinator:
                _LOGGER.error("Coordinator not found for entity %s", entity)
                return {}
            result = await coordinator.bhc.async_action_universal_get(
                device_id,
                call.data.get("path"),
            )
            return result or {}
        return {}

    # Register our service with Home Assistant.
    hass.services.async_register(
        DOMAIN,
        "get_custom_path_service",
        get_custom_path_service,
        supports_response=SupportsResponse.ONLY,
    )

    # Return boolean to indicate that initialization was successfully.
    return True
