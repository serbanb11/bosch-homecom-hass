"""Shared helpers for Matter/Bacon (bacon_rac / bacon_ap) entities."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.helpers.entity import EntityCategory

# A topics/meta payload is {"shadows": {"state": …, "schedule": …}, …}; the state
# block is the per-field capability map (type/enum/min/max/step and the ``ro``
# writability flag) that entities read.
_BACON_META_STATE_PATH: tuple[str, ...] = ("shadows", "state")

# Shadow ``*Enabled`` fields that are climate controls, not comfort features.
BACON_NON_FEATURE_FIELDS = frozenset({"powerEnabled", "hSwingEnabled", "vSwingEnabled"})

# Known ``*Enabled`` fields -> translation_key, named after the HomeCom app (#162).
# Note: setbackEnabled is 8 °C frost heating, NOT eco or a generic setback.
BACON_FEATURE_KEYS: dict[str, str] = {
    # RAC comfort features
    "fullPowerEnabled": "bacon_full_power",  # "Boost"
    "ionizerEnabled": "bacon_ionizer",
    "sleepEnabled": "bacon_sleep",
    "setbackEnabled": "bacon_frost",  # "8 °C heating" (frost protection)
    "ecoEnabled": "bacon_eco",
    "breezeAwayEnabled": "bacon_breeze_away",  # "Wind avoid me"
    "savePlusEnabled": "bacon_save_plus",
    # Air purifier settings (#203)
    "childLockEnabled": "bacon_child_lock",
    "lightEnabled": "bacon_light",  # the light ring
    "displayEnabled": "bacon_display",
}

# Fields that are device settings rather than comfort features: shown under the
# device's configuration section instead of as primary controls.
BACON_CONFIG_FIELDS: dict[str, EntityCategory] = {
    "childLockEnabled": EntityCategory.CONFIG,
    "lightEnabled": EntityCategory.CONFIG,
    "displayEnabled": EntityCategory.CONFIG,
}

# Air purifier ``topics/sensor`` airQuality levels, as the HomeCom app's
# AirQuality.ofLightRingValue maps them (the light ring colour).
BACON_AIR_QUALITY_LEVELS: dict[int, str] = {1: "good", 2: "ok", 3: "poor", 4: "bad"}
BACON_AIR_QUALITY_OPTIONS: list[str] = list(BACON_AIR_QUALITY_LEVELS.values())
# PM2.5 (µg/m³) upper bounds per level, from the app's AirQuality.ofPMValue.
_BACON_PM25_UPPER_BOUNDS: tuple[tuple[float, str], ...] = (
    (12, "good"),
    (35, "ok"),
    (55, "poor"),
)
# Purifier operating modes, from topics/meta's opMode enum on the Air 4000i.
BACON_AP_MODES: list[str] = ["auto", "manual", "silent"]
BACON_AP_MODE_MANUAL = "manual"


def bacon_meta_state(metadata: dict | None) -> dict:
    """Return the state-field block of a topics/meta payload, or {} if absent.

    Each entry looks like ``{"type": ..., "ro": bool}`` plus ``enum`` for strings
    and ``min``/``max``/``step`` for numbers. Returning ``{}`` is normal — the
    payload is push-only and may not have arrived — and callers fall back to a
    default in that case.
    """
    node: Any = metadata
    for key in _BACON_META_STATE_PATH:
        node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            return {}
    return node if isinstance(node, dict) else {}


def humanize_feature(field: str) -> str:
    """Turn an unknown ``fooBarEnabled`` field into a readable fallback name."""
    core = field[: -len("Enabled")] if field.endswith("Enabled") else field
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", core).strip()
    return spaced[:1].upper() + spaced[1:] if spaced else field


def bacon_feature_fields(reported: dict) -> list[str]:
    """Comfort-feature ``*Enabled`` fields this device actually reports."""
    return [
        field
        for field in reported
        if field.endswith("Enabled") and field not in BACON_NON_FEATURE_FIELDS
    ]


def bacon_air_quality_level(value: Any) -> str | None:
    """Map the light-ring ``airQuality`` integer to good/ok/poor/bad."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return BACON_AIR_QUALITY_LEVELS.get(int(value))


def bacon_pm25_level(value: Any) -> str | None:
    """Classify a PM2.5 reading (µg/m³) with the app's thresholds."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    for upper, level in _BACON_PM25_UPPER_BOUNDS:
        if value <= upper:
            return level
    return "bad"


def humanize_appliance_type(appliance_type: str | None) -> str | None:
    """Turn a ``topics/info`` appliance type such as ``air_4000i_v2`` into a name.

    Purifiers carry no ``customTitle`` in their shadow, so this is the best
    device name available: ``Air 4000i v2``.
    """
    if not isinstance(appliance_type, str) or not appliance_type.strip():
        return None
    words = appliance_type.strip().replace("-", "_").split("_")
    words = [w for w in words if w]
    if not words:
        return None
    return " ".join([words[0].capitalize(), *words[1:]])
