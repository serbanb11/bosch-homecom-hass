"""Bosch HomeCom Custom Component."""

from datetime import timedelta
import logging

from homeassistant import config_entries, core
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinatorK40, BoschComModuleCoordinatorRac

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
            entities.extend([
                BoschComSensorHs(
                    coordinator=coordinator,
                    config_entry=config_entry,
                    field="heat_source",
                ),            
                BoschComSensorOutdoorTemp(
                    coordinator=coordinator,
                    config_entry=config_entry,
                    field="outdoor_temp",
                )]
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
            "Init BoschComSensorNotificationsK40: name=%s, unique_id=%s",
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
                actualTemp_value = entry["actualTemp"].get("value", "unknown")
                actualTemp_unit = entry["actualTemp"].get("unitOfMeasure", "unknown")
                return str(actualTemp_value) + actualTemp_unit
        return "unknown"

    @property
    def extra_state_attributes(self):
        """Return attributes."""

        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == "/dhwCircuits/" + self.field:
                operationMode_value = entry["operationMode"].get("value", "unknown")
                charge_value = entry["charge"].get("value", "unknown")
                chargeRemainingTime_value = entry["chargeRemainingTime"].get("value", "unknown")
                singleChargeSetpoint_value = entry["singleChargeSetpoint"].get("value", "unknown")
                currentTemperatureLevel_value = entry["currentTemperatureLevel"].get("value", "unknown")

                result = {
                    "operationMode": operationMode_value,
                    "currentTemperatureLevel": currentTemperatureLevel_value,
                    "charge": charge_value,
                    "chargeRemainingTime": chargeRemainingTime_value,
                    "singleChargeSetpoint": singleChargeSetpoint_value,
                }

                for item in entry["tempLevel"]:
                    result[item] = entry["tempLevel"][item]["value"]

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
                return entry["operationMode"].get("value", "unknown")

        return "unknown"

    @property
    def extra_state_attributes(self):
        """Return attributes."""

        for entry in self.coordinator.data.heating_circuits:
            if entry.get("id") == "/heatingCircuits/" + self.field:
                currentSuWiMode_value = entry["currentSuWiMode"].get("value", "unknown")
                heatCoolMode_value = entry["heatCoolMode"].get("value", "unknown")
                roomTemp_value = entry["roomTemp"].get("value", "unknown")
                actualHumidity_value = entry["actualHumidity"].get("value", "unknown")
                manualRoomSetpoint_value = entry["manualRoomSetpoint"].get("value", "unknown")
                currentRoomSetpoint_value = entry["currentRoomSetpoint"].get("value", "unknown")
                coolingRoomTempSetpoint_value = entry["coolingRoomTempSetpoint"].get("value", "unknown")

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
        return self.coordinator.data.outdoor_temp.get("value", "unknown")


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
        return self.coordinator.data.hs_pump_type.get("value", "unknown")

    @property
    def extra_state_attributes(self):
        """Return attributes."""
        consumption = self.coordinator.data.consumption.get("values", "unknown")

        if not len(consumption):
            return {
                "outputProduced": consumption,
                "eheater": consumption,
                "compressor": consumption,
            }

        return {
            "outputProduced": consumption[0]["outputProduced"],
            "eheater": consumption[1]["eheater"],
            "compressor": consumption[2]["compressor"],
        }
