"""Bosch HomeCom Custom Component."""

from __future__ import annotations

from homeassistant import config_entries, core
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .bacon import bacon_meta_state
from .const import BACON_AP_TYPE, CONF_WB_LABEL, DEFAULT_WB_LABEL
from .coordinator import (
    BoschComModuleCoordinatorBaconRac,
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
    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] == BACON_AP_TYPE and (
            "filterReset" in (getattr(coordinator.data, "reported", None) or {})
            or "filterReset" in bacon_meta_state(coordinator.data.metadata)
        ):
            entities.append(BoschComBaconFilterResetButton(coordinator))

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


# --- Bacon (Matter-commissioned) air purifier --------------------------------


class BoschComBaconFilterResetButton(
    CoordinatorEntity[BoschComModuleCoordinatorBaconRac], ButtonEntity
):
    """Write the purifier's ``filterReset`` flag after a filter change.

    Disabled by default: the HomeCom app never writes this field (its filter
    replacement screen is purely instructional), so whether the device resets
    ``filterCapacity`` and clears the flag on its own is unverified (#203). The
    shadow and meta both list it as writable, so it is offered for those who
    want to try — the reported flag is exposed as an attribute to watch.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "bacon_filter_reset"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: BoschComModuleCoordinatorBaconRac) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}-filter-reset"
        self._attr_device_info = coordinator.device_info

    @property
    def extra_state_attributes(self) -> dict[str, bool]:
        """Expose the reported flag so a press's effect can be seen."""
        data = self.coordinator.data
        value = ((getattr(data, "reported", None) if data else None) or {}).get(
            "filterReset"
        )
        return {"filter_reset_reported": value} if isinstance(value, bool) else {}

    async def async_press(self) -> None:
        """Acknowledge a filter change."""
        await self.coordinator.bhc.async_reset_filter()
        await self.coordinator.async_request_refresh()
