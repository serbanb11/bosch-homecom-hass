"""Bosch HomeCom Custom Component Fan."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.components.fan import (
    TURN_OFF,
    TURN_ON,
    FanEntity,
    FanEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import ordered_list_item_to_percentage, percentage_to_ordered_list_item

from .coordinator import BoschComModuleCoordinatorK40

PARALLEL_UPDATES = 1
ORDERED_NAMED_FAN_SPEEDS = ["min", "red", "nom", "max", "dem"]

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom devices."""
    coordinators = config_entry.runtime_data
    for coordinator in coordinators:
        device_type = coordinator.data.device.get("deviceType")
        if device_type in ("k40", "k30"):
            # DHW circuits
            for ref in coordinator.data.ventilation:
                zone_id = ref["id"].split("/")[-1]
                entities.append(
                    BoschComDhwFan(
                        coordinator=coordinator, config_entry=config_entry, field=zone_id
                    )
                )


class BoschComDhwFan(CoordinatorEntity, FanEntity):
    """Representation of a BoschCom fan entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.TURN_ON
    )

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            name=field + "_fan",
            unique_id=f"{coordinator.unique_id}-{field}-fan",
            icon="mdi:fan",
        )
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
    def percentage(self) -> Optional[int]:
        """Return the current speed percentage."""
        return ordered_list_item_to_percentage(ORDERED_NAMED_FAN_SPEEDS, self._exhaustFanLevel)

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
            preset_mode = self._preset_mode
        await self.coordinator.bhc.async_set_ventilation_mode(self._attr_unique_id, self.field, preset_mode)

        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(
        self,
        preset_mode: str | None = None
    ) -> None:
        """Set new preset mode."""
        await self.coordinator.bhc.async_set_ventilation_mode(self._attr_unique_id, self.field, preset_mode)

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn off."""
        await self.coordinator.bhc.async_set_ventilation_mode(self._attr_unique_id, self.field, '"off"')

        await self.coordinator.async_request_refresh()

    @property
    def is_on(self) -> bool:
        """Return true if fan is on."""
        return self._exhaustFanLevel != '"off"'

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        return self._operationMode

    def set_attr(self) -> None:
        """Populate attributes with data from the coordinator."""
        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.ventialtion:
            if entry.get("id") == "/ventilation/" + self.field:
                self._operationMode = safe_get(
                    entry["operationMode"], "value"
                )
                self._preset_modes = safe_get(
                    entry["operationMode"], "allowedValues"
                )
                self._exhaustFanLevel = safe_get(
                    entry["exhaustFanLevel"], "value"
                )