"""Test select platform."""

from unittest.mock import AsyncMock, MagicMock

from homecom_alt import BHCDeviceCommodule, BHCDeviceRac

from custom_components.bosch_homecom.select import (
    BoschComCommoduleChargingStrategySelect,
    async_setup_entry,
)


def _make_commodule_coordinator(charge_points):
    """Create a mock commodule coordinator."""
    coordinator = MagicMock()
    coordinator.unique_id = "wb123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "wb123")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.data = BHCDeviceCommodule(
        device={"deviceId": "wb123", "deviceType": "commodule"},
        firmware={"value": "1.0.0"},
        notifications=[],
        charge_points=charge_points,
        eth0_state=None,
        wifi_state=None,
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


def _cp_with_strategy(value="default", allowed=("default", "solar-eco")):
    """Build a charge point reference carrying a chargingStrategy field."""
    return {
        "id": "/devices/wb123/charge_points/cp1",
        "chargingStrategy": {"value": value, "allowedValues": list(allowed)},
    }


async def test_setup_creates_charging_strategy_select():
    """A charging strategy select is created when allowedValues is present."""
    coordinator = _make_commodule_coordinator([_cp_with_strategy()])

    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]

    entities = []
    await async_setup_entry(MagicMock(), config_entry, entities.extend)

    assert len(entities) == 1
    select = entities[0]
    assert isinstance(select, BoschComCommoduleChargingStrategySelect)
    assert select._attr_unique_id == "wb123-cp1-charging-strategy"
    assert select._attr_translation_key == "wb_charging_strategy"
    assert select._attr_options == ["default", "solar-eco"]
    assert select.current_option == "default"


async def test_setup_no_select_without_allowed_values():
    """No select is created when the wallbox doesn't expose allowedValues."""
    cp = {
        "id": "/devices/wb123/charge_points/cp1",
        "chargingStrategy": {},
    }
    coordinator = _make_commodule_coordinator([cp])

    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]

    entities = []
    await async_setup_entry(MagicMock(), config_entry, entities.extend)

    assert len(entities) == 0


async def test_setup_no_select_for_non_commodule():
    """No charging strategy select is created for non-commodule devices."""
    coordinator = _make_rac_coordinator()

    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]

    entities = []
    await async_setup_entry(MagicMock(), config_entry, entities.extend)

    assert all(
        not isinstance(e, BoschComCommoduleChargingStrategySelect) for e in entities
    )


async def test_select_option_calls_library_and_refreshes():
    """Selecting an option PUTs the value and requests a refresh."""
    coordinator = _make_commodule_coordinator([_cp_with_strategy()])
    select = BoschComCommoduleChargingStrategySelect(
        coordinator=coordinator,
        cp_id="cp1",
        allowed_values=["default", "solar-eco"],
    )

    await select.async_select_option("solar-eco")

    coordinator.bhc.async_put_cp_conf_charging_strategy.assert_awaited_once_with(
        "wb123", "cp1", "solar-eco"
    )
    coordinator.async_request_refresh.assert_awaited_once()


async def test_current_option_none_when_circuit_missing():
    """current_option is None when the charge point isn't in the data."""
    coordinator = _make_commodule_coordinator([])
    select = BoschComCommoduleChargingStrategySelect(
        coordinator=coordinator,
        cp_id="cp1",
        allowed_values=["default", "solar-eco"],
    )

    assert select.current_option is None
