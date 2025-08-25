"""HomeCom coordinator."""

import logging

from tenacity import RetryError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN

from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN, MANUFACTURER, CONF_REFRESH
from homecom_alt import (
    ApiError,
    AuthFailedError,
    BHCDeviceK40,
    BHCDeviceRac,
    HomeComK40,
    HomeComRac,
    InvalidSensorDataError,
)

_LOGGER = logging.getLogger(__name__)


class BoschComModuleCoordinatorRac(DataUpdateCoordinator[BHCDeviceRac]):
    """A coordinator to manage the fetching of BoschCom data."""

    def __init__(
        self, hass: HomeAssistant, bhc: HomeComRac, device: list, firmware: dict, entry: ConfigEntry
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

        self.device_info = DeviceInfo(
            serial_number=self.unique_id,
            identifiers={(DOMAIN, self.unique_id)},
            name="Boschcom_" + device["deviceType"] + "_" + device["deviceId"],
            sw_version=firmware["value"],
            manufacturer=MANUFACTURER,
        )

    async def _async_update_data(self) -> BHCDeviceRac:
        """Update data via library."""
        try:
            data: BHCDeviceRac = await self.bhc.async_update(self.unique_id)
        except (ApiError, InvalidSensorDataError, RetryError) as error:
            raise UpdateFailed(error) from error
        except AuthFailedError as error:
            raise AuthFailedError(error) from error

        # Persist refreshed tokens if they changed
        try:
            token = getattr(self.bhc, "_options", None).token if getattr(self.bhc, "_options", None) else None
            refresh = getattr(self.bhc, "_options", None).refresh_token if getattr(self.bhc, "_options", None) else None
            if token and refresh:
                cur_token = self.entry.data.get(CONF_TOKEN)
                cur_refresh = self.entry.data.get(CONF_REFRESH)
                if token != cur_token or refresh != cur_refresh:
                    new_data = dict(self.entry.data)
                    new_data[CONF_TOKEN] = token
                    new_data[CONF_REFRESH] = refresh
                    self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        except Exception:  # best-effort; don't fail updates due to persistence
            _LOGGER.debug("Failed to persist refreshed tokens", exc_info=True)

        return BHCDeviceRac(
            device=self.device,
            firmware=data.firmware,
            notifications=data.notifications,
            stardard_functions=data.stardard_functions,
            advanced_functions=data.advanced_functions,
            switch_programs=data.switch_programs,
        )


class BoschComModuleCoordinatorK40(DataUpdateCoordinator[BHCDeviceK40]):
    """A coordinator to manage the fetching of BoschCom data."""

    def __init__(
        self, hass: HomeAssistant, bhc: HomeComK40, device: list, firmware: dict, entry: ConfigEntry
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

        self.device_info = DeviceInfo(
            serial_number=self.unique_id,
            identifiers={(DOMAIN, self.unique_id)},
            name="Boschcom_" + device["deviceType"] + "_" + device["deviceId"],
            sw_version=firmware["value"],
            manufacturer=MANUFACTURER,
        )

    async def _async_update_data(self) -> BHCDeviceK40:
        """Update data via library."""
        try:
            data: BHCDeviceK40 = await self.bhc.async_update(self.unique_id)
        except (ApiError, InvalidSensorDataError, RetryError) as error:
            raise UpdateFailed(error) from error
        except AuthFailedError as error:
            raise AuthFailedError(error) from error

        # Persist refreshed tokens if they changed
        try:
            token = getattr(self.bhc, "_options", None).token if getattr(self.bhc, "_options", None) else None
            refresh = getattr(self.bhc, "_options", None).refresh_token if getattr(self.bhc, "_options", None) else None
            if token and refresh:
                cur_token = self.entry.data.get(CONF_TOKEN)
                cur_refresh = self.entry.data.get(CONF_REFRESH)
                if token != cur_token or refresh != cur_refresh:
                    new_data = dict(self.entry.data)
                    new_data[CONF_TOKEN] = token
                    new_data[CONF_REFRESH] = refresh
                    self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        except Exception:
            _LOGGER.debug("Failed to persist refreshed tokens", exc_info=True)

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
        )
