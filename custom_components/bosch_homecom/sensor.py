"""Bosch HomeCom Custom Component."""
from __future__ import annotations
from datetime import timedelta
import logging
import re
import json

from homeassistant import config_entries, core
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinatorK40, BoschComModuleCoordinatorRac, BoschComModuleCoordinatorWddw2

from dataclasses import dataclass
from typing import Any, Optional

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import UnitOfTemperature, PERCENTAGE

from .const import BOSCH_SENSOR_DESCRIPTORS

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
        elif device_type in ("k40", "k30", "icom"):
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

        # ---- K40/K30 (existing) ----
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
                        coordinator=coordinator, config_entry=config_entry, field=zone_id
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
            # Heat source + outdoor temp
            entities.extend(
                [
                    BoschComSensorHs(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        field="heat_source",
                    ),
                    BoschComSensorOutdoorTemp(
                        coordinator=coordinator,
                        config_entry=config_entry,
                        field="outdoor_temp",
                    ),
                ]
            )

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

            # NEW: generic sensors from descriptors (BOSCH_SENSOR_DESCRIPTORS["wddw2"])
            wddw2_desc = BOSCH_SENSOR_DESCRIPTORS.get("wddw2", [])
            if wddw2_desc:
                # If descriptors are per-circuit, try to expand per each dhwX
                dhw_ids = [
                    ref["id"].split("/")[-1]
                    for ref in coordinator.data.dhw_circuits
                    if re.fullmatch(r"dhw\d", ref["id"].split("/")[-1])
                ] or [None]  # fallback to single set if not per circuit

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
                                    name=desc["name"] if not dhw_id else f"{desc['name']} {dhw_id.upper()}",
                                    unique_suffix=unique_suffix,
                                    path=resolved_path,
                                    unit=desc.get("unit"),
                                    device_class=desc.get("device_class"),
                                    state_class=desc.get("state_class"),
                                )
                            )
                        except Exception:  # keep onboarding even if one fails
                            _LOGGER.debug("Failed to add generic sensor %s", unique_suffix)

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
            _LOGGER.debug("BOSCH DATA SNAPSHOT (%s):\n%s",
                          devtype, json.dumps(snapshot, indent=2, ensure_ascii=False))
        except Exception:
            _LOGGER.exception("Failed to dump coordinator data for %s", devtype)
            
    if entities:
        async_add_entities(entities)


class BoschComSensorBase(CoordinatorEntity, SensorEntity):
    """Boshcom sensor base class."""

    def __init__(self, coordinator, config_entry, name, unique_id, icon=None) -> None:
        """Init base class."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_icon = icon
        self._attr_device_info = coordinator.device_info

        _LOGGER.debug(
            "Init base class: name=%s, unique_id=%s",
            self._attr_name,
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
            name="_notifications",
            unique_id=f"{coordinator.unique_id}-notifications",
            icon="mdi:bell",
        )
        self._attr_translation_key = "notifications"
        self._attr_unique_id = f"{coordinator.unique_id}-notifications"
        self._attr_name = "notifications"
        self._attr_should_poll = False

        _LOGGER.debug(
            "Init BoschComSensorNotificationsRac: name=%s, unique_id=%s",
            self._attr_name,
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
            name="_notifications",
            unique_id=f"{coordinator.unique_id}-notifications",
            icon="mdi:bell",
        )
        self._attr_translation_key = "notifications"
        self._attr_unique_id = f"{coordinator.unique_id}-notifications"
        self._attr_name = "notifications"
        self._attr_should_poll = False

        _LOGGER.debug(
            "Init BoschComSensorNotificationsK40: name=%s, unique_id=%s",
            self._attr_name,
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
    """BoschComSensor notifications."""

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
            name="_notifications",
            unique_id=f"{coordinator.unique_id}-notifications",
            icon="mdi:bell",
        )
        self._attr_translation_key = "notifications"
        self._attr_unique_id = f"{coordinator.unique_id}-notifications"
        self._attr_name = "notifications"
        self._attr_should_poll = False

        _LOGGER.debug(
            "Init BoschComSensorNotificationsWddw2: name=%s, unique_id=%s",
            self._attr_name,
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
            name=field + "_sensor",
            unique_id=f"{coordinator.unique_id}-{field}-sensor",
            icon="mdi:water-boiler",
        )
        self._attr_translation_key = "dhw"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field + "_sensor"
        self._attr_should_poll = False
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self.field = field

        _LOGGER.debug(
            "Init BoschComSensorDhw: name=%s, unique_id=%s",
            self._attr_name,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return BoschComSensorDhw operationMode."""
        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == "/dhwCircuits/" + self.field:
                actualTemp_value = (entry.get("actualTemp") or {}).get(
                    "value", "unknown"
                )
                return float(actualTemp_value)
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
        return "unknown"


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
            name=field + "_sensor",
            unique_id=f"{coordinator.unique_id}-{field}-sensor",
            icon="mdi:heating-coil",
        )
        self._attr_translation_key = "hc"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field + "_sensor"
        self._attr_should_poll = False
        self.field = field

        _LOGGER.debug(
            "Init BoschComSensorHc: name=%s, unique_id=%s",
            self._attr_name,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return BoschComSensorHc operationMode."""

        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                return (entry.get("operationMode") or {}).get("value", "unknown")

        return "unknown"

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
                }

        return {
            "currentSuWiMode": "unknown",
            "heatCoolMode": "unknown",
            "roomTemp": "unknown",
            "actualHumidity": "unknown",
            "manualRoomSetpoint": "unknown",
            "currentRoomSetpoint": "unknown",
            "coolingRoomTempSetpoint": "unknown",
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
            name=field + "_sensor",
            unique_id=f"{coordinator.unique_id}-{field}-sensor",
            icon="mdi:fan",
        )
        self._attr_translation_key = "ventilation"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field + "_sensor"
        self._attr_should_poll = False
        self.field = field

        _LOGGER.debug(
            "Init BoschComSensorVentilation: name=%s, unique_id=%s",
            self._attr_name,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return BoschComSensorVentilation fan level."""
        for entry in self.coordinator.data.ventilation:
            if entry.get("id") == "/ventilation/" + self.field:
                return (entry.get("exhaustFanLevel") or {}).get(
                    "value", "unknown"
                )
        return "unknown"

    @property
    def extra_state_attributes(self):
        """Return attributes."""

        for entry in self.coordinator.data.ventilation:
            if entry.get("id") == "/ventilation/" + self.field:
                maxIndoorAirQuality_value = (entry.get("maxIndoorAirQuality") or {}).get(
                    "value", "unknown"
                )
                maxRelativeHumidity_value = (entry.get("maxRelativeHumidity") or {}).get("value", "unknown")
                exhaustTemp_value = (
                    entry.get("exhaustTemp") or {}
                ).get("value", "unknown")
                extractTemp_value = (
                    entry.get("extractTemp") or {}
                ).get("value", "unknown")
                internalAirQuality_value = (
                    entry.get("internalAirQuality") or {}
                ).get("value", "unknown")
                supplyTemp_value = (
                    entry.get("supplyTemp") or {}
                ).get("value", "unknown")
                internalHumidity_value = (
                    entry.get("internalHumidity") or {}
                ).get("value", "unknown")
                outdoorTemp_value = (
                    entry.get("outdoorTemp") or {}
                ).get("value", "unknown")
                summerBypassEnable_value = (
                    entry.get("summerBypassEnable") or {}
                ).get("value", "unknown")
                summerBypassDuration_value = (
                    entry.get("summerBypassDuration") or {}
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
                    "demandindoorAirQuality": demandindoorAirQuality_value,
                    "demandrelativeHumidity": demandrelativeHumidity_value,
                }
        return "unknown"

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
            name=field + "_sensor",
            unique_id=f"{coordinator.unique_id}-{field}-sensor",
            icon="mdi:sun-thermometer",
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_translation_key = "OutdoorTemp"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field + "_sensor"
        self._attr_should_poll = False
        self.field = field

        _LOGGER.debug(
            "Init BoschComSensorOutdoorTemp: name=%s, unique_id=%s",
            self._attr_name,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return BoschComSensorHc outdoorTemp."""
        return float(
            self.coordinator.data.outdoor_temp.get("value", "unknown")
        )


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
            name=field,
            unique_id=f"{coordinator.unique_id}-{field}",
            icon="mdi:heat-wave",
        )
        self._attr_translation_key = "hs"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field
        self._attr_should_poll = False

        _LOGGER.debug(
            "Init BoschComSensorHS: name=%s, unique_id=%s",
            self._attr_name,
            self._attr_unique_id,
        )

    def seconds_to_readable(self, seconds):
        units = [
            ('year', 365 * 24 * 3600),
            ('month', 30 * 24 * 3600),
            ('week', 7 * 24 * 3600),
            ('day', 24 * 3600),
            ('hour', 3600),
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
        return (self.coordinator.data.heat_sources.get("pumpType") or {}).get(
            "value", "unknown"
        )

    @property
    def extra_state_attributes(self):
        """Return attributes."""
        consumption = (self.coordinator.data.heat_sources.get("consumption") or {}).get(
            "values", "unknown"
        )

        numberOfStarts = (self.coordinator.data.heat_sources.get("starts") or {}).get(
            "values"
        ) or []
        numberOfStarts_dict = {k: v for d in numberOfStarts for k, v in d.items()}

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
            (self.coordinator.data.heat_sources.get("actualHeatDemand") or {})
            .get("values", ["unknown"])
        )

        totalWorkingTime = str(
            (self.coordinator.data.heat_sources.get("totalWorkingTime") or {}).get(
                "value", "unknown"
            )
        ) + (self.coordinator.data.heat_sources.get("totalWorkingTime") or {}).get(
            "unitOfMeasure", "unknown"
        )

        totalWorkingTimeReadable = self.seconds_to_readable(int((self.coordinator.data.heat_sources.get("totalWorkingTime") or {}).get("value", 0) or 0))

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
        }

        if not len(consumption):
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
                    "totalConsumptionOutputProduced": (consumption[0] or {}).get(
                        "outputProduced", "unknown"
                    ),
                    "totalConsumptionEheater": (consumption[1] or {}).get("eheater", "unknown"),
                    "totalConsumptionCompressor": (consumption[2] or {}).get("compressor", "unknown"),
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
            name=field + "_sensor",
            unique_id=f"{coordinator.unique_id}-{field}-sensor",
            icon="mdi:water-boiler",
        )
        self._attr_translation_key = "dhw"
        self._attr_unique_id = f"{coordinator.unique_id}-{field}"
        self._attr_name = field + "_sensor"
        self._attr_should_poll = False
        self.field = field

        _LOGGER.debug(
            "Init BoschComSensorDhw: name=%s, unique_id=%s",
            self._attr_name,
            self._attr_unique_id,
        )
    
    @property
    def native_value(self):
        """Return numeric setpoint for the current DHW operationMode."""
        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == f"/dhwCircuits/{self.field}":
                mode = (entry.get("operationMode") or {}).get("value")
                node = (entry.get("tempLevel") or {}).get(mode) or {}
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
                result["airBoxTemperature"] = (entry.get("airBoxTemperature") or {}).get("value", "unknown")
                result["inletTemperature"]   = (entry.get("inletTemperature") or {}).get("value", "unknown")
                result["outletTemperature"]  = (entry.get("outletTemperature") or {}).get("value", "unknown")
                result["waterFlow"]          = (entry.get("waterFlow") or {}).get("value", "unknown")
                result["nbStarts"]           = (entry.get("nbStarts") or {}).get("value", "unknown")
                return result
        return {}

@dataclass
class DynamicPathResolver:
    """Resolve a nested value by following a path of keys.
    Suporta listas de objetos Bosch com campo 'id' tipo '/dhwCircuits/dhw1/...'
    quando o passo anterior é 'dhw_circuits' e o passo atual é 'dhw1'."""
    path: list[str]

    def get(self, data: dict[str, Any]) -> Any:
        cur: Any = data
        prev_key: Optional[str] = None

        for part in self.path:
            # Se estamos numa lista e o passo anterior era 'dhw_circuits',
            # o 'part' deverá ser 'dhw1', 'dhw2', etc. Fazemos lookup pelo sufixo no 'id'.
            if isinstance(cur, list) and prev_key == "dhw_circuits":
                wanted = part
                matched = None
                for item in cur:
                    if isinstance(item, dict) and item.get("id", "").endswith("/" + wanted):
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

        # Muitos nós Bosch têm {"value": X, "unitOfMeasure": "..."}
        if isinstance(cur, dict) and "value" in cur:
            return cur.get("value")

        return cur


class BoschComGenericSensor(CoordinatorEntity, SensorEntity):
    """Generic read-only sensor for Bosch HomeCom values."""

    def __init__(self, coordinator, name: str, unique_suffix: str, path: list[str], *, unit, device_class, state_class: Optional[str]):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._resolver = DynamicPathResolver(path)
        self._attr_device_info = coordinator.device_info
        self._attr_entity_category = None  # or EntityCategory.DIAGNOSTIC if you prefer

    @property
    def native_value(self) -> Any:
        data = getattr(self.coordinator, "data", {}) or {}
        if hasattr(data, "asdict"):
            data = data.asdict()
        elif hasattr(data, "__dict__"):
            data = data.__dict__
        value = self._resolver.get(data)
        return value


class BoschComDerivedDeltaTSensor(CoordinatorEntity, SensorEntity):
    """Derived sensor: delta T = outlet - inlet."""

    def __init__(self, coordinator, name: str, unique_suffix: str):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_device_info = coordinator.device_info
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        #self._attr_device_class = "temperature"
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
                    cur = next((it for it in cur if isinstance(it, dict) and it.get("id","").endswith("/"+p)), None)
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

        inlet  = _get(["dhw_circuits","dhw1","inletTemperature"])
        outlet = _get(["dhw_circuits","dhw1","outletTemperature"])

        if inlet is None or outlet is None:
            return None
        try:
            return float(outlet) - float(inlet)
        except (TypeError, ValueError):
            return None


class BoschComHeatingActiveBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary derived sensor: heating active heuristic."""

    def __init__(self, coordinator, name: str, unique_suffix: str, *, delta_t_threshold: float = 3.0):
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
        inlet      = _val("inletTemperature")
        outlet     = _val("outletTemperature")

        try:
            _LOGGER.debug("heating_active: water_flow=%s inlet=%s outlet=%s", water_flow, inlet, outlet)

            if water_flow is not None and float(water_flow) > 0 and inlet is not None and outlet is not None:
                return (float(outlet) - float(inlet)) >= self._delta_t_threshold

        except (TypeError, ValueError):
            return False

        return False
