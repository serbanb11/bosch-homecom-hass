"""Test climate platform."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homecom_alt import BHCDeviceIcom, BHCDeviceK40, BHCDeviceRac, BHCDeviceRrc2

from custom_components.bosch_homecom.climate import (
    BoschComK40Climate,
    BoschComRacClimate,
    BoschComRrc2ZoneClimate,
)
from custom_components.bosch_homecom.coordinator import (
    BoschComModuleCoordinatorIcom,
    BoschComModuleCoordinatorRrc2,
)
from custom_components.bosch_homecom.sensor import BoschComSensorHc


def _rac_ref(name: str, value: str) -> dict:
    """Build a RAC standard-function reference, e.g. airFlowHorizontal=swing."""
    return {"id": f"/airConditioning/{name}", "value": value}


def _make_rac_coordinator(standard_functions):
    """Create a mock RAC coordinator with the given standard functions."""
    coordinator = MagicMock()
    coordinator.unique_id = "rac329"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "rac329")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.device = {"deviceId": "rac329", "deviceType": "rac"}
    coordinator.data = BHCDeviceRac(
        device="rac329",
        firmware=[],
        notifications=[],
        stardard_functions=standard_functions,
        advanced_functions=[],
        switch_programs=[],
    )
    return coordinator


# A unit that reports fan speed and both airflow louvers.
_FULL_RAC_FUNCTIONS = [
    _rac_ref("operationMode", "cool"),
    _rac_ref("fanSpeed", "auto"),
    _rac_ref("airFlowHorizontal", "swing"),
    _rac_ref("airFlowVertical", "off"),
    _rac_ref("temperatureSetpoint", "21"),
    _rac_ref("roomTemperature", "22"),
]


def test_rac_without_horizontal_airflow_does_not_crash():
    """A unit with no airFlowHorizontal renders without AttributeError (#167)."""
    functions = [
        ref for ref in _FULL_RAC_FUNCTIONS if "airFlowHorizontal" not in ref["id"]
    ]
    climate = BoschComRacClimate(
        coordinator=_make_rac_coordinator(functions), field="clima"
    )

    # The value the failing state write used to read is now a safe default.
    assert climate.swing_horizontal_mode is None
    # And the horizontal axis is not advertised, so HA never reads it.
    assert ClimateEntityFeature.SWING_HORIZONTAL_MODE not in climate.supported_features
    assert ClimateEntityFeature.SWING_MODE in climate.supported_features


def test_rac_without_operation_mode_does_not_crash():
    """A payload with no operationMode/acControl leaves hvac_mode None (#180)."""
    climate = BoschComRacClimate(coordinator=_make_rac_coordinator([]), field="clima")

    assert climate.hvac_mode is None
    # state is what the failing state write read.
    assert climate.state is None


def test_rac_with_both_airflows_advertises_both_axes():
    """A fully-featured unit keeps both swing axes and their values."""
    climate = BoschComRacClimate(
        coordinator=_make_rac_coordinator(list(_FULL_RAC_FUNCTIONS)), field="clima"
    )
    features = climate.supported_features
    assert ClimateEntityFeature.SWING_HORIZONTAL_MODE in features
    assert ClimateEntityFeature.SWING_MODE in features
    assert ClimateEntityFeature.FAN_MODE in features
    assert climate.swing_horizontal_mode == "on"
    assert climate.swing_mode == "off"


def test_rac_without_vertical_or_fan_gates_those_features():
    """Vertical swing and fan mode are gated the same way (sibling of #167)."""
    functions = [
        ref
        for ref in _FULL_RAC_FUNCTIONS
        if not any(k in ref["id"] for k in ("airFlowVertical", "fanSpeed"))
    ]
    climate = BoschComRacClimate(
        coordinator=_make_rac_coordinator(functions), field="clima"
    )
    features = climate.supported_features
    assert ClimateEntityFeature.SWING_MODE not in features
    assert ClimateEntityFeature.FAN_MODE not in features
    assert climate.swing_mode is None
    assert climate.fan_mode is None


def _make_k40_coordinator(suwi=None, heatcool=None):
    """Create a mock K40 coordinator with a single hc1 circuit."""
    hc1 = {
        "id": "/heatingCircuits/hc1",
        "operationMode": {"value": "auto"},
        "currentSuWiMode": {"value": suwi},
        "heatCoolMode": {"value": heatcool},
        "currentRoomSetpoint": {"value": 21, "unitOfMeasure": "C"},
    }
    coordinator = MagicMock()
    coordinator.unique_id = "k40123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "k40123")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.device = {"deviceId": "k40123", "deviceType": "k40"}
    coordinator.data = BHCDeviceK40(
        device="k40123",
        firmware=[],
        notifications=[],
        holiday_mode=None,
        away_mode=None,
        power_limitation=None,
        outdoor_temp=None,
        heat_sources=None,
        dhw_circuits=None,
        heating_circuits=[hc1],
        ventilation=None,
        zones=None,
        flame_indication=None,
        energy_history=None,
        hourly_energy_history=None,
        indoor_humidity=None,
        devices=None,
    )
    return coordinator


def _make_icom_coordinator(suwi=None, operation_mode="auto"):
    """Create a mock icom coordinator with a single hc1 circuit.

    Built on the real class (not MagicMock) so the isinstance check in
    async_set_temperature and the real async_set_temporary_room_setpoint
    delegation are exercised. Icom data has no heatCoolMode field.
    """
    hc1 = {
        "id": "/heatingCircuits/hc1",
        "operationMode": {"value": operation_mode},
        "currentSuWiMode": {"value": suwi},
        "currentRoomSetpoint": {"value": 21, "unitOfMeasure": "C"},
    }
    coordinator = object.__new__(BoschComModuleCoordinatorIcom)
    coordinator.unique_id = "icom123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "icom123")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.device = {"deviceId": "icom123", "deviceType": "icom"}
    coordinator.data = BHCDeviceIcom(
        device="icom123",
        firmware=[],
        notifications=[],
        holiday_mode=None,
        heat_sources=None,
        dhw_circuits=None,
        heating_circuits=[hc1],
        solar_circuits=None,
        ventilation=None,
        system_info=None,
        system_bus=None,
    )
    return coordinator


def _make_climate(coordinator):
    """Build the climate entity, stubbing HA state writes."""
    climate = BoschComK40Climate(coordinator=coordinator, field="hc1")
    climate.async_write_ha_state = MagicMock()
    return climate


async def test_set_temperature_heating_uses_manual_setpoint():
    """In heating mode the manual room setpoint endpoint is used."""
    coordinator = _make_k40_coordinator(suwi="forced", heatcool="heating")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=21)

    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_awaited_once_with(
        "k40123", "hc1", 21
    )
    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_not_awaited()
    assert climate._attr_target_temperature == 21
    coordinator.async_request_refresh.assert_awaited_once()


async def test_set_temperature_cooling_uses_cooling_setpoint():
    """In cooling mode the cooling room temp setpoint endpoint is used."""
    coordinator = _make_k40_coordinator(suwi="cooling", heatcool="cooling")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=23)

    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_awaited_once_with(
        "k40123", "hc1", 23
    )
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()
    assert climate._attr_target_temperature == 23
    coordinator.async_request_refresh.assert_awaited_once()


async def test_set_temperature_cooling_season_while_idle():
    """Cooling configured but compressor idle still writes cooling setpoint."""
    coordinator = _make_k40_coordinator(suwi="off", heatcool="cooling")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=22)

    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_awaited_once_with(
        "k40123", "hc1", 22
    )
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()


async def test_set_temperature_icom_cooling_uses_cooling_setpoint():
    """Icom in cooling mode writes coolingRoomTempSetpoint, not temporary.

    Regression test for the branch order fixed in #173: the icom-specific
    temporaryRoomSetpoint path must not shadow the cooling path (404s).
    """
    coordinator = _make_icom_coordinator(suwi="cooling")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=24)

    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_awaited_once_with(
        "icom123", "hc1", 24
    )
    coordinator.bhc.async_set_hc_temporary_room_setpoint.assert_not_awaited()
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()
    assert climate._attr_target_temperature == 24
    coordinator.async_request_refresh.assert_awaited_once()


async def test_set_temperature_icom_heating_uses_temporary_setpoint():
    """Icom in heating mode still uses the temporaryRoomSetpoint path."""
    coordinator = _make_icom_coordinator(suwi="forced")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=21)

    coordinator.bhc.async_set_hc_temporary_room_setpoint.assert_awaited_once_with(
        "icom123", "hc1", 21
    )
    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_not_awaited()
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()


async def test_set_temperature_icom_manual_uses_manual_setpoint():
    """Icom in manual operation writes manualRoomSetpoint (#205).

    In manual there is no schedule to override: temporaryRoomSetpoint is not
    served (404, first noted in #170) while manualRoomSetpoint is writable.
    """
    coordinator = _make_icom_coordinator(suwi="forced", operation_mode="manual")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=22)

    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_awaited_once_with(
        "icom123", "hc1", 22
    )
    coordinator.bhc.async_set_hc_temporary_room_setpoint.assert_not_awaited()
    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_not_awaited()
    assert climate._attr_target_temperature == 22
    coordinator.async_request_refresh.assert_awaited_once()


async def test_set_temperature_icom_manual_cooling_still_uses_cooling_setpoint():
    """Cooling keeps priority over manual operation on an icom circuit."""
    coordinator = _make_icom_coordinator(suwi="cooling", operation_mode="manual")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=24)

    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_awaited_once_with(
        "icom123", "hc1", 24
    )
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()
    coordinator.bhc.async_set_hc_temporary_room_setpoint.assert_not_awaited()


async def test_set_temperature_icom_missing_operation_mode_uses_temporary():
    """An icom circuit whose operationMode is nulled keeps the auto path."""
    coordinator = _make_icom_coordinator(suwi="forced", operation_mode=None)
    coordinator.data.heating_circuits[0]["operationMode"] = None
    climate = _make_climate(coordinator)

    await climate.async_set_temperature(temperature=21)

    coordinator.bhc.async_set_hc_temporary_room_setpoint.assert_awaited_once_with(
        "icom123", "hc1", 21
    )
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()


async def test_set_temperature_no_temperature_is_noop():
    """Calling without a temperature does nothing."""
    coordinator = _make_k40_coordinator(suwi="cooling", heatcool="cooling")
    climate = _make_climate(coordinator)

    await climate.async_set_temperature()

    coordinator.bhc.async_set_hc_cooling_room_temp_setpoint.assert_not_awaited()
    coordinator.bhc.async_set_hc_manual_room_setpoint.assert_not_awaited()
    coordinator.async_request_refresh.assert_not_awaited()


# ---------------------------------------------------------------------------
# Issue #194: icom circuits name the room temperature "roomtemperature"
# ---------------------------------------------------------------------------

_ICOM_ROOM_TEMP = {
    "id": "/heatingCircuits/hc1/roomtemperature",
    "type": "floatValue",
    "writeable": 0,
    "recordable": 1,
    "value": 21.2,
    "unitOfMeasure": "C",
}


def test_icom_room_temperature_reaches_the_climate_entity():
    """The raw roomtemperature key an icom circuit carries sets current_temperature."""
    coordinator = _make_icom_coordinator(suwi="forced")
    coordinator.data.heating_circuits[0]["roomtemperature"] = _ICOM_ROOM_TEMP
    climate = _make_climate(coordinator)

    climate.set_attr()

    assert climate.current_temperature == 21.2


def test_k40_room_temperature_still_uses_room_temp_key():
    """The K40 spelling keeps working alongside the icom one."""
    coordinator = _make_k40_coordinator(suwi="forced", heatcool="heating")
    coordinator.data.heating_circuits[0]["roomTemp"] = {"value": 20.5}
    climate = _make_climate(coordinator)

    climate.set_attr()

    assert climate.current_temperature == 20.5


def test_icom_room_temperature_reaches_the_status_sensor_attribute():
    """The heating circuit status sensor exposes it as the roomTemp attribute."""
    coordinator = _make_icom_coordinator(suwi="forced")
    coordinator.data.heating_circuits[0]["roomtemperature"] = _ICOM_ROOM_TEMP
    sensor = BoschComSensorHc(
        coordinator=coordinator, config_entry=MagicMock(), field="hc1"
    )

    assert sensor.extra_state_attributes["roomTemp"] == 21.2


# ---------------------------------------------------------------------------
# Issue #196: the RAC slider must follow the setpoint's minValue/maxValue
# ---------------------------------------------------------------------------


def _rac_setpoint(value, **bounds) -> dict:
    return {"id": "/airConditioning/temperatureSetpoint", "value": value, **bounds}


def test_rac_slider_bounds_follow_the_setpoint_range():
    """minValue/maxValue bound the slider; they are not a heat/cool range."""
    functions = [
        _rac_ref("operationMode", "heat"),
        _rac_setpoint(21.0, minValue=16.0, maxValue=30.0),
    ]
    climate = BoschComRacClimate(
        coordinator=_make_rac_coordinator(functions), field="clima"
    )

    assert climate.min_temp == 16.0
    assert climate.max_temp == 30.0
    assert climate.target_temperature == 21.0
    assert ClimateEntityFeature.TARGET_TEMPERATURE_RANGE not in (
        climate.supported_features
    )
    assert ClimateEntityFeature.TARGET_TEMPERATURE in climate.supported_features


def test_rac_slider_bounds_default_then_survive_setback():
    """Without bounds the slider is 16-30; bounds seen once outlive setback mode.

    While setback holds the unit at 10 °C the cloud sends the setpoint without
    minValue/maxValue, so the last known bounds stay and the target shows 10.
    """
    coordinator = _make_rac_coordinator(
        [_rac_ref("operationMode", "heat"), _rac_setpoint(22.0)]
    )
    climate = BoschComRacClimate(coordinator=coordinator, field="clima")
    assert (climate.min_temp, climate.max_temp) == (16.0, 30.0)

    coordinator.data.stardard_functions[:] = [
        _rac_ref("operationMode", "heat"),
        _rac_setpoint(22.0, minValue=18.0, maxValue=28.0),
    ]
    climate.set_attr()
    assert (climate.min_temp, climate.max_temp) == (18.0, 28.0)

    coordinator.data.stardard_functions[:] = [
        _rac_ref("operationMode", "heat"),
        _rac_setpoint(10.0),
    ]
    climate.set_attr()
    assert (climate.min_temp, climate.max_temp) == (18.0, 28.0)
    assert climate.target_temperature == 10.0


def test_rac_without_setpoint_keeps_a_target_to_render():
    """A payload with no temperatureSetpoint still renders a 22 °C target."""
    climate = BoschComRacClimate(
        coordinator=_make_rac_coordinator([_rac_ref("operationMode", "cool")]),
        field="clima",
    )

    assert climate.target_temperature == 22
    assert (climate.min_temp, climate.max_temp) == (16.0, 30.0)


# ---------------------------------------------------------------------------
# RRC2 zones: clock-mode setpoint changes go to the clock override (#88)
# ---------------------------------------------------------------------------


def _make_rrc2_coordinator(user_mode="clock", override=0.0, away="false"):
    """A CT200-style zone as the #88 dumps show it, plus the clock override."""
    zone = {
        "id": "/zones/zn1",
        "temperatureActual": {"value": 19.5, "unitOfMeasure": "C"},
        "temperatureHeatingSetpoint": {
            "value": 15.0,
            "minValue": 5.0,
            "maxValue": 30.0,
        },
        "manualTemperatureHeating": {
            "value": 21.5,
            "minValue": 5.0,
            "maxValue": 30.0,
            "stepSize": 0.5,
        },
        "clockOverrideTemperatureHeating": (
            {"value": override} if override is not None else None
        ),
        "userMode": {"value": user_mode},
    }
    coordinator = object.__new__(BoschComModuleCoordinatorRrc2)
    coordinator.unique_id = "rrc2123"
    coordinator.device_info = {"identifiers": {("bosch_homecom", "rrc2123")}}
    coordinator.bhc = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.device = {"deviceId": "rrc2123", "deviceType": "rrc2"}
    coordinator.data = BHCDeviceRrc2(
        device="rrc2123",
        firmware=[],
        notifications=[],
        zones=[zone],
        heating_circuits=None,
        dhw_circuits=None,
        heat_sources=None,
        away_mode={"value": away},
        outdoor_temp=None,
        indoor_humidity=None,
        devices=None,
        gateway_info=None,
        system_location=None,
    )
    return coordinator


def _make_zone_climate(coordinator):
    climate = BoschComRrc2ZoneClimate(coordinator=coordinator, field="zn1")
    climate.async_write_ha_state = MagicMock()
    return climate


async def test_rrc2_clock_mode_setpoint_writes_the_clock_override():
    """In AUTO the device follows its program; only the override changes it."""
    coordinator = _make_rrc2_coordinator(user_mode="clock")
    climate = _make_zone_climate(coordinator)

    await climate.async_set_temperature(temperature=22)

    coordinator.bhc.async_set_zone_clock_override_temp_heating.assert_awaited_once_with(
        "rrc2123", "zn1", 22
    )
    coordinator.bhc.async_set_zone_manual_temp_heating.assert_not_awaited()
    assert climate._attr_target_temperature == 22
    coordinator.async_request_refresh.assert_awaited_once()


async def test_rrc2_manual_mode_setpoint_writes_the_manual_temperature():
    coordinator = _make_rrc2_coordinator(user_mode="manual")
    climate = _make_zone_climate(coordinator)

    await climate.async_set_temperature(temperature=20.5)

    coordinator.bhc.async_set_zone_manual_temp_heating.assert_awaited_once_with(
        "rrc2123", "zn1", 20.5
    )
    coordinator.bhc.async_set_zone_clock_override_temp_heating.assert_not_awaited()


def test_rrc2_clock_mode_target_is_the_program_setpoint_without_override():
    """0 means no override: the program's setpoint is the target, as before."""
    climate = _make_zone_climate(_make_rrc2_coordinator(user_mode="clock"))

    assert climate.hvac_mode == HVACMode.AUTO
    assert climate.target_temperature == 15.0
    assert climate.extra_state_attributes == {
        "zone_name": None,
        "zone_icon": None,
        "scheduled_temperature": 15.0,
        "clock_override_active": False,
        "clock_override_temperature": None,
    }


def test_rrc2_clock_mode_target_is_the_override_while_active():
    """An override the user set shows as the target until the next switch point."""
    climate = _make_zone_climate(
        _make_rrc2_coordinator(user_mode="clock", override=22.0)
    )

    assert climate.target_temperature == 22.0
    assert climate.extra_state_attributes == {
        "zone_name": None,
        "zone_icon": None,
        "scheduled_temperature": 15.0,
        "clock_override_active": True,
        "clock_override_temperature": 22.0,
    }


def test_rrc2_manual_mode_ignores_a_stale_override():
    """In manual mode the manual setpoint is the target whatever the override says."""
    climate = _make_zone_climate(
        _make_rrc2_coordinator(user_mode="manual", override=22.0)
    )

    assert climate.hvac_mode == HVACMode.HEAT
    assert climate.target_temperature == 21.5


def test_rrc2_gateway_without_the_override_resource_behaves_as_before():
    """A firmware that 404s the override (None in the payload) changes nothing."""
    climate = _make_zone_climate(
        _make_rrc2_coordinator(user_mode="clock", override=None)
    )

    assert climate.target_temperature == 15.0
    assert climate.extra_state_attributes["clock_override_active"] is False


# ---------------------------------------------------------------------------
# Data the library fetched but nothing showed (gap analysis item 4)
# ---------------------------------------------------------------------------


def test_rrc2_zone_name_and_icon_are_attributes_not_the_name():
    """The room name the user gave the zone rides along; the entity name stays."""
    coordinator = _make_rrc2_coordinator(user_mode="clock")
    zone = coordinator.data.zones[0]
    zone["name"] = {"value": "Living room"}
    zone["icon"] = {"value": "livingroom"}
    climate = _make_zone_climate(coordinator)

    assert climate.translation_placeholders == {"zone": "zn1"}
    attrs = climate.extra_state_attributes
    assert attrs["zone_name"] == "Living room"
    assert attrs["zone_icon"] == "livingroom"


def test_rrc2_zone_without_name_reports_none():
    climate = _make_zone_climate(_make_rrc2_coordinator(user_mode="clock"))
    assert climate.extra_state_attributes["zone_name"] is None
    assert climate.extra_state_attributes["zone_icon"] is None


def test_rac_schedule_override_attribute_follows_temporary_setting():
    """switchPrograms/temporarySetting/enabled says a manual change holds."""
    coordinator = _make_rac_coordinator(_FULL_RAC_FUNCTIONS)
    climate = BoschComRacClimate(coordinator=coordinator, field="ac")
    assert climate.extra_state_attributes == {}

    coordinator.data = replace(
        coordinator.data,
        switch_programs=[
            {"id": "/airConditioning/switchPrograms/activeProgram", "value": "1"},
            {
                "id": "/airConditioning/switchPrograms/temporarySetting/enabled",
                "value": "on",
            },
        ],
    )
    assert climate.extra_state_attributes == {"schedule_override_active": True}

    coordinator.data.switch_programs[1]["value"] = "off"
    assert climate.extra_state_attributes == {"schedule_override_active": False}


def test_icom_temporary_setpoint_attributes():
    """An icom shows the setpoint it holds until the next switch point."""
    coordinator = _make_icom_coordinator(suwi="heating", operation_mode="auto")
    hc1 = {
        **coordinator.data.heating_circuits[0],
        "temporaryRoomSetpoint": {"value": 23},
    }
    coordinator.data = replace(coordinator.data, heating_circuits=[hc1])
    climate = _make_climate(coordinator)

    assert climate.extra_state_attributes == {
        "temporary_room_setpoint": 23,
        "temporary_setpoint_active": True,
    }

    # 0 is "off" and -1 clears it: neither is an active override.
    for idle in (0, -1):
        hc1 = {**hc1, "temporaryRoomSetpoint": {"value": idle}}
        coordinator.data = replace(coordinator.data, heating_circuits=[hc1])
        assert climate.extra_state_attributes == {
            "temporary_room_setpoint": None,
            "temporary_setpoint_active": False,
        }


def test_k40_circuit_without_the_node_has_no_temporary_attributes():
    coordinator = _make_k40_coordinator(suwi="forced", heatcool="heating")
    assert _make_climate(coordinator).extra_state_attributes == {}
