"""Tests for wddw2 (Tronic TR4001) switches, water heater and notifications."""

import json
from unittest.mock import AsyncMock, Mock

from homeassistant.components.water_heater import WaterHeaterEntityFeature
from homeassistant.helpers import entity_registry as er
from homecom_alt import BHCDeviceWddw2

from custom_components.bosch_homecom.const import BOSCH_SENSOR_DESCRIPTORS, DOMAIN
from custom_components.bosch_homecom.sensor import (
    BoschComSensorNotificationsWddw2,
    async_setup_entry as sensor_async_setup_entry,
)
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


def test_notifications_maps_self_test_failure():
    """E10 is a fault a TR4001 raises and the table did not know.

    An unmapped code falls through to the bare code, so the sensor read "E10"
    where the manufacturer's app reads "self-test failed". Seen on a TR4001.
    """
    coord = _coordinator(notifications=[{"dcd": "E10", "act": "A", "fc": "1"}])
    sensor = BoschComSensorNotificationsWddw2(coordinator=coord, config_entry=Mock())
    assert sensor.state == "Self-test failed"


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


# ---------------------------------------------------------------------------
# Issue #175: descriptor sensors are strictly per-circuit
# ---------------------------------------------------------------------------


def _dhw1_circuit(**overrides):
    """A circuit reporting every field the wddw2 descriptors reference.

    Setup skips a descriptor whose field the circuit does not report, so a
    fixture that carries only actualTemp yields no descriptor sensors at all.
    Pass a field as None to model a device that lacks it.
    """
    circuit = {
        "id": "/dhwCircuits/dhw1",
        "actualTemp": {"value": 48},
        "operationMode": {"value": "eco"},
        "airBoxTemperature": {"value": 21},
        "inletTemperature": {"value": 12},
        "outletTemperature": {"value": 48},
        "waterFlow": {"value": 6},
        "nbStarts": {"value": 1234},
    }
    circuit.update(overrides)
    return {key: value for key, value in circuit.items() if value is not None}


async def test_descriptor_sensors_use_per_circuit_unique_ids(hass):
    """Healthy circuits yield only dhw1-suffixed ids, never the old fallback.

    The exact "<device>-dhw1-<key>" format is pinned because it keys users'
    entity history — changing it orphans their entities (issue #175).
    """
    coord = _coordinator(dhw_circuits=[_dhw1_circuit()])
    config_entry = Mock()
    config_entry.runtime_data = [coord]

    entities = []
    await sensor_async_setup_entry(hass, config_entry, entities.extend)

    unique_ids = {e._attr_unique_id for e in entities if e._attr_unique_id}
    for desc in BOSCH_SENSOR_DESCRIPTORS["wddw2"]:
        assert f"102051881-dhw1-{desc['key']}" in unique_ids
        assert f"102051881-dhw-{desc['key']}" not in unique_ids


async def test_setup_removes_stale_fallback_registry_entries(hass):
    """Registry orphans from the removed "-dhw-" fallback are cleaned up."""
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "sensor", DOMAIN, "102051881-dhw-operation_mode"
    )
    legit = registry.async_get_or_create(
        "sensor", DOMAIN, "102051881-dhw1-operation_mode"
    )

    coord = _coordinator(dhw_circuits=[_dhw1_circuit()])
    config_entry = Mock()
    config_entry.runtime_data = [coord]

    await sensor_async_setup_entry(hass, config_entry, lambda entities: None)

    assert registry.async_get(stale.entity_id) is None
    assert registry.async_get(legit.entity_id) is not None


# ---------------------------------------------------------------------------
# What a device actually onboards
# ---------------------------------------------------------------------------


async def test_descriptor_sensor_skipped_when_circuit_lacks_the_field(hass):
    """A device without a field gets no sensor for it.

    A Tronic TR4001 has no air box. Creating the descriptor anyway onboards an
    Air Box Temperature sensor that stays unknown for the life of the install,
    and a user cannot tell it apart from one that is merely offline.
    """
    coord = _coordinator(dhw_circuits=[_dhw1_circuit(airBoxTemperature=None)])
    config_entry = Mock()
    config_entry.runtime_data = [coord]

    entities = []
    await sensor_async_setup_entry(hass, config_entry, entities.extend)

    unique_ids = {e._attr_unique_id for e in entities if e._attr_unique_id}
    assert "102051881-dhw1-air_box_temperature" not in unique_ids
    # The fields it does report are unaffected.
    assert "102051881-dhw1-outlet_temperature" in unique_ids
    assert "102051881-dhw1-inlet_temperature" in unique_ids


async def test_every_wddw2_entity_is_translatable(hass):
    """No entity a wddw2 onboards may carry a hardcoded name.

    _attr_name wins over _attr_translation_key, so an entity that sets it
    shows the same English string in every language. This asserts the shape of
    what setup produces rather than the presence of a declared key, which is
    what a check over strings.json can see: a key that stops being used simply
    disappears from its view.
    """
    coord = _coordinator(dhw_circuits=[_dhw1_circuit()])
    config_entry = Mock()
    config_entry.runtime_data = [coord]

    entities = []
    await sensor_async_setup_entry(hass, config_entry, entities.extend)

    assert entities, "setup produced no entities to check"
    benannt = [
        type(entity).__name__
        for entity in entities
        if getattr(entity, "_attr_name", None) is not None
        or getattr(entity, "_attr_translation_key", None) is None
    ]
    assert not benannt, f"entities without a translation key: {sorted(set(benannt))}"


def test_notifications_sentinel_is_translated():
    """The "none" the sensor reports when nothing is pending must be translated.

    BoschComSensorNotificationsWddw2 returns the literal string "none" rather
    than a fault text, and Home Assistant resolves that through
    entity.sensor.notifications.state. Without it the sensor shows the bare
    word "none" in every language, which is what happened when this entry was
    dropped: the name survived and only the state translation was lost, so a
    check over names alone sees nothing wrong.
    """
    from pathlib import Path  # noqa: PLC0415

    component = (
        Path(__file__).resolve().parents[1] / "custom_components" / "bosch_homecom"
    )
    for datei in (
        "strings.json",
        "translations/en.json",
        "translations/de.json",
        "translations/nl.json",
    ):
        daten = json.loads((component / datei).read_text(encoding="utf-8"))
        zustaende = daten["entity"]["sensor"]["notifications"].get("state", {})
        assert "none" in zustaende, f"{datei} does not translate the none state"
        assert zustaende["none"], f"{datei} translates none to an empty string"
