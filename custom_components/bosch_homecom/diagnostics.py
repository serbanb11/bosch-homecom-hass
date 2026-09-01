"""Diagnostics support for BHC."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CODE, CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_REFRESH

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, CONF_CODE, CONF_TOKEN, CONF_REFRESH}

# The bacon MQTT client subscribes to users/{sub}/# — the whole account — so its
# raw capture also carries other devices and the sharing/claim traffic. Matter
# onboarding fields are pairing secrets and the network fields identify the home,
# so none of them may reach a dump a user pastes into an issue.
TO_REDACT_RAW = {
    "mac",
    "manualPairingCode",
    "matterOnboarding",
    "qrCodeData",
    "serialNumber",
    "sgtin",
    "ssid",
    CONF_CODE,
    CONF_TOKEN,
    CONF_REFRESH,
}

# Leading characters of a serial kept in a raw-capture key, enough to tell two
# devices apart in a dump without publishing either serial.
_SERIAL_PREFIX_KEPT = 4


def _mask_serial(serial: str) -> str:
    """Shorten a serial so devices stay distinguishable but not identifiable."""
    if len(serial) <= _SERIAL_PREFIX_KEPT:
        return "***"
    return f"{serial[:_SERIAL_PREFIX_KEPT]}***"


def _redact_raw_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Redact a BaconMqttClient.raw_snapshot() for publication.

    Keys are ``"{serial}/{channel_path}"``, so the serial is masked in the key as
    well as inside the payloads.
    """
    redacted: dict[str, Any] = {}
    for key, entry in snapshot.items():
        serial, _, path = key.partition("/")
        safe_key = f"{_mask_serial(serial) if serial != '-' else '-'}/{path}"
        redacted[safe_key] = {
            "payload": (
                async_redact_data(entry.get("payload"), TO_REDACT_RAW)
                if isinstance(entry.get("payload"), (dict, list))
                else entry.get("payload")
            ),
            "received_at": entry.get("received_at"),
        }
    return redacted


def _bacon_raw_captures(coordinators: Any) -> dict[str, Any]:
    """Collect the raw MQTT capture once per distinct bacon client.

    One client is shared by every bacon device of the entry, so the snapshot is
    identical across their coordinators — take it from the first that has one.
    """
    for coordinator in coordinators:
        client = getattr(coordinator, "client", None)
        snapshot = getattr(client, "raw_snapshot", None)
        if callable(snapshot):
            return _redact_raw_snapshot(snapshot())
    return {}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data_out: list[dict[str, Any]] = []
    for coordinator in config_entry.runtime_data:
        data = coordinator.data
        device = getattr(data, "device", {}) or {}
        if device.get("deviceType") == "bacon_rac":
            # Matter/Bacon devices have no pointt function lists; their whole state
            # lives in the MQTT shadow (reported/desired) and the push-only topics
            # channel (sensor/metadata/info). Skip the empty pointt fields.
            data_out.append(
                {
                    "devices": device,
                    "reported": getattr(data, "reported", None),
                    "desired": getattr(data, "desired", None),
                    "sensor": getattr(data, "sensor", None),
                    "metadata": getattr(data, "metadata", None),
                    "info": getattr(data, "info", None),
                }
            )
        else:
            data_out.append(
                {
                    "devices": device,
                    "firmwares": getattr(data, "firmware", {}),
                    "notifications": getattr(data, "notifications", []),
                    # (mantém a grafia para compatibilidade)
                    "stardard_functions": getattr(data, "stardard_functions", []),
                    "advanced_functions": getattr(data, "advanced_functions", []),
                    "switch_programs": getattr(data, "switch_programs", []),
                }
            )

    coordinators = config_entry.runtime_data
    return {
        "info": async_redact_data(config_entry.data, TO_REDACT),
        "data": data_out,
        # Everything seen on the bacon wildcard subscription, so a report is
        # actionable without another round trip asking the user to run a service.
        "bacon_raw": _bacon_raw_captures(coordinators),
    }
