"""Test button platform."""

from unittest.mock import AsyncMock, MagicMock, patch

from homecom_alt import BHCDeviceCommodule, BHCDeviceRac
import pytest

from custom_components.bosch_homecom.button import (
    BoschComCommoduleAuthenticateButton,
    BoschComCommodulePauseChargingButton,
    BoschComCommoduleStartChargingButton,
    async_setup_entry,
)


def _make_commodule_coordinator(charge_points):
    """Create a mock commodule coordinator."""
    coordinator = MagicMock()
    coordinator.unique_id = "wb123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "wb123")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.entry = MagicMock()
    coordinator.entry.options = {}
    coordinator.data = BHCDeviceCommodule(
        device={"deviceId": "wb123", "deviceType": "commodule"},
        firmware={"value": "1.0.0"},
        notifications=[],
        charge_points=charge_points,
        eth0_state=None,
    )
    return coordinator


def _make_rac_coordinator():
    """Create a mock RAC coordinator."""
    coordinator = MagicMock()
    coordinator.unique_id = "rac123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "rac123")}}
    coordinator.data = BHCDeviceRac(
        device={"deviceId": "rac123", "deviceType": "rac"},
        firmware={"value": "1.0.0"},
        notifications=[],
        stardard_functions=[],
        advanced_functions=[],
        switch_programs=[],
    )
    return coordinator


@pytest.fixture
def charge_points():
    """Fixture for charge point data."""
    return [
        {
            "id": "/devices/wb123/charge_points/cp1",
            "wbState": {"value": "Available"},
        }
    ]


async def test_setup_creates_buttons_for_commodule(charge_points):
    """Test that buttons are created for commodule coordinators."""
    coordinator = _make_commodule_coordinator(charge_points)

    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]

    entities = []

    def capture_entities(ents):
        entities.extend(ents)

    await async_setup_entry(MagicMock(), config_entry, capture_entities)

    assert len(entities) == 3
    assert isinstance(entities[0], BoschComCommoduleAuthenticateButton)
    assert isinstance(entities[1], BoschComCommoduleStartChargingButton)
    assert isinstance(entities[2], BoschComCommodulePauseChargingButton)
    assert entities[0]._attr_unique_id == "wb123-cp1-authenticate"
    assert entities[1]._attr_unique_id == "wb123-cp1-start_charging"
    assert entities[2]._attr_unique_id == "wb123-cp1-pause_charging"
    assert entities[0]._attr_translation_key == "wb_authenticate"
    assert entities[1]._attr_translation_key == "wb_start_charging"
    assert entities[2]._attr_translation_key == "wb_pause_charging"


async def test_setup_no_buttons_for_non_commodule():
    """Test that no buttons are created for non-commodule coordinators."""
    coordinator = _make_rac_coordinator()

    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]

    entities = []

    def capture_entities(ents):
        entities.extend(ents)

    await async_setup_entry(MagicMock(), config_entry, capture_entities)

    assert len(entities) == 0


async def test_setup_no_buttons_for_empty_charge_points():
    """Test that no buttons are created when charge_points is empty."""
    coordinator = _make_commodule_coordinator([])

    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]

    entities = []

    def capture_entities(ents):
        entities.extend(ents)

    await async_setup_entry(MagicMock(), config_entry, capture_entities)

    assert len(entities) == 0


async def test_setup_no_buttons_for_none_charge_points():
    """Test that no buttons are created when charge_points is None."""
    coordinator = _make_commodule_coordinator(None)

    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]

    entities = []

    def capture_entities(ents):
        entities.extend(ents)

    await async_setup_entry(MagicMock(), config_entry, capture_entities)

    assert len(entities) == 0


async def test_start_charging_press(charge_points):
    """Test that pressing start charging calls the correct API method."""
    coordinator = _make_commodule_coordinator(charge_points)

    button = BoschComCommoduleStartChargingButton(coordinator=coordinator, cp_id="cp1")

    await button.async_press()

    coordinator.bhc.async_cp_start_charging.assert_awaited_once_with(
        "wb123", "cp1", "Wallbox"
    )
    coordinator.async_request_refresh.assert_awaited_once()


async def test_pause_charging_press(charge_points):
    """Test that pressing pause charging calls the correct API method."""
    coordinator = _make_commodule_coordinator(charge_points)

    button = BoschComCommodulePauseChargingButton(coordinator=coordinator, cp_id="cp1")

    await button.async_press()

    coordinator.bhc.async_cp_pause_charging.assert_awaited_once_with(
        "wb123", "cp1", "Wallbox"
    )
    coordinator.async_request_refresh.assert_awaited_once()


async def test_multiple_charge_points():
    """Test that buttons are created for each charge point."""
    charge_points = [
        {"id": "/devices/wb123/charge_points/cp1", "wbState": {"value": "Available"}},
        {"id": "/devices/wb123/charge_points/cp2", "wbState": {"value": "Charging"}},
    ]
    coordinator = _make_commodule_coordinator(charge_points)

    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]

    entities = []

    def capture_entities(ents):
        entities.extend(ents)

    await async_setup_entry(MagicMock(), config_entry, capture_entities)

    assert len(entities) == 6
    unique_ids = {e._attr_unique_id for e in entities}
    assert unique_ids == {
        "wb123-cp1-authenticate",
        "wb123-cp1-start_charging",
        "wb123-cp1-pause_charging",
        "wb123-cp2-authenticate",
        "wb123-cp2-start_charging",
        "wb123-cp2-pause_charging",
    }


async def test_start_charging_custom_label(charge_points):
    """Test that start charging uses the configured wallbox label."""
    coordinator = _make_commodule_coordinator(charge_points)
    coordinator.entry.options = {"wb_label": "MyWallbox"}

    button = BoschComCommoduleStartChargingButton(coordinator=coordinator, cp_id="cp1")

    await button.async_press()

    coordinator.bhc.async_cp_start_charging.assert_awaited_once_with(
        "wb123", "cp1", "MyWallbox"
    )


async def test_pause_charging_custom_label(charge_points):
    """Test that pause charging uses the configured wallbox label."""
    coordinator = _make_commodule_coordinator(charge_points)
    coordinator.entry.options = {"wb_label": "MyWallbox"}

    button = BoschComCommodulePauseChargingButton(coordinator=coordinator, cp_id="cp1")

    await button.async_press()

    coordinator.bhc.async_cp_pause_charging.assert_awaited_once_with(
        "wb123", "cp1", "MyWallbox"
    )
