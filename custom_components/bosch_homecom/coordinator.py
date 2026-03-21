"""HomeCom coordinator."""

from abc import abstractmethod
import hashlib
import logging
from typing import Any, Generic, TypeVar

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
    BHCDeviceK40,
    BHCDeviceRac,
    BHCDeviceWddw2,
    HomeComCommodule,
    HomeComK40,
    HomeComRac,
    HomeComWddw2,
    InvalidSensorDataError,
)
from tenacity import RetryError

from .const import CONF_REFRESH, DEFAULT_UPDATE_INTERVAL, DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)

BoschDeviceT = TypeVar(
    "BoschDeviceT",
    BHCDeviceGeneric,
    BHCDeviceRac,
    BHCDeviceK40,
    BHCDeviceWddw2,
    BHCDeviceCommodule,
)


def _fingerprint_secret(secret: Any) -> str:
    """Return a short, non-reversible fingerprint for debug logging."""
    if not secret:
        return "missing"
    if isinstance(secret, bytes):
        raw = secret
    elif isinstance(secret, str):
        raw = secret.encode()
    else:
        return f"non_str:{type(secret).__name__}"
    return hashlib.sha256(raw).hexdigest()[:8]


class BoschComModuleCoordinatorBase(
    DataUpdateCoordinator[BoschDeviceT], Generic[BoschDeviceT]
):
    """Base coordinator with shared Bosch auth and device metadata logic."""

    def __init__(
        self,
        hass: HomeAssistant,
        bhc: Any,
        device: dict[str, Any],
        firmware: dict[str, Any],
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

    def _auth_debug_context(self) -> dict[str, Any]:
        """Return safe auth context for debug logging."""
        return {
            "entry_id": self.entry.entry_id,
            "device_id": self.unique_id,
            "auth_provider": self.auth_provider,
            "token": _fingerprint_secret(self.bhc.token),
            "refresh": _fingerprint_secret(self.bhc.refresh_token),
        }

    async def _async_refresh_auth(self) -> None:
        """Refresh Bosch auth state and persist new tokens when they rotate."""
        try:
            old_token = self.bhc.token
            old_refresh_token = self.bhc.refresh_token
            _LOGGER.debug("Refreshing Bosch auth: %s", self._auth_debug_context())
            await self.bhc.get_token()
        except AuthFailedError as err:
            _LOGGER.warning(
                "Bosch auth refresh failed: %s error=%s",
                self._auth_debug_context(),
                err,
            )
            self.entry.async_start_reauth(self.hass)
            raise UpdateFailed("Bosch authentication expired") from err

        token_changed = old_token != self.bhc.token
        refresh_changed = old_refresh_token != self.bhc.refresh_token
        _LOGGER.debug(
            "Bosch auth refresh completed for %s token_changed=%s refresh_changed=%s new_token=%s new_refresh=%s",
            self.unique_id,
            token_changed,
            refresh_changed,
            _fingerprint_secret(self.bhc.token),
            _fingerprint_secret(self.bhc.refresh_token),
        )

        stored_token = self.entry.data.get(CONF_TOKEN)
        stored_refresh = self.entry.data.get(CONF_REFRESH)
        if (
            not (token_changed or refresh_changed)
            and stored_token == self.bhc.token
            and stored_refresh == self.bhc.refresh_token
        ):
            return

        new_data = dict(self.entry.data)
        new_data[CONF_TOKEN] = self.bhc.token
        new_data[CONF_REFRESH] = self.bhc.refresh_token
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        _LOGGER.debug(
            "Device_Id: %s, persisted refreshed Bosch auth tokens",
            self.unique_id,
        )

    async def _async_update_data(self) -> BoschDeviceT:
        """Update data via the underlying Bosch client."""
        if self.auth_provider:
            await self._async_refresh_auth()

        try:
            data = await self.bhc.async_update(self.unique_id)
        except AuthFailedError as error:
            _LOGGER.warning(
                "Bosch async_update auth failure after refresh path: %s error=%s",
                self._auth_debug_context(),
                error,
            )
            self.entry.async_start_reauth(self.hass)
            raise UpdateFailed("Bosch authentication expired during update") from error
        except (ApiError, InvalidSensorDataError, RetryError) as error:
            raise UpdateFailed(error) from error

        return self._build_device_data(data)

    @abstractmethod
    def _build_device_data(self, data: BoschDeviceT) -> BoschDeviceT:
        """Normalize device data for Home Assistant entities."""


BoschCoordinator = BoschComModuleCoordinatorBase[Any]


class BoschComModuleCoordinatorGeneric(
    BoschComModuleCoordinatorBase[BHCDeviceGeneric]
):
    """A coordinator to manage the fetching of BoschCom data."""

    def __init__(
        self,
        hass: HomeAssistant,
        bhc: HomeComRac,
        device: dict[str, Any],
        firmware: dict[str, Any],
        entry: ConfigEntry,
        auth_provider: bool,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(hass, bhc, device, firmware, entry, auth_provider)

    def _build_device_data(self, data: BHCDeviceGeneric) -> BHCDeviceGeneric:
        """Normalize generic device data."""
        return BHCDeviceGeneric(
            device=self.device,
            firmware={},
            notifications=data.notifications,
        )


class BoschComModuleCoordinatorRac(BoschComModuleCoordinatorBase[BHCDeviceRac]):
    """A coordinator to manage the fetching of BoschCom data."""

    def __init__(
        self,
        hass: HomeAssistant,
        bhc: HomeComRac,
        device: dict[str, Any],
        firmware: dict[str, Any],
        entry: ConfigEntry,
        auth_provider: bool,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(hass, bhc, device, firmware, entry, auth_provider)

    def _build_device_data(self, data: BHCDeviceRac) -> BHCDeviceRac:
        """Normalize RAC device data."""
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

    def __init__(
        self,
        hass: HomeAssistant,
        bhc: HomeComK40,
        device: dict[str, Any],
        firmware: dict[str, Any],
        entry: ConfigEntry,
        auth_provider: bool,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(hass, bhc, device, firmware, entry, auth_provider)

    def _build_device_data(self, data: BHCDeviceK40) -> BHCDeviceK40:
        """Normalize K40 device data."""
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
            indoor_humidity=data.indoor_humidity,
            devices=data.devices,
        )


class BoschComModuleCoordinatorWddw2(
    BoschComModuleCoordinatorBase[BHCDeviceWddw2]
):
    """A coordinator to manage the fetching of BoschCom data."""

    def __init__(
        self,
        hass: HomeAssistant,
        bhc: HomeComWddw2,
        device: dict[str, Any],
        firmware: dict[str, Any],
        entry: ConfigEntry,
        auth_provider: bool,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(hass, bhc, device, firmware, entry, auth_provider)

    def _build_device_data(self, data: BHCDeviceWddw2) -> BHCDeviceWddw2:
        """Normalize WDDW2 device data."""
        return BHCDeviceWddw2(
            device=self.device,
            firmware=data.firmware,
            notifications=data.notifications,
            dhw_circuits=data.dhw_circuits,
        )


class BoschComModuleCoordinatorCommodule(
    BoschComModuleCoordinatorBase[BHCDeviceCommodule]
):
    """A coordinator to manage the fetching of BoschCom data."""

    def __init__(
        self,
        hass: HomeAssistant,
        bhc: HomeComCommodule,
        device: dict[str, Any],
        firmware: dict[str, Any],
        entry: ConfigEntry,
        auth_provider: bool,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(hass, bhc, device, firmware, entry, auth_provider)

    def _build_device_data(self, data: BHCDeviceCommodule) -> BHCDeviceCommodule:
        """Normalize commodule device data."""
        return BHCDeviceCommodule(
            device=self.device,
            firmware=data.firmware,
            notifications=data.notifications,
            charge_points=data.charge_points,
            eth0_state=data.eth0_state,
        )
