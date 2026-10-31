"""Tests for the ventilation filter remaining-time sensor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTime
from homecom_alt import BHCDeviceK40
import pytest

from custom_components.bosch_homecom.sensor import (
    BoschComSensorVentilationFilter,
    async_setup_entry as sensor_async_setup_entry,
)

# As a K 40 RF with a ventilation unit reports it.
ZONE1 = {
    "id": "/ventilation/zone1",
    "exhaustFanLevel": {"value": "nom"},
    "filterRemainingTime": {
        "id": "/ventilation/zone1/filter/remainingTime",
        "type": "floatValue",
        "writeable": 0,
        "value": 21228,
        "unitOfMeasure": "mins",
    },
}
# A zone without the resource, or an older homecom_alt that does not fetch it.
ZONE2 = {"id": "/ventilation/zone2", "exhaustFanLevel": {"value": "red"}}


def _coordinator(zones):
    coordinator = MagicMock()
    coordinator.unique_id = "k40123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "k40123")}}
    coordinator.bhc = AsyncMock()
    coordinator.extra_data = {}
    coordinator.local_first = None
    coordinator.device = {"deviceId": "k40123", "deviceType": "k40"}
    coordinator.data = BHCDeviceK40(
        device={"deviceId": "k40123", "deviceType": "k40"},
        firmware=[],
        notifications=[],
        holiday_mode=None,
        away_mode=None,
        power_limitation=None,
        outdoor_temp=None,
        heat_sources=None,
        dhw_circuits=None,
        heating_circuits=None,
        ventilation=zones,
        zones=None,
        flame_indication=None,
        energy_history=None,
        hourly_energy_history=None,
        indoor_humidity=None,
        devices=None,
    )
    return coordinator


async def test_setup_creates_filter_sensor_only_where_served(hass):
    """Only the zone that reports a remaining filter time gets the sensor."""
    coordinator = _coordinator([ZONE1, ZONE2])
    config_entry = MagicMock()
    config_entry.runtime_data = [coordinator]
    added: list = []
    await sensor_async_setup_entry(hass, config_entry, added.extend)

    filters = [e for e in added if isinstance(e, BoschComSensorVentilationFilter)]
    assert [f.unique_id for f in filters] == ["k40123-zone1-filter_remaining_time"]


def test_filter_sensor_value_and_unit():
    """The value is the gateway's minutes, shown as a duration in days."""
    sensor = BoschComSensorVentilationFilter(_coordinator([ZONE1]), None, "zone1")
    assert sensor.native_value == 21228
    assert sensor.device_class == SensorDeviceClass.DURATION
    assert sensor.native_unit_of_measurement == UnitOfTime.MINUTES
    assert sensor.suggested_unit_of_measurement == UnitOfTime.DAYS


@pytest.mark.parametrize(
    "zones",
    [
        None,
        [ZONE2],
        [{**ZONE1, "filterRemainingTime": None}],
        [{**ZONE1, "filterRemainingTime": {"value": "n/a"}}],
    ],
)
def test_filter_sensor_without_value_is_none(zones):
    """A missing zone, resource or numeric value gives None, not a bad state."""
    sensor = BoschComSensorVentilationFilter(_coordinator(zones), None, "zone1")
    assert sensor.native_value is None
