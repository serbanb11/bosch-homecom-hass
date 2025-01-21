"""Component configuration flow."""

import logging
from typing import Any, Optional

import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_CODE
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import *

_LOGGER = logging.getLogger(__name__)

AUTH_SCHEMA = vol.Schema({vol.Required(CONF_CODE): cv.string})


async def validate_auth(code: str, hass: core.HomeAssistant) -> None:
    """Validates singlekey-id code."""
    session = async_get_clientsession(hass)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}  # Set content type
    try:
        async with session.post(
            OATUH_DOMAIN + OATUH_ENDPOINT,
            data="code=" + code + "&" + OATUH_PARAMS,
            headers=headers,
        ) as response:
            # Ensure the request was successful
            if response.status == 200:
                try:
                    response_json = await response.json()
                    return response_json
                except ValueError:
                    _LOGGER.error(f"Response is not JSON")
            else:
                _LOGGER.error(f"{response.url} returned {response.status}")
                return
    except ValueError:
        _LOGGER.error(f"{response.url} exception")


class BoschHomecomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Bosch HomeCom config flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Invoked when a user initiates a flow via the user interface."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                reponse = await validate_auth(user_input[CONF_CODE], self.hass)
            except ValueError:
                errors["base"] = "auth"
            if not errors:
                # User is done, create the config entry.
                return self.async_create_entry(title="Bosch HomeCom", data=reponse)

        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Invoked when a user initiates a flow via the user interface."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                reponse = await validate_auth(user_input[CONF_CODE], self.hass)
            except ValueError:
                errors["base"] = "auth"
            if not errors:
                # Input is valid, set data.
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates=reponse,
                )

        return self.async_show_form(
            step_id="reconfigure", data_schema=AUTH_SCHEMA, errors=errors
        )
