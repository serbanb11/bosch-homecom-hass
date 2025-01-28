"""HomeCom coordinator."""

import logging

from homecom_alt import (
    ApiError,
    InvalidSensorDataError,
    AuthFailedError,
    BHCDevice,
    HomeComAlt,
)
from tenacity import RetryError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)


class BoschComModuleCoordinator(DataUpdateCoordinator[BHCDevice]):
    """A coordinator to manage the fetching of BoschCom data."""

    def __init__(
        self, hass: HomeAssistant, bhc: HomeComAlt, device: list, firmware: dict
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

        self.device_info = DeviceInfo(
            serial_number=self.unique_id,
            identifiers={(DOMAIN, self.unique_id)},
            name="Boschcom_" + device["deviceType"] + "_" + device["deviceId"],
            sw_version=firmware["value"],
            manufacturer=MANUFACTURER,
        )

    async def _async_update_data(self) -> BHCDevice:
        """Update data via library."""
        try:
            data: BHCDevice = await self.bhc.async_update(self.unique_id)
        except (ApiError, InvalidSensorDataError, RetryError) as error:
            raise UpdateFailed(error) from error
        except AuthFailedError as error:
            raise AuthFailedError(error) from error

        return BHCDevice(
            device=self.device,
            firmware=data.firmware,
            notifications=data.notifications,
            stardard_functions=data.stardard_functions,
            advanced_functions=data.advanced_functions,
            switch_programs=data.switch_programs,
        )
