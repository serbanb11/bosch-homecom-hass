"""RRC2 daily and hourly gas input from the energy history (#242)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass
from homecom_alt import BHCDeviceRrc2
import pytest

from custom_components.bosch_homecom.coordinator import BoschComModuleCoordinatorRrc2
from custom_components.bosch_homecom.sensor import (
    BoschComSensorEnergyHistory,
    BoschComSensorEnergyHistoryHourly,
    _add_or_defer,
    _add_pending_sensors_later,
    _rrc2_energy_candidates,
)

DAILY = {"value": [{"d": "14-11-2026", "T": 7.0, "gCh": 41.2, "gHw": 6.8}]}
HOURLY = {"value": [{"entries": [{"d": "14-11-2026", "h": 6, "gCh": 3.1, "gHw": 0.4}]}]}


def _coordinator(energy_history=None, hourly_energy_history=None):
    coordinator = object.__new__(BoschComModuleCoordinatorRrc2)
    coordinator.unique_id = "rrc2123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "rrc2123")}}
    coordinator.data = SimpleNamespace(
        energy_history=energy_history, hourly_energy_history=hourly_energy_history
    )
    coordinator.listeners = []
    coordinator.async_add_listener = lambda listener: (
        coordinator.listeners.append(listener) or (lambda: None)
    )
    return coordinator


def _candidates(coordinator):
    entities, pending = [], []
    for candidate in _rrc2_energy_candidates(coordinator, MagicMock()):
        _add_or_defer(candidate, entities, pending)
    return entities, pending


def test_energy_sensors_keep_the_unique_ids_they_had():
    """The ids match the K40 client's, so the old entities and history return."""
    entities, pending = _candidates(_coordinator(DAILY, HOURLY))

    daily, hourly = entities
    assert pending == []
    assert isinstance(daily, BoschComSensorEnergyHistory)
    assert isinstance(hourly, BoschComSensorEnergyHistoryHourly)
    assert daily.unique_id == "rrc2123-energy_history"
    assert hourly.unique_id == "rrc2123-energy_history_hourly"
    assert daily.device_class == SensorDeviceClass.ENERGY
    assert daily.state == 48.0
    assert hourly.state == 3.5


@pytest.mark.parametrize("node", [None, {}, {"value": []}])
def test_no_energy_sensor_until_the_gateway_serves_it(node):
    entities, pending = _candidates(_coordinator(node, node))

    assert entities == []
    assert len(pending) == 2


def test_energy_sensors_are_added_on_a_later_update():
    coordinator = _coordinator()
    entities, pending = _candidates(coordinator)
    added = []
    _add_pending_sensors_later(coordinator, MagicMock(), pending, added.extend)

    coordinator.data.energy_history = DAILY
    coordinator.data.hourly_energy_history = HOURLY
    for listener in coordinator.listeners:
        listener()
    for listener in coordinator.listeners:
        listener()

    assert sorted(sensor.unique_id for sensor in added) == [
        "rrc2123-energy_history",
        "rrc2123-energy_history_hourly",
    ]


def test_coordinator_passes_the_energy_history_through():
    coordinator = object.__new__(BoschComModuleCoordinatorRrc2)
    coordinator.device = {"deviceId": "rrc2123", "deviceType": "rrc2"}
    data = BHCDeviceRrc2(
        device="rrc2123",
        firmware=None,
        notifications=[],
        zones=[],
        heating_circuits=[],
        dhw_circuits=[],
        heat_sources={},
        away_mode={},
        outdoor_temp={},
        indoor_humidity={},
        devices=[],
        gateway_info={},
        system_location={},
        energy_history=DAILY,
        hourly_energy_history=HOURLY,
    )

    built = coordinator._build_device_data(data)

    assert built.energy_history == DAILY
    assert built.hourly_energy_history == HOURLY
