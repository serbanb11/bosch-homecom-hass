"""Define an object to manage fetching BoschCom data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from aiohttp import ClientResponseError, ClientSession

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .config_flow import do_auth, validate_auth
from .const import (
    BOSCHCOM_DOMAIN,
    BOSCHCOM_ENDPOINT_ADVANCED,
    BOSCHCOM_ENDPOINT_FIRMWARE,
    BOSCHCOM_ENDPOINT_GATEWAYS,
    BOSCHCOM_ENDPOINT_NOTIFICATIONS,
    BOSCHCOM_ENDPOINT_STANDARD,
    BOSCHCOM_ENDPOINT_SWITCH,
    OAUTH_DOMAIN,
    OAUTH_ENDPOINT,
    OAUTH_PARAMS_REFRESH,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class BoschComModuleData:
    """Provide type safe way of accessing module data from the coordinator."""

    device: list
    firmware: list
    notifications: list
    stardard_functions: list
    advanced_functions: list
    switch_programs: list


class BoschComModuleCoordinator(DataUpdateCoordinator[BoschComModuleData]):
    """A coordinator to manage the fetching of BoschCom data."""

    def __init__(self, hass: HomeAssistant, device: list, config: list) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name="BoschCom",
            update_interval=timedelta(seconds=30),
        )
        self.device = device
        self.config = config
        self.token = config["access_token"]
        self.refresh_token = config["refresh_token"]
        self.count = 0

    async def get_token(self) -> None:
        """Get firmware."""
        session = async_get_clientsession(self.hass)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            async with session.post(
                OAUTH_DOMAIN + OAUTH_ENDPOINT,
                data="refresh_token=" + self.refresh_token + "&" + OAUTH_PARAMS_REFRESH,
                headers=headers,
            ) as response:
                # Ensure the request was successful
                if response.status == 200:
                    try:
                        response_json = await response.json()
                        # Update the config entry.
                        self.token = response_json["access_token"]
                        self.refresh_token = response_json["refresh_token"]
                    except ValueError:
                        _LOGGER.error(f"{response.url} returned not json")
                else:
                    try:
                        code = await do_auth(self.config, self.hass)
                        if code is not None:
                            reponse = await validate_auth(code, self.hass)
                            self.token = reponse["access_token"]
                            self.refresh_token = reponse["refresh_token"]
                        else:
                            _LOGGER.error("Login error")
                            return
                    except ValueError:
                        _LOGGER.error(f"{response.url} returned {response.status}")
                    return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

    async def get_firmware(self, session: ClientSession) -> None:
        """Get firmware."""
        headers = {
            "Authorization": f"Bearer {self.token}"  # Set Bearer token
        }
        try:
            async with session.get(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self.device["deviceId"]
                + BOSCHCOM_ENDPOINT_FIRMWARE,
                headers=headers,
            ) as response:
                # Ensure the request was successful
                if response.status == 200:
                    try:
                        response_json = await response.json()
                    except ValueError:
                        _LOGGER.error("Response is not JSON")
                    return response_json
                # Refresh token
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.get_firmware(session)
                else:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return None
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

    async def get_notifications(self, session: ClientSession) -> None:
        """Get notifications."""
        headers = {
            "Authorization": f"Bearer {self.token}"  # Set Bearer token
        }
        try:
            async with session.get(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self.device["deviceId"]
                + BOSCHCOM_ENDPOINT_NOTIFICATIONS,
                headers=headers,
            ) as response:
                # Ensure the request was successful
                if response.status == 200:
                    try:
                        response_json = await response.json()
                    except ValueError:
                        _LOGGER.error("Response is not JSON")
                    return response_json
                _LOGGER.error(f"{response.url} returned {response.status}")
                return None
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

    async def get_stardard(self, session: ClientSession) -> None:
        """Get stardard functions."""
        headers = {
            "Authorization": f"Bearer {self.token}"  # Set Bearer token
        }
        try:
            async with session.get(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self.device["deviceId"]
                + BOSCHCOM_ENDPOINT_STANDARD,
                headers=headers,
            ) as response:
                # Ensure the request was successful
                if response.status == 200:
                    try:
                        response_json = await response.json()
                    except ValueError:
                        _LOGGER.error("Response is not JSON")
                    return response_json
                # Refresh token
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.get_firmware(session)
                else:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return None
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

    async def get_advanced(self, session: ClientSession) -> None:
        """Get advanced funtcions."""
        headers = {
            "Authorization": f"Bearer {self.token}"  # Set Bearer token
        }
        try:
            async with session.get(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self.device["deviceId"]
                + BOSCHCOM_ENDPOINT_ADVANCED,
                headers=headers,
            ) as response:
                # Ensure the request was successful
                if response.status == 200:
                    try:
                        response_json = await response.json()
                    except ValueError:
                        _LOGGER.error("Response is not JSON")
                    return response_json
                _LOGGER.error(f"{response.url} returned {response.status}")
                return
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

    async def get_switch(self, session: ClientSession) -> None:
        """Get switch programs."""
        headers = {
            "Authorization": f"Bearer {self.token}"  # Set Bearer token
        }
        try:
            async with session.get(
                BOSCHCOM_DOMAIN
                + BOSCHCOM_ENDPOINT_GATEWAYS
                + self.device["deviceId"]
                + BOSCHCOM_ENDPOINT_SWITCH,
                headers=headers,
            ) as response:
                # Ensure the request was successful
                if response.status == 200:
                    try:
                        response_json = await response.json()
                    except ValueError:
                        _LOGGER.error("Response is not JSON")
                    return response_json
                # Refresh token
                if response.status == 401:
                    errors: dict[str, str] = {}
                    try:
                        await self.get_token()
                    except ValueError:
                        errors["base"] = "auth"
                    if not errors:
                        self.get_firmware(session)
                else:
                    _LOGGER.error(f"{response.url} returned {response.status}")
                    return None
        except ValueError:
            _LOGGER.error(f"{response.url} exception")

    async def _async_update_data(self) -> BoschComModuleData:
        """Fetch data from the upstream API and pre-process into the right format."""
        session = async_get_clientsession(self.hass)
        try:
            if self.count == 0:
                firmware = await self.get_firmware(session)
                notifications = await self.get_notifications(session)
            else:
                firmware = {}
                notifications = {}
            self.count = (self.count + 1) % 72
            stardard_functions = await self.get_stardard(session)
            advanced_functions = await self.get_advanced(session)
            switch_programs = await self.get_switch(session)
        except ClientResponseError as error:
            raise UpdateFailed(error) from error

        return BoschComModuleData(
            device=self.device,
            firmware=firmware.get("value", []),
            notifications=notifications.get("values", []),
            stardard_functions=stardard_functions["references"],
            advanced_functions=advanced_functions["references"],
            switch_programs=switch_programs["references"],
        )
