"""Bosch HomeCom Custom Component."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiohttp.client_exceptions import ClientConnectorError, ClientError
from homecom_alt import (
    ApiError,
    AuthFailedError,
    BaconMqttClient,
    ConnectionOptions,
    HomeComAlt,
    HomeComBaconRac,
    HomeComCommodule,
    HomeComGeneric,
    HomeComIcom,
    HomeComK40,
    HomeComRac,
    HomeComRrc2,
    HomeComWddw2,
    NotRespondingError,
    async_get_bacon_devices,
    decode_jwt_sub,
    generate_client_id,
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

from homecom_alt.const import BACON_DEFAULT_REGION

from .const import (
    CONF_BACON_CLIENT_ID,
    CONF_BACON_REGION,
    CONF_BRAND_BUDERUS,
    CONF_REFRESH,
    DOMAIN,
    MODEL,
    CONF_UPDATE_SECONDS,
    DEFAULT_UPDATE_INTERVAL,
)
from .coordinator import (
    BoschComModuleCoordinatorBaconRac,
    BoschComModuleCoordinatorCommodule,
    BoschComModuleCoordinatorGeneric,
    BoschComModuleCoordinatorIcom,
    BoschComModuleCoordinatorK40,
    BoschComModuleCoordinatorRac,
    BoschComModuleCoordinatorRrc2,
    BoschComModuleCoordinatorWddw2,
)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.NUMBER,
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

    brand_buderus = entry.data.get(
        CONF_BRAND_BUDERUS, entry.options.get(CONF_BRAND_BUDERUS, False)
    )
    brand = "buderus" if brand_buderus else "bosch"

    if token and refresh:
        options = ConnectionOptions(token=token, refresh_token=refresh, brand=brand)
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
        token=bhc.token, refresh_token=bhc.refresh_token, brand=brand
    )
    if token != bhc.token or refresh != bhc.refresh_token:
        new_data = dict(entry.data)
        new_data[CONF_TOKEN] = bhc.token
        new_data[CONF_REFRESH] = bhc.refresh_token
        hass.config_entries.async_update_entry(entry, data=new_data)

    if asyncio.iscoroutine(devices):
        devices = await devices

    # Matter/Bacon devices are not in the pointt gateway listing; re-discover
    # them here so previously-selected ones are set up on reload.
    bacon_region = entry.data.get(CONF_BACON_REGION) or BACON_DEFAULT_REGION
    try:
        devices = list(devices) + await async_get_bacon_devices(
            websession, bhc.token, bacon_region
        )
    except Exception:  # noqa: BLE001 - never block pointt setup
        _LOGGER.warning("Could not fetch Bacon devices at setup", exc_info=True)

    config_devices: dict | None = entry.data.get(CONF_DEVICES)
    filtered_devices = [
        device
        for device in devices
        if config_devices.get(f"{device['deviceId']}_{device['deviceType']}", False)
    ]

    is_first = True
    for device in filtered_devices:
        if device["deviceType"] == "bacon_rac":
            # Matter/Bacon devices are set up below over MQTT, not pointt REST.
            continue
        device_id = device["deviceId"]
        try:
            firmware = await bhc.async_get_firmware(device_id)
        except (ApiError, NotRespondingError, TimeoutError):
            firmware = None
        if not firmware or "value" not in firmware:
            firmware = {"value": "unknown"}
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
        elif device["deviceType"] in ("k40", "k30"):
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
        elif device["deviceType"] == "icom":
            coordinators.append(
                BoschComModuleCoordinatorIcom(
                    hass,
                    HomeComIcom(
                        websession, coordinator_options, device_id, auth_provider
                    ),
                    device,
                    firmware,
                    entry,
                    auth_provider,
                )
            )
        elif device["deviceType"] == "rrc2":
            coordinators.append(
                BoschComModuleCoordinatorRrc2(
                    hass,
                    HomeComRrc2(
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
        elif device["deviceType"] == "commodule":
            coordinators.append(
                BoschComModuleCoordinatorCommodule(
                    hass,
                    HomeComCommodule(
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

    # Matter/Bacon-commissioned RAC devices: one shared MQTT device-shadow
    # connection, one coordinator per device.
    bacon_devices = [
        device
        for device in filtered_devices
        if device["deviceType"] == "bacon_rac"
    ]
    if bacon_devices:
        client_id = entry.data.get(CONF_BACON_CLIENT_ID)
        if not client_id:
            client_id = generate_client_id()
            new_data = dict(entry.data)
            new_data[CONF_BACON_CLIENT_ID] = client_id
            hass.config_entries.async_update_entry(entry, data=new_data)

        bacon_client = BaconMqttClient(client_id, region=bacon_region)
        sub = decode_jwt_sub(bhc.token)
        if not sub:
            raise ConfigEntryAuthFailed("Could not derive user id from token")
        try:
            await bacon_client.async_connect(bhc.token, sub)
        except AuthFailedError as err:
            raise ConfigEntryAuthFailed from err
        except (ApiError, ClientError, ClientConnectorError, TimeoutError) as err:
            raise ConfigEntryNotReady from err
        entry.async_on_unload(bacon_client.async_disconnect)

        bacon_lock = asyncio.Lock()
        # A single token owner (refresh tokens are single-use). If there are no
        # pointt coordinators, the first bacon coordinator owns the refresh.
        bacon_auth_provider = len(coordinators) == 0
        for device in bacon_devices:
            coordinators.append(
                BoschComModuleCoordinatorBaconRac(
                    hass,
                    HomeComBaconRac(bacon_client, device["deviceId"]),
                    device,
                    {"value": "unknown"},
                    entry,
                    bacon_client,
                    bhc,
                    bacon_lock,
                    bacon_auth_provider,
                )
            )
            bacon_auth_provider = False


    await asyncio.gather(
        *[
            coordinator.async_config_entry_first_refresh()
            for coordinator in coordinators
        ]
    )

    device_registry = dr.async_get(hass)

    # Create a new Device for each coorodinator to represent each module
    for c in coordinators:
        dev_name = c.device["deviceId"]
        # Bacon devices carry a friendly name (customTitle) in their shadow;
        # the coordinator stores it on device_info once the first state arrives.
        if c.device["deviceType"] == "bacon_rac":
            dev_name = c.device_info.get("name") or dev_name
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, c.device["deviceId"])},
            name=dev_name,
            manufacturer="Bosch",
            model=MODEL.get(c.device["deviceType"], c.device["deviceType"]),
            sw_version=c.firmware,
        )

    entry.runtime_data = coordinators
    # Forward the setup to the sensor platform.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if CONF_UPDATE_SECONDS not in entry.options:
        new_options = dict(entry.options)
        new_options[CONF_UPDATE_SECONDS] = int(DEFAULT_UPDATE_INTERVAL.total_seconds())
        hass.config_entries.async_update_entry(entry, options=new_options)

    def _get_update_interval(entry: ConfigEntry) -> timedelta:
        seconds = int(
            entry.options.get(
                CONF_UPDATE_SECONDS, int(DEFAULT_UPDATE_INTERVAL.total_seconds())
            )
        )
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


def _find_coordinator_by_device_id(hass: HomeAssistant, device_id: str):
    """Find the coordinator that owns a Bosch device ID."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        for c in getattr(entry, "runtime_data", None) or []:
            if c.device["deviceId"] == device_id:
                return c
    return None


async def async_setup(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Add custom action."""

    async def set_dhw_tempreture_service(call: ServiceCall) -> None:
        """Service to change temperature."""
        for entity in call.data["entity_id"]:
            device_id = entity.split("_")[2]
            coordinator = _find_coordinator_by_device_id(hass, device_id)
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
            coordinator = _find_coordinator_by_device_id(hass, device_id)
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
        device_id = str(call.data.get("device_id"))
        coordinator = _find_coordinator_by_device_id(hass, device_id)
        if coordinator is None:
            _LOGGER.error("Coordinator not found for device %s", device_id)
            return {}
        result = await coordinator.bhc.async_action_universal_get(
            device_id,
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

    async def get_recordings_service(call: ServiceCall) -> ServiceResponse:
        """Service to fetch /recordings/* endpoints via bulk POST.

        The single-endpoint universal GET returns empty for /recordings/*
        (that tier is only exposed via POST /pointt-api/api/v1/bulk).
        Reuses async_request_bulk from homecom_alt.
        """
        device_id = str(call.data.get("device_id"))
        coordinator = _find_coordinator_by_device_id(hass, device_id)
        if coordinator is None:
            _LOGGER.error("Coordinator not found for device %s", device_id)
            return {}
        paths = call.data.get("paths")
        if paths is None:
            _LOGGER.error("Missing paths argument")
            return {}
        if isinstance(paths, str):
            paths = [paths]
        if not isinstance(paths, list) or not paths:
            _LOGGER.error("paths must be a non-empty list of strings")
            return {}
        result = await coordinator.bhc.async_request_bulk(device_id, paths)
        return result or {}

    # Register our service with Home Assistant.
    hass.services.async_register(
        DOMAIN,
        "get_recordings_service",
        get_recordings_service,
        supports_response=SupportsResponse.ONLY,
    )

    # Return boolean to indicate that initialization was successfully.
    return True
