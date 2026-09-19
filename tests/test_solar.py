"""Tests for the solar thermal circuit sensors (K30/K40/icom)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.bosch_homecom.sensor import (
    SOLAR_CIRCUIT_SENSORS,
    BoschComSensorSolarCircuit,
)

SAMPLE_SOLAR_CIRCUITS = [
    {
        "id": "/solarCircuits/sc1",
        "collectorTemperature": {"value": 68.4, "unitOfMeasure": "C"},
        "solarYield": {"value": 123, "unitOfMeasure": "kWh"},
        "dhwTankTemperature": {"value": 55.1, "unitOfMeasure": "C"},
        "dhwTankBottomTemperature": {"value": 41.2, "unitOfMeasure": "C"},
        "maxCylinderTemperature": {"value": 80, "unitOfMeasure": "C"},
    }
]


def _mock_coordinator(solar_circuits=SAMPLE_SOLAR_CIRCUITS):
    """Build a mock coordinator exposing coordinator.data.solar_circuits."""

    class _Data:
        def __init__(self, circuits):
            self.solar_circuits = circuits
            self.device = {"deviceId": "102128202", "deviceType": "k40"}

    coordinator = MagicMock()
    coordinator.unique_id = "102128202"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "102128202")}}
    coordinator.data = _Data(solar_circuits)
    return coordinator


def _sensor(key, coordinator=None, circuit_id="sc1"):
    return BoschComSensorSolarCircuit(
        coordinator=coordinator or _mock_coordinator(),
        config_entry=None,
        circuit_id=circuit_id,
        key=key,
    )


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("collectorTemperature", 68.4),
        ("solarYield", 123.0),
        ("dhwTankTemperature", 55.1),
        ("dhwTankBottomTemperature", 41.2),
        ("maxCylinderTemperature", 80.0),
    ],
)
def test_solar_sensor_reports_value(key, expected) -> None:
    """Every solar reading is exposed as its numeric value."""
    assert _sensor(key).state == expected


def test_solar_sensor_unique_id_and_translation_key() -> None:
    """Unique ids are namespaced per circuit and reading."""
    sensor = _sensor("collectorTemperature")
    assert sensor.unique_id == "102128202-sc1_collectorTemperature"
    assert sensor.translation_key == "solar_collector_temperature"
    assert sensor.translation_placeholders == {"circuit": "sc1"}


def test_solar_sensor_without_circuits() -> None:
    """No circuits at all yields None rather than raising."""
    assert _sensor("collectorTemperature", _mock_coordinator([])).state is None


def test_solar_sensor_unknown_circuit() -> None:
    """A reading for a circuit that is not reported yields None."""
    sensor = _sensor("collectorTemperature", circuit_id="sc9")
    assert sensor.state is None


def test_solar_sensor_missing_reading() -> None:
    """A circuit missing this particular reading yields None."""
    coordinator = _mock_coordinator([{"id": "/solarCircuits/sc1"}])
    assert _sensor("collectorTemperature", coordinator).state is None


def test_solar_sensor_non_numeric_value() -> None:
    """A non-numeric payload yields None instead of raising."""
    coordinator = _mock_coordinator(
        [{"id": "/solarCircuits/sc1", "collectorTemperature": {"value": "n/a"}}]
    )
    assert _sensor("collectorTemperature", coordinator).state is None


def test_solar_sensor_fahrenheit_unit() -> None:
    """The reported unit follows unitOfMeasure when the system uses Fahrenheit."""
    coordinator = _mock_coordinator(
        [
            {
                "id": "/solarCircuits/sc1",
                "collectorTemperature": {"value": 155.1, "unitOfMeasure": "F"},
            }
        ]
    )
    sensor = _sensor("collectorTemperature", coordinator)
    assert sensor.state == 155.1
    assert sensor.native_unit_of_measurement == "°F"


def test_every_declared_sensor_is_translatable() -> None:
    """Each declared reading carries a translation key."""
    for spec in SOLAR_CIRCUIT_SENSORS.values():
        assert spec["translation_key"].startswith("solar_")
