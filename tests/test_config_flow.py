"""Tests for the config flow."""
from unittest import mock
from unittest.mock import AsyncMock, patch

from homecom_alt import ApiError, AuthFailedError, ClientConnectorError

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom.config_flow import BoschHomecomConfigFlow, async_check_credentials
from custom_components.bosch_homecom.const import DOMAIN

@pytest.fixture
def mock_config_flow():
    """Fixture to mock the config flow."""
    return BoschHomecomConfigFlow()

@pytest.mark.asyncio
async def test_async_step_user_success(hass):
    """Test the user step with valid credentials."""
    flow = BoschHomecomConfigFlow()
    flow.hass = hass

    with patch(
        "custom_components.bosch_homecom.config_flow.async_check_credentials",
        return_value=None,
    ), patch.object(
        flow, "async_set_unique_id", return_value=None
    ):
        result = await flow.async_step_user(
            user_input={CONF_USERNAME: "test-user", CONF_PASSWORD: "test-pass"}
        )

    assert result["type"] == "create_entry"
    assert result["title"] == "Bosch HomeCom"
    assert result["data"] == {CONF_USERNAME: "test-user", CONF_PASSWORD: "test-pass"}

@pytest.mark.asyncio
async def test_async_step_user_invalid_credentials(hass):
    """Test the user step with invalid credentials."""
    flow = BoschHomecomConfigFlow()
    flow.hass = hass

    with patch(
        "custom_components.bosch_homecom.config_flow.async_check_credentials",
        side_effect=Exception,
    ):
        result = await flow.async_step_user(
            user_input={CONF_USERNAME: "test-user", CONF_PASSWORD: "test-pass"}
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "unknown"}

@pytest.mark.asyncio
async def test_async_step_reauth(hass):
    """Test the reauth step."""
    flow = BoschHomecomConfigFlow()
    flow.hass = hass
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test",
        unique_id="test",
        data={CONF_USERNAME: "test-user", CONF_PASSWORD: "test-pass"},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.bosch_homecom.config_flow.async_check_credentials",
        return_value=None,
    ), patch.object(
        flow, "_get_reauth_entry", return_value=entry
    ):
        result = await flow.async_step_reauth_confirm(
            user_input={CONF_USERNAME: "test-user", CONF_PASSWORD: "test-pass"}
        )

        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"

@pytest.mark.asyncio
async def test_async_step_reauth_confirm_invalid_credentials(hass):
    """Test the reauth confirm step with invalid credentials."""
    flow = BoschHomecomConfigFlow()
    flow.hass = hass
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test",
        unique_id="test",
        data={CONF_USERNAME: "test-user", CONF_PASSWORD: "test-pass"},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.bosch_homecom.config_flow.async_check_credentials",
        side_effect=ApiError("API Error"),
    ), patch.object(
        flow, "_get_reauth_entry", return_value=entry
    ):
        result = await flow.async_step_reauth_confirm(
            user_input={CONF_USERNAME: "test-user", CONF_PASSWORD: "test-pass"}
        )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reauth_unsuccessful"

async def test_form_create_entry(hass: HomeAssistant) -> None:
    """Test that the user step with valid credentials works."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    with patch(
        "custom_components.bosch_homecom.config_flow.async_check_credentials",
        return_value=None,
    ), patch(
        "custom_components.bosch_homecom.async_setup_entry",
        return_value=True
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "valid_user", "password": "valid_pass"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bosch HomeCom"
    assert result["data"]["username"] == "valid_user"
    assert len(mock_setup_entry.mock_calls) == 1

async def test_check_credentials_success(hass: HomeAssistant) -> None:
    """Test that credentials check succeeds with valid credentials."""

    with patch(
        "custom_components.bosch_homecom.config_flow.async_check_credentials",
        return_value=None,
    ), patch(
        "custom_components.bosch_homecom.HomeComAlt.create",
        return_value=None,
    ):
        await async_check_credentials(
            hass, {"username": "valid_user", "password": "valid_pass"}
        )

@pytest.mark.parametrize(
    "side_effect, expected_exception",
    [
        (AuthFailedError, AuthFailedError),
        (TimeoutError, TimeoutError),
        (ApiError, ApiError),
    ],
)
async def test_check_credentials_errors(hass: HomeAssistant, side_effect, expected_exception) -> None:
    """Test credential check failures for different exceptions."""
    with patch(
        "custom_components.bosch_homecom.config_flow.async_check_credentials",
    ), patch(
        "custom_components.bosch_homecom.HomeComAlt.create",
        side_effect=side_effect("default_status"),
    ):
        with pytest.raises(expected_exception):
            await async_check_credentials(
                hass, {"username": "invalid_user", "password": "wrong_pass"}
            )