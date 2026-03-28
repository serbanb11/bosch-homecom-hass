"""Tests for diagnostics."""

from types import SimpleNamespace

from homeassistant.const import CONF_CODE, CONF_TOKEN, CONF_USERNAME
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom.const import CONF_REFRESH, DOMAIN
from custom_components.bosch_homecom.diagnostics import (
    async_get_config_entry_diagnostics,
)


@pytest.mark.asyncio
async def test_async_get_config_entry_diagnostics_redacts_refresh_token(hass):
    """Test diagnostics redact Bosch auth material, including refresh tokens."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        data={
            CONF_USERNAME: "test-user",
            CONF_CODE: "valid_code",
            CONF_TOKEN: "access_token",
            CONF_REFRESH: "refresh_token",
        },
    )
    entry.add_to_hass(hass)
    entry.runtime_data = [
        SimpleNamespace(
            data=SimpleNamespace(
                device={"deviceId": "123"},
                firmware={"value": "1.0.0"},
                notifications=[],
            )
        )
    ]

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["info"][CONF_USERNAME] == "**REDACTED**"
    assert diagnostics["info"][CONF_CODE] == "**REDACTED**"
    assert diagnostics["info"][CONF_TOKEN] == "**REDACTED**"
    assert diagnostics["info"][CONF_REFRESH] == "**REDACTED**"
