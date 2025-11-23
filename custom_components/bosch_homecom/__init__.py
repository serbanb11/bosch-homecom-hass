"""Bosch HomeCom Custom Component."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiohttp.client_exceptions import ClientConnectorError, ClientError
from .homecom_alt import (
    ApiError,
    AuthFailedError,
    ConnectionOptions,
    HomeComAlt,
    HomeComGeneric,
    HomeComK40,
    HomeComRac,
    HomeComWddw2,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICES, CONF_TOKEN, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_REFRESH, DOMAIN, MODEL, CONF_UPDATE_SECONDS, DEFAULT_UPDATE_INTERVAL
from .coordinator import (
    BoschComModuleCoordinatorGeneric,
    BoschComModuleCoordinatorK40,
    BoschComModuleCoordinatorRac,
    BoschComModuleCoordinatorWddw2,
)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.FAN,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up platform from a ConfigEntry."""
    coordinators: list[any] = []
    token: str | None = entry.data.get(CONF_TOKEN)
    refresh: str | None = entry.data.get(CONF_REFRESH)

    if token and refresh:
        options = ConnectionOptions(token=token, refresh_token=refresh)
    else:
        _LOGGER.error("No valid credentials provided")
        return False
    websession = async_get_clientsession(hass)

    bhc = await HomeComAlt.create(websession, options, True)

    try:
        devices = await bhc.async_get_devices()
    except (ApiError, ClientError, ClientConnectorError, TimeoutError) as err:
        raise ConfigEntryNotReady from err
    except AuthFailedError as err:
        raise ConfigEntryAuthFailed from err

    coordinator_options = ConnectionOptions(
        token=bhc.token, refresh_token=bhc.refresh_token
    )
    if token != bhc.token or refresh != bhc.refresh_token:
        new_data = dict(entry.data)
        new_data[CONF_TOKEN] = bhc.token
        new_data[CONF_REFRESH] = bhc.refresh_token
        hass.config_entries.async_update_entry(entry, data=new_data)

    if asyncio.iscoroutine(devices):
        devices = await devices

    config_devices: dict | None = entry.data.get(CONF_DEVICES)
    filtered_devices = [
        device
        for device in devices
        if config_devices.get(f"{device['deviceId']}_{device['deviceType']}", False)
    ]

    is_first = True
    for device in filtered_devices:
        device_id = device["deviceId"]
        try:
            firmware = await bhc.async_get_firmware(device_id)
        except ApiError as err:
            if "504" in str(err):
                _LOGGER.warning("Firmware request for %s timed out (504), setting to not_available", device_id)
                firmware = {"value": "unknown"}
            else:
                raise
        auth_provider = False
        if is_first:
            auth_provider = True
            is_first = False

        if device["deviceType"] == "rac":
            coordinators.append(
                BoschComModuleCoordinatorRac(
                    hass,
                    HomeComRac(
                        websession, coordinator_options, device_id, auth_provider
                    ),
                    device,
                    firmware,
                    entry,
                    auth_provider,
                )
            )
        elif device["deviceType"] in ("k40", "k30", "icom"):
            coordinators.append(
                BoschComModuleCoordinatorK40(
                    hass,
                    HomeComK40(
                        websession, coordinator_options, device_id, auth_provider
                    ),
                    device,
                    firmware,
                    entry,
                    auth_provider,
                )
            )
        elif device["deviceType"] == "wddw2":
            coordinators.append(
                BoschComModuleCoordinatorWddw2(
                    hass,
                    HomeComWddw2(
                        websession, coordinator_options, device_id, auth_provider
                    ),
                    device,
                    firmware,
                    entry,
                    auth_provider,
                )
            )
        else:
            coordinators.append(
                BoschComModuleCoordinatorGeneric(
                    hass,
                    HomeComGeneric(
                        websession, coordinator_options, device_id, auth_provider
                    ),
                    device,
                    firmware,
                    entry,
                    auth_provider,
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
            model=MODEL.get(c.device["deviceType"], c.device["deviceType"]),
            sw_version=c.data.firmware,
        )

    entry.runtime_data = coordinators
    hass.data[DOMAIN] = {"coordinators": coordinators}
    # Forward the setup to the sensor platform.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    if CONF_UPDATE_SECONDS not in entry.options:
        new_options = dict(entry.options)
        new_options[CONF_UPDATE_SECONDS] = int(DEFAULT_UPDATE_INTERVAL.total_seconds())
        hass.config_entries.async_update_entry(entry, options=new_options)
        
    def _get_update_interval(entry: ConfigEntry) -> timedelta:
        seconds = int(entry.options.get(
            CONF_UPDATE_SECONDS,
            int(DEFAULT_UPDATE_INTERVAL.total_seconds())
        ))
        return timedelta(seconds=seconds)

    # Aplica o intervalo inicial a todos os coordinators
    for coordinator in entry.runtime_data:
        coordinator.update_interval = _get_update_interval(entry)

    # Listener para futuras alterações nas opções
    async def _update_listener(hass: HomeAssistant, updated_entry: ConfigEntry):
        new_interval = _get_update_interval(updated_entry)
        for coordinator in updated_entry.runtime_data:
            coordinator.update_interval = new_interval

    entry.async_on_unload(entry.add_update_listener(_update_listener))
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
        coordinator = hass.data.get(DOMAIN).get("coordinators")[0]
        result = await coordinator.bhc.async_action_universal_get(
            str(call.data.get("device_id")),
            call.data.get("path"),
        )
        return result or {}

    # Register our service with Home Assistant.
    hass.services.async_register(
        DOMAIN,
        "get_custom_path_service",
        get_custom_path_service,
        supports_response=SupportsResponse.ONLY,
    )

    # Return boolean to indicate that initialization was successfully.
    return True
