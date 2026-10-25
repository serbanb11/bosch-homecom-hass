"""Tests for the Matter/Bacon air purifier (bacon_ap) support (#203)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_TOKEN, CONF_USERNAME
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homecom_alt import ApiError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom import (
    _async_bacon_device_type,
    _async_remove_misfiled_ap_entities,
)
from custom_components.bosch_homecom.bacon import (
    bacon_air_quality_level,
    bacon_pm25_level,
    humanize_appliance_type,
)
from custom_components.bosch_homecom.binary_sensor import (
    BoschComBaconOnlineSensor,
    async_setup_entry as binary_sensor_async_setup_entry,
)
from custom_components.bosch_homecom.button import (
    BoschComBaconFilterResetButton,
    async_setup_entry as button_async_setup_entry,
)
from custom_components.bosch_homecom.climate import (
    async_setup_entry as climate_async_setup_entry,
)
from custom_components.bosch_homecom.const import (
    BACON_AP_TYPE,
    BACON_RAC_TYPE,
    CONF_BACON_TITLES,
    CONF_REFRESH,
    DOMAIN,
)
from custom_components.bosch_homecom.coordinator import (
    BoschComModuleCoordinatorBaconRac,
)
from custom_components.bosch_homecom.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.bosch_homecom.fan import (
    BoschComBaconApFan,
    async_setup_entry as fan_async_setup_entry,
)
from custom_components.bosch_homecom.number import (
    BoschComBaconTimerNumber,
    async_setup_entry as number_async_setup_entry,
)
from custom_components.bosch_homecom.sensor import (
    BACON_AP_SENSORS,
    BoschComBaconApSensor,
    BoschComBaconRoomTemperature,
    BoschComBaconSignalQuality,
    async_setup_entry as sensor_async_setup_entry,
)
from custom_components.bosch_homecom.switch import (
    BoschComBaconFeatureSwitch,
    async_setup_entry as switch_async_setup_entry,
)

SERIAL = "86DM-577-123456-7890123456"

# The Air 4000i shadow and topics, as captured in the #203 diagnostics.
AP_REPORTED = {
    "powerEnabled": True,
    "opMode": "auto",
    "childLockEnabled": False,
    "fanSpeed": 1,
    "onTimer": 0,
    "offTimer": 0,
    "lightEnabled": False,
    "filterReset": False,
    "displayEnabled": False,
    "dataLakeBasePublishInterval": 1800,
}
AP_SENSOR = {
    "timestamp": 1792278451,
    "airQuality": 1,
    "pm2.5": 1,
    "pm2_5": 1,
    "filterCapacity": 96,
}
AP_META = {
    "shadows": {
        "state": {
            "powerEnabled": {"type": "boolean", "ro": False},
            "opMode": {
                "type": "string",
                "enum": ["auto", "manual", "silent"],
                "ro": False,
            },
            "childLockEnabled": {"type": "boolean", "ro": False},
            "fanSpeed": {"type": "int", "min": 1, "max": 3, "step": 1, "ro": False},
            "onTimer": {
                "type": "int",
                "unit": "min",
                "min": 0,
                "max": 720,
                "step": 60,
                "ro": False,
            },
            "offTimer": {
                "type": "int",
                "unit": "min",
                "min": 0,
                "max": 720,
                "step": 60,
                "ro": False,
            },
            "lightEnabled": {"type": "boolean", "ro": False},
            "filterReset": {"type": "boolean", "ro": False},
            "displayEnabled": {"type": "boolean", "ro": False},
        }
    }
}
AP_INFO = {
    "online": True,
    "gateway": {"serialNumber": SERIAL, "hardwareVersion": "G10-3"},
    "network": {"mac": "aa:bb", "ssid": "home-wifi", "signalQuality": "excellent"},
    "matterOnboarding": {"commissioned": True, "fabrics": [{"vendorId": 4996}]},
    "appliance": {"type": "air_4000i", "serialNumber": "7733703376"},
}


def _coordinator(
    *,
    reported=None,
    metadata=None,
    sensor=None,
    info=None,
    device_type=BACON_AP_TYPE,
):
    """Build a mock bacon_ap coordinator exposing the shadow + topics channels."""
    coordinator = MagicMock()
    # The sensor platform type-checks the coordinator before building entities.
    coordinator.__class__ = BoschComModuleCoordinatorBaconRac
    coordinator.unique_id = SERIAL
    coordinator.device_info = {"identifiers": {(DOMAIN, SERIAL)}}
    coordinator.data = SimpleNamespace(
        device={"deviceId": SERIAL, "deviceType": device_type},
        firmware="unknown",
        reported=dict(AP_REPORTED) if reported is None else reported,
        desired={},
        sensor=dict(AP_SENSOR) if sensor is None else sensor,
        metadata=metadata,
        info=info,
    )
    coordinator.bhc = MagicMock()
    for name in (
        "async_set_power",
        "async_set_mode",
        "async_set_fan_speed",
        "async_set_timer",
        "async_set_feature",
        "async_reset_filter",
    ):
        setattr(coordinator.bhc, name, AsyncMock())
    coordinator.async_request_refresh = AsyncMock()
    coordinator.meta_stale = False
    return coordinator


async def _run_setup(hass, setup, coordinator):
    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]
    added: list = []
    await setup(hass, config_entry, added.extend)
    return added, config_entry


# --- helpers ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, "good"), (2, "ok"), (3, "poor"), (4, "bad"), (5, None), (0, None)],
)
def test_air_quality_level_matches_the_app(value, expected):
    """airQuality is the light ring: 1 good, 2 OK, 3 poor, 4 bad (AirQuality.java)."""
    assert bacon_air_quality_level(value) == expected


def test_air_quality_level_rejects_non_numbers():
    """Booleans and strings are not levels."""
    assert bacon_air_quality_level(True) is None
    assert bacon_air_quality_level("1") is None
    assert bacon_air_quality_level(None) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "good"), (12, "good"), (13, "ok"), (35, "ok"), (36, "poor"), (55, "poor")],
)
def test_pm25_level_uses_the_app_thresholds(value, expected):
    """PM2.5 is classified 0-12 / 13-35 / 36-55 / 56+ like AirQuality.ofPMValue."""
    assert bacon_pm25_level(value) == expected


def test_pm25_level_bad_and_invalid():
    """Anything above 55 is bad; non-numbers are unknown."""
    assert bacon_pm25_level(56) == "bad"
    assert bacon_pm25_level(250.5) == "bad"
    assert bacon_pm25_level(None) is None
    assert bacon_pm25_level(False) is None


@pytest.mark.parametrize(
    ("appliance_type", "expected"),
    [
        ("air_4000i", "Air 4000i"),
        ("air_4000i_v2", "Air 4000i v2"),
        ("Air 6000i", "Air 6000i"),
        ("", None),
        (None, None),
        ("_", None),
    ],
)
def test_humanize_appliance_type(appliance_type, expected):
    """The topics/info appliance type becomes a readable device name."""
    assert humanize_appliance_type(appliance_type) == expected


# --- fan ----------------------------------------------------------------------


def test_fan_presets_from_meta_or_default():
    """Operating modes come from the opMode enum in topics/meta, else the known set."""
    assert BoschComBaconApFan(_coordinator(metadata=None)).preset_modes == [
        "auto",
        "manual",
        "silent",
    ]
    meta = {"shadows": {"state": {"opMode": {"enum": ["auto", "manual"]}}}}
    assert BoschComBaconApFan(_coordinator(metadata=meta)).preset_modes == [
        "auto",
        "manual",
    ]


def test_fan_state_in_auto_hides_the_speed():
    """In auto the device picks its speed; the app shows "Auto", so no percentage."""
    fan = BoschComBaconApFan(_coordinator(metadata=AP_META))
    assert fan.is_on is True
    assert fan.preset_mode == "auto"
    assert fan.percentage is None
    assert fan.speed_count == 3
    # The raw speed stays visible as an attribute.
    assert fan.extra_state_attributes == {"fan_speed": 1}


def test_fan_state_in_manual_maps_speed_to_percentage():
    """In manual the 1..3 speed maps onto 33/66/100 %."""
    coordinator = _coordinator(
        reported={**AP_REPORTED, "opMode": "manual", "fanSpeed": 2},
        metadata=AP_META,
    )
    fan = BoschComBaconApFan(coordinator)
    assert fan.preset_mode == "manual"
    assert fan.percentage == 66
    coordinator.data.reported["fanSpeed"] = 3
    assert fan.percentage == 100


def test_fan_state_when_off():
    """Off: percentage 0, no preset; before any shadow: unknown."""
    fan = BoschComBaconApFan(
        _coordinator(reported={**AP_REPORTED, "powerEnabled": False})
    )
    assert fan.is_on is False
    assert fan.percentage == 0
    assert fan.preset_mode is None

    fan = BoschComBaconApFan(_coordinator(reported={}))
    assert fan.is_on is None
    assert fan.percentage is None
    assert fan.extra_state_attributes == {}


def test_fan_speed_range_from_meta():
    """A model with more speeds gets its range from topics/meta."""
    meta = {"shadows": {"state": {"fanSpeed": {"min": 1, "max": 5}}}}
    fan = BoschComBaconApFan(
        _coordinator(
            reported={**AP_REPORTED, "opMode": "manual", "fanSpeed": 5},
            metadata=meta,
        )
    )
    assert fan.speed_count == 5
    assert fan.percentage == 100


async def test_fan_set_percentage_writes_manual_and_speed():
    """Setting a speed selects manual too, as the app only offers speeds there."""
    coordinator = _coordinator(metadata=AP_META)
    fan = BoschComBaconApFan(coordinator)

    await fan.async_set_percentage(100)
    coordinator.bhc.async_set_fan_speed.assert_awaited_once_with(3, power_on=False)
    coordinator.async_request_refresh.assert_awaited_once()

    coordinator.bhc.async_set_fan_speed.reset_mock()
    await fan.async_set_percentage(34)
    coordinator.bhc.async_set_fan_speed.assert_awaited_once_with(2, power_on=False)

    coordinator.bhc.async_set_fan_speed.reset_mock()
    await fan.async_set_percentage(1)
    coordinator.bhc.async_set_fan_speed.assert_awaited_once_with(1, power_on=False)


async def test_fan_set_percentage_zero_turns_off_and_from_off_powers_on():
    """0 % is off; a speed on an off unit also sets powerEnabled."""
    coordinator = _coordinator(reported={**AP_REPORTED, "powerEnabled": False})
    fan = BoschComBaconApFan(coordinator)

    await fan.async_set_percentage(0)
    coordinator.bhc.async_set_power.assert_awaited_once_with(False)
    coordinator.bhc.async_set_fan_speed.assert_not_awaited()

    await fan.async_set_percentage(66)
    coordinator.bhc.async_set_fan_speed.assert_awaited_once_with(2, power_on=True)


async def test_fan_set_preset_mode_on_and_off():
    """A mode change on a running unit writes opMode; on an off unit, power too."""
    coordinator = _coordinator()
    fan = BoschComBaconApFan(coordinator)
    await fan.async_set_preset_mode("silent")
    coordinator.bhc.async_set_mode.assert_awaited_once_with("silent")
    coordinator.bhc.async_set_power.assert_not_awaited()

    coordinator = _coordinator(reported={**AP_REPORTED, "powerEnabled": False})
    fan = BoschComBaconApFan(coordinator)
    await fan.async_set_preset_mode("silent")
    coordinator.bhc.async_set_power.assert_awaited_once_with(True, "silent")
    coordinator.bhc.async_set_mode.assert_not_awaited()


async def test_fan_turn_on_variants_and_turn_off():
    """turn_on honours a preset, a percentage, or neither; turn_off cuts power."""
    coordinator = _coordinator(reported={**AP_REPORTED, "powerEnabled": False})
    fan = BoschComBaconApFan(coordinator)

    await fan.async_turn_on(preset_mode="auto")
    coordinator.bhc.async_set_power.assert_awaited_once_with(True, "auto")

    coordinator.bhc.async_set_power.reset_mock()
    await fan.async_turn_on(percentage=100)
    coordinator.bhc.async_set_fan_speed.assert_awaited_once_with(3, power_on=True)
    coordinator.bhc.async_set_power.assert_not_awaited()

    await fan.async_turn_on()
    coordinator.bhc.async_set_power.assert_awaited_once_with(True)

    coordinator.bhc.async_set_power.reset_mock()
    await fan.async_turn_off()
    coordinator.bhc.async_set_power.assert_awaited_once_with(False)
    assert coordinator.async_request_refresh.await_count == 4


async def test_fan_platform_creates_the_purifier_fan_only_for_bacon_ap(hass):
    """The fan platform adds a fan for a purifier and nothing for a bacon AC."""
    added, _ = await _run_setup(hass, fan_async_setup_entry, _coordinator())
    assert [type(e) for e in added] == [BoschComBaconApFan]
    assert added[0].unique_id == f"{SERIAL}-fan"

    added, _ = await _run_setup(
        hass, fan_async_setup_entry, _coordinator(device_type=BACON_RAC_TYPE)
    )
    assert added == []


# --- switches -----------------------------------------------------------------


async def test_switch_platform_creates_purifier_settings(hass):
    """Child lock, light ring and display become config switches with app names."""
    added, _ = await _run_setup(hass, switch_async_setup_entry, _coordinator())
    switches = {e._field: e for e in added if isinstance(e, BoschComBaconFeatureSwitch)}
    assert set(switches) == {"childLockEnabled", "lightEnabled", "displayEnabled"}
    assert switches["childLockEnabled"].unique_id == f"{SERIAL}-bacon_child_lock"
    assert switches["childLockEnabled"].translation_key == "bacon_child_lock"
    assert switches["lightEnabled"].unique_id == f"{SERIAL}-bacon_light"
    assert switches["displayEnabled"].unique_id == f"{SERIAL}-bacon_display"
    for switch in switches.values():
        assert switch.entity_category is EntityCategory.CONFIG
        assert switch.is_on is False


async def test_switch_platform_migrates_raw_field_unique_ids(hass):
    """Switches registered under the raw field name are renamed to the app key.

    Before purifiers were recognised their settings were unknown features and
    got ``{serial}-childLockEnabled`` ids with humanized names; the entity (and
    its history/customisations) is kept under the new id.
    """
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "switch", DOMAIN, f"{SERIAL}-childLockEnabled", suggested_object_id="lock"
    )
    # A target that already exists is never clobbered.
    registry.async_get_or_create("switch", DOMAIN, f"{SERIAL}-lightEnabled")
    registry.async_get_or_create("switch", DOMAIN, f"{SERIAL}-bacon_light")

    await _run_setup(hass, switch_async_setup_entry, _coordinator())

    assert (
        registry.async_get_entity_id("switch", DOMAIN, f"{SERIAL}-bacon_child_lock")
        == old.entity_id
    )
    assert (
        registry.async_get_entity_id("switch", DOMAIN, f"{SERIAL}-childLockEnabled")
        is None
    )
    assert registry.async_get_entity_id("switch", DOMAIN, f"{SERIAL}-lightEnabled")


async def test_rac_feature_switches_keep_their_category():
    """A RAC comfort feature is a primary control, not a config entity."""
    coordinator = _coordinator(
        reported={"powerEnabled": True, "ionizerEnabled": True},
        device_type=BACON_RAC_TYPE,
    )
    switch = BoschComBaconFeatureSwitch(coordinator=coordinator, field="ionizerEnabled")
    assert switch.entity_category is None
    assert switch.unique_id == f"{SERIAL}-bacon_ionizer"


# --- button -------------------------------------------------------------------


async def test_button_platform_adds_filter_reset_disabled_by_default(hass):
    """The filter reset is offered only when the field exists, and off by default."""
    added, _ = await _run_setup(hass, button_async_setup_entry, _coordinator())
    assert [type(e) for e in added] == [BoschComBaconFilterResetButton]
    button = added[0]
    assert button.unique_id == f"{SERIAL}-filter-reset"
    assert button.entity_registry_enabled_default is False
    assert button.entity_category is EntityCategory.CONFIG
    assert button.extra_state_attributes == {"filter_reset_reported": False}

    await button.async_press()
    button.coordinator.bhc.async_reset_filter.assert_awaited_once()
    button.coordinator.async_request_refresh.assert_awaited_once()


async def test_button_platform_skips_filter_reset_when_unsupported(hass):
    """A purifier whose shadow and meta lack filterReset gets no button."""
    reported = {k: v for k, v in AP_REPORTED.items() if k != "filterReset"}
    added, _ = await _run_setup(
        hass, button_async_setup_entry, _coordinator(reported=reported, metadata=None)
    )
    assert added == []

    # Known from meta alone (e.g. right after a reload with a partial shadow).
    added, _ = await _run_setup(
        hass,
        button_async_setup_entry,
        _coordinator(reported=reported, metadata=AP_META),
    )
    assert len(added) == 1


# --- numbers ------------------------------------------------------------------


async def test_number_platform_adds_both_timers(hass):
    """onTimer/offTimer become minute numbers bounded by topics/meta."""
    added, _ = await _run_setup(
        hass, number_async_setup_entry, _coordinator(metadata=AP_META)
    )
    timers = {e._field: e for e in added if isinstance(e, BoschComBaconTimerNumber)}
    assert set(timers) == {"onTimer", "offTimer"}
    on_timer = timers["onTimer"]
    assert on_timer.unique_id == f"{SERIAL}-on-timer"
    assert on_timer.translation_key == "bacon_on_timer"
    assert timers["offTimer"].unique_id == f"{SERIAL}-off-timer"
    assert (on_timer.native_min_value, on_timer.native_max_value) == (0, 720)
    assert on_timer.native_step == 60
    assert on_timer.native_value == 0
    assert on_timer.entity_category is EntityCategory.CONFIG


async def test_number_defaults_without_meta_and_writes_minutes():
    """Without meta the Air 4000i bounds apply; a write goes to the timer field."""
    coordinator = _coordinator(reported={**AP_REPORTED, "offTimer": 120}, metadata=None)
    number = BoschComBaconTimerNumber(coordinator=coordinator, field="offTimer")
    assert (number.native_min_value, number.native_max_value, number.native_step) == (
        0,
        720,
        60,
    )
    assert number.native_value == 120

    await number.async_set_native_value(180)
    coordinator.bhc.async_set_timer.assert_awaited_once_with("offTimer", 180)
    coordinator.async_request_refresh.assert_awaited_once()

    coordinator.data.reported["offTimer"] = None
    assert number.native_value is None


async def test_number_platform_skips_timers_the_shadow_lacks(hass):
    """Only timers the device reports are created."""
    reported = {k: v for k, v in AP_REPORTED.items() if k != "onTimer"}
    added, _ = await _run_setup(
        hass, number_async_setup_entry, _coordinator(reported=reported)
    )
    assert [e._field for e in added] == ["offTimer"]


# --- sensors ------------------------------------------------------------------


async def test_sensor_platform_creates_readings_present_in_topics_sensor(hass):
    """Air quality, PM2.5 and filter capacity are created; absent fields are not."""
    added, _ = await _run_setup(hass, sensor_async_setup_entry, _coordinator())
    by_type = {}
    for entity in added:
        by_type.setdefault(type(entity), []).append(entity)
    # Signal quality is shared with the AC; the AC-only room temperature is not.
    assert len(by_type[BoschComBaconSignalQuality]) == 1
    assert BoschComBaconRoomTemperature not in by_type
    readings = {e._description.field: e for e in by_type[BoschComBaconApSensor]}
    assert set(readings) == {"airQuality", "pm2_5", "filterCapacity"}

    air = readings["airQuality"]
    assert air.unique_id == f"{SERIAL}-air-quality"
    assert air.device_class is SensorDeviceClass.ENUM
    assert air.options == ["good", "ok", "poor", "bad"]
    assert air.native_value == "good"
    assert air.extra_state_attributes == {"measured_at": "2026-10-17T23:07:31+00:00"}

    pm = readings["pm2_5"]
    assert pm.unique_id == f"{SERIAL}-pm2-5"
    assert pm.device_class is SensorDeviceClass.PM25
    assert pm.native_value == 1
    assert pm.extra_state_attributes["level"] == "good"

    capacity = readings["filterCapacity"]
    assert capacity.native_value == 96
    assert capacity.native_unit_of_measurement == "%"


async def test_sensor_platform_adds_readings_that_appear_later(hass):
    """A field first published later (e.g. humidity on another model) is added once."""
    coordinator = _coordinator(sensor={"timestamp": 1, "airQuality": 2})
    added, config_entry = await _run_setup(hass, sensor_async_setup_entry, coordinator)
    fields = {
        e._description.field for e in added if isinstance(e, BoschComBaconApSensor)
    }
    assert fields == {"airQuality"}

    listener = coordinator.async_add_listener.call_args.args[0]
    config_entry.async_on_unload.assert_called_with(
        coordinator.async_add_listener.return_value
    )
    coordinator.data.sensor = {
        "timestamp": 2,
        "airQuality": 3,
        "relHumidity": 48,
        "roomTemperature": 21.5,
    }
    listener()
    listener()
    new = [e for e in added if isinstance(e, BoschComBaconApSensor)]
    assert sorted(e._description.field for e in new) == [
        "airQuality",
        "relHumidity",
        "roomTemperature",
    ]
    humidity = next(e for e in new if e._description.field == "relHumidity")
    assert humidity.native_value == 48
    assert humidity.device_class is SensorDeviceClass.HUMIDITY


def test_ap_sensor_values_are_none_when_unknown():
    """Unknown air quality levels and non-numeric readings read as unknown."""
    coordinator = _coordinator(
        sensor={"airQuality": 9, "pm2_5": "n/a", "filterCapacity": True}
    )
    added = {}
    for description in BACON_AP_SENSORS[:3]:
        added[description.field] = BoschComBaconApSensor(
            coordinator=coordinator, config_entry=MagicMock(), description=description
        )
    assert added["airQuality"].native_value is None
    assert added["pm2_5"].native_value is None
    assert added["pm2_5"].extra_state_attributes == {}
    assert added["filterCapacity"].native_value is None

    coordinator.data.sensor = None
    assert added["airQuality"].native_value is None


# --- binary sensor / climate ---------------------------------------------------


async def test_binary_sensor_and_climate_platforms_for_a_purifier(hass):
    """A purifier gets the connectivity sensor but never a climate entity."""
    added, _ = await _run_setup(
        hass, binary_sensor_async_setup_entry, _coordinator(info=AP_INFO)
    )
    assert [type(e) for e in added] == [BoschComBaconOnlineSensor]
    assert added[0].is_on is True

    added, _ = await _run_setup(hass, climate_async_setup_entry, _coordinator())
    assert added == []


# --- setup: classification and cleanup -----------------------------------------


async def test_bacon_device_type_uses_the_library_and_falls_back_to_rac():
    """Classification is delegated; a failure keeps the pre-purifier type."""
    client = MagicMock()
    with patch(
        "custom_components.bosch_homecom.async_classify_bacon_device",
        AsyncMock(return_value=BACON_AP_TYPE),
    ) as classify:
        assert await _async_bacon_device_type(client, SERIAL) == BACON_AP_TYPE
    classify.assert_awaited_once_with(client, SERIAL)

    with patch(
        "custom_components.bosch_homecom.async_classify_bacon_device",
        AsyncMock(side_effect=ApiError("no answer")),
    ):
        assert await _async_bacon_device_type(client, SERIAL) == BACON_RAC_TYPE


async def test_remove_misfiled_ap_entities(hass):
    """The AC entities a purifier was given earlier are dropped, others kept."""
    registry = er.async_get(hass)
    registry.async_get_or_create("climate", DOMAIN, f"{SERIAL}-climate")
    registry.async_get_or_create("sensor", DOMAIN, f"{SERIAL}-room-temperature")
    registry.async_get_or_create("sensor", DOMAIN, f"{SERIAL}-signal-quality")
    registry.async_get_or_create("climate", DOMAIN, "86DM-OTHER-climate")

    _async_remove_misfiled_ap_entities(registry, _coordinator())

    assert registry.async_get_entity_id("climate", DOMAIN, f"{SERIAL}-climate") is None
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}-room-temperature")
        is None
    )
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}-signal-quality")
    assert registry.async_get_entity_id("climate", DOMAIN, "86DM-OTHER-climate")


async def test_remove_misfiled_ap_entities_keeps_a_reported_room_temperature(hass):
    """A purifier model that reports roomTemperature keeps that sensor."""
    registry = er.async_get(hass)
    registry.async_get_or_create("sensor", DOMAIN, f"{SERIAL}-room-temperature")

    _async_remove_misfiled_ap_entities(
        registry, _coordinator(sensor={**AP_SENSOR, "roomTemperature": 22})
    )

    assert registry.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}-room-temperature")


# --- diagnostics ----------------------------------------------------------------


async def test_diagnostics_redact_the_purifier_device_block(hass):
    """Serials, network identity and Matter data are redacted per device too (#203).

    The raw capture was already redacted; the per-device block was not, and the
    reporter had to hand-edit the dump before posting it.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test-user",
        data={
            CONF_USERNAME: "test-user",
            CONF_TOKEN: "access_token",
            CONF_REFRESH: "refresh",
            "devices": {f"{SERIAL}_bacon_rac": True, "123456789_rac": True},
            f"{SERIAL}_bacon_rac": True,
            CONF_BACON_TITLES: {SERIAL: "Living room"},
        },
    )
    entry.add_to_hass(hass)
    coordinator = _coordinator(info=AP_INFO, metadata=AP_META)
    coordinator.client.raw_snapshot.return_value = {
        "-/devices": {
            "payload": [{"userId": "48819aaa", "serialNumber": SERIAL}],
            "received_at": "2026-10-24T17:58:30+00:00",
        },
        f"{SERIAL}/topics/info": {"payload": AP_INFO, "received_at": "x"},
    }
    entry.runtime_data = [coordinator]

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    device = diagnostics["data"][0]
    assert device["devices"] == {"deviceId": "86DM***", "deviceType": BACON_AP_TYPE}
    assert device["info"]["gateway"]["serialNumber"] == "**REDACTED**"
    assert device["info"]["appliance"]["serialNumber"] == "**REDACTED**"
    assert device["info"]["appliance"]["type"] == "air_4000i"
    assert device["info"]["network"]["mac"] == "**REDACTED**"
    assert device["info"]["network"]["ssid"] == "**REDACTED**"
    assert device["info"]["network"]["signalQuality"] == "excellent"
    assert device["info"]["matterOnboarding"] == "**REDACTED**"
    # The state itself is what a report needs, so it stays readable.
    assert device["reported"]["opMode"] == "auto"
    assert device["sensor"]["filterCapacity"] == 96
    assert device["metadata"]["shadows"]["state"]["fanSpeed"]["max"] == 3

    info = diagnostics["info"]
    assert info["devices"] == {"86DM***_bacon_rac": True, "1234***_rac": True}
    assert info["86DM***_bacon_rac"] is True
    assert f"{SERIAL}_bacon_rac" not in info
    assert info[CONF_BACON_TITLES] == {"86DM***": "Living room"}

    raw = diagnostics["bacon_raw"]
    assert raw["-/devices"]["payload"][0] == {
        "userId": "**REDACTED**",
        "serialNumber": "**REDACTED**",
    }
    assert "86DM***/topics/info" in raw
