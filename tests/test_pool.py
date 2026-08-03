"""Tests for the swimming pool K40 entities (sensor, number, switch, select)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.bosch_homecom.number import BoschComK40PoolSetpointNumber
from custom_components.bosch_homecom.select import BoschComK40PoolAdditionalHeaterSelect
from custom_components.bosch_homecom.sensor import BoschComSensorPoolTemp
from custom_components.bosch_homecom.switch import BoschComK40PoolEnabledSwitch

SAMPLE_POOL = {
    "currentTemp": {"value": 29.9, "unitOfMeasure": "C"},
    "setpointTemp": {
        "value": 29.0,
        "minValue": 4.0,
        "maxValue": 40.0,
        "stepSize": 0.5,
        "writeable": 1,
    },
    "enabled": {"value": "on", "allowedValues": ["off", "on"], "writeable": 1},
    "additionalHeaterMode": {
        "value": "never",
        "allowedValues": ["never", "withHeating", "always"],
        "writeable": 1,
    },
}


def _mock_coordinator(pool=SAMPLE_POOL):
    """Build a mock K40 coordinator exposing coordinator.data.pool."""

    class _Data:
        def __init__(self, pool_data):
            self.pool = pool_data
            self.device = {"deviceId": "102128202", "deviceType": "k40"}

    coordinator = MagicMock()
    coordinator.unique_id = "102128202"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "102128202")}}
    coordinator.data = _Data(pool)
    coordinator.bhc = MagicMock()
    coordinator.bhc.async_put_pool_setpoint_temp = AsyncMock()
    coordinator.bhc.async_put_pool_enabled = AsyncMock()
    coordinator.bhc.async_put_pool_additional_heater_mode = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


def test_pool_temp_sensor_state() -> None:
    """The pool temperature sensor reports the currentTemp value."""
    coordinator = _mock_coordinator()
    sensor = BoschComSensorPoolTemp(
        coordinator=coordinator, config_entry=None, field="pool_current_temp"
    )
    assert sensor.state == 29.9


def test_pool_temp_sensor_none_when_absent() -> None:
    """No pool -> the sensor state is None instead of raising."""
    sensor = BoschComSensorPoolTemp(
        coordinator=_mock_coordinator(pool=None),
        config_entry=None,
        field="pool_current_temp",
    )
    assert sensor.state is None


def test_pool_setpoint_number() -> None:
    """The setpoint number reads value/min/max/step and writes via the setter."""
    coordinator = _mock_coordinator()
    number = BoschComK40PoolSetpointNumber(
        coordinator=coordinator, min_value=4.0, max_value=40.0, step=0.5
    )
    assert number.native_value == 29.0
    assert number.native_min_value == 4.0
    assert number.native_max_value == 40.0
    assert number.native_step == 0.5


@pytest.mark.asyncio
async def test_pool_setpoint_number_set() -> None:
    """Setting the number calls the library setter with a float and refreshes."""
    coordinator = _mock_coordinator()
    number = BoschComK40PoolSetpointNumber(
        coordinator=coordinator, min_value=4.0, max_value=40.0, step=0.5
    )
    await number.async_set_native_value(30.5)
    coordinator.bhc.async_put_pool_setpoint_temp.assert_awaited_once_with(
        "102128202", 30.5
    )
    coordinator.async_request_refresh.assert_awaited_once()


def test_pool_enabled_switch_is_on() -> None:
    """The switch reflects the enabled resource value."""
    assert BoschComK40PoolEnabledSwitch(_mock_coordinator()).is_on is True
    off = dict(SAMPLE_POOL, enabled={"value": "off"})
    assert BoschComK40PoolEnabledSwitch(_mock_coordinator(pool=off)).is_on is False


@pytest.mark.asyncio
async def test_pool_enabled_switch_turn() -> None:
    """turn_on/turn_off send 'on'/'off' to the library setter."""
    coordinator = _mock_coordinator()
    switch = BoschComK40PoolEnabledSwitch(coordinator)
    await switch.async_turn_on()
    coordinator.bhc.async_put_pool_enabled.assert_awaited_with("102128202", "on")
    await switch.async_turn_off()
    coordinator.bhc.async_put_pool_enabled.assert_awaited_with("102128202", "off")


def test_pool_additional_heater_select_options() -> None:
    """The select exposes allowedValues and the current option."""
    coordinator = _mock_coordinator()
    select = BoschComK40PoolAdditionalHeaterSelect(
        coordinator=coordinator,
        allowedValues=["never", "withHeating", "always"],
    )
    assert select.options == ["never", "withHeating", "always"]
    assert select.current_option == "never"


@pytest.mark.asyncio
async def test_pool_additional_heater_select_set() -> None:
    """Selecting an option calls the library setter and refreshes."""
    coordinator = _mock_coordinator()
    select = BoschComK40PoolAdditionalHeaterSelect(
        coordinator=coordinator,
        allowedValues=["never", "withHeating", "always"],
    )
    await select.async_select_option("always")
    coordinator.bhc.async_put_pool_additional_heater_mode.assert_awaited_once_with(
        "102128202", "always"
    )
    coordinator.async_request_refresh.assert_awaited_once()
