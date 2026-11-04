"""Sensors that only exist over the K 40 RF Local API.

These read ``coordinator.local_data`` rather than ``coordinator.data``, so they
keep updating while the Bosch cloud is failing. They are only created when local
access is configured for the gateway, which means a cloud-only installation sees
no new entities at all.

Every resource here is genuinely absent from the cloud API — real electrical
power draw, the refrigerant circuit, and the per-mode start/runtime split — which
is the reason the local transport is worth having beyond reliability.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
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

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class LocalSensorDescription(SensorEntityDescription):
    """Describes one local-API sensor.

    ``resource`` is the Local API path. ``field`` picks a single key out of an
    ``emonValue`` payload's ``values`` list (e.g. the ``dhw`` entry of
    ``numberOfStarts``); when it is ``None`` the payload's scalar ``value`` is
    used.

    Must stay a SensorEntityDescription: it is the entity's
    ``entity_description``, from which Home Assistant reads fields such as
    ``suggested_unit_of_measurement`` while adding the entity (issue #184).
    """

    resource: str
    field: str | None = None
    fallback_resources: tuple[str, ...] = ()


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
        fallback_resources=("/heatSources/hs1/refrigerant/compressorElecPowerActual",),
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
        resource="/heatSources/hs1/pumpVolumeFlow",
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
        fallback_resources=("/heatSources/numberOfStarts",),
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_starts_dhw",
        translation_key="local_starts_dhw",
        resource="/heatSources/hs1/numberOfStarts",
        field="dhw",
        fallback_resources=("/heatSources/numberOfStarts",),
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

# Additional Local API values that have no equivalent Home Assistant entity.
# Overlapping values are merged into the existing cloud-backed entities in the
# coordinator instead, so the device does not acquire duplicate sensors.
LOCAL_EXTRA_SENSORS: tuple[LocalSensorDescription, ...] = (
    LocalSensorDescription(
        key="local_system_type",
        translation_key="local_system_type",
        resource="/system/type",
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_system_bus",
        translation_key="local_system_bus",
        resource="/system/bus",
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_power_limitation",
        translation_key="local_power_limitation",
        resource="/system/powerLimitation/active",
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_silent_mode_status",
        translation_key="local_silent_mode_status",
        resource="/system/powerConstraints/silentMode/status",
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_em_status",
        translation_key="local_em_status",
        resource="/heatSources/emStatus",
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_additional_heater_flow_temp",
        translation_key="local_additional_heater_flow_temp",
        resource="/heatSources/additionalHeater/flowTemp",
        device_class=_TEMP,
        native_unit_of_measurement=_CELSIUS,
        state_class=_MEASUREMENT,
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_refrigerant_status",
        translation_key="local_refrigerant_status",
        resource="/heatSources/hs1/refrigerant/status",
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_dhw_current_setpoint",
        translation_key="local_dhw_current_setpoint",
        resource="/dhwCircuits/dhw1/currentSetpoint",
        device_class=_TEMP,
        native_unit_of_measurement=_CELSIUS,
        state_class=_MEASUREMENT,
        entity_category=_DIAGNOSTIC,
    ),
    LocalSensorDescription(
        key="local_dhw_thermal_disinfection",
        translation_key="local_dhw_thermal_disinfection",
        resource="/dhwCircuits/dhw1/tdrunningStatus",
        entity_category=_DIAGNOSTIC,
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


class BoschComLocalSensor(CoordinatorEntity, SensorEntity):
    """A sensor backed by a single K 40 RF Local API resource."""

    entity_description: LocalSensorDescription
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, config_entry, description) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
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
        for path in (
            self.entity_description.resource,
            *self.entity_description.fallback_resources,
        ):
            payload = resources.get(path)
            if not isinstance(payload, dict):
                continue
            if self.entity_description.field is not None:
                value = _emon_field(
                    payload.get("values"), self.entity_description.field
                )
            else:
                value = payload.get("value")
            if value is not None:
                self._attr_native_value = value
                return
        self._attr_native_value = None

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


class BoschComLocalSystemInfoSensor(CoordinatorEntity, SensorEntity):
    """Summarize the concrete module models and firmware reported by the gateway."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "local_system_info"
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize the gateway-information sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}-local_system_info"
        self._attr_device_info = coordinator.device_info
        self._config_entry = config_entry

    @property
    def native_value(self) -> str | None:
        """Return a compact model/firmware summary for direct UI display."""
        info = self.coordinator.local_system_info
        if not isinstance(info, dict):
            return None
        modules = info.get("values")
        if not isinstance(modules, list):
            return None
        summary = []
        for module in modules:
            if not isinstance(module, dict):
                continue
            name = (
                module.get("ProductName")
                or module.get("ModuleHwIdentStr")
                or module.get("Id")
            )
            version = module.get("Ver")
            if name is not None:
                summary.append(
                    f"{name} ({version})" if version is not None else str(name)
                )
        return "; ".join(summary)[:255] or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the complete basicInfo response without a fixed field schema."""
        info = self.coordinator.local_system_info
        return dict(info) if isinstance(info, dict) else {}

    def _handle_coordinator_update(self) -> None:
        """Write updated metadata after the coordinator refreshes it."""
        self.async_write_ha_state()


def local_module_key(module: dict[str, Any], index: int) -> str:
    """Return a stable key for a module, including repeated module IDs."""
    identity = [module.get("Id"), module.get("Tok")]
    identity = [str(value) for value in identity if value is not None]
    if not identity:
        serial = module.get("ModuleSerialNumber") or module.get("ProductSerialNumber")
        identity = [str(serial)] if serial is not None else [f"index-{index}"]
    return re.sub(r"[^a-zA-Z0-9_-]", "_", "-".join(identity))


class BoschComLocalModuleSensor(CoordinatorEntity, SensorEntity):
    """Show one gateway module's complete basicInfo record as its state."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "local_module_details"
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator, config_entry, module: dict, index: int) -> None:
        """Initialize a sensor for one reported module."""
        super().__init__(coordinator)
        self._module_key = local_module_key(module, index)
        name = (
            module.get("ProductName")
            or module.get("ModuleHwIdentStr")
            or f"Module {module.get('Id', index + 1)}"
        )
        module_id = module.get("Id")
        token = module.get("Tok")
        if module_id is not None or token is not None:
            name = f"{name} ({module_id or '-'} / {token or '-'})"
        self._attr_translation_placeholders = {"module": str(name)}
        self._attr_unique_id = (
            f"{coordinator.unique_id}-local-module-{self._module_key}"
        )
        self._attr_device_info = coordinator.device_info
        self._config_entry = config_entry

    def _module(self) -> dict[str, Any] | None:
        """Find this module in the latest gateway response."""
        info = self.coordinator.local_system_info
        modules = info.get("values") if isinstance(info, dict) else None
        if not isinstance(modules, list):
            return None
        for index, module in enumerate(modules):
            if (
                isinstance(module, dict)
                and local_module_key(module, index) == self._module_key
            ):
                return module
        return None

    @property
    def available(self) -> bool:
        """Report availability while this module is in the current payload."""
        return self._module() is not None

    @property
    def native_value(self) -> str | None:
        """Return every scalar field so details are visible without opening attributes."""
        module = self._module()
        if module is None:
            return None
        fields = [
            f"{key}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"
            for key, value in module.items()
            if value is not None
        ]
        return "; ".join(fields)[:255] or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Keep the unabridged module record available in entity attributes."""
        return dict(self._module() or {})

    def _handle_coordinator_update(self) -> None:
        """Write the module's latest fields after a coordinator refresh."""
        self.async_write_ha_state()
