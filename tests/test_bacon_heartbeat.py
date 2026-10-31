"""Tests for the bacon presence heartbeat experiment (#203)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.bosch_homecom.bacon_heartbeat import (
    HEARTBEAT_INTERVAL,
    async_send_heartbeat,
    async_start_bacon_heartbeat,
    heartbeat_url,
)
from custom_components.bosch_homecom.const import DOMAIN

URL = "https://claiming.euc1.bacon.bosch-tt-cw.com/v1/users/self/live"


def test_heartbeat_url_follows_the_region():
    assert heartbeat_url("euc1") == URL
    assert heartbeat_url("use1").startswith("https://claiming.use1.")


async def test_send_heartbeat_posts_an_empty_body_with_the_token(hass, aioclient_mock):
    aioclient_mock.post(URL, status=204)
    session = __import__(
        "homeassistant.helpers.aiohttp_client", fromlist=["x"]
    ).async_get_clientsession(hass)

    status = await async_send_heartbeat(session, "tok", "euc1")

    assert status == 204
    (request,) = aioclient_mock.mock_calls
    assert request[0] == "POST"
    assert request[3]["Authorization"] == "Bearer tok"
    assert not request[2]  # empty body


async def test_send_heartbeat_reports_a_rejection_without_raising(
    hass, aioclient_mock, caplog
):
    aioclient_mock.post(URL, status=403, text="nope")
    session = __import__(
        "homeassistant.helpers.aiohttp_client", fromlist=["x"]
    ).async_get_clientsession(hass)

    assert await async_send_heartbeat(session, "tok", "euc1") == 403
    assert "403 nope" in caplog.text


async def test_heartbeat_runs_now_and_every_five_minutes_while_connected(
    hass, aioclient_mock
):
    aioclient_mock.post(URL, status=204)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    session = __import__(
        "homeassistant.helpers.aiohttp_client", fromlist=["x"]
    ).async_get_clientsession(hass)
    client = Mock(is_connected=True)
    token_manager = Mock(token="tok")

    async_start_bacon_heartbeat(hass, entry, session, token_manager, client, "euc1")
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 1

    async_fire_time_changed(hass, dt_util.utcnow() + HEARTBEAT_INTERVAL)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2

    # Not connected: nothing is sent, no error.
    client.is_connected = False
    async_fire_time_changed(hass, dt_util.utcnow() + 2 * HEARTBEAT_INTERVAL)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2

    # Unloading the entry stops the timer (the entry was never set up by the
    # integration here, so run its unload hooks the way async_unload would).
    client.is_connected = True
    for hook in list(entry._on_unload):
        hook()
    async_fire_time_changed(
        hass, dt_util.utcnow() + 3 * HEARTBEAT_INTERVAL + timedelta(seconds=1)
    )
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2


def test_interval_matches_the_app():
    assert HEARTBEAT_INTERVAL == timedelta(minutes=5)
