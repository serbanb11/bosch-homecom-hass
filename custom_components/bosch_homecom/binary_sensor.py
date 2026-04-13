"""Bosch HomeCom Custom Component."""

from __future__ import annotations

from homeassistant import config_entries, core
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import (
    BoschComModuleCoordinatorCommodule,
    BoschComModuleCoordinatorK40,
)

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
        if coordinator.data.device["deviceType"] in ("k30", "k40", "icom", "rrc2"):
            for dev in coordinator.data.devices or []:
                if dev.get("rfConnectionStatus"):
                    dev_id = dev["id"].split("/")[-1]
                    entities.append(
                        BoschComThermostatRfStatusSensor(
                            coordinator=coordinator, dev_id=dev_id
                        )
                    )
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
        return eth0 in ("on", "connected") or wifi in ("on", "connected")

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
            self._attr_is_on = eth0 in ("on", "connected") or wifi in (
                "on",
                "connected",
            )
        self.async_write_ha_state()


class BoschComThermostatRfStatusSensor(CoordinatorEntity, BinarySensorEntity):
    """Thermostat RF connection status binary sensor."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        dev_id: str,
    ) -> None:
        """Initialize RF status binary sensor."""
        super().__init__(coordinator)
        self._attr_translation_key = "thermostat_rf_status"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{dev_id}-rf_status"
        self._coordinator = coordinator
        self._dev_id = dev_id

    def _get_rf_status(self) -> str | None:
        """Get RF connection status value."""
        for dev in self._coordinator.data.devices or []:
            if dev.get("id", "").endswith(f"/{self._dev_id}"):
                return (dev.get("rfConnectionStatus") or {}).get("value")
        return None

    @property
    def is_on(self) -> bool | None:
        """Return True if RF connection is active."""
        status = self._get_rf_status()
        if status is None:
            return None
        return status.lower() in ("online", "connected", "on")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        status = self._get_rf_status()
        if status is None:
            self._attr_is_on = None
        else:
            self._attr_is_on = status.lower() in ("online", "connected", "on")
        self.async_write_ha_state()
