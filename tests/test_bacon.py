"""Tests for the Matter/Bacon (bacon_rac) entities: climate, binary_sensor, sensor."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.climate import ClimateEntityFeature
import pytest

from custom_components.bosch_homecom.binary_sensor import (
    BoschComBaconFeatureSensor,
    BoschComBaconOnlineSensor,
)
from custom_components.bosch_homecom.climate import (
    BoschComBaconRacClimate,
    _bacon_meta_state,
    _clean_bacon_title,
)
from custom_components.bosch_homecom.sensor import (
    BoschComBaconRoomTemperature,
    BoschComBaconSignalStrength,
)

# A topics/sensor payload's last item, as flattened by homecom_alt's get_sensor.
SAMPLE_SENSOR = {"timestamp": 1785960137, "roomTemperature": 23.5}
# A topics/meta state block: tempSetpoint bounds + fanSpeed enum + a writable flag.
SAMPLE_META = {
    "shadows": {
        "state": {
            "tempSetpoint": {
                "type": "int",
                "min": 18,
                "max": 28,
                "step": 1,
                "ro": False,
            },
            "fanSpeed": {
                "type": "string",
                "enum": ["auto", "low", "high"],
                "ro": False,
            },
            "ionizerEnabled": {"type": "bool", "ro": False},
            "sleepEnabled": {"type": "bool", "ro": True},
        }
    }
}
SAMPLE_INFO = {
    "online": True,
    "network": {"signalStrength": -55, "signalQuality": "good"},
}
SAMPLE_REPORTED = {
    "powerEnabled": True,
    "opMode": "cool",
    "tempSetpoint": 23,
    "fanSpeed": "auto",
    "vSwingEnabled": True,
    "hSwingEnabled": False,
    "ionizerEnabled": True,
    "sleepEnabled": False,
    "customTitle": "Living Room%|$?*junk",
}


def _coordinator(
    *, reported=None, metadata=None, sensor=None, info=None, data_none=False
):
    """Build a mock bacon coordinator exposing the shadow + topics channels."""
    data = None
    if not data_none:
        data = SimpleNamespace(
            device={"deviceId": "86DM-1", "deviceType": "bacon_rac"},
            firmware="1.0.0",
            reported=reported if reported is not None else dict(SAMPLE_REPORTED),
            desired={},
            sensor=sensor,
            metadata=metadata,
            info=info,
        )
    coordinator = MagicMock()
    coordinator.unique_id = "86DM-1"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "86DM-1")}}
    coordinator.data = data
    coordinator.bhc = MagicMock()
    coordinator.bhc.async_set_swing = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


# --- module helpers -----------------------------------------------------------


def test_clean_bacon_title_strips_suffix():
    """The %| suffix Bosch appends to customTitle is stripped."""
    assert _clean_bacon_title("Living Room%|$?*junk") == "Living Room"
    assert _clean_bacon_title("Kitchen") == "Kitchen"
    assert _clean_bacon_title(None) is None
    assert _clean_bacon_title("%|only") is None


def test_bacon_meta_state_navigates_and_defaults():
    """_bacon_meta_state returns shadows.state, or {} when missing/malformed."""
    assert _bacon_meta_state(SAMPLE_META) == SAMPLE_META["shadows"]["state"]
    assert _bacon_meta_state(None) == {}
    assert _bacon_meta_state({}) == {}
    assert _bacon_meta_state({"shadows": {}}) == {}
    assert _bacon_meta_state({"shadows": {"state": "notadict"}}) == {}


# --- climate ------------------------------------------------------------------


def test_climate_supported_features_full_without_meta():
    """With no topics/meta yet, all controls are advertised (unchanged behavior)."""
    climate = BoschComBaconRacClimate(coordinator=_coordinator(metadata=None))
    features = climate.supported_features
    assert ClimateEntityFeature.TARGET_TEMPERATURE in features
    assert ClimateEntityFeature.FAN_MODE in features
    assert ClimateEntityFeature.SWING_MODE in features
    assert ClimateEntityFeature.SWING_HORIZONTAL_MODE in features


def test_climate_supported_features_gated_by_meta():
    """A meta block that omits fanSpeed drops FAN_MODE but keeps TARGET_TEMPERATURE."""
    meta = {"shadows": {"state": {"tempSetpoint": {"min": 16, "max": 30, "step": 1}}}}
    climate = BoschComBaconRacClimate(coordinator=_coordinator(metadata=meta))
    features = climate.supported_features
    assert ClimateEntityFeature.TARGET_TEMPERATURE in features
    assert ClimateEntityFeature.FAN_MODE not in features


def test_climate_bounds_and_fan_modes_from_meta():
    """Setpoint bounds/step and fan modes come from the device's meta when present."""
    climate = BoschComBaconRacClimate(coordinator=_coordinator(metadata=SAMPLE_META))
    assert climate.min_temp == 18
    assert climate.max_temp == 28
    assert climate.target_temperature_step == 1
    assert climate.fan_modes == ["auto", "low", "high"]


def test_climate_bounds_and_fan_modes_defaults():
    """Without meta the hardcoded defaults are used."""
    climate = BoschComBaconRacClimate(coordinator=_coordinator(metadata=None))
    assert climate.min_temp == 16
    assert climate.max_temp == 30
    assert climate.target_temperature_step == 1.0
    assert "turbo" in climate.fan_modes


def test_climate_swing_features_gated_by_meta():
    """Swing axes are advertised only when the device declares them (#3)."""
    no_swing = {"shadows": {"state": {"tempSetpoint": {"min": 16, "max": 30}}}}
    features = BoschComBaconRacClimate(
        coordinator=_coordinator(metadata=no_swing)
    ).supported_features
    assert ClimateEntityFeature.SWING_MODE not in features
    assert ClimateEntityFeature.SWING_HORIZONTAL_MODE not in features

    both = {
        "shadows": {
            "state": {
                "vSwingEnabled": {"type": "bool", "ro": False},
                "hSwingEnabled": {"type": "bool", "ro": False},
            }
        }
    }
    features = BoschComBaconRacClimate(
        coordinator=_coordinator(metadata=both)
    ).supported_features
    assert ClimateEntityFeature.SWING_MODE in features
    assert ClimateEntityFeature.SWING_HORIZONTAL_MODE in features


def test_climate_setpoint_bound_respects_zero():
    """A declared min of 0 is honored, not silently replaced by the default (#4)."""
    meta = {"shadows": {"state": {"tempSetpoint": {"min": 0}}}}
    climate = BoschComBaconRacClimate(coordinator=_coordinator(metadata=meta))
    assert climate.min_temp == 0
    # Bounds the device does not declare still fall back to the defaults.
    assert climate.max_temp == 30
    assert climate.target_temperature_step == 1.0


def test_climate_swing_axes_are_independent():
    """vSwing maps to swing_mode, hSwing to swing_horizontal_mode."""
    climate = BoschComBaconRacClimate(
        coordinator=_coordinator(
            reported={"vSwingEnabled": True, "hSwingEnabled": False}
        )
    )
    assert climate.swing_mode == "on"
    assert climate.swing_horizontal_mode == "off"


async def test_climate_set_swing_only_touches_vertical():
    """async_set_swing_mode drives the vertical louver alone."""
    coordinator = _coordinator()
    climate = BoschComBaconRacClimate(coordinator=coordinator)
    await climate.async_set_swing_mode("on")
    coordinator.bhc.async_set_swing.assert_awaited_once_with(vertical=True)
    coordinator.async_request_refresh.assert_awaited_once()


async def test_climate_set_swing_horizontal_only_touches_horizontal():
    """async_set_swing_horizontal_mode drives the horizontal louver alone."""
    coordinator = _coordinator()
    climate = BoschComBaconRacClimate(coordinator=coordinator)
    await climate.async_set_swing_horizontal_mode("off")
    coordinator.bhc.async_set_swing.assert_awaited_once_with(horizontal=False)
    coordinator.async_request_refresh.assert_awaited_once()


# --- binary_sensor ------------------------------------------------------------


def test_feature_sensor_is_on_from_reported():
    """A comfort-feature sensor reflects its reported boolean."""
    coordinator = _coordinator(reported={"ionizerEnabled": True})
    sensor = BoschComBaconFeatureSensor(
        coordinator=coordinator, field="ionizerEnabled", translation_key="bacon_ionizer"
    )
    assert sensor.is_on is True
    assert sensor.unique_id == "86DM-1-bacon_ionizer"


def test_feature_sensor_none_when_absent_or_not_bool():
    """Missing or non-boolean values yield None (unknown), never a guess."""
    assert (
        BoschComBaconFeatureSensor(
            coordinator=_coordinator(reported={}),
            field="ionizerEnabled",
            translation_key="bacon_ionizer",
        ).is_on
        is None
    )
    assert (
        BoschComBaconFeatureSensor(
            coordinator=_coordinator(reported={"ionizerEnabled": "yes"}),
            field="ionizerEnabled",
            translation_key="bacon_ionizer",
        ).is_on
        is None
    )


def test_feature_sensor_writable_now_attribute():
    """writable_now mirrors the meta ro flag, and is absent when meta is silent."""
    writable = BoschComBaconFeatureSensor(
        coordinator=_coordinator(metadata=SAMPLE_META),
        field="ionizerEnabled",
        translation_key="bacon_ionizer",
    )
    assert writable.extra_state_attributes == {"writable_now": True}

    locked = BoschComBaconFeatureSensor(
        coordinator=_coordinator(metadata=SAMPLE_META),
        field="sleepEnabled",
        translation_key="bacon_sleep",
    )
    assert locked.extra_state_attributes == {"writable_now": False}

    no_meta = BoschComBaconFeatureSensor(
        coordinator=_coordinator(metadata=None),
        field="ionizerEnabled",
        translation_key="bacon_ionizer",
    )
    assert no_meta.extra_state_attributes == {}


def test_online_sensor_from_info():
    """The online binary sensor reflects info.online and exposes signal quality."""
    sensor = BoschComBaconOnlineSensor(coordinator=_coordinator(info=SAMPLE_INFO))
    assert sensor.is_on is True
    assert sensor.extra_state_attributes == {"signal_quality": "good"}


def test_online_sensor_none_before_info():
    """Before topics/info arrives the sensor is unknown with no attributes."""
    sensor = BoschComBaconOnlineSensor(coordinator=_coordinator(info=None))
    assert sensor.is_on is None
    assert sensor.extra_state_attributes == {}


# --- sensor -------------------------------------------------------------------


def test_room_temperature_value_and_measured_at():
    """Room temperature reports the reading and its timestamp as ISO (seconds)."""
    sensor = BoschComBaconRoomTemperature(
        coordinator=_coordinator(sensor=SAMPLE_SENSOR), config_entry=None
    )
    assert sensor.native_value == 23.5
    measured_at = sensor.extra_state_attributes["measured_at"]
    # 1785960137 is a Unix time in *seconds* -> 2026, not 1970 (would be ms).
    assert measured_at.startswith("2026-")


def test_room_temperature_none_before_reading():
    """No topics/sensor yet -> no value and no measured_at attribute."""
    sensor = BoschComBaconRoomTemperature(
        coordinator=_coordinator(sensor=None), config_entry=None
    )
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_signal_strength_value_and_quality():
    """Signal strength reports the dBm value and the qualitative rating."""
    sensor = BoschComBaconSignalStrength(
        coordinator=_coordinator(info=SAMPLE_INFO), config_entry=None
    )
    assert sensor.native_value == -55
    assert sensor.extra_state_attributes == {"signal_quality": "good"}


def test_signal_strength_none_before_info():
    """Before topics/info arrives there is no value."""
    sensor = BoschComBaconSignalStrength(
        coordinator=_coordinator(info=None), config_entry=None
    )
    assert sensor.native_value is None


@pytest.mark.parametrize("data_none", [True, False])
def test_entities_survive_missing_data(data_none):
    """All bacon entities tolerate coordinator.data being None / empty."""
    coordinator = _coordinator(data_none=data_none, reported={})
    assert BoschComBaconRacClimate(coordinator=coordinator).swing_mode == "off"
    assert BoschComBaconOnlineSensor(coordinator=coordinator).is_on is None
    assert (
        BoschComBaconRoomTemperature(
            coordinator=coordinator, config_entry=None
        ).native_value
        is None
    )
