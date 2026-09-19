"""Tests for the solar thermal circuit sensors (K30/K40/icom)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.bosch_homecom.sensor import (
    SOLAR_CIRCUIT_SENSORS,
    BoschComSensorSolarCircuit,
    async_setup_entry,
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
    assert _sensor(key).native_value == expected


def test_solar_sensor_unique_id_and_translation_key() -> None:
    """Unique ids are namespaced per circuit and reading."""
    sensor = _sensor("collectorTemperature")
    assert sensor.unique_id == "102128202-sc1_collectorTemperature"
    assert sensor.translation_key == "solar_collector_temperature"
    assert sensor.translation_placeholders == {"circuit": "sc1"}


def test_solar_sensor_without_circuits() -> None:
    """No circuits at all yields None rather than raising."""
    assert _sensor("collectorTemperature", _mock_coordinator([])).native_value is None


def test_solar_sensor_unknown_circuit() -> None:
    """A reading for a circuit that is not reported yields None."""
    sensor = _sensor("collectorTemperature", circuit_id="sc9")
    assert sensor.native_value is None


def test_solar_sensor_missing_reading() -> None:
    """A circuit missing this particular reading yields None."""
    coordinator = _mock_coordinator([{"id": "/solarCircuits/sc1"}])
    assert _sensor("collectorTemperature", coordinator).native_value is None


def test_solar_sensor_non_numeric_value() -> None:
    """A non-numeric payload yields None instead of raising."""
    coordinator = _mock_coordinator(
        [{"id": "/solarCircuits/sc1", "collectorTemperature": {"value": "n/a"}}]
    )
    assert _sensor("collectorTemperature", coordinator).native_value is None


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
    assert sensor.native_value == 155.1
    assert sensor.native_unit_of_measurement == "°F"


def test_solar_yield_ignores_fahrenheit_unit() -> None:
    """Only temperature readings follow unitOfMeasure; energy stays kWh."""
    coordinator = _mock_coordinator(
        [{"id": "/solarCircuits/sc1", "solarYield": {"value": 5, "unitOfMeasure": "F"}}]
    )
    assert _sensor("solarYield", coordinator).native_unit_of_measurement == "kWh"


def test_solar_sensor_unit_reverts_to_celsius() -> None:
    """Reading the unit never latches Fahrenheit onto the entity."""
    coordinator = _mock_coordinator(
        [
            {
                "id": "/solarCircuits/sc1",
                "collectorTemperature": {"value": 155.1, "unitOfMeasure": "F"},
            }
        ]
    )
    sensor = _sensor("collectorTemperature", coordinator)
    assert sensor.native_unit_of_measurement == "°F"
    coordinator.data.solar_circuits = SAMPLE_SOLAR_CIRCUITS
    assert sensor.native_unit_of_measurement == "°C"


async def test_setup_skips_readings_the_device_does_not_serve() -> None:
    """homecom_alt sets every key, leaving None for unserved readings."""
    coordinator = MagicMock()
    coordinator.unique_id = "102128202"
    coordinator.data = SimpleNamespace(
        device={"deviceId": "102128202", "deviceType": "k40"},
        dhw_circuits=None,
        ventilation=None,
        heating_circuits=None,
        pool=None,
        indoor_humidity=None,
        flame_indication=None,
        energy_history=None,
        hourly_energy_history=None,
        devices=None,
        solar_circuits=[
            {
                "id": "/solarCircuits/sc1",
                "collectorTemperature": {"value": 68.4, "unitOfMeasure": "C"},
                "solarYield": None,
                "dhwTankTemperature": None,
                "dhwTankBottomTemperature": None,
                "maxCylinderTemperature": None,
            }
        ],
    )
    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]
    entities: list = []

    await async_setup_entry(MagicMock(), config_entry, entities.extend)

    solar = [e for e in entities if isinstance(e, BoschComSensorSolarCircuit)]
    assert [e.key for e in solar] == ["collectorTemperature"]


def test_every_declared_sensor_is_translatable() -> None:
    """Each declared reading carries a translation key."""
    for spec in SOLAR_CIRCUIT_SENSORS.values():
        assert spec["translation_key"].startswith("solar_")
