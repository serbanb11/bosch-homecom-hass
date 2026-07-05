"""Bosch HomeCom Custom Component."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Any, Optional

from homeassistant import config_entries, core
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BOSCH_SENSOR_DESCRIPTORS, WDDW2_NOTIFICATION_CODES
from .coordinator import (
    BoschComModuleCoordinatorCommodule,
    BoschComModuleCoordinatorIcom,
    BoschComModuleCoordinatorK40,
    BoschComModuleCoordinatorRac,
    BoschComModuleCoordinatorRrc2,
    BoschComModuleCoordinatorWddw2,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1440)
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the K40/RAC/WDDW2 sensors."""
    coordinators = config_entry.runtime_data
    entities: list[SensorEntity] = []

    def _resolve_path(path: list[str], dhw_id: str | None) -> list[str]:
        """Return a path with {dhw_id} placeholders replaced, if any."""
        if dhw_id is None:
            return path
        resolved = []
        for p in path:
            resolved.append(p.format(dhw_id=dhw_id) if "{" in p else p)
        return resolved

    for coordinator in coordinators:
        device_type = coordinator.data.device.get("deviceType")

        # ---- Notifications per device type (existing) ----
        if device_type == "rac":
            entities.append(
                BoschComSensorNotificationsRac(
                    coordinator=coordinator, config_entry=config_entry
                )
            )
        elif device_type in ("k40", "k30", "icom", "rrc2"):
            entities.append(
                BoschComSensorNotificationsK40(
                    coordinator=coordinator, config_entry=config_entry
                )
            )
        elif device_type == "wddw2":
            entities.append(
                BoschComSensorNotificationsWddw2(
                    coordinator=coordinator, config_entry=config_entry
                )
            )

        # ---- K40/K30/ICOM (shared subset: dhw, ventilation, heating, hs) ----
        if device_type in ("k40", "k30", "icom"):
            # DHW circuits
            for ref in coordinator.data.dhw_circuits:
                dhw_id = ref["id"].split("/")[-1]
                entities.append(
                    BoschComSensorDhw(
                        coordinator=coordinator, config_entry=config_entry, field=dhw_id
                    )
                )
            # Ventilation
            for ref in coordinator.data.ventilation:
                zone_id = ref["id"].split("/")[-1]
                entities.append(
                    BoschComSensorVentilation(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        field=zone_id,
                    )
                )
            # Heating circuits
            for ref in coordinator.data.heating_circuits:
                hc_id = ref["id"].split("/")[-1]
                entities.append(
                    BoschComSensorHc(
                        coordinator=coordinator, config_entry=config_entry, field=hc_id
                    )
                )
            # Heat source
            entities.append(
                BoschComSensorHs(
                    coordinator=coordinator,
                    config_entry=config_entry,
                    field="heat_source",
                )
            )

        # ---- K40/K30 only (icom does not expose these fields) ----
        if device_type in ("k40", "k30"):
            entities.append(
                BoschComSensorOutdoorTemp(
                    coordinator=coordinator,
                    config_entry=config_entry,
                    field="outdoor_temp",
                )
            )
            # Indoor humidity
            if coordinator.data.indoor_humidity:
                entities.append(
                    BoschComSensorIndoorHumidity(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        field="indoor_humidity",
                    )
                )
            # Flame indication
            if coordinator.data.flame_indication:
                entities.append(
                    BoschComSensorFlameIndication(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        field="flame_indication",
                    )
                )
            # Energy history
            if coordinator.data.energy_history:
                entities.append(
                    BoschComSensorEnergyHistory(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        field="energy_history",
                    )
                )
            # Hourly energy history
            if coordinator.data.hourly_energy_history:
                entities.append(
                    BoschComSensorEnergyHistoryHourly(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        field="energy_history_hourly",
                    )
                )

            # Thermostat device sensors
            for dev in coordinator.data.devices or []:
                dev_id = dev["id"].split("/")[-1]
                if dev.get("roomtemperature"):
                    entities.append(
                        BoschComThermostatRoomTempSensor(
                            coordinator, config_entry, dev_id
                        )
                    )
                if dev.get("actualHumidity"):
                    entities.append(
                        BoschComThermostatHumiditySensor(
                            coordinator, config_entry, dev_id
                        )
                    )
                if dev.get("currentRoomSetpoint"):
                    entities.append(
                        BoschComThermostatSetpointSensor(
                            coordinator, config_entry, dev_id
                        )
                    )
                if dev.get("battery"):
                    entities.append(
                        BoschComThermostatBatterySensor(
                            coordinator, config_entry, dev_id
                        )
                    )
                if dev.get("signal"):
                    entities.append(
                        BoschComThermostatSignalSensor(
                            coordinator, config_entry, dev_id
                        )
                    )

        # ---- ICOM diagnostic extras (healthStatus, brand, hs return/starts) ----
        if device_type == "icom":
            entities.extend(_build_icom_extra_sensors(coordinator))

        # ---- RRC2 (zone / hc / dhw / heat sources / system / gateway) ----
        if device_type == "rrc2":
            for sensor in _build_rrc2_sensors(coordinator, config_entry):
                entities.append(sensor)

        # ---- WDDW2 (existing DHW sensor + NEW generic + NEW derived) ----
        elif device_type == "wddw2":
            # Existing per-circuit DHW sensor
            for ref in coordinator.data.dhw_circuits:
                dhw_id = ref["id"].split("/")[-1]
                if re.fullmatch(r"dhw\d", dhw_id):
                    entities.append(
                        BoschComSensorDhwWddw2(
                            coordinator=coordinator,
                            config_entry=config_entry,
                            field=dhw_id,
                        )
                    )

            # Issue #129: surface heat-source + water totals (top-level paths).
            entities.extend(_build_wddw2_totals_sensors(coordinator))

            # NEW: generic sensors from descriptors (BOSCH_SENSOR_DESCRIPTORS["wddw2"])
            wddw2_desc = BOSCH_SENSOR_DESCRIPTORS.get("wddw2", [])
            if wddw2_desc:
                # If descriptors are per-circuit, try to expand per each dhwX
                dhw_ids = [
                    ref["id"].split("/")[-1]
                    for ref in coordinator.data.dhw_circuits
                    if re.fullmatch(r"dhw\d", ref["id"].split("/")[-1])
                ] or [
                    None
                ]  # fallback to single set if not per circuit

                for desc in wddw2_desc:
                    for dhw_id in dhw_ids:
                        path = desc.get("path", [])
                        resolved_path = _resolve_path(path, dhw_id)
                        unique_suffix = (
                            f"{(dhw_id or 'dhw')}-{desc['key']}"
                            if dhw_id
                            else f"dhw-{desc['key']}"
                        )
                        try:
                            entities.append(
                                BoschComGenericSensor(
                                    coordinator=coordinator,
                                    name=desc["name"],
                                    unique_suffix=unique_suffix,
                                    path=resolved_path,
                                    unit=desc.get("unit"),
                                    device_class=desc.get("device_class"),
                                    state_class=desc.get("state_class"),
                                    translation_key=desc.get("translation_key"),
                                    entity_category=desc.get("entity_category"),
                                )
                            )
                        except Exception:  # keep onboarding even if one fails
                            _LOGGER.debug(
                                "Failed to add generic sensor %s", unique_suffix
                            )

            # NEW: derived sensors (single set; adjust to per-circuit if precisares)
            try:
                entities.append(
                    BoschComDerivedDeltaTSensor(
                        coordinator=coordinator,
                        name="DHW Delta T",
                        unique_suffix="dhw1-delta_t",
                    )
                )
            except Exception:
                _LOGGER.debug("Failed to add DHW Delta T derived sensor")

            try:
                entities.append(
                    BoschComHeatingActiveBinarySensor(
                        coordinator=coordinator,
                        name="DHW Heating Active",
                        unique_suffix="dhw1-heating_active",
                        delta_t_threshold=3.0,
                    )
                )
            except Exception:
                _LOGGER.debug("Failed to add DHW Heating Active binary sensor")

        # ---- Commodule (EV Charger) ----
        elif device_type == "commodule":
            for cp in coordinator.data.charge_points or []:
                cp_id = cp["id"].split("/")[-1]
                raw_telemetry = cp.get("telemetry") or {}
                telemetry = raw_telemetry.get("values", raw_telemetry)
                if not isinstance(telemetry, dict):
                    telemetry = {}
                entities.append(
                    BoschComCommoduleStateSensor(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        cp_id=cp_id,
                    )
                )
                if telemetry.get("actualPower") is not None:
                    entities.append(
                        BoschComCommodulePowerSensor(
                            coordinator=coordinator,
                            config_entry=config_entry,
                            cp_id=cp_id,
                        )
                    )
                if telemetry.get("energyTotal") is not None:
                    entities.append(
                        BoschComCommoduleEnergySensor(
                            coordinator=coordinator,
                            config_entry=config_entry,
                            cp_id=cp_id,
                        )
                    )
                if telemetry.get("temp") is not None:
                    entities.append(
                        BoschComCommoduleTempSensor(
                            coordinator=coordinator,
                            config_entry=config_entry,
                            cp_id=cp_id,
                        )
                    )
                if telemetry.get("phases") is not None:
                    entities.append(
                        BoschComCommodulePhasesSensor(
                            coordinator=coordinator,
                            config_entry=config_entry,
                            cp_id=cp_id,
                        )
                    )
                # Per-phase sensors from telemetry.sensor
                sensor_data = telemetry.get("sensor")
                if not isinstance(sensor_data, dict):
                    sensor_data = {}
                for phase_key in sensor_data:
                    entities.append(
                        BoschComCommodulePhaseSensor(
                            coordinator=coordinator,
                            config_entry=config_entry,
                            cp_id=cp_id,
                            phase_key=phase_key,
                        )
                    )
                if cp.get("chargelog") is not None:
                    entities.append(
                        BoschComCommoduleChargelogSensor(
                            coordinator=coordinator,
                            config_entry=config_entry,
                            cp_id=cp_id,
                        )
                    )

    for coordinator in coordinators:
        devtype = (coordinator.data.device or {}).get("deviceType")
        try:
            obj = coordinator.data
            if hasattr(obj, "asdict"):
                snapshot = obj.asdict()
            elif hasattr(obj, "__dict__"):
                snapshot = dict(obj.__dict__)
            else:
                snapshot = obj
            _LOGGER.debug(
                "BOSCH DATA SNAPSHOT (%s):\n%s",
                devtype,
                json.dumps(snapshot, indent=2, ensure_ascii=False),
            )
        except Exception:
            _LOGGER.exception("Failed to dump coordinator data for %s", devtype)

    # K40/ICOM sensors from heat_sources (already fetched by homecom_alt bulk API)
    for coordinator in coordinators:
        if isinstance(
            coordinator,
            (BoschComModuleCoordinatorK40, BoschComModuleCoordinatorIcom),
        ):
            hs = coordinator.data.heat_sources or {}
            if hs.get("actualModulation"):
                entities.append(
                    BoschComK40ExtraSensor(
                        coordinator,
                        "actualModulation",
                        "compressor_modulation",
                        "compressor_modulation",
                        native_unit="%",
                    )
                )
            if hs.get("actualSupplyTemperature"):
                entities.append(
                    BoschComK40ExtraSensor(
                        coordinator,
                        "actualSupplyTemperature",
                        "supply_temperature",
                        "supply_temperature",
                        device_class=SensorDeviceClass.TEMPERATURE,
                        native_unit="°C",
                    )
                )
            if hs.get("returnTemperature"):
                entities.append(
                    BoschComK40ExtraSensor(
                        coordinator,
                        "returnTemperature",
                        "return_temperature",
                        "return_temperature",
                        device_class=SensorDeviceClass.TEMPERATURE,
                        native_unit="°C",
                    )
                )
            if hs.get("systemPressure"):
                entities.append(
                    BoschComK40ExtraSensor(
                        coordinator,
                        "systemPressure",
                        "system_pressure",
                        "system_pressure",
                        device_class=SensorDeviceClass.PRESSURE,
                        native_unit="bar",
                    )
                )
            if hs.get("totalWorkingTime"):
                entities.append(
                    BoschComK40ExtraSensor(
                        coordinator,
                        "totalWorkingTime",
                        "compressor_working_time",
                        "compressor_working_time",
                        device_class=SensorDeviceClass.DURATION,
                        state_class=SensorStateClass.TOTAL_INCREASING,
                        native_unit="s",
                    )
                )
            if hs.get("actualHeatDemand"):
                entities.append(BoschComK40HeatDemandSensor(coordinator))
            if hs.get("starts"):
                entities.append(BoschComK40StartCountsSensor(coordinator))

    if entities:
        async_add_entities(entities)


class BoschComSensorBase(CoordinatorEntity, SensorEntity):
    """Boshcom sensor base class."""

    def __init__(self, coordinator, config_entry, unique_id, icon=None) -> None:
        """Init base class."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._attr_unique_id = unique_id
        self._attr_icon = icon
        self._attr_device_info = coordinator.device_info

        _LOGGER.debug(
            "Init base class: unique_id=%s",
            self._attr_unique_id,
        )


class BoschComSensorNotificationsRac(BoschComSensorBase):
    """BoschComSensor notifications."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorRac,
        config_entry: config_entries.ConfigEntry,
    ) -> None:
        """Initialize select entity."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-notifications",
            icon="mdi:bell",
        )
        self._attr_translation_key = "notifications"
        self._attr_unique_id = f"{coordinator.unique_id}-notifications"
        self._attr_suggested_object_id = "notifications"
        self._attr_should_poll = False

        _LOGGER.debug(
            "Init BoschComSensorNotificationsRac: translation_key=%s, unique_id=%s",
            self._attr_translation_key,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return Notifications."""
        return self.coordinator.data.notifications


class BoschComSensorNotificationsK40(BoschComSensorBase):
    """BoschComSensor notifications."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        config_entry: config_entries.ConfigEntry,
    ) -> None:
        """Initialize select entity."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-notifications",
            icon="mdi:bell",
        )
        self._attr_translation_key = "notifications"
        self._attr_unique_id = f"{coordinator.unique_id}-notifications"
        self._attr_suggested_object_id = "notifications"
        self._attr_should_poll = False

        _LOGGER.debug(
            "Init BoschComSensorNotificationsK40: translation_key=%s, unique_id=%s",
            self._attr_translation_key,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return Notifications."""
        return "\n".join(
            f"{item['dcd']}-{item['ccd']}"
            for item in self.coordinator.data.notifications
            if "dcd" in item and "ccd" in item
        )


class BoschComSensorNotificationsWddw2(BoschComSensorBase):
    """BoschComSensor notifications for wddw2 devices.

    Active (non-historical, ``act != 'H'``) fault codes drive the state; the
    full history is exposed via ``extra_state_attributes`` with language-neutral
    fields. Known codes are described via ``WDDW2_NOTIFICATION_CODES``.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorWddw2,
        config_entry: config_entries.ConfigEntry,
    ) -> None:
        """Initialize select entity."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-notifications",
            icon="mdi:bell",
        )
        self._attr_translation_key = "notifications"
        self._attr_unique_id = f"{coordinator.unique_id}-notifications"
        self._attr_suggested_object_id = "notifications"
        self._attr_should_poll = False
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @staticmethod
    def _code(item: dict) -> str:
        return str(item.get("dcd", "")).strip()

    @property
    def state(self):
        """Return active (non-historical) notification codes, or 'none'."""
        active = [
            self._code(item)
            for item in (self.coordinator.data.notifications or [])
            if "dcd" in item and item.get("act") != "H"
        ]
        if not active:
            return "none"
        return "\n".join(WDDW2_NOTIFICATION_CODES.get(code, code) for code in active)

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the full notification history with language-neutral fields."""
        history = [
            {
                "code": self._code(item),
                "description": WDDW2_NOTIFICATION_CODES.get(
                    self._code(item), self._code(item)
                ),
                # TODO(#73): act/fc semantics are inferred from observed
                # TR4001 behaviour; confirm against homecom_alt issue #73.
                "active": item.get("act") != "H",
                "severity": "fault" if item.get("fc") == "8" else "warning",
            }
            for item in (self.coordinator.data.notifications or [])
            if "dcd" in item
        ]
        return {"history": history} if history else {}


class BoschComSensorDhw(BoschComSensorBase):
    """BoschComSensorDhw sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        config_entry: config_entries.ConfigEntry,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-{field}-sensor",
            icon="mdi:water-boiler",
        )
        self._attr_translation_key = "dhw"
        self._attr_translation_placeholders = {"circuit": field}
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_should_poll = False
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_suggested_object_id = field + "_sensor"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self.field = field

        _LOGGER.debug(
            "Init BoschComSensorDhw: translation_key=%s, unique_id=%s",
            self._attr_translation_key,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return BoschComSensorDhw operationMode."""
        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == "/dhwCircuits/" + self.field:
                actual_temp = entry.get("actualTemp") or {}
                unit_str = actual_temp.get("unitOfMeasure")
                if unit_str == "F":
                    self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
                else:
                    self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
                value = actual_temp.get("value")
                if value is None:
                    return None
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None
        return "unknown"

    @property
    def extra_state_attributes(self):
        """Return attributes."""

        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == "/dhwCircuits/" + self.field:
                operationMode_value = (entry.get("operationMode") or {}).get(
                    "value", "unknown"
                )
                charge_value = (entry.get("charge") or {}).get("value", "unknown")
                chargeRemainingTime_value = (
                    entry.get("chargeRemainingTime") or {}
                ).get("value", "unknown")
                singleChargeSetpoint_value = (
                    entry.get("singleChargeSetpoint") or {}
                ).get("value", "unknown")
                currentTemperatureLevel_value = (
                    entry.get("currentTemperatureLevel") or {}
                ).get("value", "unknown")

                result = {
                    "operationMode": operationMode_value,
                    "currentTemperatureLevel": currentTemperatureLevel_value,
                    "charge": charge_value,
                    "chargeRemainingTime": chargeRemainingTime_value,
                    "singleChargeSetpoint": singleChargeSetpoint_value,
                }

                for item, temp_item in (entry.get("tempLevel") or {}).items():
                    result[item] = (
                        temp_item.get("value", "unknown") if temp_item else "unknown"
                    )

                return result
        # extra_state_attributes must return a mapping. Home Assistant merges
        # it with `attr |= extra_state_attributes`; returning a string iterates
        # it as a char sequence and raises
        # "dictionary update sequence element #0 has length 1; 2 is required".
        return {}


class BoschComSensorHc(BoschComSensorBase):
    """BoschComSensorHc sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        config_entry: config_entries.ConfigEntry,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-{field}-sensor",
            icon="mdi:heating-coil",
        )
        self._attr_translation_key = "hc"
        self._attr_translation_placeholders = {"circuit": field}
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_suggested_object_id = field + "_sensor"
        self._attr_should_poll = False
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["off", "manual", "auto"]
        self.field = field

        _LOGGER.debug(
            "Init BoschComSensorHc: translation_key=%s, unique_id=%s",
            self._attr_translation_key,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return BoschComSensorHc operationMode."""

        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                return (entry.get("operationMode") or {}).get("value")

        return None

    @property
    def extra_state_attributes(self):
        """Return attributes."""

        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                currentSuWiMode_value = (entry.get("currentSuWiMode") or {}).get(
                    "value", "unknown"
                )
                heatCoolMode_value = (entry.get("heatCoolMode") or {}).get(
                    "value", "unknown"
                )
                roomTemp_value = (entry.get("roomTemp") or {}).get("value", "unknown")
                actualHumidity_value = (entry.get("actualHumidity") or {}).get(
                    "value", "unknown"
                )
                manualRoomSetpoint_value = (entry.get("manualRoomSetpoint") or {}).get(
                    "value", "unknown"
                )
                currentRoomSetpoint_value = (
                    entry.get("currentRoomSetpoint") or {}
                ).get("value", "unknown")
                coolingRoomTempSetpoint_value = (
                    entry.get("coolingRoomTempSetpoint") or {}
                ).get("value", "unknown")

                return {
                    "currentSuWiMode": currentSuWiMode_value,
                    "heatCoolMode": heatCoolMode_value,
                    "roomTemp": roomTemp_value,
                    "actualHumidity": actualHumidity_value,
                    "manualRoomSetpoint": manualRoomSetpoint_value,
                    "currentRoomSetpoint": currentRoomSetpoint_value,
                    "coolingRoomTempSetpoint": coolingRoomTempSetpoint_value,
                    "maxSupply": (entry.get("maxSupply") or {}).get("value", "unknown"),
                    "minSupply": (entry.get("minSupply") or {}).get("value", "unknown"),
                    "heatCurveMax": (entry.get("heatCurveMax") or {}).get(
                        "value", "unknown"
                    ),
                    "heatCurveMin": (entry.get("heatCurveMin") or {}).get(
                        "value", "unknown"
                    ),
                    "supplyTemperatureSetpoint": (
                        entry.get("supplyTemperatureSetpoint") or {}
                    ).get("value", "unknown"),
                    "nightSwitchMode": (entry.get("nightSwitchMode") or {}).get(
                        "value", "unknown"
                    ),
                    "control": (entry.get("control") or {}).get("value", "unknown"),
                    "nightThreshold": (entry.get("nightThreshold") or {}).get(
                        "value", "unknown"
                    ),
                    "roomInfluence": (entry.get("roomInfluence") or {}).get(
                        "value", "unknown"
                    ),
                }

        return {
            "currentSuWiMode": "unknown",
            "heatCoolMode": "unknown",
            "roomTemp": "unknown",
            "actualHumidity": "unknown",
            "manualRoomSetpoint": "unknown",
            "currentRoomSetpoint": "unknown",
            "coolingRoomTempSetpoint": "unknown",
            "maxSupply": "unknown",
            "minSupply": "unknown",
            "heatCurveMax": "unknown",
            "heatCurveMin": "unknown",
            "supplyTemperatureSetpoint": "unknown",
            "nightSwitchMode": "unknown",
            "control": "unknown",
            "nightThreshold": "unknown",
            "roomInfluence": "unknown",
        }


class BoschComSensorVentilation(BoschComSensorBase):
    """BoschComSensorVentilation sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        config_entry: config_entries.ConfigEntry,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-{field}-sensor",
            icon="mdi:fan",
        )
        self._attr_translation_key = "ventilation"
        self._attr_translation_placeholders = {"zone": field}
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_suggested_object_id = field + "_sensor"
        self._attr_should_poll = False
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["off", "min", "red", "nom", "max", "dem"]
        self.field = field

        _LOGGER.debug(
            "Init BoschComSensorVentilation: translation_key=%s, unique_id=%s",
            self._attr_translation_key,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return BoschComSensorVentilation fan level."""
        for entry in self.coordinator.data.ventilation:
            if entry.get("id") == "/ventilation/" + self.field:
                return (entry.get("exhaustFanLevel") or {}).get("value")
        return None

    @property
    def extra_state_attributes(self):
        """Return attributes."""

        for entry in self.coordinator.data.ventilation:
            if entry.get("id") == "/ventilation/" + self.field:
                maxIndoorAirQuality_value = (
                    entry.get("maxIndoorAirQuality") or {}
                ).get("value", "unknown")
                maxRelativeHumidity_value = (
                    entry.get("maxRelativeHumidity") or {}
                ).get("value", "unknown")
                exhaustTemp_value = (entry.get("exhaustTemp") or {}).get(
                    "value", "unknown"
                )
                extractTemp_value = (entry.get("extractTemp") or {}).get(
                    "value", "unknown"
                )
                internalAirQuality_value = (entry.get("internalAirQuality") or {}).get(
                    "value", "unknown"
                )
                supplyTemp_value = (entry.get("supplyTemp") or {}).get(
                    "value", "unknown"
                )
                internalHumidity_value = (entry.get("internalHumidity") or {}).get(
                    "value", "unknown"
                )
                outdoorTemp_value = (entry.get("outdoorTemp") or {}).get(
                    "value", "unknown"
                )
                summerBypassEnable_value = (entry.get("summerBypassEnable") or {}).get(
                    "value", "unknown"
                )
                summerBypassDuration_value = (
                    entry.get("summerBypassDuration") or {}
                ).get("value", "unknown")
                summerBypassFlapPower_value = (
                    entry.get("summerBypassFlapPower") or {}
                ).get("value", "unknown")
                summerBypassMinSupply_value = (
                    entry.get("summerBypassMinSupply") or {}
                ).get("value", "unknown")
                summerBypassPassiveCooling_value = (
                    entry.get("summerBypassPassiveCooling") or {}
                ).get("value", "unknown")
                demandindoorAirQuality_value = (
                    entry.get("demandindoorAirQuality") or {}
                ).get("value", "unknown")
                demandrelativeHumidity_value = (
                    entry.get("demandrelativeHumidity") or {}
                ).get("value", "unknown")

                return {
                    "maxIndoorAirQuality": maxIndoorAirQuality_value,
                    "maxRelativeHumidity": maxRelativeHumidity_value,
                    "exhaustTemp": exhaustTemp_value,
                    "extractTemp": extractTemp_value,
                    "internalAirQuality": internalAirQuality_value,
                    "supplyTemp": supplyTemp_value,
                    "internalHumidity": internalHumidity_value,
                    "outdoorTemp": outdoorTemp_value,
                    "summerBypassEnable": summerBypassEnable_value,
                    "summerBypassDuration": summerBypassDuration_value,
                    "summerBypassFlapPower": summerBypassFlapPower_value,
                    "summerBypassMinSupply": summerBypassMinSupply_value,
                    "summerBypassPassiveCooling": summerBypassPassiveCooling_value,
                    "demandindoorAirQuality": demandindoorAirQuality_value,
                    "demandrelativeHumidity": demandrelativeHumidity_value,
                }
        # See BoschComSensorDhw.extra_state_attributes — must return a mapping.
        return {}


class BoschComSensorOutdoorTemp(BoschComSensorBase):
    """BoschComSensorOutdoorTemp sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        config_entry: config_entries.ConfigEntry,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-{field}-sensor",
            icon="mdi:sun-thermometer",
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_translation_key = "outdoor_temp"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_suggested_object_id = field + "_sensor"
        self._attr_should_poll = False
        self.field = field

        _LOGGER.debug(
            "Init BoschComSensorOutdoorTemp: translation_key=%s, unique_id=%s",
            self._attr_translation_key,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return BoschComSensorHc outdoorTemp."""
        outdoor = self.coordinator.data.outdoor_temp
        if not outdoor:
            return None
        unit_str = outdoor.get("unitOfMeasure")
        if unit_str == "F":
            self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
        else:
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        value = outdoor.get("value")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


class BoschComSensorHs(BoschComSensorBase):
    """BoschComSensorHs sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        config_entry: config_entries.ConfigEntry,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-{field}",
            icon="mdi:heat-wave",
        )
        self._attr_translation_key = "hs"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_suggested_object_id = field
        self._attr_should_poll = False

        _LOGGER.debug(
            "Init BoschComSensorHS: translation_key=%s, unique_id=%s",
            self._attr_translation_key,
            self._attr_unique_id,
        )

    def seconds_to_readable(self, seconds):
        units = [
            ("year", 365 * 24 * 3600),
            ("month", 30 * 24 * 3600),
            ("week", 7 * 24 * 3600),
            ("day", 24 * 3600),
            ("hour", 3600),
        ]

        parts = []
        for name, length in units:
            value = seconds // length
            if value:
                parts.append(f"{value} {name}{'s' if value > 1 else ''}")
                seconds %= length

        return " ".join(parts) if parts else "0 hours"

    @property
    def state(self):
        """Return BoschComSensorHS type."""
        hs = self.coordinator.data.heat_sources
        pump_type = (hs.get("pumpType") or {}).get("value")
        if pump_type is not None:
            return pump_type
        # icom devices don't expose pumpType; fall back to hs1/type
        return (hs.get("type") or {}).get("value")

    @property
    def extra_state_attributes(self):
        """Return attributes."""
        consumption = (self.coordinator.data.heat_sources.get("consumption") or {}).get(
            "values", "unknown"
        )

        # The pointt-api occasionally returns 500 for
        # heatSources/.../numberOfStarts; the upstream lib may then pass a
        # non-list or a list of non-dict items. Treat anything unexpected as
        # missing so the entity does not crash during state update.
        starts_node = self.coordinator.data.heat_sources.get("starts")
        if not isinstance(starts_node, dict):
            starts_node = {}
        numberOfStarts = starts_node.get("values")
        if not isinstance(numberOfStarts, list):
            numberOfStarts = []
        numberOfStarts_dict = {
            k: v for d in numberOfStarts if isinstance(d, dict) for k, v in d.items()
        }

        returnTemperature = str(
            (self.coordinator.data.heat_sources.get("returnTemperature") or {}).get(
                "value", "unknown"
            )
        ) + (self.coordinator.data.heat_sources.get("returnTemperature") or {}).get(
            "unitOfMeasure", "unknown"
        )

        actualSupplyTemperature = str(
            (
                self.coordinator.data.heat_sources.get("actualSupplyTemperature") or {}
            ).get("value", "unknown")
        ) + (
            self.coordinator.data.heat_sources.get("actualSupplyTemperature") or {}
        ).get(
            "unitOfMeasure", "unknown"
        )

        actualModulation = str(
            (self.coordinator.data.heat_sources.get("actualModulation") or {}).get(
                "value", "unknown"
            )
        ) + (self.coordinator.data.heat_sources.get("actualModulation") or {}).get(
            "unitOfMeasure", "unknown"
        )

        collectorInflowTemp = str(
            (self.coordinator.data.heat_sources.get("collectorInflowTemp") or {}).get(
                "value", "unknown"
            )
        ) + (self.coordinator.data.heat_sources.get("collectorInflowTemp") or {}).get(
            "unitOfMeasure", "unknown"
        )

        collectorOutflowTemp = str(
            (self.coordinator.data.heat_sources.get("collectorOutflowTemp") or {}).get(
                "value", "unknown"
            )
        ) + (self.coordinator.data.heat_sources.get("collectorOutflowTemp") or {}).get(
            "unitOfMeasure", "unknown"
        )

        actualHeatDemand = (
            self.coordinator.data.heat_sources.get("actualHeatDemand") or {}
        ).get("values", ["unknown"])

        totalWorkingTime = str(
            (self.coordinator.data.heat_sources.get("totalWorkingTime") or {}).get(
                "value", "unknown"
            )
        ) + (self.coordinator.data.heat_sources.get("totalWorkingTime") or {}).get(
            "unitOfMeasure", "unknown"
        )

        systemPressure = (
            self.coordinator.data.heat_sources.get("systemPressure") or {}
        ).get("value", ["unknown"])

        totalWorkingTimeReadable = self.seconds_to_readable(
            int(
                (self.coordinator.data.heat_sources.get("totalWorkingTime") or {}).get(
                    "value", 0
                )
                or 0
            )
        )

        result = {
            "numberOfStartsCh": numberOfStarts_dict.get("ch", "unknown"),
            "numberOfStartsDhw": numberOfStarts_dict.get("dhw", "unknown"),
            "numberOfStartsTotal": numberOfStarts_dict.get("total", "unknown"),
            "returnTemperature": returnTemperature,
            "actualSupplyTemperature": actualSupplyTemperature,
            "actualModulation": actualModulation,
            "collectorInflowTemp": collectorInflowTemp,
            "collectorOutflowTemp": collectorOutflowTemp,
            "actualHeatDemandCh": "ch" in actualHeatDemand,
            "actualHeatDemandDhw": "dhw" in actualHeatDemand,
            "actualHeatDemandFrost": "frost" in actualHeatDemand,
            "totalWorkingTime": totalWorkingTime,
            "totalWorkingTimeReadable": totalWorkingTimeReadable,
            "systemPressure": systemPressure,
        }

        consumption = (self.coordinator.data.heat_sources.get("consumption") or {}).get(
            "values"
        ) or []
        # The API can return missing/unknown values; ensure we always work with a list
        if not isinstance(consumption, list):
            consumption = []

        def _cons(idx: int, key: str):
            try:
                item = consumption[idx]
            except IndexError:
                return "unknown"
            return item.get(key, "unknown") if isinstance(item, dict) else "unknown"

        if not consumption:
            result.update(
                {
                    "totalConsumptionOutputProduced": consumption,
                    "totalConsumptionEheater": consumption,
                    "totalConsumptionCompressor": consumption,
                }
            )
        else:
            result.update(
                {
                    "totalConsumptionOutputProduced": _cons(0, "outputProduced"),
                    "totalConsumptionEheater": _cons(1, "eheater"),
                    "totalConsumptionCompressor": _cons(2, "compressor"),
                }
            )
        return result


class BoschComSensorDhwWddw2(BoschComSensorBase):
    """BoschComSensorDhw sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorWddw2,
        config_entry: config_entries.ConfigEntry,
        field: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-{field}-sensor",
            icon="mdi:water-boiler",
        )
        self._attr_translation_key = "dhw"
        self._attr_translation_placeholders = {"circuit": field}
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_suggested_object_id = field + "_sensor"
        self._attr_should_poll = False
        self.field = field

        _LOGGER.debug(
            "Init BoschComSensorDhwWddw2: translation_key=%s, unique_id=%s",
            self._attr_translation_key,
            self._attr_unique_id,
        )

    @property
    def native_value(self):
        """Return numeric setpoint for the current DHW operationMode."""
        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == f"/dhwCircuits/{self.field}":
                mode = (entry.get("operationMode") or {}).get("value")
                node = (entry.get("tempLevel") or {}).get(mode) or {}
                unit_str = node.get("unitOfMeasure")
                if unit_str == "F":
                    self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
                else:
                    self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
                val = node.get("value")
                try:
                    return float(val)  # -> 45.0
                except (TypeError, ValueError):
                    return None
        return None  # Home Assistant mostra "unknown" se None

    @property
    def extra_state_attributes(self):
        """Keep the other temperatures as attributes, como já tinhas."""
        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == f"/dhwCircuits/{self.field}":
                mode = (entry.get("operationMode") or {}).get("value", "unknown")
                result = {"operationMode": mode}
                for item, temp_item in (entry.get("tempLevel") or {}).items():
                    result[item] = (temp_item or {}).get("value", "unknown")
                # sensores adicionais
                result["airBoxTemperature"] = (
                    entry.get("airBoxTemperature") or {}
                ).get("value", "unknown")
                result["inletTemperature"] = (entry.get("inletTemperature") or {}).get(
                    "value", "unknown"
                )
                result["outletTemperature"] = (
                    entry.get("outletTemperature") or {}
                ).get("value", "unknown")
                result["waterFlow"] = (entry.get("waterFlow") or {}).get(
                    "value", "unknown"
                )
                result["nbStarts"] = (entry.get("nbStarts") or {}).get(
                    "value", "unknown"
                )
                return result
        return {}


@dataclass
class DynamicPathResolver:
    """Resolve a nested value by following a path of keys.
    Suporta listas de objetos Bosch com campo 'id' tipo '/dhwCircuits/dhw1/...'
    quando o passo anterior é 'dhw_circuits' e o passo atual é 'dhw1'."""

    path: list[str]

    def _resolve(self, data: dict[str, Any]) -> Any:
        """Walk the path and return the raw node (dict or scalar)."""
        cur: Any = data
        prev_key: Optional[str] = None

        for part in self.path:
            # Se estamos numa lista e o passo anterior era 'dhw_circuits',
            # o 'part' deverá ser 'dhw1', 'dhw2', etc. Fazemos lookup pelo sufixo no 'id'.
            if isinstance(cur, list) and prev_key == "dhw_circuits":
                wanted = part
                matched = None
                for item in cur:
                    if isinstance(item, dict) and item.get("id", "").endswith(
                        "/" + wanted
                    ):
                        matched = item
                        break
                cur = matched
            elif isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return None

            if cur is None:
                return None
            prev_key = part

        return cur

    def get_node(self, data: dict[str, Any]) -> Any:
        """Return the raw resolved node without extracting 'value'."""
        return self._resolve(data)

    def get(self, data: dict[str, Any]) -> Any:
        cur = self._resolve(data)

        # Muitos nós Bosch têm {"value": X, "unitOfMeasure": "..."}
        if isinstance(cur, dict) and "value" in cur:
            return cur.get("value")

        return cur


_UNIT_NORMALISE: dict[str, str] = {
    # Volume flow
    "l/min": "L/min",
    "l/h": "L/h",
    # Volume
    "l": "L",
    # Energy
    "kwh": "kWh",
    "wh": "Wh",
    # Power
    "w": "W",
    "kw": "kW",
    # Pressure
    "bar": "bar",
    # Electrical (EV charger)
    "v": "V",
    "a": "A",
    "hz": "Hz",
}


class BoschComGenericSensor(CoordinatorEntity, SensorEntity):
    """Generic read-only sensor for Bosch HomeCom values."""

    def __init__(
        self,
        coordinator,
        name: str,
        unique_suffix: str,
        path: list[str],
        *,
        unit,
        device_class,
        state_class: Optional[str],
        translation_key: Optional[str] = None,
        entity_category: Optional[str] = None,
    ):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        if translation_key:
            self._attr_translation_key = translation_key
        else:
            self._attr_name = name
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._declared_unit = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._resolver = DynamicPathResolver(path)
        self._attr_device_info = coordinator.device_info
        self._attr_entity_category = (
            EntityCategory(entity_category) if entity_category else None
        )

    def _coordinator_data_as_dict(self) -> dict:
        data = getattr(self.coordinator, "data", {}) or {}
        if hasattr(data, "asdict"):
            return data.asdict()
        if hasattr(data, "__dict__"):
            return data.__dict__
        return data

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        """Resolve the live unit from the API's unitOfMeasure node, falling
        back to the descriptor-declared unit when the API doesn't expose one.
        """
        node = self._resolver.get_node(self._coordinator_data_as_dict())
        if isinstance(node, dict):
            unit_str = node.get("unitOfMeasure")
            if unit_str:
                if self._attr_device_class != SensorDeviceClass.TEMPERATURE:
                    return _UNIT_NORMALISE.get(unit_str, unit_str)
                if unit_str == "F":
                    return UnitOfTemperature.FAHRENHEIT
                if unit_str == "C":
                    return UnitOfTemperature.CELSIUS
        return self._declared_unit

    @property
    def native_value(self) -> Any:
        return self._resolver.get(self._coordinator_data_as_dict())


class BoschComDerivedDeltaTSensor(CoordinatorEntity, SensorEntity):
    """Derived sensor: delta T = outlet - inlet."""

    def __init__(self, coordinator, name: str, unique_suffix: str):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_device_info = coordinator.device_info
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = "measurement"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> Any:
        data = getattr(self.coordinator, "data", {}) or {}
        if hasattr(data, "asdict"):
            data = data.asdict()
        elif hasattr(data, "__dict__"):
            data = data.__dict__

        def _get(path: list[str]):
            cur = data
            prev = None
            for p in path:
                if isinstance(cur, list) and prev == "dhw_circuits":
                    cur = next(
                        (
                            it
                            for it in cur
                            if isinstance(it, dict)
                            and it.get("id", "").endswith("/" + p)
                        ),
                        None,
                    )
                elif isinstance(cur, dict):
                    cur = cur.get(p)
                else:
                    return None
                if cur is None:
                    return None
                prev = p
            if isinstance(cur, dict) and "value" in cur:
                return cur.get("value")
            return cur

        def _get_node(path: list[str]):
            cur = data
            prev = None
            for p in path:
                if isinstance(cur, list) and prev == "dhw_circuits":
                    cur = next(
                        (
                            it
                            for it in cur
                            if isinstance(it, dict)
                            and it.get("id", "").endswith("/" + p)
                        ),
                        None,
                    )
                elif isinstance(cur, dict):
                    cur = cur.get(p)
                else:
                    return None
                if cur is None:
                    return None
                prev = p
            return cur

        inlet = _get(["dhw_circuits", "dhw1", "inletTemperature"])
        outlet = _get(["dhw_circuits", "dhw1", "outletTemperature"])

        outlet_node = _get_node(["dhw_circuits", "dhw1", "outletTemperature"])
        if isinstance(outlet_node, dict):
            unit_str = outlet_node.get("unitOfMeasure")
            if unit_str == "F":
                self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
            else:
                self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

        if inlet is None or outlet is None:
            return None
        try:
            return float(outlet) - float(inlet)
        except (TypeError, ValueError):
            return None


class BoschComHeatingActiveBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary derived sensor: heating active heuristic."""

    def __init__(
        self,
        coordinator,
        name: str,
        unique_suffix: str,
        *,
        delta_t_threshold: float = 3.0,
    ):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_device_info = coordinator.device_info
        self._delta_t_threshold = delta_t_threshold
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        data = getattr(self.coordinator, "data", {}) or {}
        if hasattr(data, "asdict"):
            data = data.asdict()
        elif hasattr(data, "__dict__"):
            data = data.__dict__

        # helper para encontrar o circuito /dhwCircuits/dhw1
        def _dhw1():
            for entry in data.get("dhw_circuits", []) or []:
                if entry.get("id") == "/dhwCircuits/dhw1":
                    return entry
            return None

        dhw = _dhw1()
        if not isinstance(dhw, dict):
            return False

        def _val(node_key: str):
            node = dhw.get(node_key)
            if isinstance(node, dict):
                return node.get("value")
            return node

        # No WDDW2 os nós estão no nível do circuito (sem 'sensor')
        water_flow = _val("waterFlow")
        inlet = _val("inletTemperature")
        outlet = _val("outletTemperature")

        try:
            _LOGGER.debug(
                "heating_active: water_flow=%s inlet=%s outlet=%s",
                water_flow,
                inlet,
                outlet,
            )

            if (
                water_flow is not None
                and float(water_flow) > 0
                and inlet is not None
                and outlet is not None
            ):
                return (float(outlet) - float(inlet)) >= self._delta_t_threshold

        except (TypeError, ValueError):
            return False

        return False


class BoschComSensorIndoorHumidity(BoschComSensorBase):
    """BoschCom indoor humidity sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        config_entry: config_entries.ConfigEntry,
        field: str,
    ) -> None:
        """Initialize indoor humidity sensor."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-{field}",
            icon="mdi:water-percent",
        )
        self._attr_translation_key = "indoor_humidity"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_suggested_object_id = field
        self._attr_should_poll = False
        self._attr_device_class = SensorDeviceClass.HUMIDITY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%"

    @property
    def state(self):
        """Return indoor humidity value."""
        humidity = self.coordinator.data.indoor_humidity
        if isinstance(humidity, dict):
            return humidity.get("value")
        return humidity


class BoschComSensorFlameIndication(BoschComSensorBase):
    """BoschCom flame indication sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        config_entry: config_entries.ConfigEntry,
        field: str,
    ) -> None:
        """Initialize flame indication sensor."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-{field}",
            icon="mdi:fire",
        )
        self._attr_translation_key = "flame_indication"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_suggested_object_id = field
        self._attr_should_poll = False

    @property
    def state(self):
        """Return flame indication value."""
        flame = self.coordinator.data.flame_indication
        if isinstance(flame, dict):
            return flame.get("value")
        return flame


class BoschComSensorEnergyHistory(BoschComSensorBase):
    """BoschCom energy history sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        config_entry: config_entries.ConfigEntry,
        field: str,
    ) -> None:
        """Initialize energy history sensor."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-{field}",
            icon="mdi:lightning-bolt",
        )
        self._attr_translation_key = "energy_history"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_suggested_object_id = field
        self._attr_should_poll = False
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = "kWh"

        self._attr_device_class = SensorDeviceClass.GAS

    @property
    def state(self):
        """Return latest day total gas consumption."""
        energy = self.coordinator.data.energy_history
        if not isinstance(energy, dict):
            return None
        values = energy.get("value")
        if not isinstance(values, list) or not values:
            return None
        latest = values[-1]
        if not isinstance(latest, dict):
            return None
        g_ch = latest.get("gCh", 0) or 0
        g_hw = latest.get("gHw", 0) or 0
        return round(g_ch + g_hw, 2)

    @property
    def last_reset(self) -> datetime | None:
        """Return the start of the latest recorded day."""
        energy = self.coordinator.data.energy_history
        if not isinstance(energy, dict):
            return None
        values = energy.get("value")
        if not isinstance(values, list) or not values:
            return None
        latest = values[-1]
        if not isinstance(latest, dict):
            return None
        date_str = latest.get("d")
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%d-%m-%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @property
    def extra_state_attributes(self):
        """Return energy history details as attributes."""
        energy = self.coordinator.data.energy_history
        if not isinstance(energy, dict):
            return {}
        values = energy.get("value")
        if not isinstance(values, list):
            return {}
        return {"history": values}


class BoschComSensorEnergyHistoryHourly(BoschComSensorBase):
    """BoschCom hourly energy history sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        config_entry: config_entries.ConfigEntry,
        field: str,
    ) -> None:
        """Initialize hourly energy history sensor."""
        super().__init__(
            coordinator=coordinator,
            config_entry=config_entry,
            unique_id=f"{coordinator.unique_id}-{field}",
        )
        self._attr_translation_key = "energy_history_hourly"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_suggested_object_id = field
        self._attr_should_poll = False
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = "kWh"

        self._attr_device_class = SensorDeviceClass.GAS

    @property
    def state(self):
        """Return latest hour total gas consumption."""
        energy = self.coordinator.data.hourly_energy_history
        if not isinstance(energy, dict):
            return None
        values = energy.get("value")
        if not isinstance(values, list) or not values:
            return None
        first = values[0]
        if not isinstance(first, dict):
            return None
        entries = first.get("entries")
        if not isinstance(entries, list) or not entries:
            return None
        latest = entries[-1]
        if not isinstance(latest, dict):
            return None
        g_ch = latest.get("gCh", 0) or 0
        g_hw = latest.get("gHw", 0) or 0
        return round(g_ch + g_hw, 2)

    @property
    def last_reset(self) -> datetime | None:
        """Return the start of the latest recorded hour."""
        energy = self.coordinator.data.hourly_energy_history
        if not isinstance(energy, dict):
            return None
        values = energy.get("value")
        if not isinstance(values, list) or not values:
            return None
        first = values[0]
        if not isinstance(first, dict):
            return None
        entries = first.get("entries")
        if not isinstance(entries, list) or not entries:
            return None
        latest = entries[-1]
        if not isinstance(latest, dict):
            return None
        date_str = latest.get("d")
        hour_str = latest.get("h")
        if not date_str or hour_str is None:
            return None
        try:
            datetime_str = f"{date_str} {hour_str}:00:00"
            return datetime.strptime(datetime_str, "%d-%m-%Y %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None

    @property
    def extra_state_attributes(self):
        """Return hourly energy history details as attributes."""
        energy = self.coordinator.data.hourly_energy_history
        if not isinstance(energy, dict):
            return {}
        values = energy.get("value")
        if not isinstance(values, list):
            return {}
        entries = []
        for val in values:
            if isinstance(val, dict):
                val_entries = val.get("entries")
                if isinstance(val_entries, list):
                    entries.extend(val_entries)
        return {"history": entries}


# ---- Thermostat device sensors (K40/K30/icom/rrc2) ----


class _ThermostatDeviceSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for thermostat device sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        config_entry: config_entries.ConfigEntry,
        dev_id: str,
        unique_suffix: str,
        icon: str | None = None,
    ) -> None:
        """Initialize thermostat device sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{dev_id}-{unique_suffix}"
        self._attr_icon = icon
        self._dev_id = dev_id

    def _get_device(self) -> dict | None:
        """Get device ref data."""
        for dev in self.coordinator.data.devices or []:
            if dev.get("id", "").endswith(f"/{self._dev_id}"):
                return dev
        return None

    def _get_property(self, key: str):
        """Get a property value from the device ref."""
        dev = self._get_device()
        if dev is None:
            return None
        return (dev.get(key) or {}).get("value")


class BoschComThermostatRoomTempSensor(_ThermostatDeviceSensorBase):
    """Thermostat room temperature sensor."""

    def __init__(self, coordinator, config_entry, dev_id) -> None:
        """Initialize room temperature sensor."""
        super().__init__(
            coordinator,
            config_entry,
            dev_id,
            "thermostat_room_temp",
            icon="mdi:thermometer",
        )
        self._attr_translation_key = "thermostat_room_temp"
        self._attr_suggested_object_id = f"{dev_id}_room_temp"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return room temperature."""
        val = self._get_property("roomtemperature")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        return None


class BoschComThermostatHumiditySensor(_ThermostatDeviceSensorBase):
    """Thermostat humidity sensor."""

    def __init__(self, coordinator, config_entry, dev_id) -> None:
        """Initialize humidity sensor."""
        super().__init__(
            coordinator,
            config_entry,
            dev_id,
            "thermostat_humidity",
            icon="mdi:water-percent",
        )
        self._attr_translation_key = "thermostat_humidity"
        self._attr_suggested_object_id = f"{dev_id}_humidity"
        self._attr_device_class = SensorDeviceClass.HUMIDITY
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return humidity."""
        val = self._get_property("actualHumidity")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        return None


class BoschComThermostatSetpointSensor(_ThermostatDeviceSensorBase):
    """Thermostat room setpoint sensor."""

    def __init__(self, coordinator, config_entry, dev_id) -> None:
        """Initialize setpoint sensor."""
        super().__init__(
            coordinator,
            config_entry,
            dev_id,
            "thermostat_setpoint",
            icon="mdi:thermostat",
        )
        self._attr_translation_key = "thermostat_setpoint"
        self._attr_suggested_object_id = f"{dev_id}_setpoint"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return room setpoint."""
        val = self._get_property("currentRoomSetpoint")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        return None


class BoschComThermostatBatterySensor(_ThermostatDeviceSensorBase):
    """Thermostat battery sensor."""

    def __init__(self, coordinator, config_entry, dev_id) -> None:
        """Initialize battery sensor."""
        super().__init__(
            coordinator,
            config_entry,
            dev_id,
            "thermostat_battery",
            icon="mdi:battery",
        )
        self._attr_translation_key = "thermostat_battery"
        self._attr_suggested_object_id = f"{dev_id}_battery"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = "%"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        """Return battery level."""
        val = self._get_property("battery")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        return None


class BoschComThermostatSignalSensor(_ThermostatDeviceSensorBase):
    """Thermostat signal strength sensor."""

    def __init__(self, coordinator, config_entry, dev_id) -> None:
        """Initialize signal sensor."""
        super().__init__(
            coordinator,
            config_entry,
            dev_id,
            "thermostat_signal",
            icon="mdi:signal",
        )
        self._attr_translation_key = "thermostat_signal"
        self._attr_suggested_object_id = f"{dev_id}_signal"
        self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
        self._attr_native_unit_of_measurement = "dBm"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        """Return signal strength."""
        val = self._get_property("signal")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        return None


# ---- Commodule (EV Charger) sensors ----


class _CommoduleSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for commodule charge point sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        config_entry: config_entries.ConfigEntry,
        cp_id: str,
        unique_suffix: str,
        icon: str | None = None,
    ) -> None:
        """Initialize commodule sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{cp_id}-{unique_suffix}"
        self._attr_icon = icon
        self._cp_id = cp_id

    def _get_cp(self) -> dict | None:
        """Get charge point data."""
        for cp in self.coordinator.data.charge_points or []:
            if cp["id"].split("/")[-1] == self._cp_id:
                return cp
        return None

    def _get_telemetry(self) -> dict:
        """Get telemetry data for charge point."""
        cp = self._get_cp()
        if cp is None:
            return {}
        raw = cp.get("telemetry") or {}
        telemetry = raw.get("values", raw)
        if not isinstance(telemetry, dict):
            return {}
        return telemetry


class BoschComCommoduleStateSensor(_CommoduleSensorBase):
    """Commodule wallbox state sensor."""

    _WB_STATE_OPTIONS = [
        "available",
        "authenticated",
        "preparing",
        "locked",
        "charging",
        "suspendedev",
        "suspendedevse",
        "init",
        "faulted",
        "limited",
        "phaseswitch",
    ]

    def __init__(self, coordinator, config_entry, cp_id) -> None:
        """Initialize state sensor."""
        super().__init__(
            coordinator, config_entry, cp_id, "wb_state", icon="mdi:ev-station"
        )
        self._attr_translation_key = "wb_state"
        self._attr_suggested_object_id = f"{cp_id}_state"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = self._WB_STATE_OPTIONS

    @property
    def state(self):
        """Return wallbox state."""
        telemetry = self._get_telemetry()
        raw = telemetry.get("wbState")
        if raw is None:
            return None
        key = raw.lower()
        if key in self._WB_STATE_OPTIONS:
            return key
        return None


class BoschComCommodulePowerSensor(_CommoduleSensorBase):
    """Commodule actual power sensor."""

    def __init__(self, coordinator, config_entry, cp_id) -> None:
        """Initialize power sensor."""
        super().__init__(coordinator, config_entry, cp_id, "wb_power")
        self._attr_translation_key = "wb_power"
        self._attr_suggested_object_id = f"{cp_id}_power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = "W"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return actual power."""
        telemetry = self._get_telemetry()
        val = telemetry.get("actualPower")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        return None


class BoschComCommoduleEnergySensor(_CommoduleSensorBase):
    """Commodule total energy sensor."""

    def __init__(self, coordinator, config_entry, cp_id) -> None:
        """Initialize energy sensor."""
        super().__init__(coordinator, config_entry, cp_id, "wb_energy_total")
        self._attr_translation_key = "wb_energy_total"
        self._attr_suggested_object_id = f"{cp_id}_energy_total"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self):
        """Return total energy."""
        telemetry = self._get_telemetry()
        val = telemetry.get("energyTotal")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        return None


class BoschComCommoduleTempSensor(_CommoduleSensorBase):
    """Commodule temperature sensor."""

    def __init__(self, coordinator, config_entry, cp_id) -> None:
        """Initialize temperature sensor."""
        super().__init__(coordinator, config_entry, cp_id, "wb_temperature")
        self._attr_translation_key = "wb_temperature"
        self._attr_suggested_object_id = f"{cp_id}_temperature"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return temperature."""
        telemetry = self._get_telemetry()
        val = telemetry.get("temp")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        return None


class BoschComCommodulePhasesSensor(_CommoduleSensorBase):
    """Commodule phases sensor."""

    def __init__(self, coordinator, config_entry, cp_id) -> None:
        """Initialize phases sensor."""
        super().__init__(
            coordinator, config_entry, cp_id, "wb_phases", icon="mdi:sine-wave"
        )
        self._attr_translation_key = "wb_phases"
        self._attr_suggested_object_id = f"{cp_id}_phases"

    @property
    def state(self):
        """Return number of phases."""
        telemetry = self._get_telemetry()
        return telemetry.get("phases")


class BoschComCommodulePhaseSensor(_CommoduleSensorBase):
    """Commodule per-phase sensor (voltage/current)."""

    def __init__(self, coordinator, config_entry, cp_id, phase_key) -> None:
        """Initialize per-phase sensor."""
        super().__init__(
            coordinator,
            config_entry,
            cp_id,
            f"wb_phase_{phase_key}",
            icon="mdi:sine-wave",
        )
        self._attr_translation_key = "wb_phase_sensor"
        self._attr_suggested_object_id = f"{cp_id}_{phase_key}"
        self._phase_key = phase_key

    @property
    def state(self):
        """Return phase value."""
        telemetry = self._get_telemetry()
        sensor_data = telemetry.get("sensor") or {}
        phase = sensor_data.get(self._phase_key)
        if isinstance(phase, dict):
            return phase.get("value")
        return phase

    @property
    def extra_state_attributes(self):
        """Return phase details."""
        telemetry = self._get_telemetry()
        sensor_data = telemetry.get("sensor") or {}
        phase = sensor_data.get(self._phase_key)
        if isinstance(phase, dict):
            return {k: v for k, v in phase.items() if k != "value"}
        return {}


class BoschComCommoduleChargelogSensor(_CommoduleSensorBase):
    """Commodule charge log sensor."""

    def __init__(self, coordinator, config_entry, cp_id) -> None:
        """Initialize chargelog sensor."""
        super().__init__(
            coordinator, config_entry, cp_id, "wb_chargelog", icon="mdi:history"
        )
        self._attr_translation_key = "wb_chargelog"
        self._attr_suggested_object_id = f"{cp_id}_chargelog"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    def _get_sessions(self):
        """Get charge sessions list (newest first)."""
        cp = self._get_cp()
        if cp is None:
            return []
        chargelog = cp.get("chargelog")
        if isinstance(chargelog, list):
            return chargelog
        if isinstance(chargelog, dict):
            sessions = chargelog.get("sessions") or chargelog.get("values") or []
            if isinstance(sessions, list):
                return sessions
        return []

    @property
    def native_value(self):
        """Return start timestamp of the last charge session.

        Using the session begin time as the state guarantees a state change
        whenever a new session is logged, even if two consecutive sessions
        deliver the same amount of energy.
        """
        sessions = self._get_sessions()
        if not sessions:
            return None
        last = sessions[0]
        if not isinstance(last, dict):
            return None
        begin = last.get("begin")
        if not begin:
            return None
        try:
            return datetime.fromisoformat(begin)
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self):
        """Return last session details as flat attributes."""
        sessions = self._get_sessions()
        if not sessions:
            return {}
        last = sessions[0]
        if not isinstance(last, dict):
            return {}
        attrs = {}
        energy = last.get("energy")
        if energy is not None:
            try:
                attrs["energy"] = float(energy)
            except (ValueError, TypeError):
                attrs["energy"] = None
        attrs["begin"] = last.get("begin")
        attrs["end"] = last.get("end")
        attrs["plugged"] = last.get("plugged")
        attrs["unplugged"] = last.get("unplugged")
        attrs["session_duration"] = last.get("sessionDuration")
        attrs["charging_duration"] = last.get("chargingDuration")
        cost = last.get("cost")
        if isinstance(cost, dict):
            attrs["cost_total"] = cost.get("total")
            attrs["cost_unit"] = cost.get("unit")
            attrs["cost_currency"] = cost.get("currency")
        meter = last.get("meter")
        if isinstance(meter, dict):
            attrs["meter_begin"] = meter.get("posBegin")
            attrs["meter_end"] = meter.get("posEnd")
        solar = last.get("solar")
        if isinstance(solar, dict):
            attrs["solar_energy"] = solar.get("solarEnergy")
            attrs["grid_energy"] = solar.get("gridEnergy")
            attrs["solar_saving"] = solar.get("solarSaving")
        auth = last.get("authentication")
        if isinstance(auth, dict):
            attrs["auth_source"] = auth.get("source")
            attrs["auth_label"] = auth.get("label")
        attrs["session_count"] = len(sessions)
        return attrs


# ---- RRC2 sensors -----------------------------------------------------------


class BoschComRrc2Sensor(CoordinatorEntity, SensorEntity):
    """Read-only sensor for one field of an RRC2 circuit, system or gateway block."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorRrc2,
        *,
        scope: str,
        circuit_id: str | None,
        field: str,
        name_suffix: str,
        unique_suffix: str,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        unit: str | None = None,
        icon: str | None = None,
        diagnostic: bool = False,
    ) -> None:
        """Initialize one RRC2 sensor."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_name = name_suffix
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        if icon:
            self._attr_icon = icon
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._scope = scope
        self._circuit_id = circuit_id
        self._field = field

    def _find_circuit(self, refs: list) -> dict | None:
        if refs is None:
            return None
        suffix = f"/{self._circuit_id}"
        for ref in refs:
            if ref.get("id", "").endswith(suffix):
                return ref
        return None

    def _read_value(self) -> Any:
        data = self.coordinator.data
        if not data:
            return None

        node: dict | None = None
        if self._scope == "zone":
            ref = self._find_circuit(data.zones or [])
            node = (ref or {}).get(self._field)
        elif self._scope == "hc":
            ref = self._find_circuit(data.heating_circuits or [])
            node = (ref or {}).get(self._field)
        elif self._scope == "dhw":
            ref = self._find_circuit(data.dhw_circuits or [])
            node = (ref or {}).get(self._field)
        elif self._scope == "heat_sources":
            node = (data.heat_sources or {}).get(self._field)
        elif self._scope == "system":
            if self._field == "outdoor_temp":
                node = data.outdoor_temp
            elif self._field == "indoor_humidity":
                node = data.indoor_humidity
        elif self._scope == "gateway":
            node = (data.gateway_info or {}).get(self._field)

        if not isinstance(node, dict):
            return None
        return node.get("value")

    @property
    def native_value(self) -> Any:
        """Return sensor value."""
        return self._read_value()


def _build_rrc2_sensors(
    coordinator: BoschComModuleCoordinatorRrc2,
    config_entry: config_entries.ConfigEntry,
) -> list[SensorEntity]:
    """Build the standard RRC2 sensor set for one device."""
    entities: list[SensorEntity] = []

    for ref in coordinator.data.zones or []:
        zone_id = ref["id"].split("/")[-1]
        entities.append(
            BoschComRrc2Sensor(
                coordinator,
                scope="zone",
                circuit_id=zone_id,
                field="temperatureActual",
                name_suffix=f"{zone_id}_temperature_actual",
                unique_suffix=f"{zone_id}-temperature-actual",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfTemperature.CELSIUS,
            )
        )
        entities.append(
            BoschComRrc2Sensor(
                coordinator,
                scope="zone",
                circuit_id=zone_id,
                field="temperatureHeatingSetpoint",
                name_suffix=f"{zone_id}_heating_setpoint",
                unique_suffix=f"{zone_id}-heating-setpoint",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfTemperature.CELSIUS,
                diagnostic=True,
            )
        )

    for ref in coordinator.data.heating_circuits or []:
        hc_id = ref["id"].split("/")[-1]
        entities.append(
            BoschComRrc2Sensor(
                coordinator,
                scope="hc",
                circuit_id=hc_id,
                field="supplyTemperatureSetpoint",
                name_suffix=f"{hc_id}_supply_temperature_setpoint",
                unique_suffix=f"{hc_id}-supply-temperature-setpoint",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfTemperature.CELSIUS,
            )
        )
        entities.append(
            BoschComRrc2Sensor(
                coordinator,
                scope="hc",
                circuit_id=hc_id,
                field="operatingSeason",
                name_suffix=f"{hc_id}_operating_season",
                unique_suffix=f"{hc_id}-operating-season",
                diagnostic=True,
            )
        )

    for ref in coordinator.data.dhw_circuits or []:
        dhw_id = ref["id"].split("/")[-1]
        entities.append(
            BoschComRrc2Sensor(
                coordinator,
                scope="dhw",
                circuit_id=dhw_id,
                field="actualTemp",
                name_suffix=f"{dhw_id}_actual_temp",
                unique_suffix=f"{dhw_id}-actual-temp",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfTemperature.CELSIUS,
            )
        )
        entities.append(
            BoschComRrc2Sensor(
                coordinator,
                scope="dhw",
                circuit_id=dhw_id,
                field="state",
                name_suffix=f"{dhw_id}_state",
                unique_suffix=f"{dhw_id}-state",
                diagnostic=True,
            )
        )
        entities.append(
            BoschComRrc2Sensor(
                coordinator,
                scope="dhw",
                circuit_id=dhw_id,
                field="hotWaterSystem",
                name_suffix=f"{dhw_id}_hot_water_system",
                unique_suffix=f"{dhw_id}-hot-water-system",
                diagnostic=True,
            )
        )
        entities.append(
            BoschComRrc2Sensor(
                coordinator,
                scope="dhw",
                circuit_id=dhw_id,
                field="thermalDisinfectLastResult",
                name_suffix=f"{dhw_id}_thermal_disinfect_last_result",
                unique_suffix=f"{dhw_id}-thermal-disinfect-last-result",
                diagnostic=True,
            )
        )

    entities.extend(
        [
            BoschComRrc2Sensor(
                coordinator,
                scope="heat_sources",
                circuit_id=None,
                field="supplyTemperature",
                name_suffix="hs_supply_temperature",
                unique_suffix="hs-supply-temperature",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfTemperature.CELSIUS,
            ),
            BoschComRrc2Sensor(
                coordinator,
                scope="heat_sources",
                circuit_id=None,
                field="returnTemperature",
                name_suffix="hs_return_temperature",
                unique_suffix="hs-return-temperature",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfTemperature.CELSIUS,
            ),
            BoschComRrc2Sensor(
                coordinator,
                scope="heat_sources",
                circuit_id=None,
                field="modulation",
                name_suffix="hs_modulation",
                unique_suffix="hs-modulation",
                state_class=SensorStateClass.MEASUREMENT,
                unit="%",
            ),
            BoschComRrc2Sensor(
                coordinator,
                scope="heat_sources",
                circuit_id=None,
                field="flameIndication",
                name_suffix="hs_flame_indication",
                unique_suffix="hs-flame-indication",
                icon="mdi:fire",
                diagnostic=True,
            ),
            BoschComRrc2Sensor(
                coordinator,
                scope="heat_sources",
                circuit_id=None,
                field="type",
                name_suffix="hs_type",
                unique_suffix="hs-type",
                diagnostic=True,
            ),
        ]
    )

    entities.append(
        BoschComRrc2Sensor(
            coordinator,
            scope="system",
            circuit_id=None,
            field="outdoor_temp",
            name_suffix="outdoor_temperature",
            unique_suffix="outdoor-temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            unit=UnitOfTemperature.CELSIUS,
        )
    )
    if coordinator.data.indoor_humidity:
        entities.append(
            BoschComRrc2Sensor(
                coordinator,
                scope="system",
                circuit_id=None,
                field="indoor_humidity",
                name_suffix="indoor_humidity",
                unique_suffix="indoor-humidity",
                device_class=SensorDeviceClass.HUMIDITY,
                state_class=SensorStateClass.MEASUREMENT,
                unit="%",
            )
        )

    entities.append(
        BoschComRrc2Sensor(
            coordinator,
            scope="gateway",
            circuit_id=None,
            field="wifiRssi",
            name_suffix="wifi_rssi",
            unique_suffix="wifi-rssi",
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            state_class=SensorStateClass.MEASUREMENT,
            unit="dBm",
            diagnostic=True,
        )
    )

    for dev in coordinator.data.devices or []:
        dev_id = dev["id"].split("/")[-1]
        if dev.get("roomtemperature"):
            entities.append(
                BoschComThermostatRoomTempSensor(coordinator, config_entry, dev_id)
            )
        if dev.get("actualHumidity"):
            entities.append(
                BoschComThermostatHumiditySensor(coordinator, config_entry, dev_id)
            )
        if dev.get("currentRoomSetpoint"):
            entities.append(
                BoschComThermostatSetpointSensor(coordinator, config_entry, dev_id)
            )
        if dev.get("battery"):
            entities.append(
                BoschComThermostatBatterySensor(coordinator, config_entry, dev_id)
            )
        if dev.get("signal"):
            entities.append(
                BoschComThermostatSignalSensor(coordinator, config_entry, dev_id)
            )

    return entities


# ---- ICOM extra diagnostic sensors -----------------------------------------


class BoschComIcomExtraSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic sensor for an icom top-level or heat-sources field."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorIcom,
        *,
        attr: str,
        sub_key: str | None,
        name_suffix: str,
        unique_suffix: str,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        unit: str | None = None,
        diagnostic: bool = True,
        icon: str | None = None,
        value_divisor: float = 1.0,
    ) -> None:
        """Initialize an icom extra sensor.

        Args:
            coordinator:   The icom coordinator supplying ``BHCDeviceIcom`` data.
            attr:          Top-level ``BHCDeviceIcom`` field name to read from
                           (e.g. ``"heat_sources"`` or ``"health_status"``).
            sub_key:       Optional key to look up inside the field dict. Used
                           to reach nested heat-source entries such as
                           ``"returnTemperature"`` or ``"modulation"``.
            name_suffix:   Human-readable entity name shown in the UI.
            unique_suffix: Suffix appended to the coordinator unique ID to
                           form this entity's ``unique_id``.
            device_class:  HA sensor device class (temperature, energy, …).
            state_class:   HA state class (measurement, total_increasing, …).
            unit:          Native unit of measurement.
            diagnostic:    When ``True`` the entity is placed in the
                           ``DIAGNOSTIC`` category. Defaults to ``True``.
            icon:          Optional MDI icon override.
            value_divisor: Divide the raw API value by this factor before
                           returning it. Use ``3600`` to convert seconds to
                           hours (e.g. ``workingTime/totalSystem``).
        """
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_name = name_suffix
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        if icon:
            self._attr_icon = icon
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        # _attr_path stores the BHCDeviceIcom field name, not an HA attribute.
        self._attr_path = attr
        self._sub_key = sub_key
        self._value_divisor = value_divisor

    @property
    def native_value(self) -> Any:
        """Return the sensor value, applying value_divisor when set."""
        data = self.coordinator.data
        if data is None:
            return None
        node = getattr(data, self._attr_path, None)
        if self._sub_key is not None:
            if not isinstance(node, dict):
                return None
            node = node.get(self._sub_key)
        if not isinstance(node, dict):
            return None
        value = node.get("value")
        if self._value_divisor != 1.0 and value is not None:
            try:
                return round(float(value) / self._value_divisor, 2)
            except (ValueError, TypeError):
                _LOGGER.debug(
                    "Could not apply divisor %s to value %r for %s",
                    self._value_divisor,
                    value,
                    self.unique_id,
                )
                return value
        return value


class BoschComIcomDhwFieldSensor(CoordinatorEntity, SensorEntity):
    """Sensor for a single field inside a specific icom DHW circuit reference.

    Unlike ``BoschComIcomExtraSensor`` (which reads top-level or heat-source
    dict fields), this class handles ``dhw_circuits``, which is a list.  It
    locates the correct circuit by ``dhw_id`` and returns the ``{"value": …}``
    contained in ``field``.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorIcom,
        *,
        dhw_id: str,
        field: str,
        name_suffix: str,
        unique_suffix: str,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        unit: str | None = None,
        diagnostic: bool = False,
        icon: str | None = None,
    ) -> None:
        """Initialize a DHW circuit field sensor.

        Args:
            coordinator:   The icom coordinator supplying ``BHCDeviceIcom`` data.
            dhw_id:        DHW circuit identifier (e.g. ``"dhw1"``).
            field:         Key to read from the circuit reference dict
                           (e.g. ``"currentSetpoint"``).
            name_suffix:   Human-readable entity name shown in the UI.
            unique_suffix: Suffix appended to the coordinator unique ID.
            device_class:  HA sensor device class.
            state_class:   HA state class.
            unit:          Native unit of measurement.
            diagnostic:    When ``True`` the entity is placed in DIAGNOSTIC
                           category.
            icon:          Optional MDI icon override.
        """
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_name = name_suffix
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        if icon:
            self._attr_icon = icon
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._dhw_id = dhw_id
        self._field = field

    def _get_value(self) -> Any:
        """Return the field value for the configured DHW circuit, or None."""
        for ref in self.coordinator.data.dhw_circuits or []:
            if ref.get("id", "").split("/")[-1] == self._dhw_id:
                node = ref.get(self._field)
                if isinstance(node, dict):
                    return node.get("value")
        return None

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self._get_value()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self._get_value()
        self.async_write_ha_state()


def _build_icom_extra_sensors(
    coordinator: BoschComModuleCoordinatorIcom,
) -> list[SensorEntity]:
    """Build icom-only diagnostic sensors that don't fit the K40 entities."""
    entities: list[SensorEntity] = []

    data = coordinator.data
    if data is None:
        return entities

    if isinstance(data.health_status, dict) and "value" in data.health_status:
        entities.append(
            BoschComIcomExtraSensor(
                coordinator,
                attr="health_status",
                sub_key=None,
                name_suffix="health_status",
                unique_suffix="health-status",
                icon="mdi:heart-pulse",
            )
        )
    if isinstance(data.brand, dict) and data.brand.get("value") is not None:
        entities.append(
            BoschComIcomExtraSensor(
                coordinator,
                attr="brand",
                sub_key=None,
                name_suffix="brand",
                unique_suffix="brand",
                icon="mdi:tag",
            )
        )

    hs = data.heat_sources or {}
    if isinstance(hs.get("returnTemperature"), dict):
        entities.append(
            BoschComIcomExtraSensor(
                coordinator,
                attr="heat_sources",
                sub_key="returnTemperature",
                name_suffix="hs_return_temperature",
                unique_suffix="hs-return-temperature",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfTemperature.CELSIUS,
                diagnostic=False,
            )
        )
    if isinstance(hs.get("numberOfStarts"), dict):
        entities.append(
            BoschComIcomExtraSensor(
                coordinator,
                attr="heat_sources",
                sub_key="numberOfStarts",
                name_suffix="hs_number_of_starts",
                unique_suffix="hs-number-of-starts",
                state_class=SensorStateClass.TOTAL_INCREASING,
            )
        )
    if (
        isinstance(hs.get("supplyTemperature"), dict)
        and "value" in hs["supplyTemperature"]
    ):
        entities.append(
            BoschComIcomExtraSensor(
                coordinator,
                attr="heat_sources",
                sub_key="supplyTemperature",
                name_suffix="hs_supply_temperature",
                unique_suffix="hs-supply-temperature",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfTemperature.CELSIUS,
                diagnostic=False,
            )
        )
    if isinstance(hs.get("modulation"), dict) and "value" in hs["modulation"]:
        entities.append(
            BoschComIcomExtraSensor(
                coordinator,
                attr="heat_sources",
                sub_key="modulation",
                name_suffix="hs_modulation",
                unique_suffix="hs-modulation",
                state_class=SensorStateClass.MEASUREMENT,
                unit=PERCENTAGE,
                diagnostic=False,
                icon="mdi:sine-wave",
            )
        )
    if (
        isinstance(hs.get("totalConsumption"), dict)
        and "value" in hs["totalConsumption"]
    ):
        entities.append(
            BoschComIcomExtraSensor(
                coordinator,
                attr="heat_sources",
                sub_key="totalConsumption",
                name_suffix="hs_total_consumption",
                unique_suffix="hs-total-consumption",
                device_class=SensorDeviceClass.ENERGY,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit=UnitOfEnergy.KILO_WATT_HOUR,
                diagnostic=False,
            )
        )
    if isinstance(hs.get("workingTime"), dict) and "value" in hs["workingTime"]:
        entities.append(
            BoschComIcomExtraSensor(
                coordinator,
                attr="heat_sources",
                sub_key="workingTime",
                name_suffix="hs_working_time",
                unique_suffix="hs-working-time",
                device_class=SensorDeviceClass.DURATION,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit=UnitOfTime.HOURS,
                diagnostic=False,
                icon="mdi:timer-outline",
                value_divisor=3600,
            )
        )
    if isinstance(hs.get("systemPressure"), dict) and "value" in hs["systemPressure"]:
        entities.append(
            BoschComIcomExtraSensor(
                coordinator,
                attr="heat_sources",
                sub_key="systemPressure",
                name_suffix="hs_system_pressure",
                unique_suffix="hs-system-pressure",
                device_class=SensorDeviceClass.PRESSURE,
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfPressure.BAR,
                diagnostic=False,
            )
        )
    if (
        isinstance(hs.get("actualHeatDemand"), dict)
        and "value" in hs["actualHeatDemand"]
    ):
        entities.append(
            BoschComIcomExtraSensor(
                coordinator,
                attr="heat_sources",
                sub_key="actualHeatDemand",
                name_suffix="hs_heat_demand",
                unique_suffix="hs-heat-demand",
                state_class=SensorStateClass.MEASUREMENT,
                unit=PERCENTAGE,
                diagnostic=False,
                icon="mdi:thermometer-chevron-up",
            )
        )
    if isinstance(hs.get("outdoorTemp"), dict) and "value" in hs["outdoorTemp"]:
        entities.append(
            BoschComIcomExtraSensor(
                coordinator,
                attr="heat_sources",
                sub_key="outdoorTemp",
                name_suffix="outdoor_temperature",
                unique_suffix="outdoor-temperature",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfTemperature.CELSIUS,
                diagnostic=False,
            )
        )

    # DHW currentSetpoint — needed to detect when the DHW circuit is being
    # heated (actual temp below setpoint).  The library fetches singleCharge
    # Setpoint only; the coordinator augments each DHW ref with this field.
    for ref in data.dhw_circuits or []:
        dhw_id = ref.get("id", "").split("/")[-1]
        if not dhw_id:
            continue
        if isinstance(ref.get("currentSetpoint"), dict) and "value" in ref.get(
            "currentSetpoint", {}
        ):
            entities.append(
                BoschComIcomDhwFieldSensor(
                    coordinator,
                    dhw_id=dhw_id,
                    field="currentSetpoint",
                    name_suffix=f"{dhw_id}_current_setpoint",
                    unique_suffix=f"{dhw_id}-current-setpoint",
                    device_class=SensorDeviceClass.TEMPERATURE,
                    state_class=SensorStateClass.MEASUREMENT,
                    unit=UnitOfTemperature.CELSIUS,
                    icon="mdi:thermometer-water",
                )
            )

    return entities


# ---- WDDW2 heat-source + water totals (issue #129) -------------------------


class BoschComWddw2TotalsSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic / totals sensor for a top-level WDDW2 field.

    Reads either coordinator.data.water_total_consumption directly, or a key
    inside coordinator.data.heat_sources.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorWddw2,
        *,
        source: str,
        sub_key: str | None,
        name_suffix: str,
        unique_suffix: str,
        device_class: SensorDeviceClass | None,
        state_class: SensorStateClass | None,
        unit: str | None,
        icon: str | None = None,
        translation_key: str | None = None,
        entity_category: str | None = None,
    ) -> None:
        """Initialize one WDDW2 totals sensor."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        if translation_key:
            self._attr_translation_key = translation_key
        else:
            self._attr_name = name_suffix
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        if entity_category:
            self._attr_entity_category = EntityCategory(entity_category)
        if icon:
            self._attr_icon = icon
        self._source = source
        self._sub_key = sub_key

    def _node(self) -> dict | None:
        data = self.coordinator.data
        if data is None:
            return None
        if self._source == "water_total_consumption":
            node = data.water_total_consumption
        elif self._source == "heat_sources":
            hs = data.heat_sources or {}
            node = hs.get(self._sub_key) if self._sub_key else None
        else:
            return None
        return node if isinstance(node, dict) else None

    @property
    def native_value(self) -> Any:
        """Return the field value."""
        node = self._node()
        if node is None:
            return None
        return node.get("value")


def _build_wddw2_totals_sensors(
    coordinator: BoschComModuleCoordinatorWddw2,
) -> list[SensorEntity]:
    """Build the 5 priority WDDW2 totals sensors from issue #129."""
    entities: list[SensorEntity] = []
    data = coordinator.data
    if data is None:
        return entities

    if isinstance(data.water_total_consumption, dict) and (
        "value" in data.water_total_consumption
    ):
        entities.append(
            BoschComWddw2TotalsSensor(
                coordinator,
                source="water_total_consumption",
                sub_key=None,
                name_suffix="water_total_consumption",
                unique_suffix="water-total-consumption",
                device_class=SensorDeviceClass.WATER,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit=UnitOfVolume.LITERS,
                icon="mdi:water",
                translation_key="water_total_consumption",
            )
        )

    hs = data.heat_sources or {}
    if isinstance(hs.get("electricityTotalConsumption"), dict) and (
        "value" in hs["electricityTotalConsumption"]
    ):
        entities.append(
            BoschComWddw2TotalsSensor(
                coordinator,
                source="heat_sources",
                sub_key="electricityTotalConsumption",
                name_suffix="electricity_total_consumption",
                unique_suffix="electricity-total-consumption",
                device_class=SensorDeviceClass.ENERGY,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit=UnitOfEnergy.KILO_WATT_HOUR,
                translation_key="hs_electricity_total",
            )
        )
    if isinstance(hs.get("operationHours"), dict) and "value" in hs["operationHours"]:
        entities.append(
            BoschComWddw2TotalsSensor(
                coordinator,
                source="heat_sources",
                sub_key="operationHours",
                name_suffix="hs_operation_hours",
                unique_suffix="hs-operation-hours",
                device_class=SensorDeviceClass.DURATION,
                state_class=SensorStateClass.TOTAL_INCREASING,
                unit=UnitOfTime.HOURS,
                translation_key="hs_operation_hours",
                entity_category="diagnostic",
            )
        )
    if isinstance(hs.get("actualPower"), dict) and "value" in hs["actualPower"]:
        entities.append(
            BoschComWddw2TotalsSensor(
                coordinator,
                source="heat_sources",
                sub_key="actualPower",
                name_suffix="hs_actual_power",
                unique_suffix="hs-actual-power",
                device_class=SensorDeviceClass.POWER,
                state_class=SensorStateClass.MEASUREMENT,
                unit=UnitOfPower.KILO_WATT,
                translation_key="hs_actual_power",
            )
        )
    if isinstance(hs.get("powerPercentage"), dict) and (
        "value" in hs["powerPercentage"]
    ):
        entities.append(
            BoschComWddw2TotalsSensor(
                coordinator,
                source="heat_sources",
                sub_key="powerPercentage",
                name_suffix="hs_power_percentage",
                unique_suffix="hs-power-percentage",
                device_class=None,
                state_class=SensorStateClass.MEASUREMENT,
                unit=PERCENTAGE,
                icon="mdi:gauge",
                translation_key="hs_power_percentage",
                entity_category="diagnostic",
            )
        )

    return entities


# ===================================================================
# Extra K40 sensors (endpoints not yet in homecom_alt library)
# ===================================================================


class BoschComK40ExtraSensor(CoordinatorEntity, SensorEntity):
    """Sensor reading a float value from coordinator.extra_data."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        key: str,
        translation_key: str,
        unique_suffix: str,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
        native_unit: str | None = None,
        convert_seconds_to_hours: bool = False,
    ) -> None:
        """Initialize extra sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_suggested_object_id = unique_suffix
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = native_unit
        self._convert_s_to_h = convert_seconds_to_hours

    @property
    def native_value(self) -> float | int | None:
        """Return current value."""
        hs = self.coordinator.data.heat_sources or {}
        data = hs.get(self._key)
        if data and isinstance(data, dict):
            val = data.get("value")
            if val is not None and self._convert_s_to_h:
                return round(val / 3600, 1)
            # Return int for whole numbers (removes .0 display)
            if val is not None and val == int(val):
                return int(val)
            return val
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data."""
        hs = self.coordinator.data.heat_sources or {}
        data = hs.get(self._key)
        if data and isinstance(data, dict):
            val = data.get("value")
            if val is not None and self._convert_s_to_h:
                self._attr_native_value = round(val / 3600, 1)
            elif val is not None and val == int(val):
                self._attr_native_value = int(val)
            else:
                self._attr_native_value = val
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class BoschComK40HeatDemandSensor(CoordinatorEntity, SensorEntity):
    """Sensor for actualHeatDemand (what the compressor is doing)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: BoschComModuleCoordinatorK40) -> None:
        """Initialize heat demand sensor."""
        super().__init__(coordinator)
        self._attr_translation_key = "heat_demand"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-heat_demand"
        self._attr_suggested_object_id = "heat_demand"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["idle", "ch", "dhw", "frost"]

    @property
    def native_value(self) -> str | None:
        """Return current demand (first active or 'idle')."""
        hs = self.coordinator.data.heat_sources or {}
        data = hs.get("actualHeatDemand")
        if data and isinstance(data, dict):
            values = data.get("values", [])
            active = [v for v in values if v]
            return active[0] if active else "idle"
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data."""
        hs = self.coordinator.data.heat_sources or {}
        data = hs.get("actualHeatDemand")
        if data and isinstance(data, dict):
            values = data.get("values", [])
            active = [v for v in values if v]
            self._attr_native_value = active[0] if active else "idle"
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class BoschComK40StartCountsSensor(CoordinatorEntity, SensorEntity):
    """Sensor for numberOfStarts (total with per-domain breakdown)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: BoschComModuleCoordinatorK40) -> None:
        """Initialize start counts sensor."""
        super().__init__(coordinator)
        self._attr_translation_key = "compressor_starts"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-compressor_starts"
        self._attr_suggested_object_id = "compressor_starts"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = "starts"

    @property
    def native_value(self) -> float | None:
        """Return total starts."""
        hs = self.coordinator.data.heat_sources or {}
        data = hs.get("starts")
        if data and isinstance(data, dict):
            for entry in data.get("values", []):
                if isinstance(entry, dict) and "total" in entry:
                    return int(entry["total"])
        return None

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return per-domain breakdown."""
        hs = self.coordinator.data.heat_sources or {}
        data = hs.get("starts")
        if data and isinstance(data, dict):
            attrs = {}
            for entry in data.get("values", []):
                if isinstance(entry, dict):
                    attrs.update(entry)
            return attrs if attrs else None
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data."""
        self.async_write_ha_state()
