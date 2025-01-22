"""Bosch HomeCom Custom Component."""

from datetime import timedelta
import logging

from homeassistant import config_entries, core
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BOSCHCOM_DOMAIN,
    BOSCHCOM_ENDPOINT_AIRFLOW_HORIZONTAL,
    BOSCHCOM_ENDPOINT_AIRFLOW_VERTICAL,
    BOSCHCOM_ENDPOINT_GATEWAYS,
    BOSCHCOM_ENDPOINT_SWITCH_ENABLE,
    BOSCHCOM_ENDPOINT_SWITCH_PROGRAM,
    DOMAIN,
)
from .coordinator import BoschComModuleCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1440)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom devices."""
    coordinators = config_entry.runtime_data
    async_add_entities(
        BoschComSelectAirflowHorizontal(coordinator=coordinator, entry=config_entry)
        for coordinator in coordinators
    )
    async_add_entities(
        BoschComSelectAirflowVertical(coordinator=coordinator, entry=config_entry)
        for coordinator in coordinators
    )
    async_add_entities(
        BoschComSelectProgram(coordinator=coordinator, entry=config_entry)
        for coordinator in coordinators
    )


class BoschComSelectAirflowHorizontal(SelectEntity):
    """Representation of Horizontal airflow select."""

    def __init__(
        self,
        coordinator: BoschComModuleCoordinator,
        entry: config_entries.ConfigEntry,
    ) -> None:
        """Initialize select entity."""
        super().__init__()
        self._attr_unique_id = (
            coordinator.data.device["deviceId"] + "_horizontal_airflow"
        )
        self._attr_name = coordinator.data.device["deviceId"] + "_horizontal_airflow"
        self.name = (
            "Bosch_"
            + coordinator.data.device["deviceType"]
            + "_"
            + coordinator.data.device["deviceId"]
            + "_horizontal_airflow"
        )
        self._coordinator = coordinator

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._coordinator.device["deviceId"])},
        )

    @property
    def should_poll(self) -> bool:
        """Home Assistant will poll an entity when the should_poll property returns True."""
        return True

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self._coordinator.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._coordinator.data.device["deviceId"]
                + BOSCHCOM_ENDPOINT_AIRFLOW_HORIZONTAL,
                headers=headers,
                json={"value": option},
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self._coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_select_option(option)
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

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


class BoschComSelectAirflowVertical(SelectEntity):
    """Representation of vertical airflow select."""

    def __init__(
        self,
        coordinator: BoschComModuleCoordinator,
        entry: config_entries.ConfigEntry,
    ) -> None:
        """Initialize select entity."""
        super().__init__()
        self._attr_unique_id = coordinator.data.device["deviceId"] + "_vertical_airflow"
        self._attr_name = coordinator.data.device["deviceId"] + "_vertical_airflow"
        self.name = (
            "Bosch_"
            + coordinator.data.device["deviceType"]
            + "_"
            + coordinator.data.device["deviceId"]
            + "_vertical_airflow"
        )
        self._coordinator = coordinator

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._coordinator.device["deviceId"])},
        )

    @property
    def should_poll(self) -> bool:
        """Home Assistant will poll an entity when the should_poll property returns True."""
        return True

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self._coordinator.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._coordinator.data.device["deviceId"]
                + BOSCHCOM_ENDPOINT_AIRFLOW_VERTICAL,
                headers=headers,
                json={"value": option},
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self._coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_select_option(option)
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

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


class BoschComSelectProgram(SelectEntity):
    """Representation of program select."""

    def __init__(
        self,
        coordinator: BoschComModuleCoordinator,
        entry: config_entries.ConfigEntry,
    ) -> None:
        """Initialize select entity."""
        super().__init__()
        self._attr_unique_id = coordinator.data.device["deviceId"] + "_program"
        self._attr_name = coordinator.data.device["deviceId"] + "_program"
        self.name = (
            "Bosch_"
            + coordinator.data.device["deviceType"]
            + "_"
            + coordinator.data.device["deviceId"]
            + "_program"
        )
        self._coordinator = coordinator

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._coordinator.device["deviceId"])},
        )

    @property
    def should_poll(self) -> bool:
        """Home Assistant will poll an entity when the should_poll property returns True."""
        return True

    async def async_select_option(self, option: str) -> None:
        """Set the option."""
        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": f"Bearer {self._coordinator.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        if option == "off":
            payload = "off"
        else:
            payload = "on"
        # send enable request
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._coordinator.data.device["deviceId"]
                + BOSCHCOM_ENDPOINT_SWITCH_ENABLE,
                headers=headers,
                json={"value": payload},
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self._coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_select_option(option)
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

        if option == "off":
            return

        # send switch program request
        try:
            async with session.put(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self._coordinator.data.device["deviceId"]
                + BOSCHCOM_ENDPOINT_SWITCH_PROGRAM,
                headers=headers,
                json={"value": option},
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self._coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_select_option(option)
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

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
