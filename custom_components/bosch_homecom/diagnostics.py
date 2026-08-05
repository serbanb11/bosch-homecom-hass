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
            "payload": async_redact_data(entry.get("payload"), TO_REDACT_RAW)
            if isinstance(entry.get("payload"), (dict, list))
            else entry.get("payload"),
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
    device: list[Any] = []
    firmware: list[Any] = []
    notifications: list[Any] = []
    stardard_functions: list[Any] = []  # (mantém a grafia para compatibilidade)
    advanced_functions: list[Any] = []
    switch_programs: list[Any] = []
    # Matter/Bacon (bacon_rac) devices carry no standard_functions; their whole
    # state lives in the MQTT device shadow. Dump reported/desired so bacon
    # reports are actionable instead of showing empty function lists.
    reported: list[Any] = []
    desired: list[Any] = []
    # Also bacon-only, and not in the shadow: the push-only "topics" channel.
    # sensor is where roomTemperature lives, meta carries the device's real
    # capabilities, info its firmware and health.
    sensor: list[Any] = []
    metadata: list[Any] = []
    info: list[Any] = []

    coordinators = config_entry.runtime_data
    for coordinator in coordinators:
        data = coordinator.data
        device.append(getattr(data, "device", {}))
        firmware.append(getattr(data, "firmware", {}))
        notifications.append(getattr(data, "notifications", []))
        # estes só existem em RAC; nos outros devolvemos lista vazia
        stardard_functions.append(getattr(data, "stardard_functions", []))
        advanced_functions.append(getattr(data, "advanced_functions", []))
        switch_programs.append(getattr(data, "switch_programs", []))
        # só existem em bacon_rac; nos outros devolvemos None
        reported.append(getattr(data, "reported", None))
        desired.append(getattr(data, "desired", None))
        sensor.append(getattr(data, "sensor", None))
        metadata.append(getattr(data, "metadata", None))
        info.append(getattr(data, "info", None))

    data_out = [
        {
            "devices": a,
            "firmwares": b,
            "notifications": c,
            "stardard_functions": d,
            "advanced_functions": e,
            "switch_programs": f,
            "reported": g,
            "desired": h,
            "sensor": i,
            "metadata": j,
            "info": k,
        }
        for a, b, c, d, e, f, g, h, i, j, k in zip(
            device,
            firmware,
            notifications,
            stardard_functions,
            advanced_functions,
            switch_programs,
            reported,
            desired,
            sensor,
            metadata,
            info,
            strict=False,
        )
    ]

    return {
        "info": async_redact_data(config_entry.data, TO_REDACT),
        "data": data_out,
        # Everything seen on the bacon wildcard subscription, so a report is
        # actionable without another round trip asking the user to run a service.
        "bacon_raw": _bacon_raw_captures(coordinators),
    }
