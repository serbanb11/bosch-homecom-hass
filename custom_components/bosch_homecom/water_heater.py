"""Bosch HomeCom Custom Component."""

from homeassistant import config_entries
from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import re

from typing import Any

from .coordinator import BoschComModuleCoordinatorK40, BoschComModuleCoordinatorWddw2


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom devices."""
    coordinators = config_entry.runtime_data
    entities = []

    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] == "wddw2":
            for ref in coordinator.data.dhw_circuits:
                dhw_id = ref["id"].split("/")[-1]
                if re.fullmatch(r"dhw\d", dhw_id):
                    entities.append(
                        BoschComWddw2WaterHeater(
                            coordinator=coordinator, field=dhw_id
                        )
                    )
        elif coordinator.data.device.get("deviceType") in ("k40", "k30", "icom"):
            entities.append(
                BoschComK40WaterHeater(coordinator=coordinator, field="waterheater")
            )
    async_add_entities(entities)


class BoschComK40WaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Representation of a BoschComK40 water heater entity."""

    _attr_has_entity_name = True
    _attr_name = None
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
        # self._attr_translation_key = "ac"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}"
        self._attr_name = field
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
                self._attr_unique_id, dhw_id, self._operation_map[operation_mode]
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

    def set_attr(self) -> None:
        """Populate attributes with data from the coordinator."""
        self._set_domestic_hot_water_circuits(self.coordinator.data.dhw_circuits)


class BoschComWddw2WaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Representation of a BoschComWddw2 water heater entity."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        WaterHeaterEntityFeature.OPERATION_MODE
        | WaterHeaterEntityFeature.TARGET_TEMPERATURE
    )
    _attr_target_temperature_step = 1

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorWddw2,
        field: str,
    ) -> None:
        """Initialize water heater entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "dhw"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}"
        self._attr_name = field + "_waterheater"
        self._coordinator = coordinator
        self._attr_should_poll = False
        self.field = field

        self._attr_min_temp = 36
        self._attr_max_temp = 60
        self._attr_target_temperature = 45  # será atualizado em set_attr()
        self._attr_current_temperature = None

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
            if dhw_id == self.field:
                await self.coordinator.bhc.async_put_dhw_operation_mode(
                    self._attr_unique_id, dhw_id, operation_mode
                )
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        try:
            t = int(round(float(temperature)))
        except (TypeError, ValueError):
            return
        t = max(int(self._attr_min_temp), min(int(self._attr_max_temp), t))

        current_mode = getattr(self, "_attr_current_operation", None)
        for ref in self.coordinator.data.dhw_circuits:
            dhw_id = ref["id"].split("/")[-1]
            if dhw_id != self.field:
                continue
            if current_mode != "manual":
                await self.coordinator.bhc.async_put_dhw_operation_mode(
                    self._attr_unique_id, dhw_id, "manual"
                )
            await self.coordinator.bhc.async_set_dhw_temp_level(
                self._attr_unique_id, dhw_id, "manual", t
            )

        # pede refresh para refletir no UI
        await self.coordinator.async_request_refresh()


    def _set_domestic_hot_water_circuits(
        self, domestic_hot_water_circuits: list[dict]
    ) -> None:
        """Populate heating circuits."""
        operationMode_value = None
        actualTemp_value = None

        for ref in domestic_hot_water_circuits:
            dhw_id = ref["id"].split("/")[-1]
            if dhw_id != self.field:
                continue

            op = (ref.get("operationMode") or {}).get("value")
            allowed = (ref.get("operationMode") or {}).get("allowedValues") or []
            self._attr_operation_list = allowed
            self._attr_current_operation = op or self._attr_current_operation

            # limites do setpoint manual (usados no clamp e stepper)
            manual = (ref.get("tempLevel") or {}).get("manual") or {}
            self._attr_min_temp = manual.get("minValue", self._attr_min_temp)
            self._attr_max_temp = manual.get("maxValue", self._attr_max_temp)

            # o setpoint alvo depende do modo atual: tempLevel[mode].value
            tl = (ref.get("tempLevel") or {})
            set_for_mode = (tl.get(op) or {}).get("value")
            if isinstance(set_for_mode, (int, float)):
                self._attr_target_temperature = set_for_mode

            # se tiveres uma “current water temperature” real, podes meter aqui;
            # caso não exista, deixa None para não confundir
            self._attr_current_temperature = None

    def set_attr(self) -> None:
        """Populate attributes with data from the coordinator."""
        self._set_domestic_hot_water_circuits(self.coordinator.data.dhw_circuits)
