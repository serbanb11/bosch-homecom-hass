"""The debug data snapshot is redacted like diagnostics (hacs/default#13696)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from custom_components.bosch_homecom.sensor import _redacted_snapshot


@dataclass
class _BaconData:
    device: dict[str, Any]
    reported: dict[str, Any] = field(default_factory=dict)
    info: dict[str, Any] = field(default_factory=dict)


def test_matter_secrets_network_and_serial_are_redacted():
    data = _BaconData(
        device={"deviceId": "86DM123456789", "deviceType": "bacon_rac"},
        reported={"powerEnabled": True, "serialNumber": "86DM123456789"},
        info={
            "matterOnboarding": {
                "manualPairingCode": "12345678901",
                "qrCodeData": "MT:ABC",
            },
            "network": {"mac": "aa:bb:cc:dd:ee:ff", "ssid": "Home", "signalQuality": 3},
            "sgtin": "x",
            "userId": "u",
        },
    )

    snapshot = _redacted_snapshot(data)
    text = repr(snapshot)

    for secret in ("86DM123456789", "12345678901", "MT:ABC", "aa:bb", "'Home'"):
        assert secret not in text
    assert snapshot["device"] == {"deviceId": "86DM***", "deviceType": "bacon_rac"}
    assert snapshot["reported"]["powerEnabled"] is True
    assert snapshot["info"]["network"]["signalQuality"] == 3


def test_a_cloud_device_keeps_its_id_and_values():
    data = _BaconData(
        device={"deviceId": "101506113", "deviceType": "rac"},
        reported={"temp": 21},
    )

    snapshot = _redacted_snapshot(data)

    assert snapshot["device"]["deviceId"] == "101506113"
    assert snapshot["reported"] == {"temp": 21}


def test_non_dict_data_passes_through():
    assert _redacted_snapshot(None) is None
