"""Bosch HomeCom Custom Component."""

from homeassistant import config_entries, core
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BoschComModuleCoordinator


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom devices."""
    coordinators = config_entry.runtime_data
    async_add_entities(
        BoschComSensorNotifications(coordinator=coordinator)
        for coordinator in coordinators
    )


class BoschComSensorNotifications(SensorEntity):
    """Representation of BoschCom mptofocatopm text."""

    _attr_should_poll = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinator,
    ) -> None:
        """Initialize text entity."""
        super().__init__()
        self._coordinator = coordinator
        self._attr_unique_id = coordinator.data.device["deviceId"] + "_notifications"
        self._attr_name = coordinator.data.device["deviceId"] + "_notifications"
        self._attr_native_value = coordinator.data.notifications
        self._attr_native_max = 1000
        self.name = (
            "Bosch_"
            + coordinator.data.device["deviceType"]
            + "_"
            + coordinator.data.device["deviceId"]
            + "_notifications"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._coordinator.device["deviceId"])},
        )

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""

    @property
    def native_value(self) -> str | None:
        """Return the value reported by the text."""
        return self._coordinator.data.notifications

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self._coordinator.data.notifications
