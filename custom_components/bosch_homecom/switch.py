"""Bosch HomeCom Custom Component."""

import logging
from typing import Any

from homeassistant import config_entries, core
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinatorRac

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom plasmacluster switches."""
    coordinators = config_entry.runtime_data
    entities = [
        BoschComSwitchAirPurification(coordinator=coordinator, field="plasmacluster")
        for coordinator in coordinators
        if coordinator.data.device["deviceType"] == "rac"
        if next(
            (
                ref
                for ref in coordinator.data.advanced_functions
                if "airPurificationMode" in ref["id"]
            ),
            None,
        )
    ]
    async_add_entities(entities)


class BoschComSwitchAirPurification(CoordinatorEntity, SwitchEntity):
    """Representation of a BoschCom plasmacluster switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorRac,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "plasmacluster"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field
        self._coordinator = coordinator
        self._attr_should_poll = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off plasmacluster."""
        await self._coordinator.bhc.async_set_plasmacluster(
            self._coordinator.data.device["deviceId"], False
        )

        await self._coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on plasmacluster."""
        await self._coordinator.bhc.async_set_plasmacluster(
            self._coordinator.data.device["deviceId"], True
        )

        await self._coordinator.async_request_refresh()

    @property
    def is_on(self) -> bool | None:
        """Get air purification status."""
        airPurificationMode = next(
            (
                ref
                for ref in self._coordinator.data.advanced_functions
                if "airPurificationMode" in ref["id"]
            ),
            None,
        )
        if airPurificationMode["value"] == "on":
            return True
        return False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        airPurificationMode = next(
            (
                ref
                for ref in self._coordinator.data.advanced_functions
                if "airPurificationMode" in ref["id"]
            ),
            None,
        )
        if airPurificationMode["value"] == "on":
            self._attr_is_on = True
        else:
            self._attr_is_on = False
        self.async_write_ha_state()
