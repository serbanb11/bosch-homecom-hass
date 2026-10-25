"""Bosch HomeCom Custom Component Fan."""

from __future__ import annotations

import math
from typing import Any

from homeassistant import config_entries
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)
from homeassistant.util.scaling import int_states_in_range

from .bacon import BACON_AP_MODE_MANUAL, BACON_AP_MODES, bacon_meta_state
from .const import BACON_AP_TYPE
from .coordinator import BoschComModuleCoordinatorBaconRac, BoschComModuleCoordinatorK40

PARALLEL_UPDATES = 1
ORDERED_NAMED_FAN_SPEEDS = ["min", "red", "nom", "max", "dem"]
# Air 4000i fanSpeed bounds, used until topics/meta says otherwise.
BACON_AP_SPEED_RANGE: tuple[int, int] = (1, 3)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom devices."""
    coordinators = config_entry.runtime_data
    entities: list[FanEntity] = []

    for coordinator in coordinators:
        device_type = coordinator.data.device.get("deviceType")
        if device_type in ("k40", "k30", "icom"):
            # DHW circuits
            for ref in coordinator.data.ventilation or []:
                zone_id = ref["id"].split("/")[-1]
                entities.append(BoschComDhwFan(coordinator=coordinator, field=zone_id))
        elif device_type == BACON_AP_TYPE:
            entities.append(BoschComBaconApFan(coordinator=coordinator))

    if entities:
        async_add_entities(entities)


class BoschComDhwFan(CoordinatorEntity, FanEntity):
    """Representation of a BoschCom fan entity."""

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
    ) -> None:
        """Initialize fan entity."""
        super().__init__(coordinator)
        self.field = field
        self._attr_translation_key = "ventilation"
        self._attr_translation_placeholders = {"zone": field}
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}-fan"
        self._attr_should_poll = False
        self._attr_has_entity_name = True
        self._attr_suggested_object_id = field + "_fan"
        self._attr_supported_features = (
            FanEntityFeature.PRESET_MODE
            | FanEntityFeature.TURN_OFF
            | FanEntityFeature.TURN_ON
        )

        self._operationMode: str | None = None
        self._preset_modes: list[str] | None = None
        self._exhaustFanLevel: str | None = None

        self.set_attr()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.set_attr()
        self.async_write_ha_state()

    @property
    def preset_modes(self) -> list[str] | None:
        """Return a list of available preset modes."""
        return self._preset_modes

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        return ordered_list_item_to_percentage(
            ORDERED_NAMED_FAN_SPEEDS, self._exhaustFanLevel
        )

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return len(ORDERED_NAMED_FAN_SPEEDS)

    async def async_turn_on(
        self,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on."""
        if preset_mode is None:
            preset_mode = self._operationMode
        await self.coordinator.bhc.async_set_ventilation_mode(
            self.coordinator.unique_id, self.field, preset_mode
        )

        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str | None = None) -> None:
        """Set new preset mode."""
        await self.coordinator.bhc.async_set_ventilation_mode(
            self.coordinator.unique_id, self.field, preset_mode
        )

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn off."""
        await self.coordinator.bhc.async_set_ventilation_mode(
            self.coordinator.unique_id, self.field, "off"
        )

        await self.coordinator.async_request_refresh()

    @property
    def is_on(self) -> bool:
        """Return true if fan is on."""
        return self._exhaustFanLevel != "off"

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        return self._operationMode

    def set_attr(self) -> None:
        """Populate attributes with data from the coordinator."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            if data is None:
                return default
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.ventilation or []:
            if entry.get("id") == "/ventilation/" + self.field:
                op_mode = entry.get("operationMode")
                self._operationMode = safe_get(op_mode, "value")
                self._preset_modes = safe_get(op_mode, "allowedValues")
                self._exhaustFanLevel = safe_get(entry.get("exhaustFanLevel"), "value")


# --- Bacon (Matter-commissioned) air purifier --------------------------------


class BoschComBaconApFan(
    CoordinatorEntity[BoschComModuleCoordinatorBaconRac], FanEntity
):
    """The main control of a Matter/Bacon air purifier (Air 4000i), as a fan.

    ``opMode`` (auto/manual/silent) is the preset; ``fanSpeed`` (1..3 per
    topics/meta) is the percentage. The HomeCom app only offers the speed
    selector in manual mode and shows "Auto" otherwise, so the percentage is
    reported only while in manual and setting one switches to manual (#203).
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_translation_key = "bacon_air_purifier"
    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: BoschComModuleCoordinatorBaconRac) -> None:
        """Initialize the fan entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}-fan"
        self._attr_device_info = coordinator.device_info

    @property
    def _reported(self) -> dict:
        data = self.coordinator.data
        return (getattr(data, "reported", None) if data else None) or {}

    @property
    def _meta(self) -> dict:
        data = self.coordinator.data
        return bacon_meta_state(getattr(data, "metadata", None) if data else None)

    @property
    def _speed_range(self) -> tuple[int, int]:
        """The fanSpeed bounds from topics/meta, or the Air 4000i's 1..3."""
        meta = self._meta.get("fanSpeed")
        if isinstance(meta, dict):
            low, high = meta.get("min"), meta.get("max")
            if isinstance(low, int) and isinstance(high, int) and high >= low:
                return (low, high)
        return BACON_AP_SPEED_RANGE

    @property
    def is_on(self) -> bool | None:
        """Return whether the unit is powered on, or None before the first shadow."""
        value = self._reported.get("powerEnabled")
        return value if isinstance(value, bool) else None

    @property
    def preset_modes(self) -> list[str]:
        """Return the operating modes topics/meta advertises, or the known set."""
        meta = self._meta.get("opMode")
        enum = meta.get("enum") if isinstance(meta, dict) else None
        if isinstance(enum, list) and enum:
            return [str(mode) for mode in enum]
        return list(BACON_AP_MODES)

    @property
    def preset_mode(self) -> str | None:
        """Return the active operating mode while on."""
        if not self.is_on:
            return None
        mode = self._reported.get("opMode")
        return mode if mode in self.preset_modes else None

    @property
    def speed_count(self) -> int:
        """Return the number of manual speeds."""
        return int_states_in_range(self._speed_range)

    @property
    def percentage(self) -> int | None:
        """Return the manual speed as a percentage; 0 when off, None in auto/silent.

        In auto and silent the device still reports a ``fanSpeed`` but it is the
        one it chose; the app hides it and shows "Auto", so it is not presented
        as a setting here either (it stays visible as the ``fan_speed`` attribute).
        """
        if self.is_on is False:
            return 0
        if self._reported.get("opMode") != BACON_AP_MODE_MANUAL:
            return None
        speed = self._reported.get("fanSpeed")
        if isinstance(speed, bool) or not isinstance(speed, int):
            return None
        return ranged_value_to_percentage(self._speed_range, speed)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the raw speed, which the device reports in every mode."""
        speed = self._reported.get("fanSpeed")
        if isinstance(speed, bool) or not isinstance(speed, int):
            return {}
        return {"fan_speed": speed}

    def _speed_from_percentage(self, percentage: int) -> int:
        low, high = self._speed_range
        speed = math.ceil(percentage_to_ranged_value(self._speed_range, percentage))
        return max(low, min(high, speed))

    async def async_set_percentage(self, percentage: int) -> None:
        """Set a manual speed; 0 turns the unit off, as Home Assistant expects."""
        if percentage == 0:
            await self.coordinator.bhc.async_set_power(False)
        else:
            await self.coordinator.bhc.async_set_fan_speed(
                self._speed_from_percentage(percentage), power_on=not self.is_on
            )
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Select an operating mode, powering the unit on if needed."""
        if self.is_on:
            await self.coordinator.bhc.async_set_mode(preset_mode)
        else:
            await self.coordinator.bhc.async_set_power(True, preset_mode)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on, optionally straight into a mode or a manual speed."""
        if preset_mode is not None:
            await self.coordinator.bhc.async_set_power(True, preset_mode)
        elif percentage:
            await self.coordinator.bhc.async_set_fan_speed(
                self._speed_from_percentage(percentage), power_on=True
            )
        else:
            await self.coordinator.bhc.async_set_power(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self.coordinator.bhc.async_set_power(False)
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
