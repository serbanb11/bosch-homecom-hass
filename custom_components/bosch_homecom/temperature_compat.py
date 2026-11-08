"""Native temperature attributes on Home Assistant releases before 2026.11.

Home Assistant 2026.11 moved climate and water heater entities to native
temperature members (``native_temperature_unit``, ``native_current_temperature``,
``native_target_temperature`` and their ``_attr_native_*`` attributes) and
deprecated the old names, which stop working in 2027.11.

The entities of this integration only provide the native members. Older
releases read the old names, so on those the mixins below serve the old names
from the native members. On 2026.11 and later the mixins are empty: the entity
base classes serve the native members themselves, and a plain class attribute
in front of them would bypass their cached properties.

Remove this module once the minimum supported Home Assistant release is 2026.11.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.water_heater import WaterHeaterEntity


class _LegacyTemperatureNames:
    """Serve the pre-2026.11 temperature names from the native members."""

    _attr_native_current_temperature: float | None = None
    _attr_native_target_temperature: float | None = None
    _attr_native_temperature_unit: str

    @property
    def native_temperature_unit(self) -> str:
        """Return the unit the entity reports temperatures in."""
        return self._attr_native_temperature_unit

    @property
    def native_current_temperature(self) -> float | None:
        """Return the current temperature in the native unit."""
        return self._attr_native_current_temperature

    @property
    def native_target_temperature(self) -> float | None:
        """Return the target temperature in the native unit."""
        return self._attr_native_target_temperature

    @property
    def temperature_unit(self) -> str:
        """Return the unit, under the name Home Assistant < 2026.11 reads."""
        return self.native_temperature_unit

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature, under the old name."""
        return self.native_current_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature, under the old name."""
        return self.native_target_temperature


class _NoLegacyTemperatureNames:
    """Nothing to add: the entity base class serves the native members."""


def temperature_compat_for(entity_class: type) -> type:
    """Return the mixin an entity built on entity_class needs."""
    if hasattr(entity_class, "native_temperature_unit"):
        return _NoLegacyTemperatureNames
    return _LegacyTemperatureNames


if TYPE_CHECKING:

    class ClimateTemperatureCompat:
        """Native temperature attributes, as seen by the type checker."""

        _attr_native_current_temperature: float | None
        _attr_native_target_temperature: float | None
        _attr_native_temperature_unit: str

    class WaterHeaterTemperatureCompat(ClimateTemperatureCompat):
        """Native temperature attributes, as seen by the type checker."""

else:
    ClimateTemperatureCompat = temperature_compat_for(ClimateEntity)
    WaterHeaterTemperatureCompat = temperature_compat_for(WaterHeaterEntity)
