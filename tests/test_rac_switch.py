"""Tests for the RAC advanced-function switches (plasmacluster, setback mode)."""

from unittest.mock import AsyncMock, MagicMock

from homecom_alt import BHCDeviceRac

from custom_components.bosch_homecom.switch import (
    BoschComSwitchAirPurification,
    BoschComSwitchSetbackMode,
    async_setup_entry as switch_async_setup_entry,
)


def _function(name: str, value: str) -> dict:
    return {
        "id": f"/airConditioning/{name}",
        "value": value,
        "writeable": 1,
        "allowedValues": ["off", "on"],
    }


def _coordinator(advanced_functions):
    coordinator = MagicMock()
    coordinator.unique_id = "rac329"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "rac329")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.data = BHCDeviceRac(
        device={"deviceId": "rac329", "deviceType": "rac"},
        firmware=[],
        notifications=[],
        stardard_functions=[],
        advanced_functions=advanced_functions,
        switch_programs=[],
    )
    return coordinator


async def _run_switch_setup(hass, coordinator):
    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]
    entities = []
    await switch_async_setup_entry(hass, config_entry, entities.extend)
    return entities


async def test_setback_switch_created_when_the_unit_lists_it(hass):
    """A unit reporting setbackMode gets the switch next to plasmacluster (#196)."""
    coordinator = _coordinator(
        [_function("airPurificationMode", "off"), _function("setbackMode", "on")]
    )

    entities = await _run_switch_setup(hass, coordinator)

    by_type = {type(e): e for e in entities}
    assert set(by_type) == {BoschComSwitchAirPurification, BoschComSwitchSetbackMode}
    setback = by_type[BoschComSwitchSetbackMode]
    assert setback.unique_id == "rac329-setback_mode"
    assert setback.translation_key == "setback_mode"
    assert setback.is_on is True
    # The existing switch keeps its identity.
    plasma = by_type[BoschComSwitchAirPurification]
    assert plasma.unique_id == "rac329-plasmacluster"
    assert plasma.translation_key == "plasmacluster"
    assert plasma.is_on is False


async def test_no_setback_switch_when_the_unit_lacks_it(hass):
    """Models without setbackMode get no dead control."""
    coordinator = _coordinator([_function("airPurificationMode", "on")])

    entities = await _run_switch_setup(hass, coordinator)

    assert [type(e) for e in entities] == [BoschComSwitchAirPurification]


async def test_setback_switch_writes_through_the_library_setter():
    """Turning it on/off PUTs /airConditioning/setbackMode and refreshes."""
    coordinator = _coordinator([_function("setbackMode", "off")])
    switch = BoschComSwitchSetbackMode(coordinator=coordinator)
    assert switch.is_on is False

    await switch.async_turn_on()
    coordinator.bhc.async_set_setback_mode.assert_awaited_once_with("rac329", True)
    coordinator.async_request_refresh.assert_awaited_once()

    await switch.async_turn_off()
    coordinator.bhc.async_set_setback_mode.assert_awaited_with("rac329", False)
    assert coordinator.async_request_refresh.await_count == 2


async def test_plasmacluster_switch_still_writes_its_own_setter():
    """The shared base keeps plasmacluster on async_set_plasmacluster."""
    coordinator = _coordinator([_function("airPurificationMode", "on")])
    switch = BoschComSwitchAirPurification(
        coordinator=coordinator, field="plasmacluster"
    )
    assert switch.is_on is True

    await switch.async_turn_off()

    coordinator.bhc.async_set_plasmacluster.assert_awaited_once_with("rac329", False)
    coordinator.bhc.async_set_setback_mode.assert_not_awaited()
