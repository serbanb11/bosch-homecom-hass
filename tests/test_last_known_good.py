"""Regression tests for #182: a 200 with nulled fields must not blank entities.

The cloud has been seen answering normally while single fields (dhw1
operationMode, the per-level setpoints) came back null for 90 minutes. The K40
and icom coordinators serve such a field from its last known value for
LAST_KNOWN_GOOD_MAX_AGE, then pass the null on so staleness stays bounded.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from unittest.mock import patch

from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_homecom.const import DOMAIN
from custom_components.bosch_homecom.coordinator import (
    LAST_KNOWN_GOOD_MAX_AGE,
    BoschComModuleCoordinatorK40,
)

from .test_coordinator import _make_k40_data

DEVICE = {"deviceId": "12345", "deviceType": "k40"}
FIRMWARE = {"value": "1.0.0"}


@pytest.fixture
def entry():
    return MockConfigEntry(domain=DOMAIN, title="test-user", unique_id="test-user")


def _data(**overrides):
    return dataclasses.replace(_make_k40_data(DEVICE, FIRMWARE), **overrides)


def _dhw(**nodes):
    return [{"id": "/dhwCircuits/dhw1", **nodes}]


def _coordinator(hass, entry):
    entry.add_to_hass(hass)
    return BoschComModuleCoordinatorK40(
        hass, None, DEVICE, FIRMWARE, entry, auth_provider=False
    )


def _poll(coordinator, data):
    """Run one refresh's worth of data through the coordinator."""
    coordinator.data = coordinator._build_device_data(data)
    return coordinator.data


def test_nulled_circuit_field_keeps_last_known_value(hass, entry):
    """Only the nulled node is held; fresh siblings still update."""
    coordinator = _coordinator(hass, entry)
    _poll(
        coordinator,
        _data(
            dhw_circuits=_dhw(
                operationMode={"value": "eco"}, actualTemp={"value": 50.0}
            )
        ),
    )

    data = _poll(
        coordinator,
        _data(dhw_circuits=_dhw(operationMode=None, actualTemp={"value": 55.3})),
    )

    assert data.dhw_circuits[0]["operationMode"] == {"value": "eco"}
    assert data.dhw_circuits[0]["actualTemp"] == {"value": 55.3}


def test_fresh_value_always_wins(hass, entry):
    """A real value replaces the held one immediately."""
    coordinator = _coordinator(hass, entry)
    _poll(coordinator, _data(dhw_circuits=_dhw(operationMode={"value": "eco"})))
    _poll(coordinator, _data(dhw_circuits=_dhw(operationMode=None)))

    data = _poll(coordinator, _data(dhw_circuits=_dhw(operationMode={"value": "low"})))

    assert data.dhw_circuits[0]["operationMode"] == {"value": "low"}


def test_hold_expires_after_max_age(hass, entry):
    """Past the bound the null is passed on, and stays passed on."""
    coordinator = _coordinator(hass, entry)
    start = dt_util.utcnow()
    nulled = lambda: _data(dhw_circuits=_dhw(operationMode=None))  # noqa: E731

    with patch("custom_components.bosch_homecom.coordinator.dt_util.utcnow") as now:
        now.return_value = start
        _poll(coordinator, _data(dhw_circuits=_dhw(operationMode={"value": "eco"})))
        assert _poll(coordinator, nulled()).dhw_circuits[0]["operationMode"]

        now.return_value = start + LAST_KNOWN_GOOD_MAX_AGE - timedelta(seconds=1)
        assert _poll(coordinator, nulled()).dhw_circuits[0]["operationMode"]

        now.return_value = start + LAST_KNOWN_GOOD_MAX_AGE + timedelta(seconds=1)
        assert _poll(coordinator, nulled()).dhw_circuits[0]["operationMode"] is None

        # The expired null must not restart the clock from the held copy.
        now.return_value = start + LAST_KNOWN_GOOD_MAX_AGE + timedelta(minutes=1)
        assert _poll(coordinator, nulled()).dhw_circuits[0]["operationMode"] is None


def test_whole_field_dropped_by_the_cloud_is_held(hass, entry):
    """A dropped /bulk empties whole fields; circuits do not just vanish."""
    coordinator = _coordinator(hass, entry)
    circuits = _dhw(operationMode={"value": "eco"})
    _poll(
        coordinator,
        _data(dhw_circuits=circuits, heat_sources={"pumpType": {"value": "hp"}}),
    )

    data = _poll(coordinator, _data(dhw_circuits={}, heat_sources={"pumpType": {}}))

    assert data.dhw_circuits == circuits
    assert data.heat_sources["pumpType"] == {"value": "hp"}


def test_cleared_notifications_are_not_held(hass, entry):
    """An empty notifications list is a real value, not a hole."""
    coordinator = _coordinator(hass, entry)
    _poll(coordinator, _data(notifications=[{"dcd": "A01", "ccd": "5"}]))

    assert _poll(coordinator, _data(notifications=[])).notifications == []


def test_first_poll_and_never_seen_fields_pass_through(hass, entry):
    """Nothing is invented: no previous value means the null stays."""
    coordinator = _coordinator(hass, entry)

    data = _poll(coordinator, _data(dhw_circuits=_dhw(operationMode=None)))
    assert data.dhw_circuits[0]["operationMode"] is None

    data = _poll(coordinator, _data(dhw_circuits=_dhw(operationMode=None)))
    assert data.dhw_circuits[0]["operationMode"] is None
