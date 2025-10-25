"""Bosch HomeCom Custom Component."""

from datetime import timedelta
import logging
import re

from homeassistant import config_entries, core
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinatorK40, BoschComModuleCoordinatorRac, BoschComModuleCoordinatorWddw2

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1440)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the K40 dhw, hs and hc."""
    coordinators = config_entry.runtime_data
    entities = []

    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] == "rac":
            entities.append(
                BoschComSensorNotificationsRac(
                    coordinator=coordinator, config_entry=config_entry
                )
            )
        elif (
            coordinator.data.device["deviceType"] == "k40"
            or coordinator.data.device["deviceType"] == "k30"
        ):
            entities.append(
                BoschComSensorNotificationsK40(
                    coordinator=coordinator, config_entry=config_entry
                )
            )
        elif (
            coordinator.data.device["deviceType"] == "wddw2"
        ):
            entities.append(
                BoschComSensorNotificationsWddw2(
                    coordinator=coordinator, config_entry=config_entry
                )
            )
        if (
            coordinator.data.device["deviceType"] == "k40"
            or coordinator.data.device["deviceType"] == "k30"
        ):
            for ref in coordinator.data.dhw_circuits:
                dhw_id = ref["id"].split("/")[-1]
                entities.append(
                    BoschComSensorDhw(
                        coordinator=coordinator, config_entry=config_entry, field=dhw_id
                    )
                )
            for ref in coordinator.data.heating_circuits:
                hc_id = ref["id"].split("/")[-1]
                entities.append(
                    BoschComSensorHc(
                        coordinator=coordinator, config_entry=config_entry, field=hc_id
                    )
                )
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
        elif (
            coordinator.data.device["deviceType"] == "wddw2"
        ):
            for ref in coordinator.data.dhw_circuits:
                dhw_id = ref["id"].split("/")[-1]
                if re.fullmatch(r"dhw\d", dhw_id):
                    entities.append(
                        BoschComSensorDhwWddw2(
                            coordinator=coordinator, config_entry=config_entry, field=dhw_id
                        )
                    )
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
                actualTemp_unit = (entry.get("actualTemp") or {}).get(
                    "unitOfMeasure", "unknown"
                )
                return str(actualTemp_value) + actualTemp_unit
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


class BoschComSensorOutdoorTemp(BoschComSensorBase):
    """BoschComSensorOutdoorTemp sensor."""

    _attr_has_entity_name = True
    _attr_state_class = SensorDeviceClass.TEMPERATURE

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
        return str(
            self.coordinator.data.outdoor_temp.get("value", "unknown")
        ) + self.coordinator.data.outdoor_temp.get("unitOfMeasure", "unknown")


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

        result = {
            "numberOfStartsCh": numberOfStarts_dict.get("ch", "unknown"),
            "numberOfStartsDhw": numberOfStarts_dict.get("dhw", "unknown"),
            "numberOfStartsTotal": numberOfStarts_dict.get("total", "unknown"),
            "returnTemperature": returnTemperature,
            "actualSupplyTemperature": actualSupplyTemperature,
            "actualModulation": actualModulation,
            "collectorInflowTemp": collectorInflowTemp,
            "collectorOutflowTemp": collectorOutflowTemp,
        }

        if not len(consumption):
            result.update(
                {
                    "outputProduced": consumption,
                    "eheater": consumption,
                    "compressor": consumption,
                }
            )
        else:
            result.update(
                {
                    "outputProduced": (consumption[0] or {}).get(
                        "outputProduced", "unknown"
                    ),
                    "eheater": (consumption[1] or {}).get("eheater", "unknown"),
                    "compressor": (consumption[2] or {}).get("compressor", "unknown"),
                }
            )
        return result


class BoschComSensorDhwWddw2(BoschComSensorBase):
    """BoschComSensorDhw sensor."""

    _attr_has_entity_name = True

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
    def state(self):
        """Return BoschComSensorDhw operationMode."""
        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == "/dhwCircuits/" + self.field:
                operationMode_value = (entry.get("operationMode") or {}).get(
                    "value", "unknown"
                )
                actualTemp_value = (
                    (entry.get("tempLevel") or {}).get(operationMode_value, {}).get("value", "unknown")
                )
                actualTemp_unit = (
                    (entry.get("tempLevel") or {}).get(operationMode_value, {}).get("unitOfMeasure", "unknown")
                )
                return str(actualTemp_value) + actualTemp_unit
        return "unknown"

    @property
    def extra_state_attributes(self):
        """Return attributes."""

        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == "/dhwCircuits/" + self.field:
                operationMode_value = (entry.get("operationMode") or {}).get(
                    "value", "unknown"
                )
                numberOfStarts_value = (entry.get("nbStarts") or {}).get("value", "unknown")
                ariboxTemp_value = (entry.get("airBoxTemperature") or {}).get("value", "unknown")
                fanSpeed_value = (entry.get("fanSpeed") or {}).get("value", "unknown")
                inletTemp_value = (entry.get("inletTemperature") or {}).get("value", "unknown")
                outletTemp_value = (entry.get("outletTemperature") or {}).get("value", "unknown")
                waterFlow_value = (entry.get("waterFlow") or {}).get("value", "unknown")

                result = {
                    "nbStarts": numberOfStarts_value,
                    "airBoxTemperature": ariboxTemp_value,
                    "fanSpeed": fanSpeed_value,
                    "outletTemperature": outletTemp_value,
                    "waterFlow": waterFlow_value,
                }

                for item, temp_item in (entry.get("tempLevel") or {}).items():
                    result[item] = (
                        temp_item.get("value", "unknown") if temp_item else "unknown"
                    )

                return result
        return "unknown"
