"""HomeCom coordinator."""

import logging

from homecom_alt import (
    ApiError,
    AuthFailedError,
    BHCDeviceGeneric,
    BHCDeviceK40,
    BHCDeviceRac,
    HomeComK40,
    HomeComRac,
    InvalidSensorDataError,
)
from tenacity import RetryError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_REFRESH, DEFAULT_UPDATE_INTERVAL, DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)


class BoschComModuleCoordinatorGeneric(DataUpdateCoordinator[BHCDeviceGeneric]):
    """A coordinator to manage the fetching of BoschCom data."""

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

    async def _async_update_data(self) -> BHCDeviceGeneric:
        """Update data via library."""
        if self.auth_provider:
            try:
                data: BHCDeviceGeneric = await self.bhc.async_update(self.unique_id)
            except (ApiError, InvalidSensorDataError, RetryError) as error:
                raise UpdateFailed(error) from error
            except AuthFailedError:
                self.entry.async_start_reauth(self.hass)

        # Persist refreshed tokens if they changed
        try:
            token = self.bhc.token
            refresh = self.bhc.refresh_token
            if token and refresh:
                cur_refresh = self.entry.data.get(CONF_REFRESH)
                if not self.auth_provider:
                    conf_data = dict(self.entry.data)
                    self.bhc.token = conf_data[CONF_TOKEN]
                    self.bhc.refresh_token = conf_data[CONF_REFRESH]
                    try:
                        data: BHCDeviceGeneric = await self.bhc.async_update(
                            self.unique_id
                        )
                    except (ApiError, InvalidSensorDataError, RetryError) as error:
                        raise UpdateFailed(error) from error
                elif refresh != cur_refresh and self.auth_provider:
                    new_data = dict(self.entry.data)
                    new_data[CONF_TOKEN] = token
                    new_data[CONF_REFRESH] = refresh
                    self.hass.config_entries.async_update_entry(
                        self.entry, data=new_data
                    )
            _LOGGER.info(
                "Device_Id: %s, refresh_token: %s, token: %s",
                self.unique_id,
                refresh,
                token,
            )
        except (AttributeError, KeyError):
            _LOGGER.debug("Failed to persist refreshed tokens")

        return BHCDeviceGeneric(
            device=self.device,
            firmware={},
            notifications=data.notifications,
        )


class BoschComModuleCoordinatorRac(DataUpdateCoordinator[BHCDeviceRac]):
    """A coordinator to manage the fetching of BoschCom data."""

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

    async def _async_update_data(self) -> BHCDeviceRac:
        """Update data via library."""
        if self.auth_provider:
            try:
                data: BHCDeviceRac = await self.bhc.async_update(self.unique_id)
            except (ApiError, InvalidSensorDataError, RetryError) as error:
                raise UpdateFailed(error) from error
            except AuthFailedError:
                self.entry.async_start_reauth(self.hass)

        # Persist refreshed tokens if they changed
        try:
            token = self.bhc.token
            refresh = self.bhc.refresh_token
            if token and refresh:
                cur_refresh = self.entry.data.get(CONF_REFRESH)
                if not self.auth_provider:
                    conf_data = dict(self.entry.data)
                    self.bhc.token = conf_data[CONF_TOKEN]
                    self.bhc.refresh_token = conf_data[CONF_REFRESH]
                    try:
                        data: BHCDeviceRac = await self.bhc.async_update(self.unique_id)
                    except (ApiError, InvalidSensorDataError, RetryError) as error:
                        raise UpdateFailed(error) from error
                elif refresh != cur_refresh and self.auth_provider:
                    new_data = dict(self.entry.data)
                    new_data[CONF_TOKEN] = token
                    new_data[CONF_REFRESH] = refresh
                    self.hass.config_entries.async_update_entry(
                        self.entry, data=new_data
                    )
            _LOGGER.info(
                "Device_Id: %s, refresh_token: %s, token: %s",
                self.unique_id,
                refresh,
                token,
            )
        except (AttributeError, KeyError):
            _LOGGER.debug("Failed to persist refreshed tokens")

        return BHCDeviceRac(
            device=self.device,
            firmware={},
            notifications=data.notifications,
            stardard_functions=data.stardard_functions,
            advanced_functions=data.advanced_functions,
            switch_programs=data.switch_programs,
        )


class BoschComModuleCoordinatorK40(DataUpdateCoordinator[BHCDeviceK40]):
    """A coordinator to manage the fetching of BoschCom data."""

    def __init__(
        self,
        hass: HomeAssistant,
        bhc: HomeComK40,
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
            token = self.bhc.token
            refresh = self.bhc.refresh_token
            if token and refresh:
                cur_refresh = self.entry.data.get(CONF_REFRESH)
                if not self.auth_provider:
                    conf_data = dict(self.entry.data)
                    self.bhc.token = conf_data[CONF_TOKEN]
                    self.bhc.refresh_token = conf_data[CONF_REFRESH]
                elif refresh != cur_refresh and self.auth_provider:
                    new_data = dict(self.entry.data)
                    new_data[CONF_TOKEN] = token
                    new_data[CONF_REFRESH] = refresh
                    self.hass.config_entries.async_update_entry(
                        self.entry, data=new_data
                    )
            _LOGGER.info(
                "Device_Id: %s, refresh_token: %s, token: %s",
                self.unique_id,
                refresh,
                token,
            )
        except (AttributeError, KeyError):
            _LOGGER.debug("Failed to persist refreshed tokens")

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
