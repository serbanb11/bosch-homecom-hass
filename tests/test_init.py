"""Test component setup."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import CONF_CODE, CONF_TOKEN, CONF_USERNAME
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from homecom_alt import BHCDeviceRac
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom import PLATFORMS
from custom_components.bosch_homecom.const import (
    CONF_DEVICES,
    CONF_REFRESH,
    DOMAIN,
    MANUFACTURER,
)


@pytest.fixture
def bhc():
    """Fixture for HomeComAlt instance."""
    return Mock()


@pytest.fixture
def entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        unique_id="test-user",
        data={
            "123_rac": True,
            CONF_DEVICES: {"123_rac": True},
            CONF_REFRESH: "mock_refresh",
            CONF_TOKEN: "mock_token",
            CONF_USERNAME: "test-user",
            CONF_CODE: "valid_code",
        },
    )


@pytest.fixture()
def devices():
    return [{"deviceId": "123", "deviceType": "rac"}]


@pytest.fixture()
def sensor_data():
    """Fixture to load test data from JSON file."""
    file_path = Path(__file__).parent / "fixtures" / "bosch_homecom.json"
    with file_path.open() as f:
        data = json.load(f)
    return data


@pytest.mark.asyncio
async def test_entry_setup_unload(hass, entry, devices, sensor_data):
    """Test config entry setup and unload."""
    entry.add_to_hass(hass)

    with patch(
        "custom_components.bosch_homecom.HomeComRac.async_update",
        new_callable=AsyncMock,
    ) as mock_update, patch(
        "custom_components.bosch_homecom.HomeComAlt.create", new_callable=AsyncMock
    ) as mock_create:
        # Mock the BHC instance returned by HomeComAlt.create
        mock_bhc = AsyncMock()
        mock_bhc.refresh_token = "mock_refresh"
        mock_bhc.token = "mock_token"
        mock_bhc.async_get_devices.return_value = devices
        mock_bhc.async_get_firmware.return_value = {"value": "1.0.0"}
        mock_bhc.async_update.return_value = BHCDeviceRac(
            device={"deviceId": "123", "deviceType": "rac"},
            firmware=sensor_data["firmwares"],
            notifications=sensor_data["notifications"],
            stardard_functions=sensor_data["stardard_functions"],
            advanced_functions=sensor_data["advanced_functions"],
            switch_programs=sensor_data["switch_programs"],
        )
        mock_create.return_value = mock_bhc
        mock_update.return_value = mock_bhc
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    dev_reg = dr.async_get(hass)
    dev_entries = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)

    assert dev_entries
    dev_entry = dev_entries[0]
    assert dev_entry.identifiers == {(DOMAIN, devices[0]["deviceId"])}
    assert dev_entry.manufacturer == MANUFACTURER
    assert dev_entry.name == "Boschcom_rac_123"
    assert dev_entry.model == "Residential Air Conditioning"

    with patch.object(
        hass.config_entries, "async_forward_entry_unload", return_value=True
    ) as unload:
        await hass.config_entries.async_unload(entry.entry_id)

    await hass.async_block_till_done()
    assert unload.call_count == len(PLATFORMS)


async def test_async_setup(hass):
    """Test the component gets setup."""
    assert await async_setup_component(hass, DOMAIN, {}) is True
