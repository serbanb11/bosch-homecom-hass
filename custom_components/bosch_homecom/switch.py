"""Bosch HomeCom Custom Component."""

from typing import Any

from homeassistant import config_entries, core
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinatorK40, BoschComModuleCoordinatorRac

PARALLEL_UPDATES = 1


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
    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] in ("k30", "k40", "icom", "rrc2"):
            for dev in coordinator.data.devices or []:
                if dev.get("childLock") and dev["childLock"].get("value") is not None:
                    dev_id = dev["id"].split("/")[-1]
                    entities.append(
                        BoschComChildLockSwitch(coordinator=coordinator, field=dev_id)
                    )
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


class BoschComChildLockSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a BoschCom child lock switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
    ) -> None:
        """Initialize child lock switch entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "child_lock"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}-childlock"
        self._attr_name = field + "_childlock"
        self._coordinator = coordinator
        self._attr_should_poll = False
        self.field = field

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off child lock."""
        await self._coordinator.bhc.async_set_child_lock(
            self._coordinator.data.device["deviceId"], self.field, False
        )

        await self._coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on child lock."""
        await self._coordinator.bhc.async_set_child_lock(
            self._coordinator.data.device["deviceId"], self.field, True
        )

        await self._coordinator.async_request_refresh()

    @property
    def is_on(self) -> bool | None:
        """Get child lock status."""
        for dev in self._coordinator.data.devices or []:
            if dev.get("id", "").endswith(f"/{self.field}"):
                child_lock = dev.get("childLock") or {}
                value = child_lock.get("value")
                if value is not None:
                    return bool(value) if isinstance(value, bool) else value == "on"
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        for dev in self._coordinator.data.devices or []:
            if dev.get("id", "").endswith(f"/{self.field}"):
                child_lock = dev.get("childLock") or {}
                value = child_lock.get("value")
                if value is not None:
                    self._attr_is_on = (
                        bool(value) if isinstance(value, bool) else value == "on"
                    )
        self.async_write_ha_state()
