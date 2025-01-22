"""Bosch HomeCom Custom Component."""

from datetime import timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_DIFFUSE,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    PRESET_BOOST,
    PRESET_ECO,
    PRESET_NONE,
    SWING_OFF,
    SWING_ON,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, CONF_CODE, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BOSCHCOM_DOMAIN,
    BOSCHCOM_ENDPOINT_AIRFLOW_HORIZONTAL,
    BOSCHCOM_ENDPOINT_AIRFLOW_VERTICAL,
    BOSCHCOM_ENDPOINT_CONTROL,
    BOSCHCOM_ENDPOINT_ECO,
    BOSCHCOM_ENDPOINT_FAN_SPEED,
    BOSCHCOM_ENDPOINT_FULL_POWER,
    BOSCHCOM_ENDPOINT_GATEWAYS,
    BOSCHCOM_ENDPOINT_MODE,
    BOSCHCOM_ENDPOINT_TEMP,
    DOMAIN,
)
from .coordinator import BoschComModuleCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=10)

AUTH_SCHEMA = vol.Schema({vol.Required(CONF_CODE): cv.string})


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom devices."""
    coordinators = config_entry.runtime_data
    async_add_entities(
        BoschComClimate(coordinator=coordinator) for coordinator in coordinators
    )


class BoschComClimate(ClimateEntity):
    """Representation of a BoschCom climate entity."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_fan_modes = [FAN_AUTO, FAN_DIFFUSE, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    _attr_preset_modes = [PRESET_NONE, PRESET_BOOST, PRESET_ECO]
    _attr_swing_horizontal_modes = [SWING_OFF, SWING_ON]
    _attr_swing_modes = [SWING_OFF, SWING_ON]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.SWING_HORIZONTAL_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    def __init__(
        self,
        coordinator: BoschComModuleCoordinator,
    ) -> None:
        """Initialize climate entity."""
        super().__init__()
        self._attr_name = (
            "Bosch_"
            + coordinator.device["deviceType"]
            + "_"
            + coordinator.device["deviceId"]
        )
        self._attr_unique_id = coordinator.device["deviceId"]
        self._name = (
            "Bosch_"
            + coordinator.device["deviceType"]
            + "_"
            + coordinator.device["deviceId"]
        )
        self.coordinator = coordinator

        # Call this in __init__ so data is populated right away, since it's
        # already available in the coordinator data.
        self.set_attr()

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=self.name,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.set_attr()
        super()._handle_coordinator_update()

    async def async_turn_on(self) -> None:
        """Turn on."""
        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self.coordinator.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._attr_unique_id
                + BOSCHCOM_ENDPOINT_CONTROL,
                headers=headers,
                json={"value": "on"},
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self.coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_turn_on()
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

        await self.coordinator.async_request_refresh()
        self.set_attr()

    async def async_turn_off(self) -> None:
        """Turn off."""
        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self.coordinator.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._attr_unique_id
                + BOSCHCOM_ENDPOINT_CONTROL,
                headers=headers,
                json={"value": "off"},
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self.coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_turn_off()
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

        await self.coordinator.async_request_refresh()
        self.set_attr()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self.coordinator.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._attr_unique_id
                + BOSCHCOM_ENDPOINT_TEMP,
                headers=headers,
                json={"value": temperature},
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self.coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_set_temperature(ATTR_TEMPERATURE=temperature)
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

        await self.coordinator.async_request_refresh()
        self.set_attr()

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set new hvac mode."""
        ac_control = next(
            (
                ref
                for ref in self.coordinator.data.stardard_functions
                if "acControl" in ref["id"]
            ),
            None,
        )
        match hvac_mode:
            case HVACMode.AUTO:
                payload = {"value": "auto"}
            case HVACMode.HEAT:
                payload = {"value": "heat"}
            case HVACMode.COOL:
                payload = {"value": "cool"}
            case HVACMode.DRY:
                payload = {"value": "dry"}
            case HVACMode.FAN_ONLY:
                payload = {"value": "fanOnly"}
            case HVACMode.OFF:
                await self.async_turn_off()
                return

        if ac_control["value"] == "off":
            await self.async_turn_on()

        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self.coordinator.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._attr_unique_id
                + BOSCHCOM_ENDPOINT_MODE,
                headers=headers,
                json=payload,
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self.coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_set_hvac_mode(hvac_mode)
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

        await self.coordinator.async_request_refresh()
        self.set_attr()

    async def async_set_preset_mode(self, preset_mode) -> None:
        """Set preset mode."""
        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self.coordinator.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        if preset_mode == PRESET_ECO:
            ENDPOINT = BOSCHCOM_ENDPOINT_ECO
            payload = {"value": "on"}
        elif preset_mode == PRESET_BOOST:
            ENDPOINT = BOSCHCOM_ENDPOINT_FULL_POWER
            payload = {"value": "on"}
        else:
            eco_mode = next(
                (
                    ref
                    for ref in self.coordinator.data.advanced_functions
                    if "ecoMode" in ref["id"]
                ),
                None,
            )
            if eco_mode == "on":
                ENDPOINT = BOSCHCOM_ENDPOINT_ECO
                payload = {"value": "off"}
            else:
                ENDPOINT = BOSCHCOM_ENDPOINT_FULL_POWER
                payload = {"value": "off"}
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._attr_unique_id
                + ENDPOINT,
                headers=headers,
                json=payload,
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self.coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_set_preset_mode(preset_mode)
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

        await self.coordinator.async_request_refresh()
        self.set_attr()

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set new target fan mode."""
        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self.coordinator.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        if fan_mode == FAN_AUTO:
            payload = {"value": "auto"}
        elif fan_mode == FAN_DIFFUSE:
            payload = {"value": "quiet"}
        elif fan_mode == FAN_LOW:
            payload = {"value": "low"}
        elif fan_mode == FAN_MEDIUM:
            payload = {"value": "mid"}
        elif fan_mode == FAN_HIGH:
            payload = {"value": "high"}
        else:
            return
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._attr_unique_id
                + BOSCHCOM_ENDPOINT_FAN_SPEED,
                headers=headers,
                json=payload,
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self.coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_set_fan_mode(fan_mode)
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

        await self.coordinator.async_request_refresh()
        self.set_attr()

    async def async_set_swing_mode(self, swing_mode) -> None:
        """Set new target fan mode."""
        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self.coordinator.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        if swing_mode == SWING_ON:
            payload = {"value": "swing"}
        elif swing_mode == SWING_OFF:
            payload = {"value": "angle3"}
        else:
            return
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._attr_unique_id
                + BOSCHCOM_ENDPOINT_AIRFLOW_VERTICAL,
                headers=headers,
                json=payload,
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self.coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.set_swing_mode(swing_mode)
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

        await self.coordinator.async_request_refresh()
        self.set_attr()

    async def async_set_swing_horizontal_mode(self, swing_mode) -> None:
        """Set new target fan mode."""
        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self.coordinator.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        if swing_mode == SWING_ON:
            payload = {"value": "swing"}
        elif swing_mode == SWING_OFF:
            payload = {"value": "center"}
        else:
            return
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._attr_unique_id
                + BOSCHCOM_ENDPOINT_AIRFLOW_HORIZONTAL,
                headers=headers,
                json=payload,
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self.coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.set_swing_horizontal_mode(swing_mode)
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

        await self.coordinator.async_request_refresh()
        self.set_attr()

    def set_attr(self) -> None:
        """Populate attributes with data from the coordinator."""

        for ref in self.coordinator.data.stardard_functions:
            normalized_id = ref["id"].split("/", 2)[-1]

            match normalized_id:
                case "operationMode":
                    match ref["value"]:
                        case "auto":
                            self._attr_hvac_mode = HVACMode.AUTO
                        case "heat":
                            self._attr_hvac_mode = HVACMode.HEAT
                        case "cool":
                            self._attr_hvac_mode = HVACMode.COOL
                        case "dry":
                            self._attr_hvac_mode = HVACMode.DRY
                        case "fanOnly":
                            self._attr_hvac_mode = HVACMode.FAN_ONLY
                case "acControl":
                    if ref["value"] == "off":
                        self._attr_hvac_mode = HVACMode.OFF
                case "fanSpeed":
                    match ref["value"]:
                        case "auto":
                            self._attr_fan_mode = FAN_AUTO
                        case "quiet":
                            self._attr_fan_mode = FAN_DIFFUSE
                        case "low":
                            self._attr_fan_mode = FAN_LOW
                        case "mid":
                            self._attr_fan_mode = FAN_MEDIUM
                        case "high":
                            self._attr_fan_mode = FAN_HIGH

                case "airFlowHorizontal":
                    if ref["value"] == "swing":
                        self._attr_swing_horizontal_mode = SWING_ON
                    else:
                        self._attr_swing_horizontal_mode = SWING_OFF
                case "airFlowVertical":
                    if ref["value"] == "swing":
                        self._attr_swing_mode = SWING_ON
                    else:
                        self._attr_swing_mode = SWING_OFF
                case "temperatureSetpoint":
                    self._attr_target_temperature = ref["value"]
                    self._attr_target_temperature_high = ref.get("maxValue", 30)
                    self._attr_target_temperature_low = ref.get("minValue", 16)
                case "roomTemperature":
                    self._attr_current_temperature = ref["value"]
                case _:
                    pass

            if not hasattr(self, "_attr_target_temperature_high"):
                self._attr_target_temperature = 22
                self._attr_target_temperature_high = 30
                self._attr_target_temperature_low = 16

        for ref in self.coordinator.data.advanced_functions:
            normalized_id = ref["id"].split("/", 2)[-1]
            self._attr_preset_mode = PRESET_NONE

            match normalized_id:
                case "fullPowerMode":
                    if ref["value"] == "on":
                        self._attr_preset_mode = PRESET_BOOST
                case "ecoMode":
                    if ref["value"] == "on":
                        self._attr_preset_mode = PRESET_ECO
                case _:
                    pass
