import pytest
from unittest.mock import Mock, AsyncMock
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from custom_components.bosch_homecom.coordinator import BoschComModuleCoordinator
from custom_components.bosch_homecom.const import DOMAIN, MANUFACTURER, DEFAULT_UPDATE_INTERVAL
from homecom_alt import ApiError, InvalidSensorDataError, AuthFailedError, BHCDevice
from tenacity import RetryError
from homeassistant.helpers.update_coordinator import UpdateFailed

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

def test_init_coordinator(hass, bhc, device, firmware):
    """Test the initialization of the coordinator."""
    coordinator = BoschComModuleCoordinator(hass, bhc, device, firmware)

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
async def test_async_update_data_success(hass, bhc, device, firmware):
    """Test successful data update."""
    coordinator = BoschComModuleCoordinator(hass, bhc, device, firmware)
    bhc.async_update = AsyncMock(return_value=BHCDevice(
        device=device,
        firmware=firmware,
        notifications=[],
        stardard_functions=[],
        advanced_functions=[],
        switch_programs=[]
    ))

    data = await coordinator._async_update_data()
    assert data.device == device
    assert data.firmware == firmware
    assert data.notifications == []
    assert data.stardard_functions == []
    assert data.advanced_functions == []
    assert data.switch_programs == []

@pytest.mark.asyncio
async def test_async_update_data_api_error(hass, bhc, device, firmware):
    """Test data update with ApiError."""
    coordinator = BoschComModuleCoordinator(hass, bhc, device, firmware)
    bhc.async_update = Mock(side_effect=ApiError("error_status"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

@pytest.mark.asyncio
async def test_async_update_data_invalid_sensor_data_error(hass, bhc, device, firmware):
    """Test data update with InvalidSensorDataError."""
    coordinator = BoschComModuleCoordinator(hass, bhc, device, firmware)
    bhc.async_update = Mock(side_effect=InvalidSensorDataError("error_status"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

@pytest.mark.asyncio
async def test_async_update_data_retry_error(hass, bhc, device, firmware):
    """Test data update with RetryError."""
    coordinator = BoschComModuleCoordinator(hass, bhc, device, firmware)
    bhc.async_update = Mock(side_effect=RetryError("error_status"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

@pytest.mark.asyncio
async def test_async_update_data_auth_failed_error(hass, bhc, device, firmware):
    """Test data update with AuthFailedError."""
    coordinator = BoschComModuleCoordinator(hass, bhc, device, firmware)
    bhc.async_update = Mock(side_effect=AuthFailedError("error_status"))

    with pytest.raises(AuthFailedError):
        await coordinator._async_update_data()