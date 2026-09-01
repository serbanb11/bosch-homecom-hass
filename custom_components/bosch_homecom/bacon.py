"""Shared helpers for Matter/Bacon (bacon_rac) entities."""

from __future__ import annotations

import re
from typing import Any

# A topics/meta payload is {"shadows": {"state": …, "schedule": …}, …}; the state
# block is the per-field capability map (type/enum/min/max/step and the ``ro``
# writability flag) that entities read.
_BACON_META_STATE_PATH: tuple[str, ...] = ("shadows", "state")

# Shadow ``*Enabled`` fields that are climate controls, not comfort features.
BACON_NON_FEATURE_FIELDS = frozenset({"powerEnabled", "hSwingEnabled", "vSwingEnabled"})

# Known comfort features -> translation_key, named after the HomeCom app (#162).
# Note: setbackEnabled is 8 °C frost heating, NOT eco or a generic setback.
BACON_FEATURE_KEYS: dict[str, str] = {
    "fullPowerEnabled": "bacon_full_power",  # "Boost"
    "ionizerEnabled": "bacon_ionizer",
    "sleepEnabled": "bacon_sleep",
    "setbackEnabled": "bacon_frost",  # "8 °C heating" (frost protection)
    "ecoEnabled": "bacon_eco",
    "breezeAwayEnabled": "bacon_breeze_away",  # "Wind avoid me"
    "savePlusEnabled": "bacon_save_plus",
}


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
