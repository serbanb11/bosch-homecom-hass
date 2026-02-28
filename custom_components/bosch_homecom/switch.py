"""Bosch HomeCom Custom Component."""

from typing import Any

from homeassistant import config_entries, core
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import (
    BoschComModuleCoordinatorCommodule,
    BoschComModuleCoordinatorK40,
    BoschComModuleCoordinatorRac,
)

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
    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] == "commodule":
            for cp in coordinator.data.charge_points or []:
                cp_id = cp["id"].split("/")[-1]
                entities.append(
                    BoschComCommoduleLockSwitch(coordinator=coordinator, cp_id=cp_id)
                )
                entities.append(
                    BoschComCommoduleAuthSwitch(coordinator=coordinator, cp_id=cp_id)
                )
                entities.append(
                    BoschComCommoduleRfidSecureSwitch(
                        coordinator=coordinator, cp_id=cp_id
                    )
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
            self._coordinator.data.device["deviceId"], self.field, "false"
        )

        await self._coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on child lock."""
        await self._coordinator.bhc.async_set_child_lock(
            self._coordinator.data.device["deviceId"], self.field, "true"
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
                    return (
                        bool(value)
                        if isinstance(value, bool)
                        else value in ("on", "true")
                    )
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
                        bool(value)
                        if isinstance(value, bool)
                        else value in ("on", "true")
                    )
        self.async_write_ha_state()


class _BoschComCommoduleSwitchBase(CoordinatorEntity, SwitchEntity):
    """Base class for commodule charge point switches."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    # Subclasses must set these
    _data_key: str = ""
    _setter_method: str = ""

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        cp_id: str,
        translation_key: str,
        unique_suffix: str,
    ) -> None:
        """Initialize switch entity."""
        super().__init__(coordinator)
        self._attr_translation_key = translation_key
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{cp_id}-{unique_suffix}"
        self._coordinator = coordinator
        self._cp_id = cp_id

    def _get_cp_data(self) -> dict | None:
        """Get charge point data."""
        for cp in self._coordinator.data.charge_points or []:
            if cp["id"].split("/")[-1] == self._cp_id:
                return cp
        return None

    @property
    def is_on(self) -> bool | None:
        """Get switch status."""
        cp = self._get_cp_data()
        if cp is None:
            return None
        data = cp.get(self._data_key)
        if data is None:
            return None
        return data.get("value") == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on switch."""
        device_id = self._coordinator.data.device["deviceId"]
        setter = getattr(self._coordinator.bhc, self._setter_method)
        await setter(device_id, self._cp_id, "on")
        await self._coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off switch."""
        device_id = self._coordinator.data.device["deviceId"]
        setter = getattr(self._coordinator.bhc, self._setter_method)
        await setter(device_id, self._cp_id, "off")
        await self._coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        cp = self._get_cp_data()
        if cp is not None:
            data = cp.get(self._data_key)
            if data is not None:
                self._attr_is_on = data.get("value") == "on"
            else:
                self._attr_is_on = None
        else:
            self._attr_is_on = None
        self.async_write_ha_state()


class BoschComCommoduleLockSwitch(_BoschComCommoduleSwitchBase):
    """Representation of a commodule lock switch."""

    _data_key = "locked"
    _setter_method = "async_put_cp_conf_locked"

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        cp_id: str,
    ) -> None:
        """Initialize lock switch."""
        super().__init__(coordinator, cp_id, "wb_locked", "locked")


class BoschComCommoduleAuthSwitch(_BoschComCommoduleSwitchBase):
    """Representation of a commodule auth switch."""

    _data_key = "auth"
    _setter_method = "async_put_cp_conf_auth"

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        cp_id: str,
    ) -> None:
        """Initialize auth switch."""
        super().__init__(coordinator, cp_id, "wb_auth", "auth")


class BoschComCommoduleRfidSecureSwitch(_BoschComCommoduleSwitchBase):
    """Representation of a commodule RFID secure switch."""

    _data_key = "rfidSecure"
    _setter_method = "async_put_cp_conf_rfid_secure"

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        cp_id: str,
    ) -> None:
        """Initialize RFID secure switch."""
        super().__init__(coordinator, cp_id, "wb_rfid_secure", "rfid_secure")
