"""Presence heartbeat for Matter (bacon) devices: an experiment for #203.

The retained ``{serial}/topics/sensor`` message of an Air 4000i was eight days
old while the device measured live. Reading the HomeCom app showed exactly one
thing it does on the push channel that this integration did not: while its
MQTT session is up it POSTs an empty body to ``v1/users/self/live`` on the
claiming host every five minutes, a report that an active client is watching.
The hypothesis is that the backend relays device telemetry more often while
such a client is present. This module sends the same report so a reporter can
tell whether the sensor topic starts refreshing. Every request is logged at
INFO so the result can be read off the Home Assistant log.
"""

from __future__ import annotations

from datetime import timedelta
import logging

from aiohttp import ClientError, ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homecom_alt import BaconMqttClient, HomeComAlt
from homecom_alt.bacon import bacon_host

_LOGGER = logging.getLogger(__name__)

# The app's cadence (BaconRepositoryComponent: 5 minutes).
HEARTBEAT_INTERVAL = timedelta(minutes=5)
HEARTBEAT_PATH = "/v1/users/self/live"


def heartbeat_url(region: str) -> str:
    """Return the presence endpoint for ``region``."""
    return f"https://{bacon_host('claiming', region)}{HEARTBEAT_PATH}"


async def async_send_heartbeat(
    session: ClientSession, token: str, region: str
) -> int | None:
    """POST one presence report; return the HTTP status, None on a transport error."""
    url = heartbeat_url(region)
    try:
        async with session.post(
            url,
            data=b"",
            headers={"Authorization": f"Bearer {token}", "Content-Length": "0"},
            timeout=15,
        ) as resp:
            body = (await resp.text())[:200]
            if resp.status < 300:
                _LOGGER.info("Bacon presence heartbeat: %s -> %s", url, resp.status)
            else:
                _LOGGER.warning(
                    "Bacon presence heartbeat: %s -> %s %s", url, resp.status, body
                )
            return resp.status
    except (ClientError, TimeoutError) as err:
        _LOGGER.warning("Bacon presence heartbeat: %s failed: %s", url, err)
        return None


@callback
def async_start_bacon_heartbeat(
    hass: HomeAssistant,
    entry: ConfigEntry,
    session: ClientSession,
    token_manager: HomeComAlt,
    client: BaconMqttClient,
    region: str,
) -> None:
    """Send the presence report now and every HEARTBEAT_INTERVAL while connected.

    Stops with the entry. The token is read on every tick from the same token
    manager the MQTT session uses, so a rotated token is picked up.
    """

    async def _tick(_now=None) -> None:
        if not client.is_connected:
            _LOGGER.debug("Bacon presence heartbeat skipped: MQTT not connected")
            return
        token = token_manager.token
        if not token:
            _LOGGER.debug("Bacon presence heartbeat skipped: no access token")
            return
        await async_send_heartbeat(session, token, region)

    entry.async_on_unload(async_track_time_interval(hass, _tick, HEARTBEAT_INTERVAL))
    entry.async_create_background_task(hass, _tick(), "bosch_homecom bacon heartbeat")
