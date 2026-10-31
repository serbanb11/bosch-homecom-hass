"""Bosch HomeCom Custom Component."""

from __future__ import annotations

import re
from typing import Any

from homeassistant import config_entries, core
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BACON_DEVICE_TYPES
from .coordinator import (
    BoschComModuleCoordinatorBaconRac,
    BoschComModuleCoordinatorCommodule,
    BoschComModuleCoordinatorIcom,
    BoschComModuleCoordinatorK40,
)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom binary sensors."""
    coordinators = config_entry.runtime_data
    entities = []
    pending_pumps = []
    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] == "commodule":
            entities.append(BoschComCommoduleNetworkSensor(coordinator=coordinator))
        if coordinator.data.device["deviceType"] in ("k30", "k40"):
            for dev in coordinator.data.devices or []:
                if dev.get("rfConnectionStatus"):
                    dev_id = dev["id"].split("/")[-1]
                    entities.append(
                        BoschComThermostatRfStatusSensor(
                            coordinator=coordinator, dev_id=dev_id
                        )
                    )
        if isinstance(coordinator, BoschComModuleCoordinatorIcom):
            # One per circuit whose holidayMode/activated the gateway serves.
            for kind, refs in (
                ("heating_circuits", coordinator.data.heating_circuits),
                ("dhw_circuits", coordinator.data.dhw_circuits),
            ):
                for ref in refs or []:
                    if isinstance(ref.get("holidayActivated"), dict):
                        entities.append(
                            BoschComIcomHolidayActiveSensor(
                                coordinator, kind, ref["id"].split("/")[-1]
                            )
                        )
        if (
            isinstance(coordinator, BoschComModuleCoordinatorK40)
            and coordinator.local_first is not None
        ):
            pending = set()
            resources = (
                getattr(getattr(coordinator, "local_data", None), "resources", {}) or {}
            )
            for circuit in coordinator.data.heating_circuits or []:
                circuit_id = circuit["id"].split("/")[-1]
                if f"/heatingCircuits/{circuit_id}/pumpStatus" in resources:
                    entities.append(
                        BoschComK40LocalPumpStatusSensor(coordinator, circuit_id)
                    )
                else:
                    pending.add(circuit_id)
            if pending:
                pending_pumps.append((coordinator, pending))
        if coordinator.data.device["deviceType"] in BACON_DEVICE_TYPES:
            # Comfort features are switch entities (see switch.py); only the
            # connectivity sensor lives here.
            entities.append(BoschComBaconOnlineSensor(coordinator=coordinator))
    async_add_entities(entities)
    for coordinator, pending in pending_pumps:

        @callback
        def _add_pumps_when_served(coordinator=coordinator, pending=pending) -> None:
            resources = (
                getattr(getattr(coordinator, "local_data", None), "resources", {}) or {}
            )
            present = {
                circuit_id
                for circuit_id in pending
                if f"/heatingCircuits/{circuit_id}/pumpStatus" in resources
            }
            if present:
                pending.difference_update(present)
                async_add_entities(
                    BoschComK40LocalPumpStatusSensor(coordinator, circuit_id)
                    for circuit_id in sorted(present)
                )

        config_entry.async_on_unload(
            coordinator.async_add_listener(_add_pumps_when_served)
        )


class BoschComCommoduleNetworkSensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a commodule network connectivity sensor."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
    ) -> None:
        """Initialize binary sensor entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "wb_network"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-eth0-state"
        self._coordinator = coordinator

    @staticmethod
    def _get_state_value(state: dict | None) -> str | None:
        """Extract value from a state dict."""
        if isinstance(state, dict):
            return state.get("value")
        return None

    @property
    def is_on(self) -> bool | None:
        """Get network connectivity status (eth0 or wifi)."""
        eth0 = self._get_state_value(self._coordinator.data.eth0_state)
        wifi = self._get_state_value(self._coordinator.data.wifi_state)
        if eth0 is None and wifi is None:
            return None
        return eth0 in ("on", "connected") or wifi in ("on", "connected")

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return which network interfaces are active."""
        eth0 = self._get_state_value(self._coordinator.data.eth0_state)
        wifi = self._get_state_value(self._coordinator.data.wifi_state)
        return {"eth0": eth0, "wifi": wifi}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        eth0 = self._get_state_value(self._coordinator.data.eth0_state)
        wifi = self._get_state_value(self._coordinator.data.wifi_state)
        if eth0 is None and wifi is None:
            self._attr_is_on = None
        else:
            self._attr_is_on = eth0 in ("on", "connected") or wifi in (
                "on",
                "connected",
            )
        self.async_write_ha_state()


class BoschComThermostatRfStatusSensor(CoordinatorEntity, BinarySensorEntity):
    """Thermostat RF connection status binary sensor."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        dev_id: str,
    ) -> None:
        """Initialize RF status binary sensor."""
        super().__init__(coordinator)
        self._attr_translation_key = "thermostat_rf_status"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{dev_id}-rf_status"
        self._coordinator = coordinator
        self._dev_id = dev_id

    def _get_rf_status(self) -> str | None:
        """Get RF connection status value."""
        for dev in self._coordinator.data.devices or []:
            if dev.get("id", "").endswith(f"/{self._dev_id}"):
                return (dev.get("rfConnectionStatus") or {}).get("value")
        return None

    @property
    def is_on(self) -> bool | None:
        """Return True if RF connection is active."""
        status = self._get_rf_status()
        if status is None:
            return None
        return status.lower() in ("online", "connected", "on")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        status = self._get_rf_status()
        if status is None:
            self._attr_is_on = None
        else:
            self._attr_is_on = status.lower() in ("online", "connected", "on")
        self.async_write_ha_state()


class BoschComK40LocalPumpStatusSensor(CoordinatorEntity, BinarySensorEntity):
    """K40 circuit pump status from the read-only Local API.

    This is an on/off status, not a measured water-flow rate. A missing
    resource or local outage must be unavailable rather than falsely off.
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_should_poll = False
    _attr_translation_key = "local_hc_pump_status"

    def __init__(
        self, coordinator: BoschComModuleCoordinatorK40, circuit_id: str
    ) -> None:
        super().__init__(coordinator)
        self._resource = f"/heatingCircuits/{circuit_id}/pumpStatus"
        self._attr_unique_id = f"{coordinator.unique_id}-{circuit_id}-local_pump_status"
        self._attr_device_info = coordinator.device_info
        self._attr_translation_placeholders = {"circuit": circuit_id.upper()}
        self._attr_is_on = self._read_status()

    def _read_status(self) -> bool | None:
        local = getattr(self.coordinator, "local_data", None)
        resources = getattr(local, "resources", None) or {}
        payload = resources.get(self._resource)
        value = payload.get("value") if isinstance(payload, dict) else None
        if value == "on":
            return True
        if value == "off":
            return False
        return None

    @property
    def available(self) -> bool:
        return bool(
            getattr(self.coordinator, "local_healthy", False)
            and self._attr_is_on is not None
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_is_on = self._read_status()
        self.async_write_ha_state()


# --- Bacon (Matter-commissioned) RAC ------------------------------------------


class BoschComBaconOnlineSensor(CoordinatorEntity, BinarySensorEntity):
    """Connectivity of a bacon device, from the topics/info payload."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, coordinator: BoschComModuleCoordinatorBaconRac) -> None:
        """Initialize binary sensor entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "bacon_online"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-online"

    @property
    def _info(self) -> dict:
        data = self.coordinator.data
        return (getattr(data, "info", None) if data else None) or {}

    @property
    def is_on(self) -> bool | None:
        """Return the device's own online flag, or None before it is known."""
        value = self._info.get("online")
        return bool(value) if isinstance(value, bool) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the link quality and the versions the device reports alongside.

        The appliance firmware and the installed firmware package (from the
        ``$package`` shadow) have no better home than the connectivity sensor.
        """
        attributes: dict[str, Any] = {}
        quality = (self._info.get("network") or {}).get("signalQuality")
        if quality:
            attributes["signal_quality"] = quality
        appliance = self._info.get("appliance")
        if isinstance(appliance, dict) and appliance.get("firmwareVersion"):
            attributes["appliance_firmware"] = appliance["firmwareVersion"]
        get_package = getattr(
            getattr(self.coordinator, "client", None), "get_package", None
        )
        package = (
            get_package(self.coordinator.unique_id) if callable(get_package) else None
        )
        if isinstance(package, dict):
            for name, node in package.items():
                if not isinstance(node, dict):
                    continue
                attributes["firmware_package"] = name
                if node.get("version") is not None:
                    attributes["firmware_package_version"] = node["version"]
                auto = (node.get("attributes") or {}).get("autoUpdate")
                if isinstance(auto, bool):
                    attributes["firmware_auto_update"] = auto
                break
        return attributes


# --- icom holiday periods -----------------------------------------------------

_HOLIDAY_PERIOD_RE = re.compile(r"^hm[1-5]$")


class BoschComIcomHolidayActiveSensor(CoordinatorEntity, BinarySensorEntity):
    """Whether one of the icom's holiday periods is active on a circuit.

    ``holidayMode/activated`` names the period (``hm1`` to ``hm5``) while one
    applies and something else otherwise, as the app reads it. The period's
    dates and modes come from ``/system/holidayModes/hm{N}``, which the
    library already fetches, so they ride along as attributes.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "holiday_active"
    _attr_icon = "mdi:beach"

    def __init__(
        self, coordinator: BoschComModuleCoordinatorIcom, kind: str, circuit_id: str
    ) -> None:
        """Initialize for one heating or DHW circuit."""
        super().__init__(coordinator)
        self._kind = kind
        self._circuit_id = circuit_id
        self._attr_translation_placeholders = {"circuit": circuit_id}
        self._attr_unique_id = f"{coordinator.unique_id}-{circuit_id}-holiday_active"
        self._attr_device_info = coordinator.device_info

    def _activated(self) -> str | None:
        data = self.coordinator.data
        for ref in (getattr(data, self._kind, None) if data else None) or []:
            if ref.get("id", "").endswith(f"/{self._circuit_id}"):
                node = ref.get("holidayActivated")
                return node.get("value") if isinstance(node, dict) else None
        return None

    def _period(self) -> dict | None:
        value = self._activated()
        if not isinstance(value, str) or not _HOLIDAY_PERIOD_RE.match(value):
            return None
        data = self.coordinator.data
        for ref in (getattr(data, "holiday_mode", None) if data else None) or []:
            if isinstance(ref, dict) and ref.get("id", "").endswith(f"/{value}"):
                return ref
        return {"id": value}

    @property
    def is_on(self) -> bool | None:
        """Return whether a holiday period applies, None before the first read."""
        value = self._activated()
        if value is None:
            return None
        return bool(_HOLIDAY_PERIOD_RE.match(str(value)))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Describe the active period: id, dates, modes, fixed temperature."""
        period = self._period()
        if period is None:
            return {}

        def value(key: str) -> Any:
            node = period.get(key)
            return node.get("value") if isinstance(node, dict) else None

        start = end = None
        dates = value("startStop")
        if isinstance(dates, str) and "/" in dates:
            start, end = dates.split("/", 1)
        return {
            "period": period.get("id", "").split("/")[-1],
            "start": start,
            "end": end,
            "heating_mode": value("hcMode"),
            "dhw_mode": value("dhwMode"),
            "fixed_temperature": value("fixTemperature"),
        }
