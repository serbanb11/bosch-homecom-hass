"""Bosch HomeCom Custom Component."""

from datetime import timedelta

from homeassistant import config_entries, core
from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import (
    BoschComModuleCoordinatorCommodule,
    BoschComModuleCoordinatorK40,
    BoschComModuleCoordinatorRac,
    BoschComModuleCoordinatorRrc2,
)

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
        if coordinator.data.device["deviceType"] in ["k30", "k40", "icom"]:
            for entry in coordinator.data.dhw_circuits:
                dhw_id = entry["id"].split("/")[-1]
                if (
                    entry.get("operationMode")
                    and "allowedValues" in entry["operationMode"]
                ):
                    entities.append(
                        BoschComSelectDhwOperationMode(
                            coordinator=coordinator,
                            field=dhw_id,
                            allowedValues=entry["operationMode"]["allowedValues"],
                        )
                    )
                if (
                    entry.get("currentTemperatureLevel")
                    and "allowedValues" in entry["currentTemperatureLevel"]
                ):
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
                if (
                    entry.get("operationMode")
                    and "allowedValues" in entry["operationMode"]
                ):
                    entities.append(
                        BoschComSelectHcOperationMode(
                            coordinator=coordinator,
                            field=hc_id,
                            allowedValues=entry["operationMode"]["allowedValues"],
                        )
                    )
                if (
                    entry.get("currentSuWiMode")
                    and "allowedValues" in entry["currentSuWiMode"]
                ):
                    entities.append(
                        BoschComSelectHcSuwiMode(
                            coordinator=coordinator,
                            field=hc_id,
                            allowedValues=entry["currentSuWiMode"]["allowedValues"],
                        )
                    )
                if (
                    entry.get("heatCoolMode")
                    and "allowedValues" in entry["heatCoolMode"]
                ):
                    entities.append(
                        BoschComSelectHcHeatcoolMode(
                            coordinator=coordinator,
                            field=hc_id,
                            allowedValues=entry["heatCoolMode"]["allowedValues"],
                        )
                    )
                if (
                    entry.get("nightSwitchMode")
                    and "allowedValues" in entry["nightSwitchMode"]
                ):
                    entities.append(
                        BoschComSelectHcNightSwitchMode(
                            coordinator=coordinator,
                            field=hc_id,
                            allowedValues=entry["nightSwitchMode"]["allowedValues"],
                        )
                    )
                if entry.get("control") and "allowedValues" in entry["control"]:
                    entities.append(
                        BoschComSelectHcControl(
                            coordinator=coordinator,
                            field=hc_id,
                            allowedValues=entry["control"]["allowedValues"],
                        )
                    )
            for entry in coordinator.data.ventilation:
                zone_id = entry["id"].split("/")[-1]
                if (
                    entry.get("summerBypassEnable")
                    and "allowedValues" in entry["summerBypassEnable"]
                ):
                    entities.append(
                        BoschComSelectVentilationSummerEnable(
                            coordinator=coordinator,
                            field=zone_id,
                            allowedValues=entry["summerBypassEnable"]["allowedValues"],
                        )
                    )
            holiday_mode = getattr(coordinator.data, "holiday_mode", None)
            if isinstance(holiday_mode, dict) and "allowedValues" in holiday_mode:
                entities.append(
                    BoschComSelectHolidayMode(
                        coordinator=coordinator,
                        field="holiday_mode",
                        allowedValues=holiday_mode["allowedValues"],
                    )
                )
            away_mode = getattr(coordinator.data, "away_mode", None)
            if isinstance(away_mode, dict) and "allowedValues" in away_mode:
                entities.append(
                    BoschComSelectAwayMode(
                        coordinator=coordinator,
                        field="away_mode",
                        allowedValues=away_mode["allowedValues"],
                    )
                )
        if coordinator.data.device["deviceType"] == "rrc2":
            entities.extend(_build_rrc2_selects(coordinator))
        if coordinator.data.device["deviceType"] == "commodule":
            for cp in coordinator.data.charge_points or []:
                cp_id = cp["id"].split("/")[-1]
                strategy = cp.get("chargingStrategy") or {}
                allowed_values = strategy.get("allowedValues")
                if allowed_values:
                    entities.append(
                        BoschComCommoduleChargingStrategySelect(
                            coordinator=coordinator,
                            cp_id=cp_id,
                            allowed_values=allowed_values,
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
        if airFlowHorizontal is None:
            return []
        return airFlowHorizontal.get("allowedValues", [])

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
        if airFlowHorizontal is None:
            return None
        return airFlowHorizontal.get("value")

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
        if airFlowHorizontal is not None:
            self._attr_current_option = airFlowHorizontal.get("value")
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
        if airFlowVertical is None:
            return []
        return airFlowVertical.get("allowedValues", [])

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
        if airFlowVertical is None:
            return None
        return airFlowVertical.get("value")

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
        if airFlowVertical is not None:
            self._attr_current_option = airFlowVertical.get("value")
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
        self._attr_translation_placeholders = {"circuit": field}
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
        self._attr_translation_placeholders = {"circuit": field}
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
        self._attr_translation_placeholders = {"circuit": field}
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
        self._attr_translation_placeholders = {"circuit": field}
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
        self._attr_translation_placeholders = {"circuit": field}
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

        values = self.coordinator.data.holiday_mode.get("values") or []
        return values[0] if values else None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        values = self.coordinator.data.holiday_mode.get("values") or []
        self._attr_current_option = values[0] if values else None
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


class BoschComSelectHcNightSwitchMode(CoordinatorEntity, SelectEntity):
    """Representation of hc night switch mode select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
        allowedValues: list[str],
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "hc_night_switch_mode"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}-nightswitch"
        self._attr_name = field + "_nightswitch"
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_options = allowedValues
        self.field = field

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_set_hc_night_switch_mode(
            self._coordinator.data.device["deviceId"], self.field, option
        )

        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""
        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                return (entry.get("nightSwitchMode") or {}).get("value")
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                self._attr_current_option = (entry.get("nightSwitchMode") or {}).get(
                    "value"
                )
        self.async_write_ha_state()


class BoschComSelectHcControl(CoordinatorEntity, SelectEntity):
    """Representation of hc control select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
        allowedValues: list[str],
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "hc_control"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}-control"
        self._attr_name = field + "_control"
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_options = allowedValues
        self.field = field

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_set_hc_control(
            self._coordinator.data.device["deviceId"], self.field, option
        )

        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""
        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                return (entry.get("control") or {}).get("value")
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                self._attr_current_option = (entry.get("control") or {}).get("value")
        self.async_write_ha_state()


class BoschComSelectVentilationSummerEnable(CoordinatorEntity, SelectEntity):
    """Representation of ventilation summer-bypass manual enable select."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        field: str,
        allowedValues: list[str],
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "ventilation_summer_enable"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{field}-summerbypass-enable"
        self._attr_name = field + "_summerbypass_enable"
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_options = allowedValues
        self.field = field

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        await self._coordinator.bhc.async_set_ventilation_summer_enable(
            self._coordinator.data.device["deviceId"], self.field, option
        )

        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str | None:
        """Get the current status of the select entity from device_status."""
        for entry in self.coordinator.data.ventilation:
            if entry.get("id") == "/ventilation/" + self.field:
                return (entry.get("summerBypassEnable") or {}).get("value")
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        for entry in self.coordinator.data.ventilation:
            if entry.get("id") == "/ventilation/" + self.field:
                self._attr_current_option = (entry.get("summerBypassEnable") or {}).get(
                    "value"
                )
        self.async_write_ha_state()


# ---- RRC2 selects -----------------------------------------------------------
#
# RRC2 endpoints never return `allowedValues`, so option lists are hard-coded
# from issue #78 response dumps. Values that the device rejects on PUT will
# surface as a failed write rather than be filtered out client-side.


class BoschComRrc2CircuitSelect(CoordinatorEntity, SelectEntity):
    """Writable enum field on an RRC2 HC or DHW circuit."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorRrc2,
        *,
        scope: str,
        circuit_id: str,
        field: str,
        setter: str,
        options: list[str],
        name_suffix: str,
        unique_suffix: str,
    ) -> None:
        """Initialize one circuit-scoped select."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_name = name_suffix
        self._attr_options = options
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
    def current_option(self) -> str | None:
        """Return the current value."""
        ref = self._find_circuit()
        if not ref:
            return None
        node = ref.get(self._field)
        if not isinstance(node, dict):
            return None
        value = node.get("value")
        return None if value is None else str(value)

    async def async_select_option(self, option: str) -> None:
        """Push a new value to the device."""
        setter = getattr(self.coordinator.bhc, self._setter)
        await setter(self.coordinator.data.device["deviceId"], self._circuit_id, option)
        await self.coordinator.async_request_refresh()


def _build_rrc2_selects(
    coordinator: BoschComModuleCoordinatorRrc2,
) -> list[SelectEntity]:
    """Build the standard RRC2 select set for one device."""
    entities: list[SelectEntity] = []

    for ref in coordinator.data.heating_circuits or []:
        hc_id = ref["id"].split("/")[-1]
        if isinstance(ref.get("control"), dict):
            entities.append(
                BoschComRrc2CircuitSelect(
                    coordinator,
                    scope="hc",
                    circuit_id=hc_id,
                    field="control",
                    setter="async_set_hc_control",
                    options=["weather", "room"],
                    name_suffix=f"{hc_id}_control",
                    unique_suffix=f"{hc_id}-control",
                )
            )

    for ref in coordinator.data.dhw_circuits or []:
        dhw_id = ref["id"].split("/")[-1]
        if isinstance(ref.get("operationMode"), dict):
            entities.append(
                BoschComRrc2CircuitSelect(
                    coordinator,
                    scope="dhw",
                    circuit_id=dhw_id,
                    field="operationMode",
                    setter="async_put_dhw_operation_mode",
                    options=["Off", "Auto", "High"],
                    name_suffix=f"{dhw_id}_operation_mode",
                    unique_suffix=f"{dhw_id}-operation-mode",
                )
            )
        if isinstance(ref.get("thermalDisinfectWeekDay"), dict):
            entities.append(
                BoschComRrc2CircuitSelect(
                    coordinator,
                    scope="dhw",
                    circuit_id=dhw_id,
                    field="thermalDisinfectWeekDay",
                    setter="async_set_dhw_thermal_disinfect_weekday",
                    options=["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
                    name_suffix=f"{dhw_id}_thermal_disinfect_weekday",
                    unique_suffix=f"{dhw_id}-thermal-disinfect-weekday",
                )
            )

    return entities


class BoschComCommoduleChargingStrategySelect(CoordinatorEntity, SelectEntity):
    """Representation of a commodule charge point charging strategy select."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        cp_id: str,
        allowed_values: list[str],
    ) -> None:
        """Initialize select entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "wb_charging_strategy"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{cp_id}-charging-strategy"
        self._coordinator = coordinator
        self._cp_id = cp_id
        self._attr_options = allowed_values

    def _get_cp_data(self) -> dict | None:
        """Get charge point data."""
        for cp in self._coordinator.data.charge_points or []:
            if cp["id"].split("/")[-1] == self._cp_id:
                return cp
        return None

    def _read_value(self) -> str | None:
        """Return the current charging strategy value, or None."""
        cp = self._get_cp_data()
        if cp is None:
            return None
        strategy = cp.get("chargingStrategy")
        if not isinstance(strategy, dict):
            return None
        return strategy.get("value")

    async def async_select_option(self, option: str) -> None:
        """Set the charging strategy."""
        await self._coordinator.bhc.async_put_cp_conf_charging_strategy(
            self._coordinator.data.device["deviceId"], self._cp_id, option
        )
        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str | None:
        """Return the current charging strategy."""
        return self._read_value()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_current_option = self._read_value()
        self.async_write_ha_state()
