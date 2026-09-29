"""Tests for the brine circuit collector temperature sensors (K30/K40)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.bosch_homecom.sensor import (
    BRINE_TEMP_FIELDS,
    BoschComSensorHsBrineTemp,
    async_setup_entry,
)

HEAT_SOURCES = {
    "collectorInflowTemp": {"value": 4.5, "unitOfMeasure": "C"},
    "collectorOutflowTemp": {"value": 1.2, "unitOfMeasure": "C"},
}


def _coordinator(heat_sources=HEAT_SOURCES, device_type="k40"):
    coordinator = MagicMock()
    coordinator.unique_id = "102128202"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "102128202")}}
    coordinator.data = SimpleNamespace(
        device={"deviceId": "102128202", "deviceType": device_type},
        heat_sources=heat_sources,
        dhw_circuits=None,
        ventilation=None,
        heating_circuits=None,
        solar_circuits=None,
        pool=None,
        indoor_humidity=None,
        flame_indication=None,
        energy_history=None,
        hourly_energy_history=None,
        devices=None,
        health_status=None,
        brand=None,
        system_info=None,
        system_bus=None,
    )
    return coordinator


def _sensor(field, coordinator=None):
    return BoschComSensorHsBrineTemp(
        coordinator=coordinator or _coordinator(), config_entry=None, field=field
    )


async def _setup(coordinator):
    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]
    entities = []
    await async_setup_entry(MagicMock(), config_entry, entities.extend)
    return [e for e in entities if isinstance(e, BoschComSensorHsBrineTemp)]


@pytest.mark.parametrize(
    ("field", "expected"),
    [("collectorInflowTemp", 4.5), ("collectorOutflowTemp", 1.2)],
)
def test_reports_numeric_value(field, expected) -> None:
    sensor = _sensor(field)
    assert sensor.native_value == expected
    assert sensor.native_unit_of_measurement == "°C"
    assert sensor.translation_key == BRINE_TEMP_FIELDS[field]
    assert sensor.unique_id == f"102128202-{BRINE_TEMP_FIELDS[field]}"


def test_fahrenheit_unit_follows_payload() -> None:
    coordinator = _coordinator(
        {"collectorInflowTemp": {"value": 40.1, "unitOfMeasure": "F"}}
    )
    sensor = _sensor("collectorInflowTemp", coordinator)
    assert sensor.native_value == 40.1
    assert sensor.native_unit_of_measurement == "°F"


@pytest.mark.parametrize(
    "heat_sources",
    [
        None,
        {},
        {"collectorInflowTemp": None},
        {"collectorInflowTemp": {}},
        {"collectorInflowTemp": {"value": "n/a"}},
    ],
)
def test_missing_or_bad_reading_is_none(heat_sources) -> None:
    assert (
        _sensor("collectorInflowTemp", _coordinator(heat_sources)).native_value is None
    )


async def test_setup_creates_both_sensors_when_reported() -> None:
    sensors = await _setup(_coordinator())
    assert sorted(s.field for s in sensors) == [
        "collectorInflowTemp",
        "collectorOutflowTemp",
    ]


async def test_setup_skips_a_unit_without_brine_circuit() -> None:
    """A 404 from the cloud is stored as None by the library: onboard nothing."""
    sensors = await _setup(
        _coordinator({"collectorInflowTemp": None, "collectorOutflowTemp": None})
    )
    assert sensors == []


async def test_setup_skips_icom() -> None:
    """icom does not fetch the brine endpoints, so the field is never present."""
    sensors = await _setup(_coordinator(device_type="icom"))
    assert sensors == []
