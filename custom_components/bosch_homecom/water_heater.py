"""Bosch HomeCom Custom Component."""

from __future__ import annotations

import re
from typing import Any

from homeassistant import config_entries
from homeassistant.components.water_heater import (
    DOMAIN as WATER_HEATER_DOMAIN,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BoschComModuleCoordinatorK40, BoschComModuleCoordinatorWddw2


def _parse_temp_unit(unit_str: str | None) -> str:
    """Map API unitOfMeasure string to HA temperature unit."""
    if unit_str == "F":
        return UnitOfTemperature.FAHRENHEIT
    return UnitOfTemperature.CELSIUS


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom devices."""
    coordinators = config_entry.runtime_data
    entity_registry = er.async_get(hass)
    entities = []

    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] == "wddw2":
            for ref in coordinator.data.dhw_circuits:
                dhw_id = ref["id"].split("/")[-1]
                if re.fullmatch(r"dhw\d", dhw_id):
                    _migrate_unique_id(entity_registry, coordinator.unique_id, dhw_id)
                    entities.append(
                        BoschComWddw2WaterHeater(coordinator=coordinator, field=dhw_id)
                    )
        elif coordinator.data.device.get("deviceType") in ("k40", "k30"):
            _migrate_unique_id(entity_registry, coordinator.unique_id, "waterheater")
            entities.append(
                BoschComK40WaterHeater(coordinator=coordinator, field="waterheater")
            )
    async_add_entities(entities)


@callback
def _migrate_unique_id(
    entity_registry: er.EntityRegistry, device_unique_id: str, field: str
) -> None:
    """Migrate the legacy water heater unique_id to the per-circuit scheme.

    Older versions registered the water heater with the bare device unique_id.
    Rename that entry to ``{device_unique_id}-{field}`` so existing entities
    (and their history) are preserved instead of being orphaned.
    """
    new_unique_id = f"{device_unique_id}-{field}"
    entity_id = entity_registry.async_get_entity_id(
        WATER_HEATER_DOMAIN, DOMAIN, device_unique_id
    )
    if entity_id is None:
        return
    # Only migrate when the target unique_id isn't already taken (e.g. a second
    # DHW circuit must not steal the legacy entry once dhw1 has claimed it).
    if entity_registry.async_get_entity_id(WATER_HEATER_DOMAIN, DOMAIN, new_unique_id):
        return
    entity_registry.async_update_entity(entity_id, new_unique_id=new_unique_id)


class BoschComK40WaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Representation of a BoschComK40 water heater entity."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = WaterHeaterEntityFeature.OPERATION_MODE
    _attr_operation_list = ["Eco+", "Eco", "Comfort", "Program", "Off"]

    _operation_map = {
        "Eco+": "eco",
        "Eco": "low",
        "Comfort": "high",
        "Program": "ownprogram",
        "Off": "Off",
    }
    _ioperation_map = {}

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
    ) -> None:
        """Initialize water heater entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "dhw"
        # The K40 API exposes a single DHW circuit without a numeric id, so the
        # "circuit" placeholder is set to a fixed "dhw1" label for the name.
        self._attr_translation_placeholders = {"circuit": "dhw1"}
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_suggested_object_id = field + "_waterheater"
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._ioperation_map = {v: k for k, v in self._operation_map.items()}

        # Call this in __init__ so data is populated right away, since it's
        # already available in the coordinator data.
        self.set_attr()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.set_attr()
        self.async_write_ha_state()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new target operation mode."""
        for ref in self.coordinator.data.dhw_circuits:
            dhw_id = ref["id"].split("/")[-1]
            await self.coordinator.bhc.async_put_dhw_operation_mode(
                self.coordinator.unique_id, dhw_id, self._operation_map[operation_mode]
            )
        await self.coordinator.async_request_refresh()

    def _set_domestic_hot_water_circuits(
        self, domestic_hot_water_circuits: list[dict]
    ) -> None:
        """Populate heating circuits."""

        for ref in domestic_hot_water_circuits:
            for key in ref:
                match key:
                    case "operationMode":
                        self._attr_current_operation = self._ioperation_map[
                            ref[key]["value"]
                        ]
                    case "actualTemp":
                        self._attr_current_temperature = ref[key]["value"]
                        self._attr_temperature_unit = _parse_temp_unit(
                            ref[key].get("unitOfMeasure")
                        )

    def set_attr(self) -> None:
        """Populate attributes with data from the coordinator."""
        self._set_domestic_hot_water_circuits(self.coordinator.data.dhw_circuits)


class BoschComWddw2WaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Representation of a BoschComWddw2 water heater entity.

    Operation modes are exposed as raw API values (``manual``, ``bath``, ...)
    and localized via the entity ``state`` translations. Read-only devices
    (e.g. Tronic TR4001, ``writeable == 0``) drop the corresponding supported
    feature so the UI does not offer non-functional controls.
    """

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = WaterHeaterEntityFeature(0)
    _attr_target_temperature_step = 1

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorWddw2,
        field: str,
    ) -> None:
        """Initialize water heater entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "dhw_wddw2"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_suggested_object_id = field + "_waterheater"
        self._coordinator = coordinator
        self._attr_should_poll = False
        self.field = field

        self._attr_min_temp = 36
        self._attr_max_temp = 60
        self._attr_target_temperature = None
        self._attr_current_temperature = None

        # Populate right away since the data is already in the coordinator.
        self.set_attr()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.set_attr()
        self.async_write_ha_state()

    def _circuit(self) -> dict | None:
        """Return the dhw circuit this entity represents."""
        for ref in self.coordinator.data.dhw_circuits or []:
            if ref["id"].split("/")[-1] == self.field:
                return ref
        return None

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new target operation mode."""
        ref = self._circuit()
        if ref is None:
            return
        if (ref.get("operationMode") or {}).get("writeable", 1) == 0:
            return
        await self.coordinator.bhc.async_put_dhw_operation_mode(
            self.coordinator.unique_id, self.field, operation_mode
        )
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature (only on devices with a writable setpoint)."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        try:
            t = int(round(float(temperature)))
        except (TypeError, ValueError):
            return
        t = max(int(self._attr_min_temp), min(int(self._attr_max_temp), t))

        ref = self._circuit()
        if ref is None:
            return
        manual = (ref.get("tempLevel") or {}).get("manual") or {}
        # Only write when the device explicitly reports a writable setpoint
        # (mirrors the TARGET_TEMPERATURE capability detection).
        if not manual.get("writeable"):
            return

        current_mode = getattr(self, "_attr_current_operation", None)
        if current_mode != "manual":
            await self.coordinator.bhc.async_put_dhw_operation_mode(
                self.coordinator.unique_id, self.field, "manual"
            )
        await self.coordinator.bhc.async_set_dhw_temp_level(
            self.coordinator.unique_id, self.field, "manual", t
        )
        await self.coordinator.async_request_refresh()

    def _set_domestic_hot_water_circuits(
        self, domestic_hot_water_circuits: list[dict]
    ) -> None:
        """Populate attributes and supported features from the dhw circuit."""
        for ref in domestic_hot_water_circuits:
            dhw_id = ref["id"].split("/")[-1]
            if dhw_id != self.field:
                continue

            features = WaterHeaterEntityFeature(0)

            op_node = ref.get("operationMode") or {}
            op = op_node.get("value")
            allowed = op_node.get("allowedValues") or []
            if allowed:
                self._attr_operation_list = allowed
            if op:
                self._attr_current_operation = op
            if op_node.get("writeable", 1) != 0:
                features |= WaterHeaterEntityFeature.OPERATION_MODE

            temp_level = ref.get("tempLevel") or {}
            manual = temp_level.get("manual") or {}
            self._attr_min_temp = manual.get("minValue", self._attr_min_temp)
            self._attr_max_temp = manual.get("maxValue", self._attr_max_temp)

            unit_str = manual.get("unitOfMeasure")
            if unit_str:
                self._attr_temperature_unit = _parse_temp_unit(unit_str)

            set_for_mode = (temp_level.get(op) or {}).get("value")
            if isinstance(set_for_mode, (int, float)):
                self._attr_target_temperature = set_for_mode

            # Only offer temperature control when the setpoint is writable.
            if manual.get("writeable"):
                features |= WaterHeaterEntityFeature.TARGET_TEMPERATURE

            outlet = ref.get("outletTemperature") or {}
            if isinstance(outlet, dict) and isinstance(
                outlet.get("value"), (int, float)
            ):
                self._attr_current_temperature = outlet["value"]

            self._attr_supported_features = features

    def set_attr(self) -> None:
        """Populate attributes with data from the coordinator."""
        self._set_domestic_hot_water_circuits(self.coordinator.data.dhw_circuits)
