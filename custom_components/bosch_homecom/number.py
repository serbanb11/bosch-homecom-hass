"""Bosch HomeCom Custom Component."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries, core
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfElectricCurrent, UnitOfTemperature, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import (
    BoschComModuleCoordinatorCommodule,
    BoschComModuleCoordinatorIcom,
    BoschComModuleCoordinatorK40,
    BoschComModuleCoordinatorRrc2,
)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BoschCom number entities."""
    coordinators = config_entry.runtime_data
    entities = []
    for coordinator in coordinators:
        if coordinator.data.device["deviceType"] == "commodule":
            for cp in coordinator.data.charge_points or []:
                cp_id = cp["id"].split("/")[-1]
                entities.append(
                    BoschComCommodulePriceNumber(coordinator=coordinator, cp_id=cp_id)
                )
                entities.append(
                    BoschComCommoduleLimitNumber(coordinator=coordinator, cp_id=cp_id)
                )
        if coordinator.data.device["deviceType"] in ("k30", "k40"):
            for entry in coordinator.data.ventilation:
                zone_id = entry["id"].split("/")[-1]
                duration = entry.get("summerBypassDuration") or {}
                if "value" in duration:
                    entities.append(
                        BoschComNumberVentilationSummerDuration(
                            coordinator=coordinator,
                            zone_id=zone_id,
                            min_value=duration.get("minValue", 1),
                            max_value=duration.get("maxValue", 12),
                        )
                    )
        if coordinator.data.device["deviceType"] == "rrc2":
            entities.extend(_build_rrc2_numbers(coordinator))
        if coordinator.data.device["deviceType"] == "icom":
            entities.extend(_build_icom_dhw_numbers(coordinator))
    async_add_entities(entities)


class BoschComCommodulePriceNumber(CoordinatorEntity, NumberEntity):
    """Representation of a commodule electricity price number."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        cp_id: str,
    ) -> None:
        """Initialize number entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "wb_price"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{cp_id}-price"
        self._coordinator = coordinator
        self._cp_id = cp_id

    def _get_cp_data(self) -> dict | None:
        """Get charge point data."""
        for cp in self._coordinator.data.charge_points or []:
            if cp["id"].split("/")[-1] == self._cp_id:
                return cp
        return None

    @property
    def native_value(self) -> float | None:
        """Get current price value."""
        cp = self._get_cp_data()
        if cp is None:
            return None
        price = cp.get("price")
        if price is None:
            return None
        return price.get("value")

    async def async_set_native_value(self, value: float) -> None:
        """Set new price value."""
        device_id = self._coordinator.data.device["deviceId"]
        await self._coordinator.bhc.async_put_cp_conf_price(
            device_id, self._cp_id, value
        )
        await self._coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        cp = self._get_cp_data()
        if cp is not None:
            price = cp.get("price")
            if price is not None:
                self._attr_native_value = price.get("value")
            else:
                self._attr_native_value = None
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class BoschComCommoduleLimitNumber(CoordinatorEntity, NumberEntity):
    """Representation of a commodule charging current limit number."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_should_poll = False
    _attr_native_min_value = 6
    _attr_native_max_value = 16
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorCommodule,
        cp_id: str,
    ) -> None:
        """Initialize number entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "wb_charge_limit"
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{cp_id}-charge_limit"
        self._coordinator = coordinator
        self._cp_id = cp_id

    def _get_cp_data(self) -> dict | None:
        """Get charge point data."""
        for cp in self._coordinator.data.charge_points or []:
            if cp["id"].split("/")[-1] == self._cp_id:
                return cp
        return None

    @property
    def native_value(self) -> float | None:
        """Get current charging limit value."""
        cp = self._get_cp_data()
        if cp is None:
            return None
        raw = cp.get("telemetry") or {}
        telemetry = raw.get("values", raw)
        if not isinstance(telemetry, dict):
            return None
        val = telemetry.get("limit")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new charging limit value."""
        device_id = self._coordinator.data.device["deviceId"]
        await self._coordinator.bhc.async_cp_set_limit(
            device_id, self._cp_id, int(value)
        )
        await self._coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        cp = self._get_cp_data()
        if cp is not None:
            raw = cp.get("telemetry") or {}
            telemetry = raw.get("values", raw)
            if isinstance(telemetry, dict):
                val = telemetry.get("limit")
                if val is not None:
                    try:
                        self._attr_native_value = float(val)
                    except (ValueError, TypeError):
                        self._attr_native_value = None
                else:
                    self._attr_native_value = None
            else:
                self._attr_native_value = None
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class BoschComNumberVentilationSummerDuration(CoordinatorEntity, NumberEntity):
    """Representation of ventilation summer-bypass manual override duration."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_should_poll = False
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.HOURS

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorK40,
        zone_id: str,
        min_value: float,
        max_value: float,
    ) -> None:
        """Initialize number entity."""
        super().__init__(coordinator)
        self._attr_translation_key = "ventilation_summer_duration"
        self._attr_translation_placeholders = {"zone": zone_id}
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = (
            f"{coordinator.unique_id}-{zone_id}-summerbypass-duration"
        )
        self._attr_suggested_object_id = zone_id + "_summerbypass_duration"
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._coordinator = coordinator
        self._zone_id = zone_id

    def _get_zone(self) -> dict | None:
        """Return the ventilation zone entry."""
        for entry in self._coordinator.data.ventilation:
            if entry.get("id") == "/ventilation/" + self._zone_id:
                return entry
        return None

    @property
    def native_value(self) -> float | None:
        """Return current duration in hours."""
        zone = self._get_zone()
        if zone is None:
            return None
        val = (zone.get("summerBypassDuration") or {}).get("value")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Send new duration to the device."""
        device_id = self._coordinator.data.device["deviceId"]
        await self._coordinator.bhc.async_set_ventilation_summer_duration(
            device_id, self._zone_id, value
        )
        await self._coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.native_value
        self.async_write_ha_state()


# ---- RRC2 numbers -----------------------------------------------------------


class BoschComRrc2Number(CoordinatorEntity, NumberEntity):
    """Writable scalar for one field of an RRC2 HC or DHW circuit."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorRrc2,
        *,
        scope: str,
        circuit_id: str,
        field: str,
        setter: str,
        name_suffix: str,
        unique_suffix: str,
        min_value: float,
        max_value: float,
        step: float,
        unit: str | None = None,
        icon: str | None = None,
        diagnostic: bool = True,
        cast: type = float,
    ) -> None:
        """Initialize one RRC2 number."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_name = name_suffix
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_mode = NumberMode.BOX
        if icon:
            self._attr_icon = icon
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._scope = scope
        self._circuit_id = circuit_id
        self._field = field
        self._setter = setter
        self._cast = cast

    def _find_circuit(self) -> dict | None:
        refs = (
            self.coordinator.data.heating_circuits
            if self._scope == "hc"
            else self.coordinator.data.dhw_circuits
        )
        suffix = f"/{self._circuit_id}"
        for ref in refs or []:
            if ref.get("id", "").endswith(suffix):
                return ref
        return None

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        ref = self._find_circuit()
        if not ref:
            return None
        node = ref.get(self._field)
        if not isinstance(node, dict):
            return None
        val = node.get("value")
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Push the new value to the device."""
        device_id = self.coordinator.data.device["deviceId"]
        setter = getattr(self.coordinator.bhc, self._setter)
        await setter(device_id, self._circuit_id, self._cast(value))
        await self.coordinator.async_request_refresh()


def _build_rrc2_numbers(
    coordinator: BoschComModuleCoordinatorRrc2,
) -> list[NumberEntity]:
    """Build the standard RRC2 number set for one device."""
    entities: list[NumberEntity] = []

    hc_specs: list[dict[str, Any]] = [
        {
            "field": "heatCurveMax",
            "setter": "async_set_hc_heat_curve_max",
            "name": "heat_curve_max",
            "min": 40,
            "max": 90,
            "step": 1,
            "unit": UnitOfTemperature.CELSIUS,
        },
        {
            "field": "heatCurveMin",
            "setter": "async_set_hc_heat_curve_min",
            "name": "heat_curve_min",
            "min": 20,
            "max": 90,
            "step": 1,
            "unit": UnitOfTemperature.CELSIUS,
        },
        {
            "field": "maxSupply",
            "setter": "async_set_hc_max_supply",
            "name": "max_supply",
            "min": 25,
            "max": 90,
            "step": 1,
            "unit": UnitOfTemperature.CELSIUS,
        },
        {
            "field": "minSupply",
            "setter": "async_set_hc_min_supply",
            "name": "min_supply",
            "min": 10,
            "max": 90,
            "step": 1,
            "unit": UnitOfTemperature.CELSIUS,
        },
        {
            "field": "nightThreshold",
            "setter": "async_set_hc_night_threshold",
            "name": "night_threshold",
            "min": 5,
            "max": 30,
            "step": 0.5,
            "unit": UnitOfTemperature.CELSIUS,
        },
        {
            "field": "roomInfluence",
            "setter": "async_set_hc_room_influence",
            "name": "room_influence",
            "min": 0,
            "max": 3,
            "step": 1,
            "unit": None,
        },
    ]

    for ref in coordinator.data.heating_circuits or []:
        hc_id = ref["id"].split("/")[-1]
        for spec in hc_specs:
            if not isinstance(ref.get(spec["field"]), dict):
                continue
            entities.append(
                BoschComRrc2Number(
                    coordinator,
                    scope="hc",
                    circuit_id=hc_id,
                    field=spec["field"],
                    setter=spec["setter"],
                    name_suffix=f"{hc_id}_{spec['name']}",
                    unique_suffix=f"{hc_id}-{spec['name']}",
                    min_value=spec["min"],
                    max_value=spec["max"],
                    step=spec["step"],
                    unit=spec["unit"],
                )
            )

    dhw_specs: list[dict[str, Any]] = [
        {
            "field": "extraDhwDuration",
            "setter": "async_set_dhw_extra_dhw_duration",
            "name": "extra_dhw_duration",
            "min": 15,
            "max": 2880,
            "step": 15,
            "unit": UnitOfTime.MINUTES,
            "cast": int,
        },
        {
            "field": "temperatureLevelHigh",
            "setter": "async_set_dhw_temp_level_high",
            "name": "temperature_level_high",
            "min": 10,
            "max": 80,
            "step": 1,
            "unit": UnitOfTemperature.CELSIUS,
            "cast": float,
        },
        {
            "field": "thermalDisinfectTime",
            "setter": "async_set_dhw_thermal_disinfect_time",
            "name": "thermal_disinfect_time",
            "min": 0,
            "max": 1439,
            "step": 1,
            "unit": UnitOfTime.MINUTES,
            "cast": int,
        },
    ]

    for ref in coordinator.data.dhw_circuits or []:
        dhw_id = ref["id"].split("/")[-1]
        for spec in dhw_specs:
            if not isinstance(ref.get(spec["field"]), dict):
                continue
            entities.append(
                BoschComRrc2Number(
                    coordinator,
                    scope="dhw",
                    circuit_id=dhw_id,
                    field=spec["field"],
                    setter=spec["setter"],
                    name_suffix=f"{dhw_id}_{spec['name']}",
                    unique_suffix=f"{dhw_id}-{spec['name']}",
                    min_value=spec["min"],
                    max_value=spec["max"],
                    step=spec["step"],
                    unit=spec["unit"],
                    cast=spec.get("cast", float),
                )
            )

    return entities


# ---- ICOM DHW numbers -------------------------------------------------------


class BoschComIcomDhwNumber(CoordinatorEntity, NumberEntity):
    """Writable scalar for one DHW field of an icom heat pump."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: BoschComModuleCoordinatorIcom,
        *,
        dhw_id: str,
        field: str,
        setter: str,
        name_suffix: str,
        unique_suffix: str,
        min_value: float,
        max_value: float,
        step: float,
        unit: str | None = None,
        icon: str | None = None,
        cast: type = float,
    ) -> None:
        """Initialize one icom DHW number."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}-{unique_suffix}"
        self._attr_name = name_suffix
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        if icon:
            self._attr_icon = icon
        self._dhw_id = dhw_id
        self._field = field
        self._setter = setter
        self._cast = cast

    def _find_dhw(self) -> dict | None:
        suffix = f"/{self._dhw_id}"
        for ref in self.coordinator.data.dhw_circuits or []:
            if ref.get("id", "").endswith(suffix):
                return ref
        return None

    @property
    def native_value(self) -> float | None:
        """Return current value."""
        ref = self._find_dhw()
        if not ref:
            return None
        node = ref.get(self._field)
        if not isinstance(node, dict):
            return None
        val = node.get("value")
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Push new value to the device."""
        device_id = self.coordinator.data.device["deviceId"]
        setter = getattr(self.coordinator.bhc, self._setter)
        await setter(device_id, self._dhw_id, self._cast(value))
        await self.coordinator.async_request_refresh()


def _build_icom_dhw_numbers(
    coordinator: BoschComModuleCoordinatorIcom,
) -> list[NumberEntity]:
    """Build the writable icom DHW number set for one device."""
    entities: list[NumberEntity] = []

    for ref in coordinator.data.dhw_circuits or []:
        dhw_id = ref["id"].split("/")[-1]

        charge_dur = ref.get("chargeDuration")
        if isinstance(charge_dur, dict):
            entities.append(
                BoschComIcomDhwNumber(
                    coordinator,
                    dhw_id=dhw_id,
                    field="chargeDuration",
                    setter="async_set_dhw_charge_duration",
                    name_suffix=f"{dhw_id}_charge_duration",
                    unique_suffix=f"{dhw_id}-charge-duration",
                    min_value=charge_dur.get("minValue", 15),
                    max_value=charge_dur.get("maxValue", 2880),
                    step=15,
                    unit=UnitOfTime.MINUTES,
                    cast=int,
                )
            )

        single_setpoint = ref.get("singleChargeSetpoint")
        if isinstance(single_setpoint, dict):
            entities.append(
                BoschComIcomDhwNumber(
                    coordinator,
                    dhw_id=dhw_id,
                    field="singleChargeSetpoint",
                    setter="async_set_dhw_charge_setpoint",
                    name_suffix=f"{dhw_id}_single_charge_setpoint",
                    unique_suffix=f"{dhw_id}-single-charge-setpoint",
                    min_value=single_setpoint.get("minValue", 50),
                    max_value=single_setpoint.get("maxValue", 70),
                    step=1,
                    unit=UnitOfTemperature.CELSIUS,
                )
            )

    return entities
