"""Bosch HomeCom Custom Component."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries, core
from homeassistant.components.number import NumberEntity, NumberMode
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
    """Set up the BoschCom number entities."""
    coordinators = config_entry.runtime_data
    entities = []
    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] == "commodule":
            for cp in coordinator.data.charge_points or []:
                cp_id = cp["id"].split("/")[-1]
                entities.append(
                    BoschComCommodulePriceNumber(
                        coordinator=coordinator, cp_id=cp_id
                    )
                )
    async_add_entities(entities)


class BoschComCommodulePriceNumber(CoordinatorEntity, NumberEntity):
    """Representation of a commodule electricity price number."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        cp_id: str,
    ) -> None:
        """Initialize number entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "wb_price"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{cp_id}-price"
        self._coordinator = coordinator
        self._cp_id = cp_id

    def _get_cp_data(self) -> dict | None:
        """Get charge point data."""
        for cp in self._coordinator.data.charge_points or []:
            if cp["id"].split("/")[-1] == self._cp_id:
                return cp
        return None

    @property
    def native_value(self) -> float | None:
        """Get current price value."""
        cp = self._get_cp_data()
        if cp is None:
            return None
        price = cp.get("price")
        if price is None:
            return None
        return price.get("value")

    async def async_set_native_value(self, value: float) -> None:
        """Set new price value."""
        device_id = self._coordinator.data.device["deviceId"]
        await self._coordinator.bhc.async_put_cp_conf_price(
            device_id, self._cp_id, value
        )
        await self._coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        cp = self._get_cp_data()
        if cp is not None:
            price = cp.get("price")
            if price is not None:
                self._attr_native_value = price.get("value")
            else:
                self._attr_native_value = None
        else:
            self._attr_native_value = None
        self.async_write_ha_state()
