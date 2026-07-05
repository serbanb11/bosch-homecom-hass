"""Tests for wddw2 (Tronic TR4001) switches, water heater and notifications."""

from unittest.mock import AsyncMock, Mock

from homeassistant.components.water_heater import WaterHeaterEntityFeature
from homecom_alt import BHCDeviceWddw2

from custom_components.bosch_homecom.sensor import BoschComSensorNotificationsWddw2
from custom_components.bosch_homecom.switch import (
    BoschComWddw2HolidayModeSwitch,
    BoschComWddw2SafetyTempSwitch,
)
from custom_components.bosch_homecom.water_heater import BoschComWddw2WaterHeater

# ---------------------------------------------------------------------------
# Data fixtures modelling the homecom_alt-enriched wddw2 payload
# ---------------------------------------------------------------------------

# Read-only device (TR4001): operationMode.writeable == 0, tempLevel populated
# by the library fallback but without a writable manual setpoint.
_DHW_READ_ONLY = [
    {
        "id": "/dhwCircuits/dhw1",
        "operationMode": {"value": "eco", "writeable": 0, "allowedValues": []},
        "outletTemperature": {"value": 45.0, "unitOfMeasure": "C"},
        "tempLevel": {"manual": {"value": 48}, "bath": {"value": 52}},
        "safetyTemperature": {"value": "on"},
    }
]

# Writable device: operationMode + manual setpoint both writeable.
_DHW_WRITABLE = [
    {
        "id": "/dhwCircuits/dhw1",
        "operationMode": {
            "value": "manual",
            "writeable": 1,
            "allowedValues": ["off", "manual", "high"],
        },
        "outletTemperature": {"value": 50.0, "unitOfMeasure": "C"},
        "tempLevel": {
            "manual": {
                "value": 57.0,
                "writeable": 1,
                "minValue": 36,
                "maxValue": 60,
            }
        },
        "safetyTemperature": {"value": "off"},
    }
]


def _make_data(dhw_circuits=None, notifications=None, holiday_mode=None):
    return BHCDeviceWddw2(
        device={"deviceId": "102051881", "deviceType": "wddw2"},
        firmware=[],
        notifications=notifications or [],
        dhw_circuits=dhw_circuits or [],
        holiday_mode=holiday_mode,
    )


def _coordinator(dhw_circuits=None, notifications=None, holiday_mode=None):
    coord = Mock()
    coord.unique_id = "102051881"
    coord.device_info = Mock()
    coord.data = _make_data(dhw_circuits, notifications, holiday_mode)
    coord.async_request_refresh = AsyncMock()
    coord.bhc = Mock()
    coord.bhc.async_put_dhw_safety_temperature = AsyncMock()
    coord.bhc.async_put_holiday_mode = AsyncMock()
    coord.bhc.async_put_dhw_operation_mode = AsyncMock()
    coord.bhc.async_set_dhw_temp_level = AsyncMock()
    return coord


# ---------------------------------------------------------------------------
# Safety temperature switch
# ---------------------------------------------------------------------------


def test_safety_temp_switch_is_on():
    coord = _coordinator(dhw_circuits=_DHW_READ_ONLY)
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord, field="dhw1")
    assert switch.is_on is True
    assert switch.unique_id == "102051881-dhw1-safety-temperature"


def test_safety_temp_switch_is_off():
    coord = _coordinator(dhw_circuits=_DHW_WRITABLE)
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord, field="dhw1")
    assert switch.is_on is False


def test_safety_temp_switch_is_none_when_absent():
    circuits = [{"id": "/dhwCircuits/dhw1", "operationMode": {}}]
    coord = _coordinator(dhw_circuits=circuits)
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord, field="dhw1")
    assert switch.is_on is None


async def test_safety_temp_switch_turn_on_calls_public_api():
    coord = _coordinator(dhw_circuits=_DHW_READ_ONLY)
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord, field="dhw1")

    await switch.async_turn_on()

    coord.bhc.async_put_dhw_safety_temperature.assert_called_once_with(
        "102051881", "dhw1", "on"
    )
    coord.async_request_refresh.assert_called_once()


async def test_safety_temp_switch_turn_off_calls_public_api():
    coord = _coordinator(dhw_circuits=_DHW_READ_ONLY)
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord, field="dhw1")

    await switch.async_turn_off()

    coord.bhc.async_put_dhw_safety_temperature.assert_called_once_with(
        "102051881", "dhw1", "off"
    )


# ---------------------------------------------------------------------------
# Holiday mode switch
# ---------------------------------------------------------------------------


def test_holiday_switch_is_on():
    coord = _coordinator(holiday_mode={"value": "on"})
    switch = BoschComWddw2HolidayModeSwitch(coordinator=coord)
    assert switch.is_on is True


def test_holiday_switch_is_none_when_absent():
    coord = _coordinator(holiday_mode=None)
    switch = BoschComWddw2HolidayModeSwitch(coordinator=coord)
    assert switch.is_on is None


async def test_holiday_switch_turn_on_calls_public_api():
    coord = _coordinator(holiday_mode={"value": "off"})
    switch = BoschComWddw2HolidayModeSwitch(coordinator=coord)

    await switch.async_turn_on()

    coord.bhc.async_put_holiday_mode.assert_called_once_with("102051881", "on")
    coord.async_request_refresh.assert_called_once()


# ---------------------------------------------------------------------------
# Water heater capability detection
# ---------------------------------------------------------------------------


def test_water_heater_readonly_disables_features():
    coord = _coordinator(dhw_circuits=_DHW_READ_ONLY)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert WaterHeaterEntityFeature.TARGET_TEMPERATURE not in entity.supported_features
    assert WaterHeaterEntityFeature.OPERATION_MODE not in entity.supported_features
    # raw operation value preserved (localized via translations, not in Python)
    assert entity.current_operation == "eco"
    # current temperature read from the outlet sensor
    assert entity.current_temperature == 45.0


def test_water_heater_writable_enables_features():
    coord = _coordinator(dhw_circuits=_DHW_WRITABLE)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert WaterHeaterEntityFeature.TARGET_TEMPERATURE in entity.supported_features
    assert WaterHeaterEntityFeature.OPERATION_MODE in entity.supported_features
    assert entity.target_temperature == 57.0
    assert entity.operation_list == ["off", "manual", "high"]


def test_water_heater_ignores_other_circuit():
    coord = _coordinator(dhw_circuits=_DHW_READ_ONLY)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw2")
    assert entity.current_temperature is None
    assert entity.supported_features == WaterHeaterEntityFeature(0)


async def test_water_heater_set_operation_mode_readonly_noop():
    coord = _coordinator(dhw_circuits=_DHW_READ_ONLY)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    await entity.async_set_operation_mode("manual")

    coord.bhc.async_put_dhw_operation_mode.assert_not_called()
    coord.async_request_refresh.assert_not_called()


async def test_water_heater_set_operation_mode_writable_calls_api():
    coord = _coordinator(dhw_circuits=_DHW_WRITABLE)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    await entity.async_set_operation_mode("high")

    coord.bhc.async_put_dhw_operation_mode.assert_called_once_with(
        "102051881", "dhw1", "high"
    )
    coord.async_request_refresh.assert_called_once()


async def test_water_heater_set_temperature_readonly_noop():
    coord = _coordinator(dhw_circuits=_DHW_READ_ONLY)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    await entity.async_set_temperature(temperature=55.0)

    coord.bhc.async_set_dhw_temp_level.assert_not_called()
    coord.async_request_refresh.assert_not_called()


async def test_water_heater_set_temperature_writable_calls_api():
    coord = _coordinator(dhw_circuits=_DHW_WRITABLE)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    await entity.async_set_temperature(temperature=55.0)

    coord.bhc.async_set_dhw_temp_level.assert_called_once_with(
        "102051881", "dhw1", "manual", 55
    )


# ---------------------------------------------------------------------------
# Notification sensor
# ---------------------------------------------------------------------------


def test_notifications_filters_historical():
    notifications = [
        {"dcd": "E01", "act": "A", "fc": "8"},
        {"dcd": "E07", "act": "H", "fc": "4"},
    ]
    coord = _coordinator(notifications=notifications)
    sensor = BoschComSensorNotificationsWddw2(coordinator=coord, config_entry=Mock())
    # active only: E01 mapped to its description; historical E07 excluded
    assert sensor.state == "High temperature"


def test_notifications_none_when_all_historical():
    coord = _coordinator(notifications=[{"dcd": "E01", "act": "H"}])
    sensor = BoschComSensorNotificationsWddw2(coordinator=coord, config_entry=Mock())
    assert sensor.state == "none"


def test_notifications_history_attribute():
    notifications = [
        {"dcd": "E01", "act": "A", "fc": "8"},
        {"dcd": "E99", "act": "H", "fc": "4"},
    ]
    coord = _coordinator(notifications=notifications)
    sensor = BoschComSensorNotificationsWddw2(coordinator=coord, config_entry=Mock())
    history = sensor.extra_state_attributes["history"]
    assert history[0] == {
        "code": "E01",
        "description": "High temperature",
        "active": True,
        "severity": "fault",
    }
    # unknown code falls back to the raw code; warning severity; historical
    assert history[1] == {
        "code": "E99",
        "description": "E99",
        "active": False,
        "severity": "warning",
    }
