"""Bosch HomeCom Custom Component."""

from datetime import timedelta

from homeassistant import config_entries, core
from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinatorK40, BoschComModuleCoordinatorRac

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
        if coordinator.data.device["deviceType"] == "rac":
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
                    BoschComSelectAirflowVertical(
                        coordinator=coordinator, field="vertical"
                    )
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
        if coordinator.data.device["deviceType"] in ["k30", "k40"]:
            for entry in coordinator.data.dhw_circuits:
                dhw_id = entry["id"].split("/")[-1]
                if entry["operationMode"]:
                    entities.append(
                        BoschComSelectDhwOperationMode(
                            coordinator=coordinator,
                            field=dhw_id,
                            allowedValues=entry["operationMode"]["allowedValues"],
                        )
                    )
                if entry["currentTemperatureLevel"]:
                    entities.append(
                        BoschComSelectDhwCurrentTemp(
                            coordinator=coordinator,
                            field=dhw_id,
                            allowedValues=entry["currentTemperatureLevel"][
                                "allowedValues"
                            ],
                        )
                    )
            for entry in coordinator.data.heating_circuits:
                hc_id = entry["id"].split("/")[-1]
                if entry["operationMode"]:
                    entities.append(
                        BoschComSelectHcOperationMode(
                            coordinator=coordinator,
                            field=hc_id,
                            allowedValues=entry["operationMode"]["allowedValues"],
                        )
                    )
                if entry["currentSuWiMode"]:
                    entities.append(
                        BoschComSelectHcSuwiMode(
                            coordinator=coordinator,
                            field=hc_id,
                            allowedValues=entry["currentSuWiMode"]["allowedValues"],
                        )
                    )
                if entry["heatCoolMode"]:
                    entities.append(
                        BoschComSelectHcHeatcoolMode(
                            coordinator=coordinator,
                            field=hc_id,
                            allowedValues=entry["heatCoolMode"]["allowedValues"],
                        )
                    )
            if coordinator.data.holiday_mode:
                entities.append(
                    BoschComSelectHolidayMode(
                        coordinator=coordinator,
                        field="holiday_mode",
                        allowedValues=coordinator.data.holiday_mode["allowedValues"],
                    )
                )
            if coordinator.data.away_mode:
                entities.append(
                    BoschComSelectAwayMode(
                        coordinator=coordinator,
                        field="away_mode",
                        allowedValues=coordinator.data.away_mode["allowedValues"],
                    )
                )
    async_add_entities(entities)


class BoschComSelectAirflowHorizontal(CoordinatorEntity, SelectEntity):
    """Representation of Horizontal airflow select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorRac,
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
        coordinator: BoschComModuleCoordinatorRac,
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
        coordinator: BoschComModuleCoordinatorRac,
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


class BoschComSelectDhwOperationMode(CoordinatorEntity, SelectEntity):
    """Representation of dhw operation mode select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
        allowedValues: list[str],
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "dhw_operation_mode"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_options = allowedValues

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_put_dhw_operation_mode(
            self._coordinator.data.device["deviceId"], self._attr_name, option
        )

        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == "/dhwCircuits/" + self._attr_name:
                operationMode = safe_get(entry["operationMode"], "value")

        return operationMode

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == "/dhwCircuits/" + self._attr_name:
                operationMode = safe_get(entry["operationMode"], "value")

        self._attr_current_option = operationMode
        self.async_write_ha_state()


class BoschComSelectDhwCurrentTemp(CoordinatorEntity, SelectEntity):
    """Representation of dhw current temp select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
        allowedValues: list[str],
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "dhw_current_temp"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}-temp"
        self._attr_name = field + "_temp"
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_options = allowedValues
        self.field = field

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_put_dhw_current_temp_level(
            self._coordinator.data.device["deviceId"], self.field, option
        )

        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == "/dhwCircuits/" + self.field:
                currentTemperatureLevel = safe_get(
                    entry["currentTemperatureLevel"], "value"
                )

        return currentTemperatureLevel

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == "/dhwCircuits/" + self.field:
                currentTemperatureLevel = safe_get(
                    entry["currentTemperatureLevel"], "value"
                )

        self._attr_current_option = currentTemperatureLevel
        self.async_write_ha_state()


class BoschComSelectHcOperationMode(CoordinatorEntity, SelectEntity):
    """Representation of hc operation mode select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
        allowedValues: list[str],
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "hc_operation_mode"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_options = allowedValues

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_put_hc_operation_mode(
            self._coordinator.data.device["deviceId"], self._attr_name, option
        )

        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self._attr_name:
                operationMode = safe_get(entry["operationMode"], "value")

        return operationMode

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self._attr_name:
                operationMode = safe_get(entry["operationMode"], "value")

        self._attr_current_option = operationMode
        self.async_write_ha_state()


class BoschComSelectHcSuwiMode(CoordinatorEntity, SelectEntity):
    """Representation of hc summer winter mode select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
        allowedValues: list[str],
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "hc_suwi_mode"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}-suwi"
        self._attr_name = field + "_suwi"
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_options = allowedValues
        self.field = field

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_put_hc_suwi_mode(
            self._coordinator.data.device["deviceId"], self.field, option
        )

        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                currentSuWiMode = safe_get(entry["currentSuWiMode"], "value")

        return currentSuWiMode

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                currentSuWiMode = safe_get(entry["currentSuWiMode"], "value")

        self._attr_current_option = currentSuWiMode
        self.async_write_ha_state()


class BoschComSelectHcHeatcoolMode(CoordinatorEntity, SelectEntity):
    """Representation of hc heat cool mode select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
        allowedValues: list[str],
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "hc_heatcool_mode"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}-heatcool"
        self._attr_name = field + "_heatcool"
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_options = allowedValues
        self.field = field

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_put_hc_heatcool_mode(
            self._coordinator.data.device["deviceId"], self.field, option
        )

        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                heatCoolMode = safe_get(entry["heatCoolMode"], "value")

        return heatCoolMode

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                heatCoolMode = safe_get(entry["heatCoolMode"], "value")

        self._attr_current_option = heatCoolMode
        self.async_write_ha_state()


class BoschComSelectHolidayMode(CoordinatorEntity, SelectEntity):
    """Representation of holiday mode select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
        allowedValues: list[str],
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "holiday_mode"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_options = allowedValues

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_put_holiday_mode(
            self._coordinator.data.device["deviceId"], option
        )

        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""

        return self.coordinator.data.holiday_mode["values"]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        self._attr_current_option = self.coordinator.data.holiday_mode["values"]
        self.async_write_ha_state()


class BoschComSelectAwayMode(CoordinatorEntity, SelectEntity):
    """Representation of away mode select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
        allowedValues: list[str],
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "away_mode"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_options = allowedValues

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_put_away_mode(
            self._coordinator.data.device["deviceId"], option
        )

        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""

        return self.coordinator.data.away_mode["value"]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        self._attr_current_option = self.coordinator.data.away_mode["value"]
        self.async_write_ha_state()
