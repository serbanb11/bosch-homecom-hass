"""Bosch HomeCom Custom Component."""

from __future__ import annotations

from homeassistant import config_entries, core
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinatorCommodule

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom wallbox charging buttons."""
    coordinators = config_entry.runtime_data
    entities: list[ButtonEntity] = []
    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] == "commodule":
            for cp in coordinator.data.charge_points or []:
                cp_id = cp["id"].split("/")[-1]
                entities.append(
                    BoschComCommoduleStartChargingButton(
                        coordinator=coordinator, cp_id=cp_id
                    )
                )
                entities.append(
                    BoschComCommodulePauseChargingButton(
                        coordinator=coordinator, cp_id=cp_id
                    )
                )
    async_add_entities(entities)


class BoschComCommoduleStartChargingButton(CoordinatorEntity, ButtonEntity):
    """Button to start charging on a wallbox charge point."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        cp_id: str,
    ) -> None:
        """Initialize start charging button."""
        super().__init__(coordinator)
        self._attr_translation_key = "wb_start_charging"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{cp_id}-start_charging"
        self._coordinator = coordinator
        self._cp_id = cp_id

    async def async_press(self) -> None:
        """Start charging."""
        device_id = self._coordinator.data.device["deviceId"]
        await self._coordinator.bhc.async_cp_start_charging(device_id, self._cp_id)
        await self._coordinator.async_request_refresh()


class BoschComCommodulePauseChargingButton(CoordinatorEntity, ButtonEntity):
    """Button to pause charging on a wallbox charge point."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        cp_id: str,
    ) -> None:
        """Initialize pause charging button."""
        super().__init__(coordinator)
        self._attr_translation_key = "wb_pause_charging"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{cp_id}-pause_charging"
        self._coordinator = coordinator
        self._cp_id = cp_id

    async def async_press(self) -> None:
        """Pause charging."""
        device_id = self._coordinator.data.device["deviceId"]
        await self._coordinator.bhc.async_cp_pause_charging(device_id, self._cp_id)
        await self._coordinator.async_request_refresh()
