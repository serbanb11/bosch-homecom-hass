"""Bosch HomeCom Custom Component."""

from homeassistant import config_entries, core
from homeassistant.components.text import TextEntity
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinator


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom devices."""
    coordinators = config_entry.runtime_data
    async_add_entities(
        BoschComSensorNotifications(coordinator=coordinator, field="notifications")
        for coordinator in coordinators
    )


class BoschComSensorNotifications(CoordinatorEntity, TextEntity):
    """Representation of a BoschCom plasmacluster switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinator,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "notifications"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field
        self._coordinator = coordinator
        self._attr_should_poll = False

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""

    @property
    def native_value(self) -> str | None:
        """Return the value reported by the text."""
        return self._coordinator.data.notifications

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self._coordinator.data.notifications
        self.async_write_ha_state()
