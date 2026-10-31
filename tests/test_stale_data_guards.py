"""Regression tests for #176: partial cloud payloads must not freeze entities.

A bulk response that misses an endpoint leaves the corresponding coordinator
data field None. Any unguarded access in _handle_coordinator_update raises,
which permanently ends that entity's updates — a transient outage becomes a
frozen entity until the config entry is reloaded.
"""

from unittest.mock import AsyncMock, MagicMock, Mock

from custom_components.bosch_homecom.select import BoschComSelectHolidayMode
from custom_components.bosch_homecom.sensor import BoschComSensorHs


def _coordinator(**data_fields):
    coord = Mock()
    coord.unique_id = "k40-176"
    coord.device_info = Mock()
    coord.bhc = Mock()
    coord.async_request_refresh = AsyncMock()
    for name, value in data_fields.items():
        setattr(coord.data, name, value)
    return coord


# ---------------------------------------------------------------------------
# BoschComSelectHolidayMode — select.py, the reported traceback site
# ---------------------------------------------------------------------------


def test_holiday_select_none_survives_update():
    """holiday_mode=None yields None instead of AttributeError (#176)."""
    coord = _coordinator(holiday_mode=None)
    select = BoschComSelectHolidayMode(
        coordinator=coord, field="holiday_mode", allowedValues=["off", "on"]
    )
    select.async_write_ha_state = MagicMock()

    assert select.current_option is None

    select._handle_coordinator_update()
    assert select._attr_current_option is None
    select.async_write_ha_state.assert_called_once()


def test_holiday_select_non_dict_is_none():
    """The library annotates holiday_mode list|None; a list must not crash."""
    coord = _coordinator(holiday_mode=["unexpected"])
    select = BoschComSelectHolidayMode(
        coordinator=coord, field="holiday_mode", allowedValues=["off", "on"]
    )

    assert select.current_option is None


def test_holiday_select_value_roundtrip():
    """A healthy payload still yields the first value."""
    coord = _coordinator(holiday_mode={"values": ["hm1"], "allowedValues": ["hm1"]})
    select = BoschComSelectHolidayMode(
        coordinator=coord, field="holiday_mode", allowedValues=["hm1"]
    )
    select.async_write_ha_state = MagicMock()

    assert select.current_option == "hm1"

    select._handle_coordinator_update()
    assert select._attr_current_option == "hm1"


# ---------------------------------------------------------------------------
# BoschComSensorHs — sensor.py, the second reported site
# ---------------------------------------------------------------------------


def _hs_sensor(heat_sources):
    coord = _coordinator(heat_sources=heat_sources)
    return BoschComSensorHs(coordinator=coord, config_entry=Mock(), field="hs")


def test_hs_sensor_none_heat_sources_survives():
    """heat_sources=None yields unknowns instead of AttributeError (#176)."""
    sensor = _hs_sensor(None)

    assert sensor.state is None
    attrs = sensor.extra_state_attributes
    assert attrs["returnTemperature"] == "unknown"
    assert attrs["numberOfStartsTotal"] == "unknown"
    assert attrs["systemPressure"] == "unknown"


def test_hs_sensor_healthy_payload_roundtrip():
    """A healthy payload still populates state and attributes."""
    sensor = _hs_sensor(
        {
            "pumpType": {"value": "heatpump"},
            "returnTemperature": {"value": 31.5, "unitOfMeasure": "C"},
            "starts": {"values": [{"total": 1234}]},
        }
    )

    assert sensor.state == "heatpump"
    attrs = sensor.extra_state_attributes
    assert attrs["returnTemperature"] == "31.5C"
    assert attrs["numberOfStartsTotal"] == 1234


def test_hs_sensor_unreported_readings_are_unknown():
    """A reading the device does not report is "unknown", not "unknownunknown".

    A K40 heat pump sends empty collector temperatures; an icom sends no
    supply temperature, modulation or working time (#178).
    """
    sensor = _hs_sensor(
        {
            "returnTemperature": {"value": 27.7, "unitOfMeasure": "C"},
            "collectorInflowTemp": {},
            "collectorOutflowTemp": {},
            "actualModulation": {"value": None, "unitOfMeasure": "%"},
            "totalWorkingTime": {"value": 21084230.0},
        }
    )

    attrs = sensor.extra_state_attributes
    assert attrs["returnTemperature"] == "27.7C"
    assert attrs["collectorInflowTemp"] == "unknown"
    assert attrs["collectorOutflowTemp"] == "unknown"
    assert attrs["actualModulation"] == "unknown"
    assert attrs["actualSupplyTemperature"] == "unknown"
    # A value without a unit keeps the value instead of appending "unknown".
    assert attrs["totalWorkingTime"] == "21084230.0"


def test_hs_sensor_reads_the_icom_key_names():
    """An icom names modulation, supply and working time differently (icom.py)."""
    sensor = _hs_sensor(
        {
            "type": {"value": "heatpump"},
            "supplyTemperature": {"value": 35.5, "unitOfMeasure": "C"},
            "modulation": {"value": 42.0, "unitOfMeasure": "%"},
            "workingTime": {"value": 7200, "unitOfMeasure": "s"},
        }
    )

    assert sensor.state == "heatpump"
    attrs = sensor.extra_state_attributes
    assert attrs["actualSupplyTemperature"] == "35.5C"
    assert attrs["actualModulation"] == "42.0%"
    assert attrs["totalWorkingTime"] == "7200s"
    assert attrs["totalWorkingTimeReadable"] == "2 hours"
