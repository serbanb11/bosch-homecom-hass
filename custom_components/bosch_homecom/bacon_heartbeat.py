"""Presence heartbeat for Matter (bacon) devices.

The retained ``{serial}/topics/sensor`` message of an Air 4000i sat unchanged
for fourteen days while the device measured live. The HomeCom app does one
thing on the push channel that this integration did not: while its MQTT session
is up it POSTs ``{}`` to ``v1/users/self/live`` on the claiming host every five
minutes, a report that an active client is watching. The backend relays device
telemetry only while such a client is present: in the #203 test the first
accepted report was followed by a fresh publish within a second, and the cloud
sensor then tracked the local Matter sensor reading for reading, while a
rejected report (415, no Content-Type) moved nothing. Requests are logged at
DEBUG; a rejection at WARNING.
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
from homecom_alt.const import BACON_USER_AGENT

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
    # The body must be JSON (an empty one is fine) or the backend answers 415
    # and ignores the report. Accept and User-Agent match the library's other
    # claiming calls, so this looks like the same client as the app.
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": BACON_USER_AGENT,
    }
    try:
        async with session.post(url, data=b"{}", headers=headers, timeout=15) as resp:
            body = (await resp.text())[:200]
            if resp.status < 300:
                _LOGGER.debug("Bacon presence heartbeat: %s -> %s", url, resp.status)
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
