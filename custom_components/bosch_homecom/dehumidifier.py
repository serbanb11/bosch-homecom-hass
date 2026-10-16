"""Dehumidifier entities for the Bosch 6000i and 8000i using the existing HomeCom cloud MQTT connection.

Local extension for bosch-homecom-hass 1.5.1. The transport calls are public
homecom_alt 1.8.2 APIs; settings come from the device's own capability metadata.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.humidifier import (
    HumidifierAction,
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homecom_alt import ApiError

from .bacon import bacon_meta_state
from .const import DOMAIN

DEHUMIDIFIER_MODES = ("auto", "night", "laundry")
DEHUMIDIFIER_APPLIANCE_TYPES = ("dry_6000i", "dry_8000i")


def is_dehumidifier_device(coordinator: Any) -> bool:
    """Identify 6000i/8000i dehumidifiers from identity or humidity capability."""
    data = coordinator.data
    if data is None or data.device.get("deviceType") != "bacon_rac":
        return False
    info = getattr(data, "info", None) or {}
    appliance_type = (info.get("appliance") or {}).get("type", "")
    if isinstance(appliance_type, str) and appliance_type:
        # These names are Bosch protocol identifiers, not our internal naming.
        return any(
            appliance_type == model or appliance_type.startswith(f"{model}_")
            for model in DEHUMIDIFIER_APPLIANCE_TYPES
        )
    # The state shadow is fetched at startup, whereas info/meta are push-only.
    reported = getattr(data, "reported", None) or {}
    metadata = bacon_meta_state(getattr(data, "metadata", None))
    return (
        ("humiditySetpoint" in reported or "humiditySetpoint" in metadata)
        and "tempSetpoint" not in reported
        and "tempSetpoint" not in metadata
    )


@callback
def _async_migrate_dehumidifier_ids(hass, entry) -> None:
    """Rename internal unique IDs without changing the user's entity IDs."""
    registry = er.async_get(hass)
    prefixes = {
        f"{coordinator.unique_id}-dry-": f"{coordinator.unique_id}-dehumidifier-"
        for coordinator in entry.runtime_data
    }
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.platform != DOMAIN:
            continue
        for old_prefix, new_prefix in prefixes.items():
            if not registered.unique_id.startswith(old_prefix):
                continue
            new_unique_id = new_prefix + registered.unique_id[len(old_prefix) :]
            if registry.async_get_entity_id(registered.domain, DOMAIN, new_unique_id):
                break
            registry.async_update_entity(
                registered.entity_id, new_unique_id=new_unique_id
            )
            break


@callback
def async_setup_dehumidifier_entities(
    hass, entry, async_add_entities, factory: Callable
) -> None:
    """Add entities also when device identification arrives after startup."""
    _async_migrate_dehumidifier_ids(hass, entry)
    for coordinator in entry.runtime_data:
        data = coordinator.data
        if data is None or data.device.get("deviceType") != "bacon_rac":
            continue
        _watch_dehumidifier_device(entry, coordinator, async_add_entities, factory)


@callback
def _watch_dehumidifier_device(entry, coordinator, async_add_entities, factory) -> None:
    added = False

    @callback
    def discover() -> None:
        nonlocal added
        if added or not is_dehumidifier_device(coordinator):
            return
        added = True
        async_add_entities(factory(coordinator))

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class BoschComDehumidifierEntity(CoordinatorEntity):
    """Read device reports without treating desired settings as confirmed state."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, suffix: str, name: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}-dehumidifier-{suffix}"
        self._attr_device_info = coordinator.device_info
        self._attr_name = name

    @property
    def reported(self) -> dict:
        return getattr(self.coordinator.data, "reported", None) or {}

    @property
    def readings(self) -> dict:
        return getattr(self.coordinator.data, "sensor", None) or {}

    @property
    def metadata(self) -> dict:
        return bacon_meta_state(getattr(self.coordinator.data, "metadata", None))

    @property
    def available(self) -> bool:
        info = getattr(self.coordinator.data, "info", None) or {}
        return super().available and info.get("online") is not False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        timestamp = self.readings.get("timestamp")
        if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
            try:
                return {
                    "measured_at": datetime.fromtimestamp(timestamp, UTC).isoformat()
                }
            except (ValueError, OverflowError, OSError):
                pass
        return {}


class BoschComDehumidifier(BoschComDehumidifierEntity, HumidifierEntity):
    """A native dehumidifier with power, modes and a humidity setpoint."""

    _attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER
    _attr_supported_features = HumidifierEntityFeature.MODES

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "control", "Luftentfeuchter")

    @property
    def is_on(self) -> bool | None:
        value = self.reported.get("powerEnabled")
        return value if isinstance(value, bool) else None

    @property
    def current_humidity(self) -> float | None:
        value = self.readings.get("relHumidity")
        return value if type(value) in (int, float) else None

    @property
    def target_humidity(self) -> float | None:
        value = self.reported.get("humiditySetpoint")
        return value if type(value) in (int, float) else None

    def _bound(self, key: str, fallback: float) -> float:
        value = self.metadata.get("humiditySetpoint", {}).get(key)
        return (
            value if type(value) in (int, float) and math.isfinite(value) else fallback
        )

    @property
    def min_humidity(self) -> float:
        return self._bound("min", 40)

    @property
    def max_humidity(self) -> float:
        return self._bound("max", 70)

    @property
    def target_humidity_step(self) -> float:
        step = self._bound("step", 5)
        return step if step > 0 else 5

    @property
    def available_modes(self) -> list[str]:
        values = self.metadata.get("opMode", {}).get("enum")
        if isinstance(values, list) and values:
            return [mode for mode in DEHUMIDIFIER_MODES if mode in values]
        return list(DEHUMIDIFIER_MODES)

    @property
    def mode(self) -> str | None:
        value = self.reported.get("opMode")
        return value if value in self.available_modes else None

    @property
    def action(self) -> HumidifierAction | None:
        if self.is_on is False:
            return HumidifierAction.OFF
        if self.is_on is None:
            return None
        if any(
            self.readings.get(key) is True
            for key in ("idleState", "waterTankFull", "defrostingActive")
        ):
            return HumidifierAction.IDLE
        if self.readings.get("idleState") is False:
            return HumidifierAction.DRYING
        return None

    async def _publish(self, payload: dict[str, Any]) -> None:
        """Publish only known writable fields through the existing MQTT client."""
        for field in payload:
            capability = self.metadata.get(field)
            # Moving from laundry to auto also enables target humidity.
            changing_to_auto = (
                field == "humiditySetpoint" and payload.get("opMode") == "auto"
            )
            if capability and capability.get("ro") is True and not changing_to_auto:
                raise ServiceValidationError(f"{field} ist momentan schreibgeschützt.")
        try:
            await self.coordinator.client.async_set_desired(
                self.coordinator.unique_id, payload
            )
            await self.coordinator.async_request_refresh()
        except ApiError as err:
            raise HomeAssistantError(
                "Bosch HomeCom konnte den Befehl nicht übertragen."
            ) from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._publish({"powerEnabled": True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._publish({"powerEnabled": False})

    async def async_set_mode(self, mode: str) -> None:
        if mode not in self.available_modes:
            raise ServiceValidationError(f"Nicht unterstützte Betriebsart: {mode}")
        await self._publish({"opMode": mode})

    async def async_set_humidity(self, humidity: int) -> None:
        if type(humidity) not in (int, float) or not math.isfinite(humidity):
            raise ServiceValidationError("Die Sollfeuchte muss eine gültige Zahl sein.")
        step = self.target_humidity_step
        offset = (humidity - self.min_humidity) / step
        if not self.min_humidity <= humidity <= self.max_humidity or not math.isclose(
            offset, round(offset)
        ):
            raise ServiceValidationError(
                f"Sollfeuchte: {self.min_humidity:g}–{self.max_humidity:g} % in {step:g}-%-Schritten."
            )
        payload: dict[str, Any] = {"humiditySetpoint": int(humidity)}
        if self.mode == "laundry":
            if "auto" not in self.available_modes:
                raise ServiceValidationError(
                    "Die Sollfeuchte ist im Wäschebetrieb nicht einstellbar."
                )
            payload["opMode"] = "auto"
        await self._publish(payload)


class BoschComDehumidifierHumidity(BoschComDehumidifierEntity, SensorEntity):
    """Actual relative humidity from the device's sensor channel."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "humidity", "Luftfeuchtigkeit")

    @property
    def native_value(self) -> float | None:
        value = self.readings.get("relHumidity")
        return value if type(value) in (int, float) else None


class BoschComDehumidifierStatus(BoschComDehumidifierEntity, BinarySensorEntity):
    """Reported tank, defrost, pump and idle flags; absent is unknown."""

    def __init__(self, coordinator, field: str, name: str, device_class=None) -> None:
        super().__init__(coordinator, field, name)
        self._field = field
        self._attr_device_class = device_class

    @property
    def is_on(self) -> bool | None:
        value = self.readings.get(self._field)
        return value if isinstance(value, bool) else None


def dehumidifier_status_entities(coordinator) -> list[BoschComDehumidifierStatus]:
    return [
        BoschComDehumidifierStatus(
            coordinator,
            "waterTankFull",
            "Wassertank voll",
            BinarySensorDeviceClass.PROBLEM,
        ),
        BoschComDehumidifierStatus(
            coordinator, "defrostingActive", "Abtauen", BinarySensorDeviceClass.RUNNING
        ),
        BoschComDehumidifierStatus(
            coordinator,
            "condensatePumpRunning",
            "Kondensatpumpe",
            BinarySensorDeviceClass.RUNNING,
        ),
        BoschComDehumidifierStatus(coordinator, "idleState", "Ruhezustand"),
    ]
