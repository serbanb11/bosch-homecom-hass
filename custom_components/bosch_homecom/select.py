"""Bosch HomeCom Custom Component."""

from datetime import timedelta
import logging

from homeassistant import config_entries, core
from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1440)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom airflows and porgram selects."""
    coordinators = config_entry.runtime_data
    entities = []
    for coordinator in coordinators:
        if next(
            (
                ref
                for ref in coordinator.data.stardard_functions
                if "airFlowHorizontal" in ref["id"]
            ),
            None,
        ):
            entities.append(
                BoschComSelectAirflowHorizontal(
                    coordinator=coordinator, field="horizontal"
                )
            )
        if next(
            (
                ref
                for ref in coordinator.data.stardard_functions
                if "airFlowVertical" in ref["id"]
            ),
            None,
        ):
            entities.append(
                BoschComSelectAirflowVertical(coordinator=coordinator, field="vertical")
            )
        if next(
            (
                ref
                for ref in coordinator.data.switch_programs
                if "activeProgram" in ref["id"]
            ),
            None,
        ):
            entities.append(
                BoschComSelectProgram(coordinator=coordinator, field="program")
            )
    async_add_entities(entities)


class BoschComSelectAirflowHorizontal(CoordinatorEntity, SelectEntity):
    """Representation of Horizontal airflow select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinator,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "airflow_horizontal"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field
        self._coordinator = coordinator
        self._attr_should_poll = False

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_set_horizontal_swing_mode(
            self._coordinator.data.device["deviceId"], option
        )

        await self._coordinator.async_request_refresh()

    @property
    def options(self) -> list[str]:
        """Gets all of the names of rooms that we are currently aware of."""
        airFlowHorizontal = next(
            (
                ref
                for ref in self._coordinator.data.stardard_functions
                if "airFlowHorizontal" in ref["id"]
            ),
            None,
        )
        return airFlowHorizontal["allowedValues"]

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""
        airFlowHorizontal = next(
            (
                ref
                for ref in self._coordinator.data.stardard_functions
                if "airFlowHorizontal" in ref["id"]
            ),
            None,
        )
        return airFlowHorizontal["value"]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        airFlowHorizontal = next(
            (
                ref
                for ref in self._coordinator.data.stardard_functions
                if "airFlowHorizontal" in ref["id"]
            ),
            None,
        )
        self._attr_current_option = airFlowHorizontal["value"]
        self.async_write_ha_state()


class BoschComSelectAirflowVertical(CoordinatorEntity, SelectEntity):
    """Representation of Vertical airflow select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinator,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "airflow_vertical"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field
        self._coordinator = coordinator
        self._attr_should_poll = False

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_set_vertical_swing_mode(
            self._coordinator.data.device["deviceId"], option
        )

        await self._coordinator.async_request_refresh()

    @property
    def options(self) -> list[str]:
        """Gets all of the names of rooms that we are currently aware of."""
        airFlowVertical = next(
            (
                ref
                for ref in self._coordinator.data.stardard_functions
                if "airFlowVertical" in ref["id"]
            ),
            None,
        )
        return airFlowVertical["allowedValues"]

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""
        airFlowVertical = next(
            (
                ref
                for ref in self._coordinator.data.stardard_functions
                if "airFlowVertical" in ref["id"]
            ),
            None,
        )
        return airFlowVertical["value"]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        airFlowVertical = next(
            (
                ref
                for ref in self._coordinator.data.stardard_functions
                if "airFlowVertical" in ref["id"]
            ),
            None,
        )
        self._attr_current_option = airFlowVertical["value"]
        self.async_write_ha_state()


class BoschComSelectProgram(CoordinatorEntity, SelectEntity):
    """Representation of program select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinator,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "program"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field
        self._coordinator = coordinator
        self._attr_should_poll = False

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_control_program(
            self._coordinator.data.device["deviceId"], "on"
        )
        await self._coordinator.bhc.async_switch_program(
            self._coordinator.data.device["deviceId"], option
        )

        await self._coordinator.async_request_refresh()

    @property
    def options(self) -> list[str]:
        """Gets all of the names of rooms that we are currently aware of."""
        programs = next(
            (
                ref
                for ref in self._coordinator.data.switch_programs
                if "activeProgram" in ref["id"]
            ),
            None,
        )
        return programs["allowedValues"] + ["off"]

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""
        enabled = next(
            (
                ref
                for ref in self._coordinator.data.switch_programs
                if "switchPrograms/enabled" in ref["id"]
            ),
            None,
        )
        if enabled["value"] == "off":
            return "off"

        program = next(
            (
                ref
                for ref in self._coordinator.data.switch_programs
                if "activeProgram" in ref["id"]
            ),
            None,
        )
        return program["value"]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        enabled = next(
            (
                ref
                for ref in self._coordinator.data.switch_programs
                if "switchPrograms/enabled" in ref["id"]
            ),
            None,
        )
        if enabled["value"] == "off":
            self._attr_current_option = "off"

        program = next(
            (
                ref
                for ref in self._coordinator.data.switch_programs
                if "activeProgram" in ref["id"]
            ),
            None,
        )
        self._attr_current_option = program["value"]
        self.async_write_ha_state()
