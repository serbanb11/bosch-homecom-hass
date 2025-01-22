"""Bosch HomeCom Custom Component."""

import logging
from typing import Any

from homeassistant import config_entries, core
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BOSCHCOM_DOMAIN,
    BOSCHCOM_ENDPOINT_GATEWAYS,
    BOSCHCOM_ENDPOINT_PLASMACLUSTER,
    DOMAIN,
)
from .coordinator import BoschComModuleCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom devices."""
    coordinators = config_entry.runtime_data
    async_add_entities(
        BoschComSwitchAirPurification(coordinator=coordinator, entry=config_entry)
        for coordinator in coordinators
    )


class BoschComSwitchAirPurification(SwitchEntity):
    """Representation of a BoschCom sensor."""

    def __init__(
        self,
        coordinator: BoschComModuleCoordinator,
        entry: config_entries.ConfigEntry,
    ) -> None:
        super().__init__()
        self._attr_unique_id = coordinator.data.device["deviceId"] + "_plasmacluster"
        self._attr_name = coordinator.data.device["deviceId"] + "_plasmacluster"
        self.name = (
            "Bosch_"
            + coordinator.data.device["deviceType"]
            + "_"
            + coordinator.data.device["deviceId"]
            + "_plasmacluster"
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

    async def async_turn_off(self, **kwargs: Any) -> None:
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
                + BOSCHCOM_ENDPOINT_PLASMACLUSTER,
                headers=headers,
                json={"value": "off"},
            ) as response:
                # Ensure the request was successful
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self._coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_turn_off()
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

        await self._coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
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
                + BOSCHCOM_ENDPOINT_PLASMACLUSTER,
                headers=headers,
                json={"value": "on"},
            ) as response:
                # Ensure the request was successful
                print("Status:", response.status)
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self._coordinator.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.async_turn_on()
                elif response.status != 204:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

        await self._coordinator.async_request_refresh()

    @property
    def is_on(self) -> bool | None:
        """Gets all of the names of rooms that we are currently aware of."""
        airPurificationMode = next(
            (
                ref
                for ref in self._coordinator.data.advanced_functions
                if "airPurificationMode" in ref["id"]
            ),
            None,
        )
        if airPurificationMode["value"] == "on":
            return True
        return False
