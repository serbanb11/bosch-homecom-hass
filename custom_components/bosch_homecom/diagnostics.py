"""Diagnostics support for BHC."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    (
        device,
        firmware,
        notifications,
        stardard_functions,
        advanced_functions,
        switch_programs,
    ) = [], [], [], [], [], []
    coordinators = config_entry.runtime_data
    for coordinator in coordinators:
        device.append(coordinator.data.device)
        firmware.append(coordinator.data.firmware)
        notifications.append(coordinator.data.notifications)
        stardard_functions.append(coordinator.data.stardard_functions)
        advanced_functions.append(coordinator.data.advanced_functions)
        switch_programs.append(coordinator.data.switch_programs)

    data = [
        {
            "devices": a,
            "firmwares": b,
            "notifications": c,
            "stardard_functions": d,
            "advanced_functions": e,
            "switch_programs": f,
        }
        for a, b, c, d, e, f in zip(
            device,
            firmware,
            notifications,
            stardard_functions,
            advanced_functions,
            switch_programs,
            strict=False,
        )
    ]

    return {
        "info": async_redact_data(config_entry.data, TO_REDACT),
        "data": data,
    }
