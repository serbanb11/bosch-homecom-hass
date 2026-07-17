"""Bosch HomeCom Custom Component."""

from __future__ import annotations


from typing import Any, Literal

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

from .coordinator import (
    BoschComModuleCoordinatorBaconRac,
    BoschComModuleCoordinatorIcom,
    BoschComModuleCoordinatorK40,
    BoschComModuleCoordinatorRac,
    BoschComModuleCoordinatorRrc2,
)

PARALLEL_UPDATES = 1


def _parse_temp_unit(unit_str: str | None) -> str:
    """Map API unitOfMeasure string to HA temperature unit."""
    if unit_str == "F":
        return UnitOfTemperature.FAHRENHEIT
    return UnitOfTemperature.CELSIUS


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom devices."""
    coordinators = config_entry.runtime_data
    entities: list[ClimateEntity] = []

    for coordinator in coordinators:
        device_type = coordinator.data.device.get("deviceType")

        if device_type == "rac":
            entities.append(BoschComRacClimate(coordinator=coordinator, field="clima"))
        elif device_type == "bacon_rac":
            entities.append(BoschComBaconRacClimate(coordinator=coordinator))
        elif device_type in ("k40", "k30", "icom"):
            for ref in coordinator.data.heating_circuits:
                hc_id = ref["id"].split("/")[-1]
                entities.append(
                    BoschComK40Climate(coordinator=coordinator, field=hc_id)
                )
        if device_type in ("k40", "k30"):
            for ref in coordinator.data.zones or []:
                zone_id = ref["id"].split("/")[-1]
                entities.append(
                    BoschComZoneClimate(coordinator=coordinator, field=zone_id)
                )
        if device_type == "rrc2":
            for ref in coordinator.data.zones or []:
                zone_id = ref["id"].split("/")[-1]
                entities.append(
                    BoschComRrc2ZoneClimate(coordinator=coordinator, field=zone_id)
                )
    if entities:
        async_add_entities(entities)


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
        self._attr_suggested_object_id = field
        self._attr_should_poll = False

        # Call this in __init__ so data is populated right away, since it's
        # already available in the coordinator data.
        if not coordinator.data:
            return
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
                    self._attr_temperature_unit = _parse_temp_unit(
                        ref.get("unitOfMeasure")
                    )
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

        self._attr_preset_mode = PRESET_NONE
        for ref in self.coordinator.data.advanced_functions:
            normalized_id = ref["id"].split("/", 2)[-1]

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
        self._attr_translation_key = "hc"
        self._attr_translation_placeholders = {"circuit": field}
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_should_poll = False
        self._attr_hvac_mode = HVACMode.OFF
        self.field = field
        self._attr_suggested_object_id = field

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

        if isinstance(self.coordinator, BoschComModuleCoordinatorIcom):
            # icom: use temporaryRoomSetpoint to match the Bosch app behaviour
            await self.coordinator.async_set_temporary_room_setpoint(
                self.field, temperature
            )
        elif self._is_cooling():
            # In cooling mode the manualRoomSetpoint endpoint returns 404;
            # the writable setpoint is coolingRoomTempSetpoint instead.
            await self.coordinator.bhc.async_set_hc_cooling_room_temp_setpoint(
                self.coordinator.unique_id, self.field, temperature
            )
        else:
            await self.coordinator.bhc.async_set_hc_manual_room_setpoint(
                self.coordinator.unique_id, self.field, temperature
            )

        # Optimistically reflect the new setpoint immediately — the Bosch cloud
        # API may lag before the updated value appears in GET responses.
        self._attr_target_temperature = temperature
        self.async_write_ha_state()

        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new hvac mode."""
        match hvac_mode:
            case HVACMode.AUTO:
                payload = "auto"
            case HVACMode.OFF:
                payload = "off"
            case _:
                return

        await self.coordinator.bhc.async_put_hc_operation_mode(
            self.coordinator.unique_id, self.field, payload
        )

        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode) -> None:
        """Set preset mode."""
        is_rrc2 = self.coordinator.device.get("deviceType") == "rrc2"
        if preset_mode == PRESET_NONE:
            value = "false" if is_rrc2 else "off"
            await self.coordinator.bhc.async_put_away_mode(
                self.coordinator.unique_id, value
            )
        elif preset_mode == PRESET_AWAY:
            value = "true" if is_rrc2 else "on"
            await self.coordinator.bhc.async_put_away_mode(
                self.coordinator.unique_id, value
            )

        await self.coordinator.async_request_refresh()

    def _set_heating_circuits(self, heating_circuits: dict) -> None:
        """Populate heating circuits."""

        for key in heating_circuits:
            val = heating_circuits[key]
            if not isinstance(val, dict):
                continue
            if val.get("value") is None:
                continue
            match key:
                case "operationMode":
                    match heating_circuits[key]["value"]:
                        case "auto":
                            self._attr_hvac_mode = HVACMode.AUTO
                        case "off":
                            self._attr_hvac_mode = HVACMode.OFF
                        case "manual":
                            # Not sure what to do here
                            self._attr_hvac_mode = HVACMode.AUTO
                case "currentSuWiMode":
                    match heating_circuits[key]["value"]:
                        case "off":
                            self._attr_hvac_action = HVACAction.IDLE
                        case "forced":
                            self._attr_hvac_action = HVACAction.HEATING
                        case "cooling":
                            self._attr_hvac_action = HVACAction.COOLING
                case "currentRoomSetpoint":
                    self._attr_target_temperature = heating_circuits[key]["value"]
                    self._attr_temperature_unit = _parse_temp_unit(
                        heating_circuits[key].get("unitOfMeasure")
                    )
                case "roomTemp":
                    room_temp = heating_circuits[key]["value"]
                    if isinstance(room_temp, (int, float)) and -40 <= room_temp <= 60:
                        self._attr_current_temperature = room_temp
                    else:
                        self._attr_current_temperature = None
                case "actualHumidity":
                    self._attr_current_humidity = heating_circuits[key]["value"]

    def _is_cooling(self) -> bool:
        """Return True when this circuit is cooling.

        In cooling the manualRoomSetpoint endpoint returns 404, so the write
        path must target coolingRoomTempSetpoint instead. Matching either the
        live season (currentSuWiMode) or the configured mode (heatCoolMode)
        also covers cooling season while the compressor is idle.
        """
        for entry in self.coordinator.data.heating_circuits or []:
            if entry.get("id") == f"/heatingCircuits/{self.field}":
                suwi = (entry.get("currentSuWiMode") or {}).get("value")
                heatcool = (entry.get("heatCoolMode") or {}).get("value")
                return suwi == "cooling" or heatcool == "cooling"
        return False

    def set_attr(self) -> None:
        """Populate attributes with data from the coordinator."""
        data = self.coordinator.data
        if not data:
            return

        for entry in data.heating_circuits or []:
            if entry.get("id") == f"/heatingCircuits/{self.field}":
                self._set_heating_circuits(entry)
                break

        # away_mode is only on K40/K30 dataclass, not Icom — guard with getattr.
        away = (getattr(data, "away_mode", None) or {}).get("value")
        self._attr_preset_mode = PRESET_AWAY if away in ("on", "true") else PRESET_NONE


class BoschComZoneClimate(CoordinatorEntity, ClimateEntity):
    """Representation of a BoschCom zone climate entity."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.AUTO]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
    ) -> None:
        """Initialize zone climate entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "zone"
        self._attr_translation_placeholders = {"zone": field}
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_should_poll = False
        self._attr_hvac_mode = HVACMode.HEAT
        self.field = field
        self._manual_temp: float | None = None
        self._clock_temp: float | None = None
        self._attr_suggested_object_id = field

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

        self._attr_target_temperature = temperature
        self.async_write_ha_state()

        await self.coordinator.bhc.async_set_zone_manual_temp_heating(
            self.coordinator.unique_id, self.field, temperature
        )

        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new hvac mode (zone user mode)."""
        mode: Literal["manual", "clock"] = "manual"

        if hvac_mode == HVACMode.AUTO:
            mode = "clock"

        self._attr_hvac_mode = hvac_mode
        if hvac_mode == HVACMode.HEAT and self._manual_temp is not None:
            self._attr_target_temperature = self._manual_temp
        elif hvac_mode == HVACMode.AUTO and self._clock_temp is not None:
            self._attr_target_temperature = self._clock_temp
        self.async_write_ha_state()

        await self.coordinator.bhc.async_set_zone_user_mode(
            self.coordinator.unique_id, self.field, mode
        )

        await self.coordinator.async_request_refresh()

    def set_attr(self) -> None:
        """Populate attributes with data from the coordinator."""
        data = self.coordinator.data
        if not data:
            return

        for entry in data.zones or []:
            if entry.get("id", "").endswith(f"/{self.field}"):

                temp_actual_node = entry.get("temperatureActual") or {}
                temp_actual = temp_actual_node.get("value")
                if temp_actual is not None:
                    self._attr_current_temperature = temp_actual
                    self._attr_temperature_unit = _parse_temp_unit(
                        temp_actual_node.get("unitOfMeasure")
                    )

                hvac_mode = self._get_hvac_mode(entry)
                temp_data = self._get_temperature_data(entry)

                manual_data = entry.get("manualTemperatureHeating") or {}
                clock_data = entry.get("tempSetpoint") or {}
                if manual_data.get("value") is not None:
                    self._manual_temp = manual_data["value"]
                if clock_data.get("value") is not None:
                    self._clock_temp = clock_data["value"]

                self._attr_hvac_mode = hvac_mode
                self._attr_target_temperature = temp_data.get("value")
                self._attr_min_temp = temp_data.get("minValue", 5)
                self._attr_max_temp = temp_data.get("maxValue", 30)
                self._attr_target_temperature_step = temp_data.get("stepSize", 0.5)
                break

    def _get_hvac_mode(self, entry: dict) -> HVACMode:
        """Return the correct HVAC mode based on user mode."""
        user_mode = (entry.get("userMode") or {}).get("value")
        if user_mode == "clock":
            return HVACMode.AUTO
        return HVACMode.HEAT

    def _get_temperature_data(self, entry: dict) -> dict:
        """Return the correct temperature object based on user mode."""
        user_mode = (entry.get("userMode") or {}).get("value")

        if user_mode == "manual":
            return entry.get("manualTemperatureHeating") or {}

        return entry.get("tempSetpoint") or {}


class BoschComRrc2ZoneClimate(CoordinatorEntity, ClimateEntity):
    """Climate entity for an RRC2 zone."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.AUTO, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorRrc2,
        field: str,
    ) -> None:
        """Initialize RRC2 zone climate entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "zone"
        self._attr_translation_placeholders = {"zone": field}
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_should_poll = False
        self._attr_hvac_mode = HVACMode.HEAT
        self.field = field
        self._manual_temp: float | None = None
        self._clock_temp: float | None = None
        self._attr_suggested_object_id = field
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

        self._attr_target_temperature = temperature
        self.async_write_ha_state()

        await self.coordinator.bhc.async_set_zone_manual_temp_heating(
            self.coordinator.unique_id, self.field, temperature
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode: AUTO=clock, HEAT=manual, OFF=away."""
        self._attr_hvac_mode = hvac_mode

        if hvac_mode == HVACMode.OFF:
            self.async_write_ha_state()
            await self.coordinator.bhc.async_put_away_mode(
                self.coordinator.unique_id, "true"
            )
            await self.coordinator.async_request_refresh()
            return

        if hvac_mode == HVACMode.HEAT and self._manual_temp is not None:
            self._attr_target_temperature = self._manual_temp
        elif hvac_mode == HVACMode.AUTO and self._clock_temp is not None:
            self._attr_target_temperature = self._clock_temp
        self.async_write_ha_state()

        mode: Literal["manual", "clock"] = "manual"
        if hvac_mode == HVACMode.AUTO:
            mode = "clock"

        await self.coordinator.bhc.async_put_away_mode(
            self.coordinator.unique_id, "false"
        )
        await self.coordinator.bhc.async_set_zone_user_mode(
            self.coordinator.unique_id, self.field, mode
        )
        await self.coordinator.async_request_refresh()

    def set_attr(self) -> None:
        """Populate attributes from coordinator data."""
        data = self.coordinator.data
        if not data:
            return

        away = (data.away_mode or {}).get("value")
        if str(away).lower() == "true":
            self._attr_hvac_mode = HVACMode.OFF
        else:
            self._attr_hvac_mode = self._get_hvac_mode_from_zone()

        for entry in data.zones or []:
            if not entry.get("id", "").endswith(f"/{self.field}"):
                continue

            actual_node = entry.get("temperatureActual") or {}
            actual = actual_node.get("value")
            if actual is not None:
                self._attr_current_temperature = actual
                self._attr_temperature_unit = _parse_temp_unit(
                    actual_node.get("unitOfMeasure")
                )

            manual = entry.get("manualTemperatureHeating") or {}
            clock = entry.get("temperatureHeatingSetpoint") or {}
            if manual.get("value") is not None:
                self._manual_temp = manual["value"]
            if clock.get("value") is not None:
                self._clock_temp = clock["value"]

            target_node = self._get_temperature_data(entry)
            if target_node.get("value") is not None:
                self._attr_target_temperature = target_node["value"]
            self._attr_min_temp = manual.get("minValue", 5)
            self._attr_max_temp = manual.get("maxValue", 30)
            self._attr_target_temperature_step = manual.get("stepSize", 0.5)
            break

    def _get_hvac_mode_from_zone(self) -> HVACMode:
        """Return HVAC mode based on zone userMode."""
        data = self.coordinator.data
        if not data:
            return HVACMode.HEAT
        for entry in data.zones or []:
            if entry.get("id", "").endswith(f"/{self.field}"):
                user_mode = (entry.get("userMode") or {}).get("value")
                if user_mode == "clock":
                    return HVACMode.AUTO
                return HVACMode.HEAT
        return HVACMode.HEAT

    def _get_temperature_data(self, entry: dict) -> dict:
        """Return the correct temperature object based on user mode."""
        user_mode = (entry.get("userMode") or {}).get("value")
        if user_mode == "manual":
            return entry.get("manualTemperatureHeating") or {}
        return entry.get("temperatureHeatingSetpoint") or {}


# --- Bacon (Matter-commissioned) RAC over MQTT device-shadow -----------------

BACON_OP_MODE_TO_HVAC: dict[str, HVACMode] = {
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "auto": HVACMode.AUTO,
    "dry": HVACMode.DRY,
    "fan": HVACMode.FAN_ONLY,
}
BACON_HVAC_TO_OP_MODE: dict[HVACMode, str] = {
    v: k for k, v in BACON_OP_MODE_TO_HVAC.items()
}
BACON_FAN_MODES: list[str] = ["auto", "quiet", "low", "medium", "high", "turbo"]


def _clean_bacon_title(title: str | None) -> str | None:
    """Strip the ``%|$?*...`` suffix Bosch appends to the shadow customTitle."""
    if not title:
        return None
    return title.split("%|")[0].strip() or None


class BoschComBaconRacClimate(
    CoordinatorEntity[BoschComModuleCoordinatorBaconRac], ClimateEntity
):
    """Climate entity for a Matter/Bacon-commissioned RAC controlled over MQTT."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1.0
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_fan_modes = BACON_FAN_MODES
    _attr_swing_modes = [SWING_OFF, SWING_ON]
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.AUTO,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: BoschComModuleCoordinatorBaconRac) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}-climate"
        title = _clean_bacon_title(self._reported.get("customTitle"))
        if title:
            coordinator.device_info["name"] = title
        self._attr_device_info = coordinator.device_info

    @property
    def _reported(self) -> dict:
        data = self.coordinator.data
        return (data.reported if data else {}) or {}

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation."""
        reported = self._reported
        if not reported.get("powerEnabled"):
            return HVACMode.OFF
        return BACON_OP_MODE_TO_HVAC.get(reported.get("opMode"), HVACMode.AUTO)

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._reported.get("tempSetpoint")

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        return self._reported.get("fanSpeed")

    @property
    def swing_mode(self) -> str:
        """Return the swing setting."""
        reported = self._reported
        if reported.get("hSwingEnabled") or reported.get("vSwingEnabled"):
            return SWING_ON
        return SWING_OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.coordinator.bhc.async_set_temperature(int(temperature))
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new operation mode."""
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.bhc.async_set_power(False)
        else:
            await self.coordinator.bhc.async_set_power(
                True, BACON_HVAC_TO_OP_MODE.get(hvac_mode)
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.coordinator.bhc.async_set_power(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.coordinator.bhc.async_set_power(False)
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        await self.coordinator.bhc.async_set_fan(fan_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new swing mode (drives both horizontal and vertical louvers)."""
        enabled = swing_mode == SWING_ON
        await self.coordinator.bhc.async_set_swing(
            horizontal=enabled, vertical=enabled
        )
        await self.coordinator.async_request_refresh()
