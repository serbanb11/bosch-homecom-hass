"""Tests for the K40-family and RAC notification sensors."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.bosch_homecom.sensor import (
    BoschComSensorNotificationsK40,
    BoschComSensorNotificationsRac,
)

# As the gateway lists them: one current fault, one the user already cleared.
ACTIVE = {"cat": "E", "act": "A", "dcd": "A01", "ccd": "5", "dlv": "8", "t": "1"}
CLEARED = {"cat": "E", "act": "H", "dcd": "E07", "ccd": "4", "dlv": "4", "t": "0"}


def _coordinator(notifications):
    coord = Mock()
    coord.unique_id = "102128202"
    coord.device_info = Mock()
    coord.data = Mock()
    coord.data.notifications = notifications
    return coord


@pytest.mark.parametrize(
    "cls", [BoschComSensorNotificationsK40, BoschComSensorNotificationsRac]
)
def test_cleared_faults_leave_the_state(cls):
    """Only current faults make up the state; history goes to an attribute."""
    sensor = cls(coordinator=_coordinator([ACTIVE, CLEARED]), config_entry=Mock())

    assert sensor.state == "A01-5"
    assert sensor.extra_state_attributes == {
        "history": [
            {"code": "A01-5", "active": True, "fatal": True, "timestamp": "1"},
            {"code": "E07-4", "active": False, "fatal": False, "timestamp": "0"},
        ]
    }


@pytest.mark.parametrize(
    "cls", [BoschComSensorNotificationsK40, BoschComSensorNotificationsRac]
)
def test_active_codes_are_listed_one_per_line(cls):
    """Several current faults keep the long-standing dcd-ccd line format."""
    second = {**ACTIVE, "dcd": "H01", "ccd": "12"}
    sensor = cls(coordinator=_coordinator([ACTIVE, second]), config_entry=Mock())

    assert sensor.state == "A01-5\nH01-12"


@pytest.mark.parametrize("notifications", [None, [], [CLEARED], "garbage"])
def test_nothing_active_is_an_empty_state(notifications):
    """No current fault gives the empty state the sensor always had."""
    sensor = BoschComSensorNotificationsK40(
        coordinator=_coordinator(notifications), config_entry=Mock()
    )

    assert sensor.state == ""
    if notifications == [CLEARED]:
        assert sensor.extra_state_attributes["history"][0]["active"] is False
    else:
        assert sensor.extra_state_attributes == {}


def test_entries_without_a_code_are_skipped():
    """A malformed entry neither crashes the sensor nor shows up."""
    sensor = BoschComSensorNotificationsK40(
        coordinator=_coordinator([{"act": "A"}, "x", {"dcd": "A02"}]),
        config_entry=Mock(),
    )

    assert sensor.state == "A02"
    assert [h["code"] for h in sensor.extra_state_attributes["history"]] == ["A02"]
