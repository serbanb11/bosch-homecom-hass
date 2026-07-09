"""HomeCom coordinator."""

from __future__ import annotations

from abc import abstractmethod
from datetime import timedelta
import logging
from typing import TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
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
        self.firmware = firmware["value"]

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


ENERGY_RECORDINGS_POLL_INTERVAL = timedelta(hours=1)

# Maps (path_suffix under /recordings/heatSources/emon/) -> local key stored
# in coordinator.energy_recordings. Discovered via refEnum browsability at
# GET /resource/recordings/heatSources/emon on a K40 (Bosch Compress 5800iAW).
# Endpoints the device does not support silently drop out of the bulk response
# (existing _log_endpoint_status handling) and the previous good value is kept.
ENERGY_RECORDING_PATHS: dict[str, str] = {
    "total/compressor": "energy_compressor_total",
    "total/eheater": "energy_eheater_total",
    "total/ventilation": "energy_ventilation_total",
    "total/outputProduced": "heat_produced_total",
    "ventilation/heatRecovered": "heat_recovered_ventilation",
    "ch/compressor": "energy_compressor_ch",
    "ch/eheater": "energy_eheater_ch",
    "ch/outputProduced": "heat_produced_ch",
    "dhw/compressor": "energy_compressor_dhw",
    "dhw/eheater": "energy_eheater_dhw",
    "dhw/outputProduced": "heat_produced_dhw",
    "cooling/compressor": "energy_compressor_cooling",
    "cooling/outputProduced": "heat_produced_cooling",
}


class _K40ExtraEndpointsMixin:
    """Fetch/cache K40-family endpoints not in the homecom_alt bulk update.

    ``additionalHeater``, ``silentMode`` and ``dhwChargeDuration`` are exposed
    by homecom_alt as standalone getters/setters (not part of ``async_update``),
    so they are fetched separately and cached in ``extra_data``. Shared by the
    K40 and ICOM coordinators. Endpoints the device does not support resolve to
    ``None`` and simply produce no entity.

    Also fetches the ``/recordings/heatSources/emon/*`` energy time-series at a
    slower cadence (see ENERGY_RECORDINGS_POLL_INTERVAL) and caches per-path
    cumulative-today values in ``energy_recordings``. On network or per-endpoint
    failures the previous good value is kept — the sensors thus stay flat at
    their last good number rather than resetting to zero, which would trip HA's
    ``total_increasing`` reset detection.
    """

    EXTRA_KEYS = ("additional_heater", "silent_mode", "dhw_charge_duration")

    def __init__(self, *args, **kwargs) -> None:
        """Initialize coordinator with the extra-endpoint cache."""
        super().__init__(*args, **kwargs)
        self.extra_data: dict[str, dict | None] = {}
        self.energy_recordings: dict[str, float] = {}
        self._last_energy_recordings_fetch = None

    async def _async_update_data(self):
        """Update via library, then fetch the standalone endpoints."""
        data = await super()._async_update_data()
        await self._fetch_extra_endpoints()
        await self._fetch_energy_recordings()
        return data

    async def _fetch_extra_endpoints(self) -> None:
        """Fetch standalone endpoints via the library, caching None on failure."""
        thunks = {
            "additional_heater": lambda: self.bhc.async_get_additional_heater_mode(
                self.unique_id
            ),
            "silent_mode": lambda: self.bhc.async_get_silent_mode(self.unique_id),
            "dhw_charge_duration": lambda: self.bhc.async_get_dhw_charge_duration(
                self.unique_id, "dhw1"
            ),
        }
        for key, thunk in thunks.items():
            try:
                result = await thunk()
            except (
                ApiError,
                InvalidSensorDataError,
                NotRespondingError,
                RetryError,
                TimeoutError,
            ):
                _LOGGER.debug(
                    "Device %s: endpoint %s not available", self.unique_id, key
                )
                self.extra_data[key] = None
                continue
            self.extra_data[key] = result if result else None

    async def _fetch_energy_recordings(self) -> None:
        """Fetch /recordings/heatSources/emon/* time-series (hourly, rate-limited).

        Runs at most once per ENERGY_RECORDINGS_POLL_INTERVAL. The bulk
        endpoint accepts up to 30 paths per call — 13 fits comfortably.
        """
        now = dt_util.utcnow()
        if (
            self._last_energy_recordings_fetch is not None
            and now - self._last_energy_recordings_fetch
            < ENERGY_RECORDINGS_POLL_INTERVAL
        ):
            return

        today = dt_util.now().strftime("%Y-%m-%d")
        paths = [
            f"/recordings/heatSources/emon/{suffix}?interval={today}"
            for suffix in ENERGY_RECORDING_PATHS
        ]
        try:
            result = await self.bhc.async_request_bulk(self.unique_id, paths)
        except (
            ApiError,
            InvalidSensorDataError,
            NotRespondingError,
            RetryError,
            TimeoutError,
        ):
            _LOGGER.debug(
                "Device %s: energy recordings fetch failed, keeping last values",
                self.unique_id,
            )
            return

        if not result:
            return

        for suffix, key in ENERGY_RECORDING_PATHS.items():
            path = f"/recordings/heatSources/emon/{suffix}?interval={today}"
            payload = result.get(path)
            if not isinstance(payload, dict):
                # Endpoint not supported on this device (404/403) or unexpected shape.
                # Keep previous good value if any.
                continue
            recording = payload.get("recording") or []
            if not isinstance(recording, list):
                continue
            total = 0.0
            for item in recording:
                if isinstance(item, dict):
                    y = item.get("y")
                    if isinstance(y, (int, float)):
                        total += y
            self.energy_recordings[key] = round(total, 3)

        self._last_energy_recordings_fetch = now


class BoschComModuleCoordinatorK40(
    _K40ExtraEndpointsMixin, BoschComModuleCoordinatorBase[BHCDeviceK40]
):
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
            holiday_mode=data.holiday_mode,
        )


class BoschComModuleCoordinatorIcom(
    _K40ExtraEndpointsMixin, BoschComModuleCoordinatorBase[BHCDeviceIcom]
):
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
