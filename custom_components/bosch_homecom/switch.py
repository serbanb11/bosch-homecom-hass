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
    BoschComModuleCoordinatorRrc2,
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
        if coordinator.data.device["deviceType"] in ("k30", "k40"):
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
    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] == "rrc2":
            entities.extend(_build_rrc2_switches(coordinator))
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
        self._attr_suggested_object_id = field
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
        self._attr_suggested_object_id = field + "_childlock"
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


# ---- RRC2 switches ----------------------------------------------------------


def _coerce_bool(value: Any) -> bool | None:
    """Coerce stringy boolean values to a bool."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "on", "1")


class BoschComRrc2AwayModeSwitch(CoordinatorEntity, SwitchEntity):
    """System-level away/holiday mode (writes /system/awayMode/enabled)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:home-export-outline"

    def __init__(self, coordinator: BoschComModuleCoordinatorRrc2) -> None:
        """Initialize away mode switch."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-away-mode"
        self._attr_name = "away_mode"
        self._attr_should_poll = False

    @property
    def is_on(self) -> bool | None:
        """Return away-mode state."""
        return _coerce_bool((self.coordinator.data.away_mode or {}).get("value"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable away mode."""
        await self.coordinator.bhc.async_put_away_mode(
            self.coordinator.data.device["deviceId"], "true"
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable away mode."""
        await self.coordinator.bhc.async_put_away_mode(
            self.coordinator.data.device["deviceId"], "false"
        )
        await self.coordinator.async_request_refresh()


class BoschComRrc2CircuitFieldSwitch(CoordinatorEntity, SwitchEntity):
    """Boolean field on an RRC2 HC or DHW circuit."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorRrc2,
        *,
        scope: str,
        circuit_id: str,
        field: str,
        setter: str,
        name_suffix: str,
        unique_suffix: str,
        icon: str | None = None,
    ) -> None:
        """Initialize one circuit-scoped switch."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_name = name_suffix
        self._attr_should_poll = False
        if icon:
            self._attr_icon = icon
        self._scope = scope
        self._circuit_id = circuit_id
        self._field = field
        self._setter = setter

    def _find_circuit(self) -> dict | None:
        refs = (
            self.coordinator.data.heating_circuits
            if self._scope == "hc"
            else self.coordinator.data.dhw_circuits
        )
        suffix = f"/{self._circuit_id}"
        for ref in refs or []:
            if ref.get("id", "").endswith(suffix):
                return ref
        return None

    @property
    def is_on(self) -> bool | None:
        """Return current state of the field."""
        ref = self._find_circuit()
        if not ref:
            return None
        node = ref.get(self._field)
        if not isinstance(node, dict):
            return None
        return _coerce_bool(node.get("value"))

    async def _put(self, value: str) -> None:
        setter = getattr(self.coordinator.bhc, self._setter)
        await setter(self.coordinator.data.device["deviceId"], self._circuit_id, value)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the field on."""
        await self._put("true")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the field off."""
        await self._put("false")


def _build_rrc2_switches(
    coordinator: BoschComModuleCoordinatorRrc2,
) -> list[SwitchEntity]:
    """Build the standard RRC2 switch set for one device."""
    entities: list[SwitchEntity] = [BoschComRrc2AwayModeSwitch(coordinator)]

    for dev in coordinator.data.devices or []:
        child_lock = dev.get("childLockEnabled") or {}
        if child_lock.get("value") is None:
            continue
        dev_id = dev["id"].split("/")[-1]
        entities.append(BoschComChildLockSwitch(coordinator=coordinator, field=dev_id))

    for ref in coordinator.data.heating_circuits or []:
        hc_id = ref["id"].split("/")[-1]
        if isinstance(ref.get("nightSwitchMode"), dict):
            entities.append(
                BoschComRrc2CircuitFieldSwitch(
                    coordinator,
                    scope="hc",
                    circuit_id=hc_id,
                    field="nightSwitchMode",
                    setter="async_set_hc_night_switch_mode",
                    name_suffix=f"{hc_id}_night_switch_mode",
                    unique_suffix=f"{hc_id}-night-switch-mode",
                )
            )

    for ref in coordinator.data.dhw_circuits or []:
        dhw_id = ref["id"].split("/")[-1]
        if isinstance(ref.get("extraDhw"), dict):
            entities.append(
                BoschComRrc2CircuitFieldSwitch(
                    coordinator,
                    scope="dhw",
                    circuit_id=dhw_id,
                    field="extraDhw",
                    setter="async_set_dhw_extra_dhw",
                    name_suffix=f"{dhw_id}_extra_dhw",
                    unique_suffix=f"{dhw_id}-extra-dhw",
                    icon="mdi:water-boiler",
                )
            )
        if isinstance(ref.get("thermalDisinfectState"), dict):
            entities.append(
                BoschComRrc2CircuitFieldSwitch(
                    coordinator,
                    scope="dhw",
                    circuit_id=dhw_id,
                    field="thermalDisinfectState",
                    setter="async_set_dhw_thermal_disinfect_state",
                    name_suffix=f"{dhw_id}_thermal_disinfect",
                    unique_suffix=f"{dhw_id}-thermal-disinfect",
                )
            )

    return entities
