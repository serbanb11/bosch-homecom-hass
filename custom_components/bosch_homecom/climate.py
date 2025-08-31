"""Bosch HomeCom Custom Component."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_DIFFUSE,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_ECO,
    PRESET_NONE,
    SWING_OFF,
    SWING_ON,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinatorK40, BoschComModuleCoordinatorRac

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom devices."""
    coordinators = config_entry.runtime_data
    async_add_entities(
        BoschComRacClimate(coordinator=coordinator, field="clima")
        for coordinator in coordinators
        if coordinator.data.device["deviceType"] == "rac"
    )
    async_add_entities(
        BoschComK40Climate(coordinator=coordinator, field="clima")
        for coordinator in coordinators
        if coordinator.data.device["deviceType"] in ["k30", "k40"]
    )


class BoschComRacClimate(CoordinatorEntity, ClimateEntity):
    """Representation of a BoschCom climate entity."""

    _attr_has_entity_name = True
    _attr_name = None
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
        coordinator: BoschComModuleCoordinatorRac,
        field: str,
    ) -> None:
        """Initialize climate entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "ac"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}"
        self._attr_name = field
        self._coordinator = coordinator
        self._attr_should_poll = False

        # Call this in __init__ so data is populated right away, since it's
        # already available in the coordinator data.
        self.set_attr()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.set_attr()
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn on."""
        await self.coordinator.bhc.async_turn_on(self._attr_unique_id)

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn off."""
        await self.coordinator.bhc.async_turn_off(self._attr_unique_id)

        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        await self.coordinator.bhc.async_set_temperature(
            self._attr_unique_id, temperature
        )

        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set new hvac mode."""

        match hvac_mode:
            case HVACMode.AUTO:
                payload = "auto"
            case HVACMode.HEAT:
                payload = "heat"
            case HVACMode.COOL:
                payload = "cool"
            case HVACMode.DRY:
                payload = "dry"
            case HVACMode.FAN_ONLY:
                payload = "fanOnly"
            case HVACMode.OFF:
                await self.coordinator.bhc.async_turn_off(self._attr_unique_id)
                await self.coordinator.async_request_refresh()
                return

        await self.coordinator.bhc.async_turn_on(self._attr_unique_id)
        await self.coordinator.bhc.async_set_hvac_mode(self._attr_unique_id, payload)

        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode) -> None:
        """Set preset mode."""
        if preset_mode == PRESET_ECO:
            await self.coordinator.bhc.async_set_eco(self._attr_unique_id, True)
        elif preset_mode == PRESET_BOOST:
            await self.coordinator.bhc.async_set_boost(self._attr_unique_id, True)
        else:
            await self.coordinator.bhc.async_set_eco(self._attr_unique_id, False)
            await self.coordinator.bhc.async_set_boost(self._attr_unique_id, False)

        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set new target fan mode."""
        if fan_mode == FAN_AUTO:
            payload = "auto"
        elif fan_mode == FAN_DIFFUSE:
            payload = "quiet"
        elif fan_mode == FAN_LOW:
            payload = "low"
        elif fan_mode == FAN_MEDIUM:
            payload = "mid"
        elif fan_mode == FAN_HIGH:
            payload = "high"
        else:
            return
        await self.coordinator.bhc.async_set_fan_mode(self._attr_unique_id, payload)

        await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode) -> None:
        """Set new vertical swing mode."""
        if swing_mode == SWING_ON:
            payload = "swing"
        elif swing_mode == SWING_OFF:
            payload = "angle3"
        else:
            return
        await self.coordinator.bhc.async_set_vertical_swing_mode(
            self._attr_unique_id, payload
        )

        await self.coordinator.async_request_refresh()

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode) -> None:
        """Set new horizontal swing mode."""
        if swing_horizontal_mode == SWING_ON:
            payload = {"value": "swing"}
        elif swing_horizontal_mode == SWING_OFF:
            payload = {"value": "center"}
        else:
            return
        await self.coordinator.bhc.async_set_horizontal_swing_mode(
            self._attr_unique_id, payload
        )

        await self.coordinator.async_request_refresh()

    def _set_standard_functions(self, standard_functions: list[dict]) -> None:
        """Populate standard functions."""

        for ref in standard_functions:
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

    def set_attr(self) -> None:
        """Populate attributes with data from the coordinator."""
        self._set_standard_functions(self.coordinator.data.stardard_functions)

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


class BoschComK40Climate(CoordinatorEntity, ClimateEntity):
    """Representation of a BoschComK40 climate entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.AUTO,
    ]
    _attr_preset_modes = [PRESET_NONE, PRESET_AWAY]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
    ) -> None:
        """Initialize climate entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "ac"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}"
        self._attr_name = field
        self._coordinator = coordinator
        self._attr_should_poll = False

        # Call this in __init__ so data is populated right away, since it's
        # already available in the coordinator data.
        self.set_attr()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.set_attr()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        heating_circuits = await self.coordinator.bhc.async_get_hc(self._attr_unique_id)
        references = heating_circuits.get("references", [])
        if not references:
            return

        for ref in references:
            hc_id = ref["id"].split("/")[-1]
            await self.coordinator.bhc.async_set_hc_manual_room_setpoint(
                self._attr_unique_id, hc_id, temperature
            )

        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode) -> None:
        """Set preset mode."""
        if preset_mode == PRESET_NONE:
            await self.coordinator.bhc.async_put_away_mode(self._attr_unique_id, "off")
        elif preset_mode == PRESET_AWAY:
            await self.coordinator.bhc.async_put_away_mode(self._attr_unique_id, "on")

        await self.coordinator.async_request_refresh()

    def _set_heating_circuits(self, heating_circuits: list[dict]) -> None:
        """Populate heating circuits."""

        for ref in heating_circuits:
            for key in ref:
                val = ref[key]
                if not isinstance(val, dict):
                    continue
                if val.get("value") is None:
                    continue
                match key:
                    case "operationMode":
                        match ref[key]["value"]:
                            case "auto":
                                self._attr_hvac_mode = HVACMode.AUTO
                            case "off":
                                self._attr_hvac_mode = HVACMode.OFF
                            case "manual":
                                # Not sure what to do here
                                self._attr_hvac_mode = HVACMode.AUTO
                    case "currentSuWiMode":
                        match ref[key]["value"]:
                            case "off":
                                self._attr_hvac_action = HVACAction.IDLE
                            case "forced":
                                self._attr_hvac_action = HVACAction.HEATING
                            case "cooling":
                                self._attr_hvac_action = HVACAction.COOLING
                    case "currentRoomSetpoint":
                        self._attr_target_temperature = ref[key]["value"]
                    case "roomTemp":
                        self._attr_current_temperature = ref[key]["value"]
                    case "actualHumidity":
                        self._attr_current_humidity = ref[key]["value"]

    def set_attr(self) -> None:
        """Populate attributes with data from the coordinator."""
        # self._set_standard_functions(self.coordinator.data.stardard_functions)
        self._set_heating_circuits(self.coordinator.data.heating_circuits)

        match self.coordinator.data.away_mode.get("value"):
            case "off":
                self._attr_preset_mode = PRESET_NONE
            case "on":
                self._attr_preset_mode = PRESET_AWAY
            case _:
                self._attr_preset_mode = PRESET_NONE
