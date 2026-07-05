"""Bosch HomeCom Custom Component."""

from __future__ import annotations

from homeassistant import config_entries, core
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_WB_LABEL, DEFAULT_WB_LABEL
from .coordinator import (
    BoschComModuleCoordinatorCommodule,
    BoschComModuleCoordinatorIcom,
    BoschComModuleCoordinatorK40,
)

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
                    BoschComCommoduleAuthenticateButton(
                        coordinator=coordinator, cp_id=cp_id
                    )
                )
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
    # Extra K40/ICOM button entities
    for coordinator in coordinators:
        if isinstance(
            coordinator,
            (BoschComModuleCoordinatorK40, BoschComModuleCoordinatorIcom),
        ):
            # DHW charge button — available if device has dhw_circuits
            if coordinator.data.dhw_circuits:
                entities.append(BoschComK40DhwChargeButton(coordinator))

    async_add_entities(entities)


class BoschComCommoduleAuthenticateButton(CoordinatorEntity, ButtonEntity):
    """Button to authenticate on a wallbox charge point."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        cp_id: str,
    ) -> None:
        """Initialize authenticate button."""
        super().__init__(coordinator)
        self._attr_translation_key = "wb_authenticate"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{cp_id}-authenticate"
        self._coordinator = coordinator
        self._cp_id = cp_id

    async def async_press(self) -> None:
        """Authenticate on charge point."""
        device_id = self._coordinator.data.device["deviceId"]
        label = self._coordinator.entry.options.get(CONF_WB_LABEL, DEFAULT_WB_LABEL)
        await self._coordinator.bhc.async_cp_authenticate(device_id, self._cp_id, label)
        await self._coordinator.async_request_refresh()


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
        label = self._coordinator.entry.options.get(CONF_WB_LABEL, DEFAULT_WB_LABEL)
        await self._coordinator.bhc.async_cp_start_charging(
            device_id, self._cp_id, label
        )
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
        label = self._coordinator.entry.options.get(CONF_WB_LABEL, DEFAULT_WB_LABEL)
        await self._coordinator.bhc.async_cp_pause_charging(
            device_id, self._cp_id, label
        )
        await self._coordinator.async_request_refresh()


# ===================================================================
# Extra K40 button (endpoints not yet in homecom_alt library)
# ===================================================================


class BoschComK40DhwChargeButton(CoordinatorEntity, ButtonEntity):
    """Button to trigger a one-time DHW charge (extra hot water)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: BoschComModuleCoordinatorK40) -> None:
        """Initialize DHW charge button."""
        super().__init__(coordinator)
        self._attr_translation_key = "dhw_extra_charge"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-dhw_extra_charge"
        self._attr_suggested_object_id = "dhw_extra_charge"

    async def async_press(self) -> None:
        """Trigger a single hot water charge."""
        await self.coordinator.bhc.async_set_dhw_charge(
            self.coordinator.data.device["deviceId"], "dhw1", "start"
        )
        await self.coordinator.async_request_refresh()
