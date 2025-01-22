"""Component configuration flow."""

import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import voluptuous as vol

from homeassistant import core
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, OAUTH_DOMAIN, OAUTH_ENDPOINT, OAUTH_LOGIN, OAUTH_PARAMS

_LOGGER = logging.getLogger(__name__)

AUTH_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): cv.string, vol.Required(CONF_PASSWORD): cv.string}
)


async def do_auth(user_input: dict[str, Any], hass: core.HomeAssistant) -> str:
    """Singlekey-id login - get code."""
    session = async_get_clientsession(hass)
    session.cookie_jar.clear_domain(OAUTH_DOMAIN[8:])
    try:
        # GET login CSRF token
        async with session.get(
            OAUTH_DOMAIN + OAUTH_LOGIN,
            allow_redirects=True,
        ) as response:
            login_data = await response.text()

            # Extract __RequestVerificationToken value
            token_match = re.search(
                r'<input[^>]*name="__RequestVerificationToken"[^>]*value="([^"]+)"',
                login_data,
            )
            if token_match:
                request_verification_token = token_match.group(1)
            else:
                _LOGGER.error("Login failed")
                return None

        # POST username
        user_payload = {
            "UserIdentifierInput.EmailInput.StringValue": user_input[CONF_USERNAME],
            "__RequestVerificationToken": request_verification_token,
        }
        async with session.post(
            str(response.url), data=user_payload
        ) as response_username:
            user_data = await response_username.text()

            token_match = re.search(
                r'<input[^>]*name="__RequestVerificationToken"[^>]*value="([^"]+)"',
                user_data,
            )
            if token_match:
                request_verification_token = token_match.group(1)
            else:
                _LOGGER.error("Login failed")
                return None

        # POST password
        pass_payload = {
            "Password": user_input[CONF_PASSWORD],
            "__RequestVerificationToken": request_verification_token,
        }
        async with session.post(
            str(response_username.url),
            data=pass_payload,
            allow_redirects=False,
        ) as response_pass:
            location_header = response_pass.headers.get("Location")

        # First redirect
        async with session.get(
            response_pass.url.scheme + "://" + response_pass.host + location_header,
            allow_redirects=False,
        ) as respose_redirect:
            # Get and parse the Location header from the response
            location_header = respose_redirect.headers.get("Location")
            if location_header:
                location_query_params = parse_qs(urlparse(location_header).query)
                if "code" in location_query_params:
                    return location_query_params["code"][0]
                _LOGGER.error("Login failed")
                return None
            _LOGGER.error("Login failed")
            return None
    except ValueError:
        _LOGGER.error(f"{response.url} exception")


async def validate_auth(code: str, hass: core.HomeAssistant) -> None:
    """Get access and refresh token from singlekey-id."""
    session = async_get_clientsession(hass)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}  # Set content type
    try:
        async with session.post(
            OAUTH_DOMAIN + OAUTH_ENDPOINT,
            data="code=" + code + "&" + OAUTH_PARAMS,
            headers=headers,
        ) as response:
            # Ensure the request was successful
            if response.status == 200:
                try:
                    response_json = await response.json()
                except ValueError:
                    _LOGGER.error(f"Response is not JSON")
                return response_json
            _LOGGER.error(f"{response.url} returned {response.status}")
            return None
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
                code = await do_auth(user_input, self.hass)
                if code is not None:
                    reponse = await validate_auth(code, self.hass)
                else:
                    _LOGGER.error("Login failed")
                    return None
            except ValueError:
                errors["base"] = "auth"
            if not errors:
                # User is done, create the config entry.
                return self.async_create_entry(
                    title="Bosch HomeCom", data=user_input | reponse
                )

        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Invoked when a user initiates a reconfigure flow via the user interface."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                code = await do_auth(user_input, self.hass)
                if code is not None:
                    reponse = await validate_auth(code, self.hass)
                else:
                    _LOGGER.error("Login failed")
                    return None

            except ValueError:
                errors["base"] = "auth"
            if not errors:
                # Input is valid, set data.
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates=user_input | reponse,
                )

        return self.async_show_form(
            step_id="reconfigure", data_schema=AUTH_SCHEMA, errors=errors
        )
