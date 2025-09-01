import pytest
from unittest.mock import Mock, AsyncMock
from homeassistant.helpers.device_registry import DeviceInfo
from custom_components.bosch_homecom.coordinator import BoschComModuleCoordinatorRac
from custom_components.bosch_homecom.const import DOMAIN, MANUFACTURER, DEFAULT_UPDATE_INTERVAL,CONF_DEVICES, CONF_REFRESH
from homecom_alt import ApiError, InvalidSensorDataError, AuthFailedError, BHCDeviceRac
from tenacity import RetryError
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.const import CONF_CODE, CONF_TOKEN, CONF_USERNAME

"""Tests for the BoschComModuleCoordinator."""

@pytest.fixture
def bhc():
    """Fixture for HomeComAlt instance."""
    return Mock()

@pytest.fixture
def device():
    """Fixture for device data."""
    return {
        "deviceId": "12345",
        "deviceType": "Thermostat"
    }

@pytest.fixture
def firmware():
    """Fixture for firmware data."""
    return {
        "value": "1.0.0"
    }

@pytest.fixture
def entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        unique_id="test-user",
        data={"123_rac": True, CONF_DEVICES: {"123_rac": True}, CONF_REFRESH: "mock_refresh", CONF_TOKEN: "mock_token", CONF_USERNAME: "test-user", CONF_CODE: "valid_code"},
    )

def test_init_coordinator(hass, entry, bhc, device, firmware):
    """Test the initialization of the coordinator."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(hass, bhc, device, firmware, entry, False)

    assert coordinator.hass == hass
    assert coordinator.bhc == bhc
    assert coordinator.unique_id == device["deviceId"]
    assert coordinator.device == device
    assert coordinator.device_info == DeviceInfo(
        serial_number=device["deviceId"],
        identifiers={(DOMAIN, device["deviceId"])},
        name=f"Boschcom_{device['deviceType']}_{device['deviceId']}",
        sw_version=firmware["value"],
        manufacturer=MANUFACTURER,
    )
    assert coordinator.update_interval == DEFAULT_UPDATE_INTERVAL
    assert coordinator.always_update is True

@pytest.mark.asyncio
async def test_async_update_data_success(hass, entry, bhc, device, firmware):
    """Test successful data update."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(hass, bhc, device, firmware, entry, False)
    bhc.async_update = AsyncMock(return_value=BHCDeviceRac(
        device=device,
        firmware=firmware,
        notifications=[],
        stardard_functions=[],
        advanced_functions=[],
        switch_programs=[]
    ))

    data = await coordinator._async_update_data()
    assert data.device == device
    assert data.firmware == {}
    assert data.notifications == []
    assert data.stardard_functions == []
    assert data.advanced_functions == []
    assert data.switch_programs == []

@pytest.mark.asyncio
async def test_async_update_data_api_error(hass, entry, bhc, device, firmware):
    """Test data update with ApiError."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(hass, bhc, device, firmware, entry, False)
    bhc.async_update = Mock(side_effect=ApiError("error_status"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

@pytest.mark.asyncio
async def test_async_update_data_invalid_sensor_data_error(hass, entry, bhc, device, firmware):
    """Test data update with InvalidSensorDataError."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(hass, bhc, device, firmware, entry, False)
    bhc.async_update = Mock(side_effect=InvalidSensorDataError("error_status"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

@pytest.mark.asyncio
async def test_async_update_data_retry_error(hass, entry, bhc, device, firmware):
    """Test data update with RetryError."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(hass, bhc, device, firmware, entry, False)
    bhc.async_update = Mock(side_effect=RetryError("error_status"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

@pytest.mark.asyncio
async def test_async_update_data_auth_failed_error(hass, entry, bhc, device, firmware):
    """Test data update with AuthFailedError."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorRac(hass, bhc, device, firmware, entry, False)
    bhc.async_update = Mock(side_effect=AuthFailedError("error_status"))

    with pytest.raises(AuthFailedError):
        await coordinator._async_update_data()