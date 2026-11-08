"""Sensors that only exist over the K 40 RF Local API.

These read ``coordinator.local_data`` rather than ``coordinator.data``, so they
keep updating while the Bosch cloud is failing. They are only created when local
access is configured for the gateway, which means a cloud-only installation sees
no new entities at all.

Every resource here is absent from the K40 cloud entities — real electrical
power draw, the refrigerant circuit, the per-mode start/runtime split, setpoints
and system state — which is the reason the local transport is worth having
beyond reliability.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import HC1_PUMP_VOLUME_FLOW

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class LocalSensorDescription(SensorEntityDescription):
    """Describes one local-API sensor.

    ``resource`` is the Local API path. ``field`` picks a single key out of an
    ``emonValue`` payload's ``values`` list (e.g. the ``dhw`` entry of
    ``numberOfStarts``); when it is ``None`` the payload's scalar ``value`` is
    used.

    ``fallback_resources`` are read, in order, when ``resource`` is absent on
    this appliance. A number the payload declares as a named state (e.g.
    ``{"LOW_FLOW": 65535}`` or ``[{"open": -32768}, {"short": 32767}]``) is a
    marker, not a reading: the value becomes None, which makes the entity
    unavailable (see ``available``) instead of showing the raw number. This
    does not suit a resource whose state map names the readings themselves,
    as some ``/signals`` do (``{"ON": 1, "OFF": 0}``); none is read here.
    ``invalid_values`` are sentinels that carry no state list, such as the
    -3276.8 W of an absent power reading.

    ``states`` maps the gateway's raw strings to translatable state keys and
    makes the sensor an enum of those keys; a raw value outside the map is no
    reading rather than an invalid enum state.

    Must stay a SensorEntityDescription: it is the entity's
    ``entity_description``, from which Home Assistant reads fields such as
    ``suggested_unit_of_measurement`` while adding the entity (issue #184).
    """

    resource: str
    field: str | None = None
    fallback_resources: tuple[str, ...] = ()
    invalid_values: tuple[float, ...] = ()
    states: dict[str, str] | None = None


_TEMP = SensorDeviceClass.TEMPERATURE
_CELSIUS = UnitOfTemperature.CELSIUS
_MEASUREMENT = SensorStateClass.MEASUREMENT
_DIAGNOSTIC = EntityCategory.DIAGNOSTIC

LOCAL_SENSORS: tuple[LocalSensorDescription, ...] = (
    # --- real electrical power: not available from the cloud at all ----------
    LocalSensorDescription(
        key="local_compressor_power",
        translation_key="local_compressor_power",
        resource="/heatSources/compressor/powerElecActual",
        # Gateways without the aggregate serve the refrigerant circuit's own
        # reading, whose absent value is the -3276.8 W sentinel (API spec).
        fallback_resources=("/heatSources/hs1/refrigerant/compressorElecPowerActual",),
        invalid_values=(-3276.8,),
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=_MEASUREMENT,
    ),
    LocalSensorDescription(
        key="local_eheater_power",
        translation_key="local_eheater_power",
        resource="/heatSources/eHeater/powerElecActual",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=_MEASUREMENT,
    ),
    # --- refrigerant circuit -------------------------------------------------
    LocalSensorDescription(
        key="local_hot_gas_temp",
        translation_key="local_hot_gas_temp",
        resource="/heatSources/hs1/refrigerant/hotGasTemp",
        device_class=_TEMP,
        native_unit_of_measurement=_CELSIUS,
        state_class=_MEASUREMENT,
    ),
    LocalSensorDescription(
        key="local_suction_gas_temp",
        translation_key="local_suction_gas_temp",
        resource="/heatSources/hs1/refrigerant/suctionGasTemp",
        device_class=_TEMP,
        native_unit_of_measurement=_CELSIUS,
        state_class=_MEASUREMENT,
    ),
    LocalSensorDescription(
        key="local_compressor_temp",
        translation_key="local_compressor_temp",
        resource="/heatSources/hs1/refrigerant/compressorTemp",
        device_class=_TEMP,
        native_unit_of_measurement=_CELSIUS,
        state_class=_MEASUREMENT,
    ),
    LocalSensorDescription(
        key="local_high_pressure_temp",
        translation_key="local_high_pressure_temp",
        resource="/heatSources/hs1/refrigerant/highPressureTemp",
        device_class=_TEMP,
        native_unit_of_measurement=_CELSIUS,
        state_class=_MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    LocalSensorDescription(
        key="local_low_pressure_temp",
        translation_key="local_low_pressure_temp",
        resource="/heatSources/hs1/refrigerant/lowPressureTemp",
        device_class=_TEMP,
        native_unit_of_measurement=_CELSIUS,
        state_class=_MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    LocalSensorDescription(
        key="local_condenser_supply_temp",
        translation_key="local_condenser_supply_temp",
        resource="/heatSources/hs1/supplyFlowCondenserTemp",
        device_class=_TEMP,
        native_unit_of_measurement=_CELSIUS,
        state_class=_MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    LocalSensorDescription(
        key="local_compressor_speed",
        translation_key="local_compressor_speed",
        resource="/heatSources/hs1/refrigerant/compressorActualSpeed",
        native_unit_of_measurement="%",
        state_class=_MEASUREMENT,
    ),
    LocalSensorDescription(
        key="local_odu_fan_speed",
        translation_key="local_odu_fan_speed",
        resource="/heatSources/hs1/oduFanSpeed",
        native_unit_of_measurement="%",
        state_class=_MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    LocalSensorDescription(
        key="local_pump_volume_flow",
        translation_key="local_pump_volume_flow",
        # The heating-circuit signal carries the measured flow. On a K 40 RF
        # with a CS5800iAW the heat source resource reports its LOW_FLOW marker
        # (65535) nearly all the time, while the signal matches the HMI.
        resource=HC1_PUMP_VOLUME_FLOW,
        fallback_resources=("/heatSources/hs1/pumpVolumeFlow",),
        # The gateway reports l/h (API spec: unitOfMeasure "l/h").
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_HOUR,
        state_class=_MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # --- per-mode counters: the cloud only exposes the totals ----------------
    LocalSensorDescription(
        key="local_starts_ch",
        translation_key="local_starts_ch",
        resource="/heatSources/hs1/numberOfStarts",
        field="ch",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_starts_dhw",
        translation_key="local_starts_dhw",
        resource="/heatSources/hs1/numberOfStarts",
        field="dhw",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_runtime_ch",
        translation_key="local_runtime_ch",
        resource="/heatSources/hs1/workingTime",
        field="ch",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_runtime_dhw",
        translation_key="local_runtime_dhw",
        resource="/heatSources/hs1/workingTime",
        field="dhw",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=_DIAGNOSTIC,
    ),
)


# Resources not every gateway serves. Unlike LOCAL_SENSORS, these are created
# only once the gateway answers for them, so a system without, say, an energy
# manager gets no permanently unavailable entity. States follow the
# allowedValues of the K 40 RF OpenAPI spec.
LOCAL_OPTIONAL_SENSORS: tuple[LocalSensorDescription, ...] = (
    LocalSensorDescription(
        key="local_refrigerant_status",
        translation_key="local_refrigerant_status",
        resource="/heatSources/hs1/refrigerant/status",
        states={
            "idle": "idle",
            "startup": "startup",
            "heating": "heating",
            "cooling": "cooling",
            "defrost": "defrost",
            "passive_defrost": "passive_defrost",
            "shutoff": "shutoff",
            "alarm": "alarm",
            "test_mode": "test_mode",
        },
    ),
    LocalSensorDescription(
        key="local_supply_setpoint",
        translation_key="local_supply_setpoint",
        resource="/heatSources/currentSupplySetpoint",
        device_class=_TEMP,
        native_unit_of_measurement=_CELSIUS,
        state_class=_MEASUREMENT,
    ),
    LocalSensorDescription(
        key="local_dhw_current_setpoint",
        translation_key="local_dhw_current_setpoint",
        resource="/dhwCircuits/dhw1/currentSetpoint",
        device_class=_TEMP,
        native_unit_of_measurement=_CELSIUS,
        state_class=_MEASUREMENT,
    ),
    LocalSensorDescription(
        key="local_additional_heater_flow_temp",
        translation_key="local_additional_heater_flow_temp",
        resource="/heatSources/additionalHeater/flowTemp",
        device_class=_TEMP,
        native_unit_of_measurement=_CELSIUS,
        state_class=_MEASUREMENT,
    ),
    LocalSensorDescription(
        key="local_em_status",
        translation_key="local_em_status",
        resource="/heatSources/emStatus",
        entity_category=_DIAGNOSTIC,
        states={
            "notConnected": "not_connected",
            "inactive": "inactive",
            "activeCh": "active_ch",
            "activeDHW": "active_dhw",
        },
    ),
    LocalSensorDescription(
        key="local_system_type",
        translation_key="local_system_type",
        resource="/system/type",
        entity_category=_DIAGNOSTIC,
        entity_registry_enabled_default=False,
        states={
            "unknown": "unknown",
            "heatpump_cascade": "heatpump_cascade",
            "heatpump_single": "heatpump_single",
            "eHybrid": "e_hybrid",
            "hybman": "hybman",
            "hybridBoiler": "hybrid_boiler",
            "boiler": "boiler",
        },
    ),
    LocalSensorDescription(
        key="local_system_bus",
        translation_key="local_system_bus",
        resource="/system/bus",
        entity_category=_DIAGNOSTIC,
        entity_registry_enabled_default=False,
        states={"No_Bus": "no_bus", "EMS2_0": "ems2_0", "Detecting": "detecting"},
    ),
)


def _emon_field(values: Any, field: str) -> Any | None:
    """Pull one named key out of an emonValue ``values`` list.

    The gateway returns e.g. ``[{"ch": 149}, {"dhw": 129}, {"total": 278}]``.
    """
    if not isinstance(values, list):
        return None
    for item in values:
        if isinstance(item, dict) and field in item:
            return item[field]
    return None


def _state_values(state: Any) -> set[Any]:
    """Collect the values a payload declares as named states.

    The gateway uses both ``{"LOW_FLOW": 65535}`` and ``[{"lowflow": 65535}]``.
    """
    items = state if isinstance(state, list) else [state]
    return {
        value
        for item in items
        if isinstance(item, dict)
        for value in item.values()
        if isinstance(value, (int, float, str))
    }


class BoschComLocalSensor(CoordinatorEntity, SensorEntity):
    """A sensor backed by a single K 40 RF Local API resource."""

    entity_description: LocalSensorDescription
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, config_entry, description) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        if description.states is not None:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(dict.fromkeys(description.states.values()))
        self._attr_unique_id = f"{coordinator.unique_id}-{description.key}"
        self._attr_device_info = coordinator.device_info
        self._config_entry = config_entry
        self.set_attr()

    @property
    def available(self) -> bool:
        """Return True while the local transport is healthy and has a value.

        Deliberately independent of the cloud: that is the whole point of these
        entities. They stay available through a cloud outage and go unavailable
        only when the gateway itself stops answering.
        """
        return bool(
            getattr(self.coordinator, "local_healthy", False)
            and self._attr_native_value is not None
        )

    def set_attr(self) -> None:
        """Read this sensor's value out of the local payload."""
        local = getattr(self.coordinator, "local_data", None)
        resources = getattr(local, "resources", None) or {}
        description = self.entity_description
        payload = next(
            (
                resources[path]
                for path in (description.resource, *description.fallback_resources)
                if isinstance(resources.get(path), dict)
            ),
            None,
        )
        if payload is None:
            self._attr_native_value = None
            return

        if description.field is not None:
            self._attr_native_value = _emon_field(
                payload.get("values"), description.field
            )
            return
        value = payload.get("value")
        if isinstance(value, (int, float)) and value in _state_values(
            payload.get("state")
        ):
            value = None
        if value in description.invalid_values:
            value = None
        if description.states is not None:
            value = description.states.get(value) if isinstance(value, str) else None
        self._attr_native_value = value

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.set_attr()
        self.async_write_ha_state()


class BoschComLocalSourceSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic sensor reporting which transport served the last update.

    Values: ``both``, ``local`` (the cloud failed and local carried the update),
    or ``cloud`` (the gateway did not answer locally). Useful for telling a cloud
    outage apart from a LAN problem without reading the log.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "local_data_source"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["both", "local", "cloud"]

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}-local_data_source"
        self._attr_device_info = coordinator.device_info
        self._config_entry = config_entry
        self.set_attr()

    def set_attr(self) -> None:
        """Read the active source off the coordinator."""
        self._attr_native_value = getattr(self.coordinator, "local_source", None)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.set_attr()
        self.async_write_ha_state()
