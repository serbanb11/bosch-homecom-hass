"""Test select platform."""

from unittest.mock import AsyncMock, MagicMock

from homecom_alt import BHCDeviceCommodule, BHCDeviceRac
import pytest

from custom_components.bosch_homecom.select import (
    BoschComCommoduleChargingStrategySelect,
    BoschComSelectDhwCurrentTemp,
    BoschComSelectHcCoolingOperationMode,
    BoschComSelectHcHeatcoolMode,
    BoschComSelectHcSuwiMode,
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


def _make_k40_coordinator(heating_circuits):
    """Create a mock K40 coordinator carrying heating circuits."""
    coordinator = MagicMock()
    coordinator.unique_id = "k40-123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "k40-123")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.data.device = {"deviceId": "k40-123", "deviceType": "k40"}
    coordinator.data.heating_circuits = heating_circuits
    return coordinator


async def test_setup_creates_cooling_operation_mode_select():
    """A cooling operation mode select is created when allowedValues is present."""
    circuit = {
        "id": "/heatingCircuits/hc1",
        "coolingOperationMode": {
            "value": "off",
            "allowedValues": ["off", "manual", "auto"],
        },
    }
    coordinator = _make_k40_coordinator([circuit])
    # Only heating circuits are relevant here — keep the other loops empty.
    coordinator.data.dhw_circuits = []
    coordinator.data.ventilation = []

    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]

    entities = []
    await async_setup_entry(MagicMock(), config_entry, entities.extend)

    cooling = [
        e for e in entities if isinstance(e, BoschComSelectHcCoolingOperationMode)
    ]
    assert len(cooling) == 1
    select = cooling[0]
    assert select._attr_unique_id == "k40-123-hc1-cooling"
    assert select._attr_translation_key == "hc_cooling_operation_mode"
    assert select._attr_options == ["off", "manual", "auto"]
    assert select.current_option == "off"


async def test_cooling_operation_mode_select_calls_library_and_refreshes():
    """Selecting a cooling mode PUTs the value and requests a refresh."""
    circuit = {
        "id": "/heatingCircuits/hc1",
        "coolingOperationMode": {
            "value": "off",
            "allowedValues": ["off", "manual", "auto"],
        },
    }
    coordinator = _make_k40_coordinator([circuit])
    select = BoschComSelectHcCoolingOperationMode(
        coordinator=coordinator,
        field="hc1",
        allowedValues=["off", "manual", "auto"],
    )

    await select.async_select_option("auto")

    coordinator.bhc.async_put_hc_cooling_operation_mode.assert_awaited_once_with(
        "k40-123", "hc1", "auto"
    )
    coordinator.async_request_refresh.assert_awaited_once()


# Classes that read their state variable after a matching loop — regression
# cases for the UnboundLocalError reported in #172 and the unguarded nested
# field access (same family as #176).
_LOOP_STATE_CASES = [
    (BoschComSelectDhwCurrentTemp, "dhw_circuits", "dhw1", "currentTemperatureLevel"),
    (BoschComSelectHcSuwiMode, "heating_circuits", "hc1", "currentSuWiMode"),
    (BoschComSelectHcHeatcoolMode, "heating_circuits", "hc1", "heatCoolMode"),
]

_CIRCUIT_PREFIX = {
    "dhw_circuits": "/dhwCircuits/",
    "heating_circuits": "/heatingCircuits/",
}


def _make_loop_state_select(cls, attr, field, circuits):
    """Build one of the loop-state selects on a coordinator carrying circuits."""
    coordinator = _make_k40_coordinator([])
    setattr(coordinator.data, attr, circuits)
    select = cls(coordinator=coordinator, field=field, allowedValues=["high", "eco"])
    select.async_write_ha_state = MagicMock()
    return select


@pytest.mark.parametrize(("cls", "attr", "field", "key"), _LOOP_STATE_CASES)
async def test_select_no_matching_circuit_is_none(cls, attr, field, key):
    """No matching circuit yields None instead of UnboundLocalError (#172)."""
    select = _make_loop_state_select(cls, attr, field, [])

    assert select.current_option is None

    select._handle_coordinator_update()
    assert select._attr_current_option is None
    select.async_write_ha_state.assert_called_once()


@pytest.mark.parametrize(("cls", "attr", "field", "key"), _LOOP_STATE_CASES)
async def test_select_circuits_list_none_is_none(cls, attr, field, key):
    """A transiently missing circuits list yields None instead of raising."""
    select = _make_loop_state_select(cls, attr, field, None)

    assert select.current_option is None

    select._handle_coordinator_update()
    assert select._attr_current_option is None


@pytest.mark.parametrize(("cls", "attr", "field", "key"), _LOOP_STATE_CASES)
@pytest.mark.parametrize("payload", [{}, None])
async def test_select_missing_or_null_field_is_unknown(cls, attr, field, key, payload):
    """A matching circuit without the field yields 'unknown' instead of raising."""
    circuit = {"id": _CIRCUIT_PREFIX[attr] + field}
    if payload is not None:
        circuit[key] = payload
    select = _make_loop_state_select(cls, attr, field, [circuit])

    assert select.current_option == "unknown"

    select._handle_coordinator_update()
    assert select._attr_current_option == "unknown"


@pytest.mark.parametrize(("cls", "attr", "field", "key"), _LOOP_STATE_CASES)
async def test_select_matching_circuit_returns_value(cls, attr, field, key):
    """A matching circuit with a value keeps returning that value."""
    circuit = {"id": _CIRCUIT_PREFIX[attr] + field, key: {"value": "high"}}
    select = _make_loop_state_select(cls, attr, field, [circuit])

    assert select.current_option == "high"

    select._handle_coordinator_update()
    assert select._attr_current_option == "high"
