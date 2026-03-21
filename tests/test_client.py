"""Tests for Bosch auth-persisting client wrappers."""

import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_CODE, CONF_TOKEN, CONF_USERNAME
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom.client import PersistentHomeComRac
from custom_components.bosch_homecom.const import CONF_DEVICES, CONF_REFRESH, DOMAIN
from homecom_alt import AuthFailedError
from homecom_alt import ConnectionOptions


@pytest.fixture
def entry():
    """Return a config entry with stored Bosch auth."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        unique_id="test-user",
        data={
            "123_rac": True,
            CONF_DEVICES: {"123_rac": True},
            CONF_REFRESH: "stored_refresh",
            CONF_TOKEN: "stored_token",
            CONF_USERNAME: "test-user",
            CONF_CODE: "valid_code",
        },
    )


@pytest.mark.asyncio
async def test_persistent_client_get_token_saves_rotated_auth(hass, entry):
    """Persist auth immediately when a client call rotates credentials."""
    entry.add_to_hass(hass)
    client = PersistentHomeComRac(
        AsyncMock(),
        ConnectionOptions(
            token="stored_token",
            refresh_token="stored_refresh",
            brand="bosch",
        ),
        "123",
        True,
        hass,
        entry,
    )

    async def mutate_tokens():
        client.token = "new_token"
        client.refresh_token = "new_refresh"
        return True

    with patch(
        "custom_components.bosch_homecom.client.HomeComAlt.get_token",
        new=AsyncMock(side_effect=mutate_tokens),
    ):
        await client.get_token()

    assert entry.data[CONF_TOKEN] == "new_token"
    assert entry.data[CONF_REFRESH] == "new_refresh"


@pytest.mark.asyncio
async def test_persistent_client_get_token_saves_preexisting_runtime_auth(hass, entry):
    """Persist auth even if runtime state already drifted before the current call."""
    entry.add_to_hass(hass)
    client = PersistentHomeComRac(
        AsyncMock(),
        ConnectionOptions(
            token="runtime_token",
            refresh_token="runtime_refresh",
            brand="bosch",
        ),
        "123",
        True,
        hass,
        entry,
    )

    with patch(
        "custom_components.bosch_homecom.client.HomeComAlt.get_token",
        new=AsyncMock(return_value=None),
    ):
        await client.get_token()

    assert entry.data[CONF_TOKEN] == "runtime_token"
    assert entry.data[CONF_REFRESH] == "runtime_refresh"


@pytest.mark.asyncio
async def test_persistent_clients_serialize_shared_refresh(hass, entry):
    """Serialize concurrent refresh attempts that share Bosch auth state."""
    entry.add_to_hass(hass)
    options = ConnectionOptions(
        token="stored_token",
        refresh_token="stored_refresh",
        brand="bosch",
    )
    client_a = PersistentHomeComRac(
        AsyncMock(),
        options,
        "123",
        True,
        hass,
        entry,
    )
    client_b = PersistentHomeComRac(
        AsyncMock(),
        options,
        "123",
        True,
        hass,
        entry,
    )

    async def fake_get_token(_self):
        seen_refresh = _self.refresh_token
        await asyncio.sleep(0)
        if seen_refresh == "stored_refresh":
            if _self.refresh_token != "stored_refresh":
                raise AuthFailedError("stale refresh token")
            _self.token = "new_token"
            _self.refresh_token = "new_refresh"
            return True
        if seen_refresh == "new_refresh":
            return None
        raise AssertionError(f"Unexpected refresh state: {seen_refresh}")

    with patch(
        "custom_components.bosch_homecom.client.HomeComAlt.get_token",
        new=fake_get_token,
    ):
        await asyncio.gather(client_a.get_token(), client_b.get_token())

    assert entry.data[CONF_TOKEN] == "new_token"
    assert entry.data[CONF_REFRESH] == "new_refresh"
