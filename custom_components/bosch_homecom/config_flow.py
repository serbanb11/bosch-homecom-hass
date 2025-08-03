"""Bosch HomeCom integration configuration flow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import logging
from typing import Any

from aiohttp import ClientConnectorError
import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_CODE, CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import CONF_DEVICES, CONF_REFRESH, DOMAIN
from homecom_alt import ApiError, AuthFailedError, ConnectionOptions, HomeComAlt


@dataclass
class BhcConfig:
    """HomeCom device configuration class."""

    username: str
    password: str
    token: str
    refresh_token: str
    code: str


_LOGGER = logging.getLogger(__name__)

AUTH_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): cv.string, vol.Required(CONF_PASSWORD): cv.string}
)

BROWSER_AUTH_SCHEMA = vol.Schema({vol.Required(CONF_CODE): cv.string})


async def async_check_credentials(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Login using provided creds."""
    websession = async_get_clientsession(hass)

    options = ConnectionOptions(
        username=data.get(CONF_USERNAME), password=data.get(CONF_PASSWORD)
    )
    await HomeComAlt.create(websession, options)


class BoschHomecomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Bosch HomeCom config flow."""

    VERSION = 1
    user: str
    data: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                options = ConnectionOptions(
                    username=user_input.get(CONF_USERNAME),
                    password=user_input.get(CONF_PASSWORD),
                )

                websession = async_get_clientsession(self.hass)
                bhc = await HomeComAlt.create(websession, options)

                # need to use browser login
                if bhc is not None:
                    return await self.async_step_browser()

                # await async_check_credentials(self.hass, user_input)
            except (ApiError, AuthFailedError, ClientConnectorError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            try:
                devices = await bhc.async_get_devices()
            except (ApiError, AuthFailedError, ClientConnectorError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            self.data = user_input
            self.data[CONF_DEVICES] = await devices
            _LOGGER.info("Devices: %s", self.data[CONF_DEVICES])
            return await self.async_step_devices()

        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )

    async def async_step_browser(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                options = ConnectionOptions(
                    code=user_input.get(CONF_CODE),
                )

                websession = async_get_clientsession(self.hass)
                bhc = await HomeComAlt.create(websession, options)

                # await async_check_credentials(self.hass, user_input)
            except (ApiError, AuthFailedError, ClientConnectorError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            try:
                devices = await bhc.async_get_devices()
            except (ApiError, AuthFailedError, ClientConnectorError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            self.data = user_input
            self.data[CONF_DEVICES] = await devices
            self.data[CONF_REFRESH] = bhc._options.refresh_token
            self.data[CONF_TOKEN] = bhc._options.token

            _LOGGER.info("Devices: %s", self.data[CONF_DEVICES])
            return await self.async_step_devices()

        return self.async_show_form(
            step_id="browser", data_schema=BROWSER_AUTH_SCHEMA, errors=errors
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}

        data_schema = {
            vol.Required(
                device["deviceId"] + "_" + device["deviceType"], default=True
            ): cv.boolean
            for device in self.data[CONF_DEVICES]
        }

        if user_input is not None:
            self.data[CONF_DEVICES] = user_input
            await self.async_set_unique_id(user_input.get(CONF_USERNAME))
            self._abort_if_unique_id_configured(
                {CONF_USERNAME: user_input.get(CONF_USERNAME)}
            )

            if self.source == SOURCE_REAUTH:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates=self.data,
                )
            if self.source in SOURCE_RECONFIGURE:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates=self.data,
                )
            # User is done, create the config entry.
            return self.async_create_entry(title="Bosch HomeCom", data=self.data)

        return self.async_show_form(
            step_id="devices", data_schema=vol.Schema(data_schema), errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle configuration by re-auth."""
        self.user = entry_data[CONF_USERNAME]
        self.context["title_placeholders"] = {"user": self.user}
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await async_check_credentials(self.hass, user_input)
            except (ApiError, AuthFailedError, ClientConnectorError, TimeoutError):
                return await self.async_step_browser()

            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data=user_input
            )

        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={"user": self.user},
            data_schema=AUTH_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a reconfiguration flow initialized by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                options = ConnectionOptions(
                    username=user_input.get(CONF_USERNAME),
                    password=user_input.get(CONF_PASSWORD),
                )

                websession = async_get_clientsession(self.hass)
                bhc = await HomeComAlt.create(websession, options)

                # need to use browser login
                if bhc is not None:
                    return await self.async_step_browser()

                # await async_check_credentials(self.hass, user_input)
            except (ApiError, AuthFailedError, ClientConnectorError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            try:
                devices = await bhc.async_get_devices()
            except (ApiError, AuthFailedError, ClientConnectorError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            self.data = user_input
            self.data[CONF_DEVICES] = await devices
            return await self.async_step_reconfigure_devices()

        return self.async_show_form(
            step_id="reconfigure", data_schema=AUTH_SCHEMA, errors=errors
        )

    async def async_step_reconfigure_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        data_schema = {
            vol.Required(
                device["deviceId"] + "_" + device["deviceType"], default=True
            ): cv.boolean
            for device in self.data[CONF_DEVICES]
        }

        if user_input is not None:
            return self.async_update_reload_and_abort(
                reconfigure_entry,
                data_updates={
                    CONF_USERNAME: self.data[CONF_USERNAME],
                    CONF_PASSWORD: self.data[CONF_PASSWORD],
                    CONF_DEVICES: user_input,
                },
            )

        return self.async_show_form(
            step_id="reconfigure_devices",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )
