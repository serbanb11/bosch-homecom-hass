"""Bosch HomeCom Custom Component."""

from __future__ import annotations

from homeassistant import config_entries, core
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinatorCommodule

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom binary sensors."""
    coordinators = config_entry.runtime_data
    entities = []
    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] == "commodule":
            entities.append(BoschComCommoduleNetworkSensor(coordinator=coordinator))
    async_add_entities(entities)


class BoschComCommoduleNetworkSensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a commodule network connectivity sensor."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
    ) -> None:
        """Initialize binary sensor entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "wb_network"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-eth0-state"
        self._coordinator = coordinator

    @staticmethod
    def _get_state_value(state: dict | None) -> str | None:
        """Extract value from a state dict."""
        if isinstance(state, dict):
            return state.get("value")
        return None

    @property
    def is_on(self) -> bool | None:
        """Get network connectivity status (eth0 or wifi)."""
        eth0 = self._get_state_value(self._coordinator.data.eth0_state)
        wifi = self._get_state_value(self._coordinator.data.wifi_state)
        if eth0 is None and wifi is None:
            return None
        return eth0 == "on" or wifi == "on"

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return which network interfaces are active."""
        eth0 = self._get_state_value(self._coordinator.data.eth0_state)
        wifi = self._get_state_value(self._coordinator.data.wifi_state)
        return {"eth0": eth0, "wifi": wifi}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        eth0 = self._get_state_value(self._coordinator.data.eth0_state)
        wifi = self._get_state_value(self._coordinator.data.wifi_state)
        if eth0 is None and wifi is None:
            self._attr_is_on = None
        else:
            self._attr_is_on = eth0 == "on" or wifi == "on"
        self.async_write_ha_state()
