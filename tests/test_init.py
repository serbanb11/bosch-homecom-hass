"""Test component setup."""

import json
from pathlib import Path
from homeassistant.config_entries import ConfigEntryState
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import CONF_CODE, CONF_TOKEN, CONF_USERNAME
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from homecom_alt import BHCDeviceRac
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom import DOMAIN as COMPONENT_DOMAIN, PLATFORMS
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

    rac_data = BHCDeviceRac(
        device={"deviceId": "123", "deviceType": "rac"},
        firmware=sensor_data["firmwares"],
        notifications=sensor_data["notifications"],
        stardard_functions=sensor_data["stardard_functions"],
        advanced_functions=sensor_data["advanced_functions"],
        switch_programs=sensor_data["switch_programs"],
    )

    with patch(
        "custom_components.bosch_homecom.HomeComRac.async_update",
        new_callable=AsyncMock,
        return_value=rac_data,
    ), patch(
        "custom_components.bosch_homecom.HomeComRac.get_token",
        new_callable=AsyncMock,
    ), patch(
        "custom_components.bosch_homecom.HomeComAlt.create", new_callable=AsyncMock
    ) as mock_create:
        # Mock the BHC instance returned by HomeComAlt.create
        mock_bhc = AsyncMock()
        mock_bhc.refresh_token = "mock_refresh"
        mock_bhc.token = "mock_token"
        mock_bhc.async_get_devices.return_value = devices
        mock_bhc.async_get_firmware.return_value = {"value": "1.0.0"}
        mock_create.return_value = mock_bhc
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


@pytest.mark.asyncio
async def test_entry_setup_stores_coordinators_per_entry(hass, sensor_data):
    """Test coordinator storage does not overwrite previous config entries."""
    entry_one = MockConfigEntry(
        domain=DOMAIN,
        title="test-user-1",
        unique_id="test-user-1",
        data={
            "123_rac": True,
            CONF_DEVICES: {"123_rac": True},
            CONF_REFRESH: "mock_refresh_1",
            CONF_TOKEN: "mock_token_1",
            CONF_USERNAME: "test-user-1",
            CONF_CODE: "valid_code_1",
        },
    )
    entry_two = MockConfigEntry(
        domain=DOMAIN,
        title="test-user-2",
        unique_id="test-user-2",
        data={
            "456_rac": True,
            CONF_DEVICES: {"456_rac": True},
            CONF_REFRESH: "mock_refresh_2",
            CONF_TOKEN: "mock_token_2",
            CONF_USERNAME: "test-user-2",
            CONF_CODE: "valid_code_2",
        },
    )
    entry_one.add_to_hass(hass)
    entry_two.add_to_hass(hass)

    def create_side_effect(*args, **kwargs):
        token = kwargs["options"].token if "options" in kwargs else args[1].token
        mock_bhc = AsyncMock()
        if token == "mock_token_1":
            mock_bhc.refresh_token = "mock_refresh_1"
            mock_bhc.token = "mock_token_1"
            mock_bhc.async_get_devices.return_value = [{"deviceId": "123", "deviceType": "rac"}]
            mock_bhc.async_get_firmware.return_value = {"value": "1.0.0"}
        else:
            mock_bhc.refresh_token = "mock_refresh_2"
            mock_bhc.token = "mock_token_2"
            mock_bhc.async_get_devices.return_value = [{"deviceId": "456", "deviceType": "rac"}]
            mock_bhc.async_get_firmware.return_value = {"value": "2.0.0"}
        return mock_bhc

    def rac_side_effect(*args, **kwargs):
        device_id = args[2]
        client = AsyncMock()
        client.get_token = AsyncMock()
        client.async_update = AsyncMock(
            return_value=BHCDeviceRac(
                device={"deviceId": device_id, "deviceType": "rac"},
                firmware=sensor_data["firmwares"],
                notifications=sensor_data["notifications"],
                stardard_functions=sensor_data["stardard_functions"],
                advanced_functions=sensor_data["advanced_functions"],
                switch_programs=sensor_data["switch_programs"],
            )
        )
        client.async_action_universal_get = AsyncMock(return_value={"device_id": device_id})
        return client

    with patch(
        "custom_components.bosch_homecom.HomeComAlt.create",
        side_effect=create_side_effect,
    ), patch(
        "custom_components.bosch_homecom.HomeComRac",
        side_effect=rac_side_effect,
    ):
        assert await hass.config_entries.async_setup(entry_one.entry_id) is True
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id) is True
        await hass.async_block_till_done()

    domain_data = hass.data[COMPONENT_DOMAIN]
    assert set(domain_data) == {entry_one.entry_id, entry_two.entry_id}
    assert domain_data[entry_one.entry_id][0].device["deviceId"] == "123"
    assert domain_data[entry_two.entry_id][0].device["deviceId"] == "456"


@pytest.mark.asyncio
async def test_get_custom_path_service_uses_matching_entry_coordinator(hass, sensor_data):
    """Test custom path service resolves the correct coordinator across entries."""
    await async_setup_component(hass, DOMAIN, {})

    entry_one = MockConfigEntry(
        domain=DOMAIN,
        title="test-user-1",
        unique_id="test-user-1",
        data={
            "123_rac": True,
            CONF_DEVICES: {"123_rac": True},
            CONF_REFRESH: "mock_refresh_1",
            CONF_TOKEN: "mock_token_1",
            CONF_USERNAME: "test-user-1",
            CONF_CODE: "valid_code_1",
        },
    )
    entry_two = MockConfigEntry(
        domain=DOMAIN,
        title="test-user-2",
        unique_id="test-user-2",
        data={
            "456_rac": True,
            CONF_DEVICES: {"456_rac": True},
            CONF_REFRESH: "mock_refresh_2",
            CONF_TOKEN: "mock_token_2",
            CONF_USERNAME: "test-user-2",
            CONF_CODE: "valid_code_2",
        },
    )
    entry_one.add_to_hass(hass)
    entry_two.add_to_hass(hass)

    clients_by_device = {}

    def create_side_effect(*args, **kwargs):
        token = kwargs["options"].token if "options" in kwargs else args[1].token
        mock_bhc = AsyncMock()
        if token == "mock_token_1":
            mock_bhc.refresh_token = "mock_refresh_1"
            mock_bhc.token = "mock_token_1"
            mock_bhc.async_get_devices.return_value = [{"deviceId": "123", "deviceType": "rac"}]
            mock_bhc.async_get_firmware.return_value = {"value": "1.0.0"}
        else:
            mock_bhc.refresh_token = "mock_refresh_2"
            mock_bhc.token = "mock_token_2"
            mock_bhc.async_get_devices.return_value = [{"deviceId": "456", "deviceType": "rac"}]
            mock_bhc.async_get_firmware.return_value = {"value": "2.0.0"}
        return mock_bhc

    def rac_side_effect(*args, **kwargs):
        device_id = args[2]
        client = AsyncMock()
        client.get_token = AsyncMock()
        client.async_update = AsyncMock(
            return_value=BHCDeviceRac(
                device={"deviceId": device_id, "deviceType": "rac"},
                firmware=sensor_data["firmwares"],
                notifications=sensor_data["notifications"],
                stardard_functions=sensor_data["stardard_functions"],
                advanced_functions=sensor_data["advanced_functions"],
                switch_programs=sensor_data["switch_programs"],
            )
        )
        client.async_action_universal_get = AsyncMock(return_value={"device_id": device_id})
        clients_by_device[device_id] = client
        return client

    with patch(
        "custom_components.bosch_homecom.HomeComAlt.create",
        side_effect=create_side_effect,
    ), patch(
        "custom_components.bosch_homecom.HomeComRac",
        side_effect=rac_side_effect,
    ):
        assert await hass.config_entries.async_setup(entry_one.entry_id) is True
        if entry_two.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_two.entry_id) is True
        await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "get_custom_path_service",
        {"device_id": "456", "path": "/test/path"},
        blocking=True,
        return_response=True,
    )

    assert response == {"device_id": "456"}
    clients_by_device["123"].async_action_universal_get.assert_not_called()
    clients_by_device["456"].async_action_universal_get.assert_awaited_once_with(
        "456",
        "/test/path",
    )
