"""Bosch HomeCom integration configuration flow."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
import logging
from typing import Any

from aiohttp import ClientConnectorError
from homeassistant import config_entries
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_CODE, CONF_TOKEN, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homecom_alt import (
    ApiError,
    AuthFailedError,
    ConnectionOptions,
    HomeComAlt,
    HomeComK40Local,
    NotRespondingError,
    ProximityRequiredError,
    TokenStoreFullError,
    async_get_bacon_devices,
)
from homecom_alt.const import BACON_DEFAULT_REGION, BACON_KNOWN_REGIONS
import voluptuous as vol

from .const import (
    CONF_BACON_REGION,
    CONF_BRAND_BUDERUS,
    CONF_DEVICES,
    CONF_LOCAL,
    CONF_LOCAL_GATEWAY,
    CONF_LOCAL_HOST,
    CONF_LOCAL_LOGIN,
    CONF_LOCAL_PASSWORD,
    CONF_LOCAL_REMOVE,
    CONF_LOCAL_TOKEN,
    CONF_LOCAL_TOKEN_ID,
    CONF_REFRESH,
    CONF_UPDATE_SECONDS,
    CONF_WB_LABEL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_WB_LABEL,
    DOMAIN,
    LOCAL_CLIENT_NAME,
    MAX_UPDATE_SECONDS,
    MIN_UPDATE_SECONDS,
    SINGLEKEY_LOGIN_URL,
    SINGLEKEY_LOGIN_URL_BUDERUS,
)


@dataclass
class BhcConfig:
    """HomeCom device configuration class."""

    username: str
    token: str
    refresh_token: str
    code: str


_LOGGER = logging.getLogger(__name__)

BRAND_OPTIONS = ["bosch", "buderus"]

AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_BRAND_BUDERUS, default=False): cv.boolean,
        vol.Required(CONF_BACON_REGION, default=BACON_DEFAULT_REGION): vol.In(
            list(BACON_KNOWN_REGIONS)
        ),
    }
)

BROWSER_AUTH_SCHEMA = vol.Schema({vol.Required(CONF_CODE): cv.string})


class BoschHomecomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Bosch HomeCom config flow."""

    VERSION = 1
    user: str
    data: dict[str, Any] | None = None

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return BoschHomeComOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.data = user_input
            return await self.async_step_browser()

        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )

    def _get_login_url(self) -> str:
        """Return the correct login URL based on brand selection."""
        if self.data and self.data.get(CONF_BRAND_BUDERUS, False):
            return SINGLEKEY_LOGIN_URL_BUDERUS
        return SINGLEKEY_LOGIN_URL

    async def async_step_browser(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}
        login_url = self._get_login_url()
        brand = (
            "buderus"
            if self.data and self.data.get(CONF_BRAND_BUDERUS, False)
            else "bosch"
        )

        if user_input is not None:
            try:
                options = ConnectionOptions(
                    code=user_input.get(CONF_CODE),
                    brand=brand,
                )

                websession = async_get_clientsession(self.hass)
                bhc = await HomeComAlt.create(websession, options, True)

                # await async_check_credentials(self.hass, user_input)
            except (ApiError, AuthFailedError, ClientConnectorError, TimeoutError):
                errors["base"] = "cannot_connect"
                return self.async_show_form(
                    step_id="browser",
                    data_schema=BROWSER_AUTH_SCHEMA,
                    description_placeholders={"url": login_url},
                    errors=errors,
                )
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="browser",
                    data_schema=BROWSER_AUTH_SCHEMA,
                    description_placeholders={"url": login_url},
                    errors=errors,
                )

            try:
                devices = await bhc.async_get_devices()
            except (ApiError, AuthFailedError, ClientConnectorError, TimeoutError):
                errors["base"] = "cannot_connect"
                return self.async_show_form(
                    step_id="browser",
                    data_schema=BROWSER_AUTH_SCHEMA,
                    description_placeholders={"url": login_url},
                    errors=errors,
                )
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="browser",
                    data_schema=BROWSER_AUTH_SCHEMA,
                    description_placeholders={"url": login_url},
                    errors=errors,
                )

            if asyncio.iscoroutine(devices):
                devices = await devices

            # Also discover Matter/Bacon-commissioned devices, which are not
            # part of the pointt gateway listing. Degrade gracefully on failure.
            bacon_region = (self.data or {}).get(
                CONF_BACON_REGION, BACON_DEFAULT_REGION
            )
            try:
                bacon_devices = await async_get_bacon_devices(
                    websession, bhc.token, bacon_region
                )
                known = {(d["deviceId"], d["deviceType"]) for d in devices}
                for bacon_device in bacon_devices:
                    if (
                        bacon_device["deviceId"],
                        bacon_device["deviceType"],
                    ) not in known:
                        devices.append(bacon_device)
            except Exception:  # noqa: BLE001 - never block pointt setup
                _LOGGER.warning("Could not fetch Bacon devices", exc_info=True)

            if self.data is None:
                self.data = {}
            self.data.update(user_input)
            self.data[CONF_DEVICES] = devices
            self.data[CONF_REFRESH] = bhc.refresh_token
            self.data[CONF_TOKEN] = bhc.token

            _LOGGER.info("Devices: %s", self.data[CONF_DEVICES])
            return await self.async_step_devices()

        return self.async_show_form(
            step_id="browser",
            data_schema=BROWSER_AUTH_SCHEMA,
            description_placeholders={"url": login_url},
            errors=errors,
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
            self.data.update(user_input)
            self.data[CONF_DEVICES] = user_input

            if self.source == SOURCE_REAUTH:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates=self.data,
                )
            if self.source == SOURCE_RECONFIGURE:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates=self.data,
                )
            username = self.data.get(CONF_USERNAME)
            await self.async_set_unique_id(username)
            self._abort_if_unique_id_configured({CONF_USERNAME: username})
            # User is done, create the config entry.
            return self.async_create_entry(title="Bosch HomeCom", data=self.data)

        return self.async_show_form(
            step_id="devices", data_schema=vol.Schema(data_schema), errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle configuration by re-auth."""
        if entry_data is not None:
            self.user = entry_data.get(CONF_USERNAME)
        else:
            self.user = None
        self.context["title_placeholders"] = {"user": self.user}
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return await self.async_step_browser()

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
            self.data = user_input
            return await self.async_step_browser()

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
                    CONF_DEVICES: user_input,
                },
            )

        return self.async_show_form(
            step_id="reconfigure_devices",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )


class BoschHomeComOptionsFlowHandler(config_entries.OptionsFlowWithReload):
    """Handle Bosch HomeCom options.

    Uses ``OptionsFlowWithReload`` so changed options trigger an automatic
    reload (which re-applies the poll interval and brand/wb settings). This
    replaces the deprecated ``entry.add_update_listener`` pattern (removed in
    Home Assistant 2026.12).
    """

    def __init__(self, entry: config_entries.ConfigEntry):
        super().__init__()
        self._entry = entry
        self._local_gateway: str | None = None

    def _k40_gateways(self) -> dict[str, str]:
        """Return {device_id: label} for the configured K40-family gateways.

        Only k40/k30 gateways are offered: the Local API is a K 40 RF feature and
        the other device types have no equivalent.
        """
        selected = self._entry.data.get(CONF_DEVICES) or {}
        gateways: dict[str, str] = {}
        for key, enabled in selected.items():
            if not enabled or not isinstance(key, str) or "_" not in key:
                continue
            device_id, _, device_type = key.rpartition("_")
            if device_type in ("k40", "k30"):
                gateways[device_id] = f"{device_id} ({device_type})"
        return gateways

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Offer the general settings or the optional local-API setup."""
        return self.async_show_menu(step_id="init", menu_options=["general", "local"])

    async def async_step_local(self, user_input=None) -> FlowResult:
        """Choose which gateway to configure local access for.

        Skipped automatically when there is exactly one candidate, which is the
        common case.
        """
        gateways = self._k40_gateways()
        if not gateways:
            return self.async_abort(reason="no_k40_gateway")

        if len(gateways) == 1:
            self._local_gateway = next(iter(gateways))
            return await self.async_step_local_credentials()

        if user_input is not None:
            self._local_gateway = user_input[CONF_LOCAL_GATEWAY]
            return await self.async_step_local_credentials()

        return self.async_show_form(
            step_id="local",
            data_schema=vol.Schema(
                {vol.Required(CONF_LOCAL_GATEWAY): vol.In(gateways)}
            ),
        )

    async def async_step_local_credentials(self, user_input=None) -> FlowResult:
        """Collect the gateway address and label credentials, then get a token.

        The gateway only issues a token while it can prove physical proximity, so
        the user has to press its WLAN and Wireless buttons within five minutes
        before submitting. That instruction lives in the step description.
        """
        errors: dict[str, str] = {}
        existing = (self._entry.data.get(CONF_LOCAL) or {}).get(self._local_gateway, {})

        if user_input is not None:
            if user_input.get(CONF_LOCAL_REMOVE):
                await self._async_revoke_local_token(existing)
                return self._save_local(None)

            host = user_input[CONF_LOCAL_HOST].strip()
            client = HomeComK40Local(
                async_get_clientsession(self.hass),
                host,
                device_id=self._local_gateway,
            )
            try:
                await client.async_create_token(
                    user_input[CONF_LOCAL_LOGIN],
                    user_input[CONF_LOCAL_PASSWORD],
                    LOCAL_CLIENT_NAME,
                )
            except ProximityRequiredError:
                # Not a credential problem: the button press is missing or the
                # five-minute window expired.
                errors["base"] = "local_proximity_required"
            except TokenStoreFullError:
                errors["base"] = "local_token_store_full"
            except AuthFailedError:
                errors["base"] = "local_invalid_auth"
            except (NotRespondingError, ClientConnectorError, TimeoutError):
                errors["base"] = "local_cannot_connect"
            except ApiError:
                # Wrong Login/Pass comes back as 400 invalid_grant.
                errors["base"] = "local_invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error creating a local access token")
                errors["base"] = "unknown"
            else:
                token_id = await self._async_new_token_id(client, existing)
                # Re-provisioning replaces the token, so drop the old one or the
                # gateway's store fills up and starts answering 507.
                await self._async_revoke_local_token(existing, client)
                config = {CONF_LOCAL_HOST: host, CONF_LOCAL_TOKEN: client.token}
                if token_id is not None:
                    config[CONF_LOCAL_TOKEN_ID] = token_id
                return self._save_local(config)

            return self.async_show_form(
                step_id="local_credentials",
                data_schema=self._local_schema(user_input.get(CONF_LOCAL_HOST, "")),
                description_placeholders={"gateway": self._local_gateway or ""},
                errors=errors,
            )

        return self.async_show_form(
            step_id="local_credentials",
            data_schema=self._local_schema(existing.get(CONF_LOCAL_HOST, "")),
            description_placeholders={"gateway": self._local_gateway or ""},
            errors=errors,
        )

    async def _async_new_token_id(
        self, client: HomeComK40Local, existing: dict
    ) -> str | None:
        """Find the gateway's id for the token ``client`` was just issued.

        The token response carries no id and the listing no token, so the new
        entry is the newest one under our client name that is not the token this
        gateway was configured with before. Best effort: without an id the token
        still works, it just cannot be revoked later.
        """
        try:
            tokens = await client.async_list_tokens()
        except (ApiError, AuthFailedError, NotRespondingError, TimeoutError):
            _LOGGER.debug("Could not list local tokens", exc_info=True)
            return None
        old_id = existing.get(CONF_LOCAL_TOKEN_ID)
        ours = [
            token
            for token in tokens
            if isinstance(token, dict)
            and token.get("client_name") == LOCAL_CLIENT_NAME
            and token.get("token_id") is not None
            and str(token["token_id"]) != str(old_id)
        ]
        if not ours:
            return None
        # created_at is an epoch int in the docs and an ISO string on firmware
        # 15.00.01; both order correctly as strings within one listing.
        newest = max(ours, key=lambda token: str(token.get("created_at", "")))
        return str(newest["token_id"])

    async def _async_revoke_local_token(
        self, existing: dict, client: HomeComK40Local | None = None
    ) -> None:
        """Revoke the token this gateway was configured with, if we know its id.

        Never blocks the flow: an unreachable gateway must not stop the user from
        removing local access, the token is then just left on the gateway.
        """
        token_id = existing.get(CONF_LOCAL_TOKEN_ID)
        if not token_id or not existing.get(CONF_LOCAL_HOST):
            return
        if client is None:
            if not existing.get(CONF_LOCAL_TOKEN):
                return
            client = HomeComK40Local(
                async_get_clientsession(self.hass),
                existing[CONF_LOCAL_HOST],
                existing[CONF_LOCAL_TOKEN],
                device_id=self._local_gateway,
            )
        try:
            await client.async_revoke_token(token_id)
        except (ApiError, AuthFailedError, NotRespondingError, TimeoutError) as err:
            _LOGGER.warning(
                "Could not revoke local token %s on the gateway, remove it there "
                "if its token store fills up: %s",
                token_id,
                err,
            )

    def _local_schema(self, host_default: str) -> vol.Schema:
        """Return the local-credentials form schema."""
        return vol.Schema(
            {
                vol.Required(CONF_LOCAL_HOST, default=host_default): cv.string,
                vol.Optional(CONF_LOCAL_LOGIN, default=""): cv.string,
                vol.Optional(CONF_LOCAL_PASSWORD, default=""): cv.string,
                vol.Optional(CONF_LOCAL_REMOVE, default=False): cv.boolean,
            }
        )

    def _save_local(self, config: dict[str, str] | None) -> FlowResult:
        """Persist (or clear) the local config for the selected gateway.

        Stored in ``entry.data`` rather than options because the token is a
        credential; the update triggers a reload so the coordinator picks it up.
        """
        local = dict(self._entry.data.get(CONF_LOCAL) or {})
        if config is None:
            local.pop(self._local_gateway, None)
        else:
            local[self._local_gateway] = config

        new_data = dict(self._entry.data)
        new_data[CONF_LOCAL] = local
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)
        # OptionsFlowWithReload only reloads when the *options* changed, and
        # these are unchanged, so the coordinator would never pick the new
        # entry.data up. Reload explicitly.
        self.hass.config_entries.async_schedule_reload(self._entry.entry_id)
        return self.async_create_entry(title="", data=dict(self._entry.options))

    async def async_step_general(self, user_input=None) -> FlowResult:
        """Handle the poll interval, brand and wallbox-label settings."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_seconds = int(
            self._entry.options.get(
                CONF_UPDATE_SECONDS, int(DEFAULT_UPDATE_INTERVAL.total_seconds())
            )
        )
        current_brand_buderus = self._entry.options.get(CONF_BRAND_BUDERUS, False)
        current_wb_label = self._entry.options.get(CONF_WB_LABEL, DEFAULT_WB_LABEL)

        schema = vol.Schema(
            {
                vol.Required(CONF_UPDATE_SECONDS, default=current_seconds): vol.All(
                    int, vol.Range(min=MIN_UPDATE_SECONDS, max=MAX_UPDATE_SECONDS)
                ),
                vol.Required(
                    CONF_BRAND_BUDERUS, default=current_brand_buderus
                ): cv.boolean,
                vol.Optional(CONF_WB_LABEL, default=current_wb_label): cv.string,
            }
        )

        return self.async_show_form(step_id="general", data_schema=schema)
