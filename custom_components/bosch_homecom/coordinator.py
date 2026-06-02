"""HomeCom coordinator."""

from __future__ import annotations

from abc import abstractmethod
import asyncio
import logging
from typing import Any, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homecom_alt import (
    ApiError,
    AuthFailedError,
    BHCDeviceCommodule,
    BHCDeviceGeneric,
    BHCDeviceIcom,
    BHCDeviceK40,
    BHCDeviceRac,
    BHCDeviceRrc2,
    BHCDeviceWddw2,
    HomeComRac,
    InvalidSensorDataError,
    NotRespondingError,
)
from tenacity import RetryError

from .const import CONF_REFRESH, DEFAULT_UPDATE_INTERVAL, DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)

T = TypeVar(
    "T",
    BHCDeviceGeneric,
    BHCDeviceRac,
    BHCDeviceK40,
    BHCDeviceIcom,
    BHCDeviceRrc2,
    BHCDeviceWddw2,
    BHCDeviceCommodule,
)


class BoschComModuleCoordinatorBase(DataUpdateCoordinator[T]):
    """Base coordinator with shared auth and device metadata logic."""

    def __init__(
        self,
        hass: HomeAssistant,
        bhc: HomeComRac,
        device: list,
        firmware: dict,
        entry: ConfigEntry,
        auth_provider: bool,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
            always_update=True,
        )
        self.bhc = bhc
        self.unique_id = device["deviceId"]
        self.device = device
        self.entry = entry
        self.auth_provider = auth_provider

        self.device_info = DeviceInfo(
            serial_number=self.unique_id,
            identifiers={(DOMAIN, self.unique_id)},
            name="Boschcom_" + device["deviceType"] + "_" + device["deviceId"],
            sw_version=firmware["value"],
            manufacturer=MANUFACTURER,
        )

    async def _async_update_data(self) -> T:
        """Update data via library."""
        if self.auth_provider:
            try:
                await self.bhc.get_token()
                if self.bhc.token != self.entry.data.get(
                    CONF_TOKEN
                ) or self.bhc.refresh_token != self.entry.data.get(CONF_REFRESH):
                    new_data = dict(self.entry.data)
                    new_data[CONF_TOKEN] = self.bhc.token
                    new_data[CONF_REFRESH] = self.bhc.refresh_token
                    self.hass.config_entries.async_update_entry(
                        self.entry, data=new_data
                    )
                    _LOGGER.debug(
                        "Device_Id: %s, persisted refreshed auth tokens",
                        self.unique_id,
                    )
            except AuthFailedError:
                self.entry.async_start_reauth(self.hass)
                raise UpdateFailed("Re-authentication required")

        try:
            data = await self.bhc.async_update(self.unique_id)
        except (
            ApiError,
            InvalidSensorDataError,
            RetryError,
            NotRespondingError,
        ) as error:
            raise UpdateFailed(error) from error

        return self._build_device_data(data)

    @abstractmethod
    def _build_device_data(self, data: T) -> T:
        """Build device-specific data object from raw API response."""


class BoschComModuleCoordinatorGeneric(BoschComModuleCoordinatorBase[BHCDeviceGeneric]):
    """A coordinator to manage the fetching of BoschCom data."""

    def _build_device_data(self, data: BHCDeviceGeneric) -> BHCDeviceGeneric:
        """Build generic device data."""
        return BHCDeviceGeneric(
            device=self.device,
            firmware={},
            notifications=data.notifications,
        )


class BoschComModuleCoordinatorRac(BoschComModuleCoordinatorBase[BHCDeviceRac]):
    """A coordinator to manage the fetching of BoschCom data."""

    def _build_device_data(self, data: BHCDeviceRac) -> BHCDeviceRac:
        """Build RAC device data."""
        return BHCDeviceRac(
            device=self.device,
            firmware={},
            notifications=data.notifications,
            stardard_functions=data.stardard_functions,
            advanced_functions=data.advanced_functions,
            switch_programs=data.switch_programs,
        )


class BoschComModuleCoordinatorK40(BoschComModuleCoordinatorBase[BHCDeviceK40]):
    """A coordinator to manage the fetching of BoschCom data."""

    def _build_device_data(self, data: BHCDeviceK40) -> BHCDeviceK40:
        """Build K40 device data."""
        return BHCDeviceK40(
            device=self.device,
            firmware=data.firmware,
            notifications=data.notifications,
            holiday_mode=data.holiday_mode,
            away_mode=data.away_mode,
            power_limitation=data.power_limitation,
            outdoor_temp=data.outdoor_temp,
            heat_sources=data.heat_sources,
            dhw_circuits=data.dhw_circuits,
            heating_circuits=data.heating_circuits,
            ventilation=data.ventilation,
            zones=data.zones,
            flame_indication=data.flame_indication,
            energy_history=data.energy_history,
            hourly_energy_history=data.hourly_energy_history,
            energy_gas_unit=data.energy_gas_unit,
            indoor_humidity=data.indoor_humidity,
            devices=data.devices,
        )


class BoschComModuleCoordinatorWddw2(BoschComModuleCoordinatorBase[BHCDeviceWddw2]):
    """A coordinator to manage the fetching of BoschCom data."""

    def _build_device_data(self, data: BHCDeviceWddw2) -> BHCDeviceWddw2:
        """Build WDDW2 device data."""
        return BHCDeviceWddw2(
            device=self.device,
            firmware=data.firmware,
            notifications=data.notifications,
            dhw_circuits=data.dhw_circuits,
            heat_sources=data.heat_sources,
            water_total_consumption=data.water_total_consumption,
        )


class BoschComModuleCoordinatorIcom(BoschComModuleCoordinatorBase[BHCDeviceIcom]):
    """A coordinator for icom heat pumps (subset of K40 endpoint surface)."""

    def _build_device_data(self, data: BHCDeviceIcom) -> BHCDeviceIcom:
        """Build icom device data."""
        return BHCDeviceIcom(
            device=self.device,
            firmware=data.firmware,
            notifications=data.notifications,
            holiday_mode=data.holiday_mode,
            heat_sources=data.heat_sources,
            dhw_circuits=data.dhw_circuits,
            heating_circuits=data.heating_circuits,
            solar_circuits=data.solar_circuits,
            ventilation=data.ventilation,
            system_info=data.system_info,
            system_bus=data.system_bus,
            health_status=data.health_status,
            brand=data.brand,
        )

    async def _async_update_data(self) -> BHCDeviceIcom:
        """Fetch base icom data, then augment heat_sources and DHW circuits.

        The base update (auth + core icom endpoints) runs first via super().
        Seven additional heat-source endpoints and per-circuit DHW currentSetpoint
        are then fetched in parallel.  Each call is wrapped in _safe() so a 404
        or any other API error for an unsupported endpoint silently returns {}
        without failing the whole coordinator update cycle.
        """
        data = await super()._async_update_data()

        async def _safe(coro: Any) -> dict:
            """Await *coro* and return its result, or {} on any error.

            Unsupported endpoints return HTTP 404 / raise ApiError; catching
            broadly here is intentional so that a missing optional sensor never
            prevents the coordinator from delivering data to other entities.
            """
            try:
                result = await coro
                return result or {}
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Optional icom endpoint unavailable: %s", err)
                return {}

        async def _get_dhw_current_setpoint(dhw_id: str) -> dict:
            """Fetch the live DHW current setpoint for *dhw_id*.

            Uses the homecom_alt library method added in v1.6.2 which exposes
            the active programme setpoint (not just singleChargeSetpoint).
            """
            return await self.bhc.async_get_dhw_current_setpoint(self.unique_id, dhw_id)

        (
            supply_temp,
            modulation,
            total_consumption,
            working_time,
            system_pressure,
            heat_demand,
            outdoor_temp,
        ) = await asyncio.gather(
            _safe(self.bhc.async_get_hs_supply_temp(self.unique_id)),
            _safe(self.bhc.async_get_hs_modulation(self.unique_id)),
            _safe(self.bhc.async_get_hs_total_consumption(self.unique_id)),
            _safe(self.bhc.async_get_hs_working_time(self.unique_id)),
            _safe(self.bhc.async_get_hs_system_pressure(self.unique_id)),
            _safe(self.bhc.async_get_hs_heat_demand(self.unique_id)),
            _safe(self.bhc.async_get_outdoor_temp(self.unique_id)),
        )

        hs = dict(data.heat_sources or {})
        hs["supplyTemperature"] = supply_temp
        hs["modulation"] = modulation
        hs["totalConsumption"] = total_consumption
        hs["workingTime"] = working_time
        hs["systemPressure"] = system_pressure
        hs["actualHeatDemand"] = heat_demand
        hs["outdoorTemp"] = outdoor_temp

        # Augment each DHW circuit reference with its live currentSetpoint.
        # The library's populate_dhw fetches singleChargeSetpoint only; we need
        # the active programme setpoint to detect when DHW is being heated.
        dhw_circuits = list(data.dhw_circuits or [])
        for ref in dhw_circuits:
            dhw_id = ref.get("id", "").split("/")[-1]
            if dhw_id:
                ref["currentSetpoint"] = await _safe(_get_dhw_current_setpoint(dhw_id))

        return BHCDeviceIcom(
            device=data.device,
            firmware=data.firmware,
            notifications=data.notifications,
            holiday_mode=data.holiday_mode,
            heat_sources=hs,
            dhw_circuits=dhw_circuits,
            heating_circuits=data.heating_circuits,
            solar_circuits=data.solar_circuits,
            ventilation=data.ventilation,
            system_info=data.system_info,
            system_bus=data.system_bus,
            health_status=data.health_status,
            brand=data.brand,
        )

    async def async_set_temporary_room_setpoint(self, hc_id: str, temp: float) -> None:
        """Set a temporary room-temperature override for a heating circuit.

        This mirrors the Bosch app behaviour: the scheduled programme is
        preserved and the override is active until the next programme switch.
        Uses *temporaryRoomSetpoint* instead of *manualRoomSetpoint* so the
        heating schedule is not permanently altered.

        Delegates to the homecom_alt library method added in v1.6.2.

        Args:
            hc_id: Heating-circuit identifier (e.g. ``"hc1"``).
            temp:  Target temperature in degrees Celsius.
        """
        await self.bhc.async_set_hc_temporary_room_setpoint(self.unique_id, hc_id, temp)


class BoschComModuleCoordinatorRrc2(BoschComModuleCoordinatorBase[BHCDeviceRrc2]):
    """A coordinator for rrc2 (Remeha Remote Control) gateways."""

    def _build_device_data(self, data: BHCDeviceRrc2) -> BHCDeviceRrc2:
        """Build rrc2 device data."""
        return BHCDeviceRrc2(
            device=self.device,
            firmware=data.firmware,
            notifications=data.notifications,
            zones=data.zones,
            heating_circuits=data.heating_circuits,
            dhw_circuits=data.dhw_circuits,
            heat_sources=data.heat_sources,
            away_mode=data.away_mode,
            outdoor_temp=data.outdoor_temp,
            indoor_humidity=data.indoor_humidity,
            devices=data.devices,
            gateway_info=data.gateway_info,
            system_location=data.system_location,
        )


class BoschComModuleCoordinatorCommodule(
    BoschComModuleCoordinatorBase[BHCDeviceCommodule]
):
    """A coordinator to manage the fetching of BoschCom data."""

    def _build_device_data(self, data: BHCDeviceCommodule) -> BHCDeviceCommodule:
        """Build commodule device data."""
        return BHCDeviceCommodule(
            device=self.device,
            firmware=data.firmware,
            notifications=data.notifications,
            charge_points=data.charge_points,
            eth0_state=data.eth0_state,
            wifi_state=data.wifi_state,
        )
