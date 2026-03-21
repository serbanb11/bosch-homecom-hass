"""Persistent HomeCom client wrappers."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homecom_alt import (
    ConnectionOptions,
    HomeComAlt,
    HomeComCommodule,
    HomeComGeneric,
    HomeComK40,
    HomeComRac,
    HomeComWddw2,
)

from .const import CONF_REFRESH


class _PersistAuthMixin:
    """Persist Bosch auth state whenever the client rotates credentials."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, options: ConnectionOptions
    ) -> None:
        """Store Home Assistant context for auth persistence."""
        self._persist_hass = hass
        self._persist_entry = entry
        lock = getattr(options, "_auth_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            setattr(options, "_auth_lock", lock)
        self._auth_lock: asyncio.Lock = lock

    async def _async_persist_auth_state(self) -> None:
        """Persist in-memory Bosch auth state if it diverges from entry storage."""
        token = self.token
        refresh = self.refresh_token
        if not token or not refresh:
            return

        if (
            self._persist_entry.data.get(CONF_TOKEN) == token
            and self._persist_entry.data.get(CONF_REFRESH) == refresh
        ):
            return

        new_data = dict(self._persist_entry.data)
        new_data[CONF_TOKEN] = token
        new_data[CONF_REFRESH] = refresh
        self._persist_hass.config_entries.async_update_entry(
            self._persist_entry, data=new_data
        )

    async def get_token(self) -> bool | None:
        """Refresh Bosch auth and immediately sync rotated credentials to storage."""
        async with self._auth_lock:
            refreshed = await super().get_token()
            await self._async_persist_auth_state()
            return refreshed


class PersistentHomeComAlt(_PersistAuthMixin, HomeComAlt):
    """HomeCom bootstrap client with auth persistence."""

    def __init__(
        self,
        session: Any,
        options: ConnectionOptions,
        auth_provider: bool,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        _PersistAuthMixin.__init__(self, hass, entry, options)
        HomeComAlt.__init__(self, session, options, auth_provider)


class PersistentHomeComGeneric(_PersistAuthMixin, HomeComGeneric):
    """Generic Bosch client with auth persistence."""

    def __init__(
        self,
        session: Any,
        options: ConnectionOptions,
        device_id: str,
        auth_provider: bool,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        _PersistAuthMixin.__init__(self, hass, entry, options)
        HomeComGeneric.__init__(self, session, options, device_id, auth_provider)


class PersistentHomeComRac(_PersistAuthMixin, HomeComRac):
    """RAC Bosch client with auth persistence."""

    def __init__(
        self,
        session: Any,
        options: ConnectionOptions,
        device_id: str,
        auth_provider: bool,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        _PersistAuthMixin.__init__(self, hass, entry, options)
        HomeComRac.__init__(self, session, options, device_id, auth_provider)


class PersistentHomeComK40(_PersistAuthMixin, HomeComK40):
    """K40 Bosch client with auth persistence."""

    def __init__(
        self,
        session: Any,
        options: ConnectionOptions,
        device_id: str,
        auth_provider: bool,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        _PersistAuthMixin.__init__(self, hass, entry, options)
        HomeComK40.__init__(self, session, options, device_id, auth_provider)


class PersistentHomeComWddw2(_PersistAuthMixin, HomeComWddw2):
    """WDDW2 Bosch client with auth persistence."""

    def __init__(
        self,
        session: Any,
        options: ConnectionOptions,
        device_id: str,
        auth_provider: bool,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        _PersistAuthMixin.__init__(self, hass, entry, options)
        HomeComWddw2.__init__(self, session, options, device_id, auth_provider)


class PersistentHomeComCommodule(_PersistAuthMixin, HomeComCommodule):
    """Commodule Bosch client with auth persistence."""

    def __init__(
        self,
        session: Any,
        options: ConnectionOptions,
        device_id: str,
        auth_provider: bool,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        _PersistAuthMixin.__init__(self, hass, entry, options)
        HomeComCommodule.__init__(self, session, options, device_id, auth_provider)
