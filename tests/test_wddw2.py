"""Tests for wddw2 (Tronic TR4001) switches, water heater and notifications."""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.components.water_heater import WaterHeaterEntityFeature
from homeassistant.helpers import entity_registry as er
from homecom_alt import ApiError, BHCDeviceWddw2
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom.const import (
    BOSCH_SENSOR_DESCRIPTORS,
    CONF_DEVICES,
    DOMAIN,
)
from custom_components.bosch_homecom.coordinator import (
    WDDW2_WATER_TODAY_KEY,
    BoschComModuleCoordinatorWddw2,
)
from custom_components.bosch_homecom.sensor import (
    BoschComHeatingActiveBinarySensor,
    BoschComSensorNotificationsWddw2,
    BoschComWddw2HealthStatusSensor,
    BoschComWddw2HeatingActivePowerSensor,
    BoschComWddw2WaterTodaySensor,
    _build_wddw2_descriptor_sensor,
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
    coord.recordings = {}
    coord.health_status = None
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


# Tronic presets as a Tronic 7000 control panel reports them with the safety
# temperature off: camelCase API values, dishWash only offered above 42 °C.
_DHW_PRESETS = [
    {
        "id": "/dhwCircuits/dhw1",
        "operationMode": {
            "value": "handWash",
            "writeable": 1,
            "allowedValues": ["manual", "handWash", "shower", "bath", "dishWash"],
        },
        "outletTemperature": {"value": 35.0, "unitOfMeasure": "C"},
        "tempLevel": {
            "manual": {"value": 34, "writeable": 1, "minValue": 20, "maxValue": 60},
            "handWash": {"value": 35},
            "dishWash": {"value": 48},
        },
        "safetyTemperature": {"value": "off"},
    }
]


def test_water_heater_presets_use_state_keys():
    coord = _coordinator(dhw_circuits=_DHW_PRESETS)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert entity.operation_list == [
        "manual",
        "hand_wash",
        "shower",
        "bath",
        "dish_wash",
    ]
    assert entity.current_operation == "hand_wash"
    assert entity.target_temperature == 35


async def test_water_heater_set_preset_writes_api_value():
    coord = _coordinator(dhw_circuits=_DHW_PRESETS)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    await entity.async_set_operation_mode("dish_wash")

    coord.bhc.async_put_dhw_operation_mode.assert_called_once_with(
        "102051881", "dhw1", "dishWash"
    )


async def test_water_heater_manual_reapplies_last_manual_setpoint():
    circuits = [
        dict(
            _DHW_PRESETS[0],
            operationMode=dict(_DHW_PRESETS[0]["operationMode"], value="manual"),
        )
    ]
    coord = _coordinator(dhw_circuits=circuits)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    # The device switches to a preset; the remembered manual setpoint stays.
    coord.data = _make_data(_DHW_PRESETS)
    entity.set_attr()
    await entity.async_set_operation_mode("manual")

    coord.bhc.async_put_dhw_operation_mode.assert_called_once_with(
        "102051881", "dhw1", "manual"
    )
    coord.bhc.async_set_dhw_temp_level.assert_called_once_with(
        "102051881", "dhw1", "manual", 34
    )


async def test_water_heater_manual_without_known_setpoint_writes_mode_only():
    coord = _coordinator(dhw_circuits=_DHW_PRESETS)
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    await entity.async_set_operation_mode("manual")

    coord.bhc.async_put_dhw_operation_mode.assert_called_once()
    coord.bhc.async_set_dhw_temp_level.assert_not_called()


def test_operation_mode_sensor_reports_state_key():
    desc = next(
        d for d in BOSCH_SENSOR_DESCRIPTORS["wddw2"] if d["key"] == "operation_mode"
    )
    coord = _coordinator(dhw_circuits=_DHW_PRESETS)
    sensor = _build_wddw2_descriptor_sensor(coord, desc, "dhw1", desc["path"])

    assert sensor.native_value == "hand_wash"


def test_translations_cover_every_preset():
    path = "custom_components/bosch_homecom/translations/{}.json"
    for lang in ("en", "de", "nl"):
        with open(path.format(lang), encoding="utf-8") as fh:
            entity = json.load(fh)["entity"]
        for states in (
            entity["water_heater"]["dhw_wddw2"]["state"],
            entity["sensor"]["dhw_operation_mode"]["state"],
        ):
            for key in ("manual", "hand_wash", "shower", "bath", "dish_wash"):
                assert key in states, (lang, key)


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
        "fanSpeed": {"value": 0},
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
        # The property, not _attr_translation_key: an entity may take its key
        # from its entity_description instead.
        or entity.translation_key is None
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


# ---------------------------------------------------------------------------
# A cloud hiccup at setup must not drop a sensor for good
# ---------------------------------------------------------------------------


async def _setup_recording(hass, coord):
    """Run sensor setup; return the added entities and the late listener.

    Setup and the listener share one async_add_entities, so whatever the
    listener adds later lands in the same list.
    """
    config_entry = Mock()
    config_entry.runtime_data = [coord]
    entities = []
    await sensor_async_setup_entry(hass, config_entry, entities.extend)
    listener = (
        coord.async_add_listener.call_args.args[0]
        if coord.async_add_listener.called
        else None
    )
    return entities, listener


def _ids(entities):
    return [e._attr_unique_id for e in entities if e._attr_unique_id]


async def test_descriptor_sensor_missing_at_setup_is_added_later(hass):
    """A field lost to a 502/504 at setup gets its sensor once it shows up.

    homecom_alt returns the same empty value for a 504 as for a 404, so setup
    cannot tell a transient cloud failure from a device that lacks the field.
    Skipping for good would drop a sensor the device does have until the next
    reload, and strand its registry entry as no longer provided.
    """
    coord = _coordinator(dhw_circuits=[_dhw1_circuit(inletTemperature=None)])
    entities, listener = await _setup_recording(hass, coord)
    assert "102051881-dhw1-inlet_temperature" not in _ids(entities)

    coord.data = _make_data(dhw_circuits=[_dhw1_circuit()])
    listener()

    assert _ids(entities).count("102051881-dhw1-inlet_temperature") == 1
    # Once added it is no longer pending: a further update adds nothing.
    count = len(entities)
    listener()
    assert len(entities) == count


async def test_field_the_device_lacks_stays_absent_across_updates(hass):
    """A field that never shows up never gets a sensor (TR4001 air box)."""
    coord = _coordinator(dhw_circuits=[_dhw1_circuit(airBoxTemperature=None)])
    entities, listener = await _setup_recording(hass, coord)
    count = len(entities)

    for _ in range(3):
        listener()

    assert len(entities) == count
    assert "102051881-dhw1-air_box_temperature" not in _ids(entities)


async def test_totals_sensor_missing_at_setup_is_added_later(hass):
    """The issue #129 totals follow the same rule as the descriptors."""
    full_hs = {
        key: {"value": 1}
        for key in (
            "actualPower",
            "powerPercentage",
            "operationHours",
            "electricityTotalConsumption",
        )
    }
    coord = _coordinator(dhw_circuits=[_dhw1_circuit()])
    # The 504 shape: every heat-source endpoint came back empty.
    coord.data = replace(
        coord.data,
        heat_sources=dict.fromkeys(full_hs, {}),
        water_total_consumption={"value": 1102},
    )
    entities, listener = await _setup_recording(hass, coord)
    assert "102051881-water-total-consumption" in _ids(entities)
    assert "102051881-hs-actual-power" not in _ids(entities)

    coord.data = replace(coord.data, heat_sources=full_hs)
    listener()

    for suffix in (
        "hs-actual-power",
        "hs-power-percentage",
        "hs-operation-hours",
        "electricity-total-consumption",
    ):
        assert _ids(entities).count(f"102051881-{suffix}") == 1


async def test_no_listener_when_every_sensor_is_present(hass):
    """A device reporting everything at setup registers no late listener."""
    coord = _coordinator(dhw_circuits=[_dhw1_circuit()])
    coord.recordings = {WDDW2_WATER_TODAY_KEY: 94.5}
    coord.health_status = {"value": "no_error"}
    coord.data = replace(
        coord.data,
        heat_sources={
            key: {"value": 1}
            for key in (
                "actualPower",
                "powerPercentage",
                "operationHours",
                "electricityTotalConsumption",
            )
        },
        water_total_consumption={"value": 1102},
    )
    _, listener = await _setup_recording(hass, coord)
    assert listener is None


# ---------------------------------------------------------------------------
# Recorded payloads: one Tronic, TR4001 panel vs. TR7001 panel
# ---------------------------------------------------------------------------

_TRONIC = json.loads(
    (Path(__file__).parent / "fixtures" / "wddw2_tronic.json").read_text("utf-8")
)


def test_tronic_tr4001_panel_stays_read_only():
    coord = _coordinator(dhw_circuits=_TRONIC["tr4001"])
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert entity.supported_features == WaterHeaterEntityFeature(0)
    assert entity.operation_list is None
    assert entity.current_operation == "bath"
    assert entity.target_temperature == 42


def test_tronic_tr7001_panel_with_safety_temperature():
    coord = _coordinator(dhw_circuits=_TRONIC["tr7001_safety_on"])
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert WaterHeaterEntityFeature.OPERATION_MODE in entity.supported_features
    assert WaterHeaterEntityFeature.TARGET_TEMPERATURE in entity.supported_features
    assert entity.operation_list == ["manual", "hand_wash", "shower", "bath"]
    assert (entity.min_temp, entity.max_temp) == (20, 42)


def test_tronic_tr7001_panel_without_safety_temperature():
    coord = _coordinator(dhw_circuits=_TRONIC["tr7001_safety_off"])
    entity = BoschComWddw2WaterHeater(coordinator=coord, field="dhw1")

    assert entity.operation_list == [
        "manual",
        "hand_wash",
        "shower",
        "bath",
        "dish_wash",
    ]
    assert (entity.min_temp, entity.max_temp) == (20, 60)
    assert entity.current_operation == "manual"
    assert entity.target_temperature == 41


# ---------------------------------------------------------------------------
# Optional sensors (#220): today's water, health status, power while heating
# ---------------------------------------------------------------------------

_HEALTH_PATH = "/system/healthStatus"
_WATER_PATH = "/recordings/dhwCircuits/dhw1/sensor/water?interval={day}"
_OPTIONAL_IDS = (
    "102051881-dhw-water-today",
    "102051881-system-health-status",
    "102051881-heating-active-power",
)


def _bulk_answers(day, water=None, health="no_error"):
    """Answer each bulk request by its path, as the cloud does."""
    answers = {}
    if health is not None:
        answers[_HEALTH_PATH] = {"id": _HEALTH_PATH, "value": health}
    if water is not None:
        answers[_WATER_PATH.format(day=day)] = {"recording": water}

    async def _bulk(_device_id, paths):
        return {path: answers[path] for path in paths if path in answers}

    return AsyncMock(side_effect=_bulk)


def _real_coordinator(hass, bulk):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        unique_id="test-user",
        data={CONF_DEVICES: {"102051881_wddw2": True}},
    )
    entry.add_to_hass(hass)
    bhc = Mock()
    bhc.async_update = AsyncMock(
        return_value=_make_data(dhw_circuits=[{"id": "/dhwCircuits/dhw1"}])
    )
    bhc.async_request_bulk = bulk
    return BoschComModuleCoordinatorWddw2(
        hass,
        bhc,
        {"deviceId": "102051881", "deviceType": "wddw2"},
        {"value": "1.0"},
        entry,
        auth_provider=False,
    )


def _today():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")


async def test_recordings_fetch_fills_water_today_and_health(hass):
    """One update reads both optional resources; the next one is rate-limited."""
    bulk = _bulk_answers(_today(), water=[{"y": 40, "c": 1}, {"y": 54.5, "c": 1}])
    coord = _real_coordinator(hass, bulk)

    await coord._async_update_data()

    assert coord.recordings == {WDDW2_WATER_TODAY_KEY: 94.5}
    assert coord.health_status["value"] == "no_error"
    assert bulk.await_count == 2

    await coord._async_update_data()
    assert bulk.await_count == 2, "re-read within the poll interval"


async def test_recordings_fetch_failure_keeps_last_values_and_retries(hass):
    """A transport error keeps the last values and does not arm the rate limit."""
    coord = _real_coordinator(hass, _bulk_answers(_today(), water=[{"y": 12, "c": 1}]))
    await coord._async_update_data()
    coord._last_recordings_fetch = None

    coord.bhc.async_request_bulk = AsyncMock(side_effect=ApiError("504"))
    await coord._async_update_data()

    assert coord.recordings == {WDDW2_WATER_TODAY_KEY: 12.0}
    assert coord.health_status["value"] == "no_error"
    assert coord._last_recordings_fetch is None


async def test_unsupported_recordings_leave_the_caches_empty(hass):
    """A device without these resources never fills the caches."""
    coord = _real_coordinator(hass, AsyncMock(return_value={}))

    await coord._async_update_data()

    assert coord.recordings == {}
    assert coord.health_status is None


async def test_water_today_is_dropped_on_a_new_day(hass):
    """Yesterday's litres must not show as today's before today's first read."""
    day1 = datetime(2026, 10, 30, 23, 50, tzinfo=timezone.utc)
    day2 = datetime(2026, 10, 31, 0, 5, tzinfo=timezone.utc)
    coord = _real_coordinator(
        hass, _bulk_answers("2026-10-30", water=[{"y": 94.5, "c": 1}])
    )
    with patch(
        "custom_components.bosch_homecom.coordinator.dt_util.now", return_value=day1
    ):
        await coord._async_update_data()
    assert coord.recordings[WDDW2_WATER_TODAY_KEY] == 94.5

    # Midnight: the new day's recording has no buckets yet.
    coord.bhc.async_request_bulk = _bulk_answers("2026-10-31", water=[])
    with patch(
        "custom_components.bosch_homecom.coordinator.dt_util.now", return_value=day2
    ):
        await coord._async_update_data()

    assert WDDW2_WATER_TODAY_KEY not in coord.recordings
    assert coord.bhc.async_request_bulk.await_count == 2, "read despite rate limit"


async def test_optional_sensors_wait_for_their_data(hass):
    """Nothing at setup, all three once the coordinator serves their data."""
    coord = _coordinator(dhw_circuits=[_dhw1_circuit()])
    coord.data = replace(coord.data, heat_sources={"powerPercentage": {}})
    entities, listener = await _setup_recording(hass, coord)
    assert not set(_OPTIONAL_IDS) & set(_ids(entities))

    coord.recordings[WDDW2_WATER_TODAY_KEY] = 94.5
    coord.health_status = {"value": "no_error"}
    coord.data = replace(coord.data, heat_sources={"powerPercentage": {"value": 35}})
    listener()

    for unique_id in _OPTIONAL_IDS:
        assert _ids(entities).count(unique_id) == 1
    count = len(entities)
    listener()
    assert len(entities) == count


async def test_power_sensor_absent_on_a_device_without_power_percentage(hass):
    """A Tronic gas heater reports no power percentage and gets no sensor."""
    coord = _coordinator(dhw_circuits=[_dhw1_circuit()])
    coord.recordings[WDDW2_WATER_TODAY_KEY] = 10.0
    coord.health_status = {"value": "no_error"}
    entities, listener = await _setup_recording(hass, coord)

    for _ in range(3):
        listener()

    ids = _ids(entities)
    assert "102051881-dhw-water-today" in ids
    assert "102051881-system-health-status" in ids
    assert "102051881-heating-active-power" not in ids


def test_water_today_and_health_sensors_read_the_caches():
    coord = _coordinator(dhw_circuits=[_dhw1_circuit()])
    water = BoschComWddw2WaterTodaySensor(coord)
    health = BoschComWddw2HealthStatusSensor(coord)
    assert water.native_value is None
    assert health.native_value is None

    coord.recordings[WDDW2_WATER_TODAY_KEY] = 94.5
    coord.health_status = {"value": "no_error"}
    assert water.native_value == 94.5
    assert water.unique_id == "102051881-dhw-water-today"
    assert health.native_value == "no_error"
    assert health.unique_id == "102051881-system-health-status"


def test_power_sensor_follows_the_heating_heuristic():
    """Power only while water flows and warms by 3 K, as the binary sensor."""
    heating = _dhw1_circuit(
        waterFlow={"value": 6},
        inletTemperature={"value": 12},
        outletTemperature={"value": 48},
    )
    coord = _coordinator(dhw_circuits=[heating])
    coord.data = replace(coord.data, heat_sources={"powerPercentage": {"value": 35}})
    power = BoschComWddw2HeatingActivePowerSensor(coord)
    active = BoschComHeatingActiveBinarySensor(
        coord, unique_suffix="dhw1-heating_active"
    )
    assert active.is_on is True
    assert power.native_value == 35.0

    for idle in (
        _dhw1_circuit(waterFlow={"value": 0}),
        _dhw1_circuit(inletTemperature={"value": 46}, outletTemperature={"value": 48}),
        _dhw1_circuit(waterFlow=None),
    ):
        coord.data = replace(coord.data, dhw_circuits=[idle])
        assert active.is_on is False
        assert power.native_value is None

    coord.data = replace(
        coord.data,
        dhw_circuits=[heating],
        heat_sources={"powerPercentage": {"value": 0}},
    )
    assert power.native_value is None
    coord.data = replace(coord.data, heat_sources={"powerPercentage": {"value": "n/a"}})
    assert power.native_value is None
