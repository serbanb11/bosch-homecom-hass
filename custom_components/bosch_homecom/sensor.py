"""Bosch HomeCom Custom Component."""

from datetime import timedelta
import logging

from homeassistant import config_entries, core
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BoschComModuleCoordinatorK40

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
        if coordinator.data.device["deviceType"] == "k40":
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
            entities.append(
                BoschComSensorHs(
                    coordinator=coordinator,
                    config_entry=config_entry,
                    field="heat_source",
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
            if (
                entry.get("id") == "/dhwCircuits/" + self.field
                and "operationMode" in entry
            ):
                return entry["operationMode"].get("value")
        _LOGGER.debug("BoschComSensorDhw - unknown")
        return "unknown"

    @property
    def extra_state_attributes(self):
        """Return attributes."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        for entry in self.coordinator.data.dhw_circuits:
            if entry.get("id") == "/dhwCircuits/" + self.field:
                actualTemp_value = safe_get(entry["actualTemp"], "value")
                actualTemp_unit = safe_get(entry["actualTemp"], "unitOfMeasure")
                # charge_value = safe_get(entry["charge"], "value")
                # chargeRemainingTime_value = safe_get(
                #    entry["chargeRemainingTime"], "value"
                # )
                # singleChargeSetpoint_value = safe_get(
                #    entry["singleChargeSetpoint"], "value"
                # )

        return {
            "actualTemp": str(actualTemp_value) + actualTemp_unit,
            #            "charge": charge_value,
            #            "chargeRemainingTime": chargeRemainingTime_value,
            #            "singleChargeSetpoint": singleChargeSetpoint_value,
        }


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

        _LOGGER.debug(
            "Init BoschComSensorHc: name=%s, unique_id=%s",
            self._attr_name,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return BoschComSensorHc operationMode."""
        return "available"


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
        return "available"

    @property
    def extra_state_attributes(self):
        """Return attributes."""

        def safe_get(data, key, default="unknown"):
            """Return unknown if null."""
            value = data.get(key)
            return value if value is not None else default

        consumption = safe_get(self.coordinator.data.consumption, "values")

        return {
            "outputProduced": consumption[0]["outputProduced"],
            "eheater": consumption[1]["eheater"],
            "compressor": consumption[2]["compressor"],
        }
