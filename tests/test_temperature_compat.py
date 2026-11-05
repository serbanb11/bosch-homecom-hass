"""Tests for the native temperature attributes on older Home Assistant releases."""

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.water_heater import WaterHeaterEntity
from homeassistant.const import UnitOfTemperature

from custom_components.bosch_homecom.temperature_compat import (
    ClimateTemperatureCompat,
    WaterHeaterTemperatureCompat,
    _LegacyTemperatureNames,
    _NoLegacyTemperatureNames,
    temperature_compat_for,
)


class _OldEntity:
    """An entity base class from before Home Assistant 2026.11."""


class _NewEntity:
    """An entity base class from Home Assistant 2026.11 on."""

    native_temperature_unit = UnitOfTemperature.CELSIUS


class _Climate(ClimateTemperatureCompat, ClimateEntity):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS


class _WaterHeater(WaterHeaterTemperatureCompat, WaterHeaterEntity):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS


def test_old_base_gets_the_legacy_names():
    assert temperature_compat_for(_OldEntity) is _LegacyTemperatureNames


def test_new_base_gets_nothing():
    assert temperature_compat_for(_NewEntity) is _NoLegacyTemperatureNames
    assert not [
        name for name in vars(_NoLegacyTemperatureNames) if not name.startswith("__")
    ]


def test_legacy_names_follow_the_native_attributes():
    entity = _LegacyTemperatureNames()
    assert entity.current_temperature is None
    assert entity.target_temperature is None

    entity._attr_native_temperature_unit = UnitOfTemperature.FAHRENHEIT
    entity._attr_native_current_temperature = 68.5
    entity._attr_native_target_temperature = 70

    assert entity.temperature_unit == UnitOfTemperature.FAHRENHEIT
    assert entity.current_temperature == 68.5
    assert entity.target_temperature == 70


def test_legacy_names_follow_overridden_native_properties():
    class _Entity(_LegacyTemperatureNames):
        @property
        def native_current_temperature(self) -> float | None:
            return 23.5

        @property
        def native_target_temperature(self) -> float | None:
            return 24

    entity = _Entity()
    assert entity.current_temperature == 23.5
    assert entity.target_temperature == 24


def test_climate_reports_the_native_values_on_this_release():
    entity = _Climate()
    entity._attr_native_current_temperature = 21.2
    entity._attr_native_target_temperature = 22

    assert entity.native_temperature_unit == UnitOfTemperature.CELSIUS
    assert entity.native_current_temperature == 21.2
    assert entity.native_target_temperature == 22
    if ClimateTemperatureCompat is _LegacyTemperatureNames:
        # What Home Assistant < 2026.11 reads; deprecated from 2026.11 on.
        assert entity.temperature_unit == UnitOfTemperature.CELSIUS
        assert entity.current_temperature == 21.2
        assert entity.target_temperature == 22


def test_water_heater_reports_the_native_values_on_this_release():
    entity = _WaterHeater()
    entity._attr_native_current_temperature = 51.5
    entity._attr_native_target_temperature = 55

    assert entity.native_temperature_unit == UnitOfTemperature.CELSIUS
    assert entity.native_current_temperature == 51.5
    assert entity.native_target_temperature == 55
    if WaterHeaterTemperatureCompat is _LegacyTemperatureNames:
        # What Home Assistant < 2026.11 reads; deprecated from 2026.11 on.
        assert entity.temperature_unit == UnitOfTemperature.CELSIUS
        assert entity.current_temperature == 51.5
        assert entity.target_temperature == 55
