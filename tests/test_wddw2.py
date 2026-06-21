"""Tests for wddw2 coordinator, water heater and switch entities."""

from unittest.mock import AsyncMock, Mock, patch

from homeassistant.components.water_heater import WaterHeaterEntityFeature
from homeassistant.const import CONF_CODE, CONF_TOKEN, CONF_USERNAME
from homeassistant.helpers.update_coordinator import UpdateFailed
from homecom_alt import BHCDeviceWddw2
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom.const import CONF_DEVICES, CONF_REFRESH, DOMAIN
from custom_components.bosch_homecom.coordinator import BoschComModuleCoordinatorWddw2
from custom_components.bosch_homecom.switch import (
    BoschComWddw2HolidayModeSwitch,
    BoschComWddw2SafetyTempSwitch,
)
from custom_components.bosch_homecom.water_heater import (
    BoschComWddw2WaterHeater,
    _parse_temp_unit,
    _translate_op_mode,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bhc():
    return Mock()


@pytest.fixture
def device():
    return {"deviceId": "102051881", "deviceType": "wddw2"}


@pytest.fixture
def firmware():
    return {"value": "2.0.0"}


@pytest.fixture
def entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        unique_id="test-user",
        data={
            CONF_DEVICES: {"102051881_wddw2": True},
            CONF_REFRESH: "mock_refresh",
            CONF_TOKEN: "mock_token",
            CONF_USERNAME: "test-user",
            CONF_CODE: "valid_code",
        },
    )


def _make_wddw2_data(dhw_circuits=None):
    return BHCDeviceWddw2(
        device={"deviceId": "102051881", "deviceType": "wddw2"},
        firmware={"value": "2.0.0"},
        notifications=[],
        dhw_circuits=dhw_circuits or [],
    )


# ---------------------------------------------------------------------------
# Helper: build a mock coordinator with pre-populated wddw2 state
# ---------------------------------------------------------------------------


def _mock_wddw2_coordinator(
    safety_temperature="off",
    holiday_mode="off",
    temp_levels=None,
    dhw_circuits=None,
):
    coord = Mock()
    coord.unique_id = "102051881"
    coord.device_info = Mock()
    coord.wddw2_safety_temperature = safety_temperature
    coord.wddw2_holiday_mode = holiday_mode
    coord.wddw2_temp_levels = temp_levels if temp_levels is not None else {}
    coord.data = _make_wddw2_data(dhw_circuits=dhw_circuits or [])
    coord.async_request_refresh = AsyncMock()
    coord.bhc = Mock()
    coord.bhc._async_http_request = AsyncMock()
    coord.bhc.get_token = AsyncMock()
    return coord


# ---------------------------------------------------------------------------
# Coordinator tests
# ---------------------------------------------------------------------------


def test_wddw2_coordinator_init(hass, entry, bhc, device, firmware):
    """Extra wddw2 attributes are initialised to safe defaults."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorWddw2(
        hass, bhc, device, firmware, entry, False
    )
    assert coordinator.wddw2_safety_temperature is None
    assert coordinator.wddw2_holiday_mode is None
    assert coordinator.wddw2_temp_levels == {}


@pytest.mark.asyncio
async def test_wddw2_coordinator_update_populates_extra_attributes(
    hass, entry, bhc, device, firmware
):
    """Successful update fetches all four extra endpoints and stores results."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorWddw2(
        hass, bhc, device, firmware, entry, False
    )

    base_data = _make_wddw2_data()
    bhc.async_update = AsyncMock(return_value=base_data)
    bhc.async_action_universal_get = AsyncMock(
        side_effect=[
            {"value": "on"},  # safetyTemperature
            {"value": "off"},  # holidayMode
            {"value": 57.0},  # manualsetpoint
            {"value": 42.0},  # temperatureLevels/bath
        ]
    )

    await coordinator._async_update_data()

    assert coordinator.wddw2_safety_temperature == "on"
    assert coordinator.wddw2_holiday_mode == "off"
    assert coordinator.wddw2_temp_levels == {"manual": 57.0, "bath": 42.0}


@pytest.mark.asyncio
async def test_wddw2_coordinator_safety_temp_endpoint_failure_is_silent(
    hass, entry, bhc, device, firmware
):
    """Failure on safetyTemperature endpoint does not raise; attribute stays None."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorWddw2(
        hass, bhc, device, firmware, entry, False
    )

    bhc.async_update = AsyncMock(return_value=_make_wddw2_data())
    bhc.async_action_universal_get = AsyncMock(side_effect=Exception("timeout"))

    await coordinator._async_update_data()

    assert coordinator.wddw2_safety_temperature is None
    assert coordinator.wddw2_holiday_mode is None
    assert coordinator.wddw2_temp_levels == {}


@pytest.mark.asyncio
async def test_wddw2_coordinator_temp_levels_ignores_non_numeric(
    hass, entry, bhc, device, firmware
):
    """Non-numeric temperature values from the API are not stored."""
    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorWddw2(
        hass, bhc, device, firmware, entry, False
    )

    bhc.async_update = AsyncMock(return_value=_make_wddw2_data())
    bhc.async_action_universal_get = AsyncMock(
        side_effect=[
            None,  # safetyTemperature returns None
            {"value": "off"},  # holidayMode
            {"value": "N/A"},  # manualsetpoint — non-numeric
            {"value": 42.0},  # bath — numeric
        ]
    )

    await coordinator._async_update_data()

    assert coordinator.wddw2_temp_levels == {"bath": 42.0}


@pytest.mark.asyncio
async def test_wddw2_coordinator_update_base_error_raises_update_failed(
    hass, entry, bhc, device, firmware
):
    """Base update errors propagate as UpdateFailed (extra endpoints not called)."""
    from homecom_alt import ApiError

    entry.add_to_hass(hass)
    coordinator = BoschComModuleCoordinatorWddw2(
        hass, bhc, device, firmware, entry, False
    )
    bhc.async_update = AsyncMock(side_effect=ApiError("error"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


# ---------------------------------------------------------------------------
# _translate_op_mode and _parse_temp_unit helper tests
# ---------------------------------------------------------------------------


def test_translate_op_mode_german():
    assert _translate_op_mode("de", "manual") == "Manuell"
    assert _translate_op_mode("de", "bath") == "Sicherheitstemperatur"


def test_translate_op_mode_english():
    assert _translate_op_mode("en", "manual") == "Manual"
    assert _translate_op_mode("en", "bath") == "Safety Temperature"


def test_translate_op_mode_unknown_language_falls_back_to_english():
    assert _translate_op_mode("fr", "manual") == "Manual"


def test_translate_op_mode_unknown_mode_returns_raw_value():
    assert _translate_op_mode("en", "eco") == "eco"


def test_parse_temp_unit_fahrenheit():
    from homeassistant.const import UnitOfTemperature

    assert _parse_temp_unit("F") == UnitOfTemperature.FAHRENHEIT


def test_parse_temp_unit_celsius_for_anything_else():
    from homeassistant.const import UnitOfTemperature

    assert _parse_temp_unit("C") == UnitOfTemperature.CELSIUS
    assert _parse_temp_unit(None) == UnitOfTemperature.CELSIUS
    assert _parse_temp_unit("K") == UnitOfTemperature.CELSIUS


# ---------------------------------------------------------------------------
# BoschComWddw2WaterHeater tests
# ---------------------------------------------------------------------------

_DHW_READ_ONLY = [
    {
        "id": "/dhwCircuits/dhw1",
        "operationMode": {
            "value": "manual",
            "writeable": 0,
            "allowedValues": ["manual", "bath"],
        },
        "outletTemperature": {"value": 45.0, "unitOfMeasure": "C"},
        "tempLevel": {},
    }
]

_DHW_WRITABLE = [
    {
        "id": "/dhwCircuits/dhw1",
        "operationMode": {
            "value": "manual",
            "writeable": 1,
            "allowedValues": ["manual", "bath"],
        },
        "outletTemperature": {"value": 50.0, "unitOfMeasure": "C"},
        "tempLevel": {
            "manual": {"value": 57.0, "writeable": 1},
            "bath": {"value": 42.0, "writeable": 1},
        },
    }
]


def test_wddw2_water_heater_extra_state_attributes_when_readonly():
    """solltemperatur is exposed as attribute when TARGET_TEMPERATURE is not supported."""
    coord = _mock_wddw2_coordinator(
        temp_levels={"manual": 57.0, "bath": 42.0},
        dhw_circuits=_DHW_READ_ONLY,
    )
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    attrs = entity.extra_state_attributes
    assert "solltemperatur" in attrs
    assert attrs["solltemperatur"] == 57.0


def test_wddw2_water_heater_extra_state_attributes_empty_when_writable():
    """extra_state_attributes is empty when TARGET_TEMPERATURE feature is active."""
    coord = _mock_wddw2_coordinator(dhw_circuits=_DHW_WRITABLE)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert entity.extra_state_attributes == {}


def test_wddw2_water_heater_target_temperature_disabled_for_readonly_device():
    """TARGET_TEMPERATURE is not in supported_features for read-only devices."""
    coord = _mock_wddw2_coordinator(
        temp_levels={"manual": 57.0},
        dhw_circuits=_DHW_READ_ONLY,
    )
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert WaterHeaterEntityFeature.TARGET_TEMPERATURE not in entity.supported_features


def test_wddw2_water_heater_target_temperature_enabled_for_writable_device():
    """TARGET_TEMPERATURE is in supported_features when library provides tempLevel."""
    coord = _mock_wddw2_coordinator(dhw_circuits=_DHW_WRITABLE)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert WaterHeaterEntityFeature.TARGET_TEMPERATURE in entity.supported_features


def test_wddw2_water_heater_uses_coord_temps_as_fallback():
    """When tempLevel is empty, coordinator.wddw2_temp_levels provides temperature."""
    coord = _mock_wddw2_coordinator(
        temp_levels={"manual": 57.0},
        dhw_circuits=_DHW_READ_ONLY,
    )
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert entity._attr_target_temperature == 57.0


def test_wddw2_water_heater_lib_temps_override_coord_temps():
    """Library-provided tempLevel values override coordinator fallback values."""
    coord = _mock_wddw2_coordinator(
        temp_levels={"manual": 99.0},  # stale fallback
        dhw_circuits=_DHW_WRITABLE,  # lib provides 57.0
    )
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert entity._attr_target_temperature == 57.0


def test_wddw2_water_heater_current_temperature_from_outlet():
    """current_temperature is read from outletTemperature."""
    coord = _mock_wddw2_coordinator(dhw_circuits=_DHW_READ_ONLY)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert entity._attr_current_temperature == 45.0


def test_wddw2_water_heater_ignores_wrong_dhw_id():
    """Entity only processes the dhw circuit matching its field."""
    coord = _mock_wddw2_coordinator(
        temp_levels={"manual": 57.0},
        dhw_circuits=_DHW_READ_ONLY,
    )
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw2")

    # dhw1 data must not be applied to a dhw2 entity
    assert entity._attr_target_temperature is None


@pytest.mark.asyncio
async def test_wddw2_water_heater_set_temperature_early_return_for_readonly(hass):
    """async_set_temperature returns early when tempLevel.manual.writeable is 0."""
    # This tests the explicit writeable=0 guard in async_set_temperature.
    # For TR4001 the guard is never reached because tempLevel is empty — HA
    # simply doesn't show the temperature slider (TARGET_TEMPERATURE not enabled).
    dhw_readonly_manual = [
        {
            "id": "/dhwCircuits/dhw1",
            "operationMode": {
                "value": "manual",
                "writeable": 1,
                "allowedValues": ["manual", "bath"],
            },
            "outletTemperature": {"value": 45.0, "unitOfMeasure": "C"},
            "tempLevel": {
                "manual": {"value": 57.0, "writeable": 0},
            },
        }
    ]
    coord = _mock_wddw2_coordinator(dhw_circuits=dhw_readonly_manual)
    coord.bhc.async_put_dhw_operation_mode = AsyncMock()
    coord.bhc.async_set_dhw_temp_level = AsyncMock()
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")
    entity.hass = hass

    await entity.async_set_temperature(temperature=55.0)

    coord.bhc.async_set_dhw_temp_level.assert_not_called()
    coord.async_request_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_wddw2_water_heater_set_operation_mode_readonly_returns_early(hass):
    """async_set_operation_mode returns early when operationMode is writeable=0."""
    coord = _mock_wddw2_coordinator(dhw_circuits=_DHW_READ_ONLY)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")
    entity.hass = hass
    hass.config.language = "en"

    await entity.async_set_operation_mode("Manual")

    coord.bhc.async_put_dhw_operation_mode.assert_not_called()


@pytest.mark.asyncio
async def test_wddw2_water_heater_set_operation_mode_writable_calls_api(hass):
    """async_set_operation_mode sends the API call when writeable != 0."""
    coord = _mock_wddw2_coordinator(dhw_circuits=_DHW_WRITABLE)
    coord.bhc.async_put_dhw_operation_mode = AsyncMock()
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")
    entity.hass = hass
    hass.config.language = "en"

    await entity.async_set_operation_mode("Safety Temperature")

    coord.bhc.async_put_dhw_operation_mode.assert_called_once()
    coord.async_request_refresh.assert_called_once()


# ---------------------------------------------------------------------------
# BoschComWddw2SafetyTempSwitch / BoschComWddw2HolidayModeSwitch tests
# ---------------------------------------------------------------------------


def test_safety_temp_switch_is_on_when_value_on():
    coord = _mock_wddw2_coordinator(safety_temperature="on")
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord)
    assert switch.is_on is True


def test_safety_temp_switch_is_off_when_value_off():
    coord = _mock_wddw2_coordinator(safety_temperature="off")
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord)
    assert switch.is_on is False


def test_safety_temp_switch_is_none_when_no_coordinator_value():
    coord = _mock_wddw2_coordinator(safety_temperature=None)
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord)
    assert switch.is_on is None


def test_holiday_mode_switch_is_on():
    coord = _mock_wddw2_coordinator(holiday_mode="on")
    switch = BoschComWddw2HolidayModeSwitch(coordinator=coord)
    assert switch.is_on is True


def test_holiday_mode_switch_is_off():
    coord = _mock_wddw2_coordinator(holiday_mode="off")
    switch = BoschComWddw2HolidayModeSwitch(coordinator=coord)
    assert switch.is_on is False


@pytest.mark.asyncio
async def test_safety_temp_switch_turn_on_calls_put_and_refresh():
    coord = _mock_wddw2_coordinator(safety_temperature="off")
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord)

    await switch.async_turn_on()

    coord.bhc._async_http_request.assert_called_once()
    call_args = coord.bhc._async_http_request.call_args
    assert call_args[0][0] == "put"
    assert call_args[0][2] == {"value": "on"}
    coord.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_safety_temp_switch_turn_off_calls_put_and_refresh():
    coord = _mock_wddw2_coordinator(safety_temperature="on")
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord)

    await switch.async_turn_off()

    coord.bhc._async_http_request.assert_called_once()
    call_args = coord.bhc._async_http_request.call_args
    assert call_args[0][2] == {"value": "off"}
    coord.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_holiday_mode_switch_turn_on_calls_correct_resource_path():
    coord = _mock_wddw2_coordinator(holiday_mode="off")
    switch = BoschComWddw2HolidayModeSwitch(coordinator=coord)

    await switch.async_turn_on()

    call_args = coord.bhc._async_http_request.call_args
    url: str = call_args[0][1]
    assert "/resource/system/holidayMode" in url
    assert call_args[0][2] == {"value": "on"}


def test_safety_temp_switch_handle_coordinator_update_sets_is_on():
    coord = _mock_wddw2_coordinator(safety_temperature="on")
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord)
    switch.async_write_ha_state = Mock()

    coord.wddw2_safety_temperature = "off"
    switch._handle_coordinator_update()

    assert switch._attr_is_on is False
    switch.async_write_ha_state.assert_called_once()


def test_safety_temp_switch_handle_coordinator_update_none_stays_none():
    coord = _mock_wddw2_coordinator(safety_temperature=None)
    switch = BoschComWddw2SafetyTempSwitch(coordinator=coord)
    switch.async_write_ha_state = Mock()

    switch._handle_coordinator_update()

    assert switch._attr_is_on is None
