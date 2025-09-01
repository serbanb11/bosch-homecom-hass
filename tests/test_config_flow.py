"""Tests for the config flow."""
from unittest.mock import AsyncMock, patch

from homecom_alt import ApiError, AuthFailedError

from homeassistant import config_entries, setup
from homeassistant.const import CONF_CODE, CONF_TOKEN, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom.const import CONF_DEVICES, CONF_REFRESH, DOMAIN

@pytest.mark.asyncio
async def test_async_step_user_success(hass):
    """Test the user step with valid credentials."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    flow = hass.config_entries.flow._progress[result["flow_id"]]
    with patch(
        "custom_components.bosch_homecom.async_setup", return_value=True
    ) as mock_setup, patch(
        "custom_components.bosch_homecom.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        """Test the user step."""
        await setup.async_setup_component(hass, "persistent_notification", {})
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == "form"
    assert result["errors"] == {}

    result = await flow.async_step_user(
        user_input={CONF_USERNAME: "test-user"}
    )

    assert result["type"] == "form"
    assert result["step_id"] == "browser"
    assert flow.data == {CONF_USERNAME: "test-user"}
    flow.async_abort(reason="test_cleanup")
    await hass.async_block_till_done()
    assert len(mock_setup.mock_calls) == 0
    assert len(mock_setup_entry.mock_calls) == 0

@pytest.mark.asyncio
async def test_async_step_browser_success(hass):
    """Test the browser step with valid credentials."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    flow = hass.config_entries.flow._progress[result["flow_id"]]

    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.bosch_homecom.async_setup", return_value=True
    ) as mock_setup, patch(
        "custom_components.bosch_homecom.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry, patch(
        "custom_components.bosch_homecom.config_flow.async_get_clientsession",
        return_value=AsyncMock()
    ), patch(
        "custom_components.bosch_homecom.config_flow.HomeComAlt.create",
        new_callable=AsyncMock
    ) as mock_create:
        # Mock the BHC instance returned by HomeComAlt.create
        mock_bhc = AsyncMock()
        mock_bhc.async_get_devices.return_value = [{"deviceId": "123", "deviceType": "generic"}]
        mock_bhc.refresh_token = "mock_refresh"
        mock_bhc.token = "mock_token"
        mock_create.return_value = mock_bhc

        result = await flow.async_step_user(
            user_input={CONF_USERNAME: "test-user"}
        )

        assert result["type"] == "form"
        assert result["step_id"] == "browser"
        assert flow.data == {CONF_USERNAME: "test-user"}

        # Call the browser step with a valid code
        result = await flow.async_step_browser(user_input={CONF_CODE: "valid_code"})

    # Check that data was updated
    assert result["type"] == "form"
    assert result["step_id"] == "devices"
    assert flow.data == {CONF_DEVICES: [{"deviceId": "123", "deviceType": "generic"}], CONF_REFRESH: "mock_refresh", CONF_TOKEN: "mock_token", CONF_USERNAME: "test-user", CONF_CODE: "valid_code"}

    await hass.async_block_till_done()
    assert len(mock_setup.mock_calls) == 0
    assert len(mock_setup_entry.mock_calls) == 0

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "side_effect",
    [
        (ApiError),
        (AuthFailedError),
        (TimeoutError),
        (AuthFailedError),
    ],
)
async def test_async_step_browser_invalid(hass, side_effect):
    """Test the browser step with invalid credentials."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    flow = hass.config_entries.flow._progress[result["flow_id"]]

    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.bosch_homecom.config_flow.async_get_clientsession",
        return_value=AsyncMock()
    ), patch(
        "custom_components.bosch_homecom.config_flow.HomeComAlt.create",
        new_callable=AsyncMock
    ) as mock_create:
        # Mock the BHC instance returned by HomeComAlt.create
        mock_bhc = AsyncMock()
        mock_bhc.async_get_devices.side_effect = side_effect("default_status")
        mock_bhc.async_get_devices.return_value = [{"deviceId": "123", "deviceType": "generic"}]
        mock_bhc.refresh_token = "mock_refresh"
        mock_bhc.token = "mock_token"
        mock_create.return_value = mock_bhc

        result = await flow.async_step_user(
            user_input={CONF_USERNAME: "test-user"}
        )

        assert result["type"] == "form"
        assert result["step_id"] == "browser"
        assert flow.data == {CONF_USERNAME: "test-user"}

        # Call the browser step with a valid code
        result = await flow.async_step_browser(user_input={CONF_CODE: "invalid_code"})

    # Check that data was updated
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}

@pytest.mark.asyncio
async def test_async_step_devices_success(hass):
    """Test the browser step with valid credentials."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    flow = hass.config_entries.flow._progress[result["flow_id"]]

    with patch(
        "custom_components.bosch_homecom.config_flow.async_get_clientsession",
        return_value=AsyncMock()
    ), patch(
        "custom_components.bosch_homecom.config_flow.HomeComAlt.create",
        new_callable=AsyncMock
    ) as mock_create:
        # Mock the BHC instance returned by HomeComAlt.create
        mock_bhc = AsyncMock()
        mock_bhc.async_get_devices.return_value = [{"deviceId": "123", "deviceType": "bhc"},{"deviceId": "124", "deviceType": "generic"},{"deviceId": "125", "deviceType": "k40"}]
        mock_bhc.refresh_token = "mock_refresh"
        mock_bhc.token = "mock_token"
        mock_create.return_value = mock_bhc

        result = await flow.async_step_user(
            user_input={CONF_USERNAME: "test-user"}
        )

        assert result["type"] == "form"
        assert result["step_id"] == "browser"
        assert flow.data == {CONF_USERNAME: "test-user"}

        # Call the browser step with a valid code
        result = await flow.async_step_browser(user_input={CONF_CODE: "valid_code"})

        # Check that data was updated
        assert result["type"] == "form"
        assert result["step_id"] == "devices"
        assert flow.data == {CONF_DEVICES: [{"deviceId": "123", "deviceType": "bhc"},{"deviceId": "124", "deviceType": "generic"},{"deviceId": "125", "deviceType": "k40"}], CONF_REFRESH: "mock_refresh", CONF_TOKEN: "mock_token", CONF_USERNAME: "test-user", CONF_CODE: "valid_code"}

        # Call the devices step
        result = await flow.async_step_devices(user_input={"123_bhc": True, "124_generic": True, "125_k40": False})

        # Check that data was updated
        assert flow.data["123_bhc"] is True
        assert flow.data["124_generic"] is True
        assert flow.data["125_k40"] is False

        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bosch HomeCom"

@pytest.mark.asyncio
async def test_async_step_reauth(hass):
    """Test the reauth step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        unique_id="test-user",
        data={"123_bhc": True, "124_generic": True, "125_k40": False, CONF_DEVICES: [{"deviceId": "123", "deviceType": "bhc"},{"deviceId": "124", "deviceType": "generic"},{"deviceId": "125", "deviceType": "k40"}], CONF_REFRESH: "mock_refresh", CONF_TOKEN: "mock_token", CONF_USERNAME: "test-user", CONF_CODE: "valid_code"},
    )
    entry.add_to_hass(hass)

    await setup.async_setup_component(hass, "persistent_notification", {})

    # Initialize the reauth flow via HA
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id}
    )
    flow = hass.config_entries.flow._progress[result["flow_id"]]

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.bosch_homecom.async_setup_entry",
        return_value=True
    ) as mock_setup_entry, patch(
        "custom_components.bosch_homecom.config_flow.async_get_clientsession",
        return_value=AsyncMock()
    ), patch(
        "custom_components.bosch_homecom.config_flow.HomeComAlt.create",
        new_callable=AsyncMock
    ) as mock_create, patch(
        "custom_components.bosch_homecom.async_setup_entry",
        new_callable=AsyncMock
    ) as mock_create_init:
        # Mock the BHC instance returned by HomeComAlt.create
        mock_bhc = AsyncMock()
        mock_bhc.async_get_devices.return_value = [{"deviceId": "123", "deviceType": "bhc"},{"deviceId": "124", "deviceType": "generic"},{"deviceId": "125", "deviceType": "k40"}]
        mock_bhc.refresh_token = "mock_refresh"
        mock_bhc.token = "mock_token"
        mock_create.return_value = mock_bhc
        mock_create_init.return_value = mock_bhc

        result = await flow.async_step_reauth_confirm(
            user_input={CONF_USERNAME: "test-user"}
        )

        assert result["type"] == "form"
        assert result["step_id"] == "browser"

        # Call the browser step with a valid code
        result = await flow.async_step_browser(user_input={CONF_CODE: "valid_code"})

        # Check that data was updated
        assert result["type"] == "form"
        assert result["step_id"] == "devices"
        # Call the devices step
        result = await flow.async_step_devices(user_input={"123_bhc": True, "124_generic": True, "125_k40": False})

        # Check that data was updated
        assert flow.data["123_bhc"] is True
        assert flow.data["124_generic"] is True
        assert flow.data["125_k40"] is False

        await hass.async_block_till_done()
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        assert len(mock_setup_entry.mock_calls) == 0