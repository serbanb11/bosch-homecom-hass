"""HomeCom coordinator."""

from __future__ import annotations

from abc import abstractmethod
import asyncio
from datetime import datetime, timedelta
import logging
from typing import TypeVar

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import (
    CALLBACK_TYPE,
    DOMAIN as HOMEASSISTANT_DOMAIN,
    HomeAssistant,
    callback,
)
from homeassistant.data_entry_flow import UnknownFlow
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homecom_alt import (
    ApiError,
    AuthFailedError,
    BaconMqttClient,
    BHCDeviceBaconRac,
    BHCDeviceCommodule,
    BHCDeviceGeneric,
    BHCDeviceIcom,
    BHCDeviceK40,
    BHCDeviceRac,
    BHCDeviceRrc2,
    BHCDeviceWddw2,
    HomeComAlt,
    HomeComBaconRac,
    HomeComRac,
    InvalidSensorDataError,
    MqttNotAuthorizedError,
    NotRespondingError,
    decode_jwt_exp,
    decode_jwt_sub,
)
from tenacity import RetryError

from .const import (
    CONF_BACON_TITLES,
    CONF_REFRESH,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MANUFACTURER,
)

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


RECORDINGS_POLL_INTERVAL = timedelta(hours=1)

# Maps (path_suffix under /recordings/heatSources/) -> {key, agg} for the
# local coordinator.recordings dict. Discovered via refEnum browsability
# at GET /resource/recordings/heatSources on a K40 (Bosch Compress 5800iAW).
# Endpoints the device does not support silently drop out of the bulk
# response (existing _log_endpoint_status handling) and the previous good
# value is kept.
#
# ``agg`` selects the aggregation of the hourly bucket values:
#   ``sum`` -> sum of ``y`` values (Bosch's kWh energy counters, c=1 each).
#   ``avg`` -> ``sum(y) / sum(c)``. Bosch stores some sensor recordings as
#             per-hour sample-sums; the count is the number of samples that
#             went into the sum. Used for temperature time-series such as
#             ``actualSupplyTemperature``.
RECORDING_PATHS: dict[str, dict] = {
    # Energy counters — /recordings/heatSources/emon/*, unit kWh
    "emon/total/compressor": {"key": "energy_compressor_total", "agg": "sum"},
    "emon/total/eheater": {"key": "energy_eheater_total", "agg": "sum"},
    "emon/total/ventilation": {"key": "energy_ventilation_total", "agg": "sum"},
    "emon/total/outputProduced": {"key": "heat_produced_total", "agg": "sum"},
    "emon/ventilation/heatRecovered": {
        "key": "heat_recovered_ventilation",
        "agg": "sum",
    },
    "emon/ch/compressor": {"key": "energy_compressor_ch", "agg": "sum"},
    "emon/ch/eheater": {"key": "energy_eheater_ch", "agg": "sum"},
    "emon/ch/outputProduced": {"key": "heat_produced_ch", "agg": "sum"},
    "emon/dhw/compressor": {"key": "energy_compressor_dhw", "agg": "sum"},
    "emon/dhw/eheater": {"key": "energy_eheater_dhw", "agg": "sum"},
    "emon/dhw/outputProduced": {"key": "heat_produced_dhw", "agg": "sum"},
    "emon/cooling/compressor": {"key": "energy_compressor_cooling", "agg": "sum"},
    "emon/cooling/outputProduced": {"key": "heat_produced_cooling", "agg": "sum"},
    "emon/pool/compressor": {"key": "energy_compressor_pool", "agg": "sum"},
    "emon/pool/eheater": {"key": "energy_eheater_pool", "agg": "sum"},
    "emon/pool/outputProduced": {"key": "heat_produced_pool", "agg": "sum"},
    # Sensor time-series — direct leaves under /recordings/heatSources/*,
    # per-hour sample-sum with count -> averaging.
    "actualSupplyTemperature": {"key": "supply_temp_avg_today", "agg": "avg"},
}


class _K40ExtraEndpointsMixin:
    """Fetch/cache K40-family endpoints not in the homecom_alt bulk update.

    ``additionalHeater``, ``silentMode`` and ``dhwChargeDuration`` are exposed
    by homecom_alt as standalone getters/setters (not part of ``async_update``),
    so they are fetched separately and cached in ``extra_data``. Shared by the
    K40 and ICOM coordinators. Endpoints the device does not support resolve to
    ``None`` and simply produce no entity.

    Also fetches the ``/recordings/heatSources/*`` time-series (energy under
    ``/emon/*`` and sensor averages such as ``actualSupplyTemperature``) at a
    slower cadence (see RECORDINGS_POLL_INTERVAL) and caches per-path values
    in ``recordings``. On network or per-endpoint failures the previous good
    value is kept — the sensors thus stay flat at their last good number
    rather than resetting to zero, which would trip HA's ``total_increasing``
    reset detection for energy sensors.
    """

    EXTRA_KEYS = ("additional_heater", "silent_mode", "dhw_charge_duration")

    def __init__(self, *args, **kwargs) -> None:
        """Initialize coordinator with the extra-endpoint cache."""
        super().__init__(*args, **kwargs)
        self.extra_data: dict[str, dict | None] = {}
        self.recordings: dict[str, float] = {}
        self._last_recordings_fetch = None

    async def _async_update_data(self):
        """Update via library, then fetch the standalone endpoints."""
        data = await super()._async_update_data()
        await self._fetch_extra_endpoints()
        await self._fetch_recordings()
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

    async def _fetch_recordings(self) -> None:
        """Fetch /recordings/heatSources/* time-series (hourly, rate-limited).

        Runs at most once per RECORDINGS_POLL_INTERVAL. The bulk endpoint
        accepts up to 30 paths per call — 14 fits comfortably. Each entry
        of RECORDING_PATHS has its own aggregation mode:
            ``sum`` -> sum of ``y`` (kWh counters)
            ``avg`` -> sum(y) / sum(c) (sensor sample averages)
        """
        now = dt_util.utcnow()
        if (
            self._last_recordings_fetch is not None
            and now - self._last_recordings_fetch < RECORDINGS_POLL_INTERVAL
        ):
            return

        today = dt_util.now().strftime("%Y-%m-%d")
        paths = [
            f"/recordings/heatSources/{suffix}?interval={today}"
            for suffix in RECORDING_PATHS
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
            # Transport failure — don't set the timestamp so the next regular
            # coordinator tick retries immediately.
            _LOGGER.debug(
                "Device %s: recordings fetch failed, keeping last values",
                self.unique_id,
            )
            return

        # HTTP call succeeded (even if empty) — mark the tick to enforce the
        # rate-limit for the next hour regardless of payload contents.
        self._last_recordings_fetch = now

        if not result:
            return

        for suffix, meta in RECORDING_PATHS.items():
            path = f"/recordings/heatSources/{suffix}?interval={today}"
            payload = result.get(path)
            if not isinstance(payload, dict):
                # Endpoint not supported on this device (404/403) or unexpected shape.
                # Keep previous good value if any.
                continue
            recording = payload.get("recording") or []
            if not isinstance(recording, list):
                continue
            y_sum = 0.0
            c_sum = 0
            for item in recording:
                if not isinstance(item, dict):
                    continue
                c = item.get("c")
                # Skip future / unpopulated hour slots. Some devices (e.g.
                # Buderus Logatherm WLW166i) return {"c": 0, "y": 1.0} for
                # every not-yet-populated hour of the current day; without
                # this guard both ``sum`` and ``avg`` aggregations would
                # count those placeholders as real samples. Reported by
                # @ombuyse in PR #155.
                if not isinstance(c, (int, float)) or c <= 0:
                    continue
                y = item.get("y")
                if isinstance(y, (int, float)):
                    y_sum += y
                c_sum += int(c)
            if meta["agg"] == "avg":
                if c_sum > 0:
                    self.recordings[meta["key"]] = round(y_sum / c_sum, 2)
            else:  # "sum"
                self.recordings[meta["key"]] = round(y_sum, 3)


class BoschComModuleCoordinatorK40(
    _K40ExtraEndpointsMixin, BoschComModuleCoordinatorBase[BHCDeviceK40]
):
    """A coordinator to manage the fetching of BoschCom data."""

    def _build_device_data(self, data: BHCDeviceK40) -> BHCDeviceK40:
        """Build K40 device data."""
        kwargs = {
            "device": self.device,
            "firmware": data.firmware,
            "notifications": data.notifications,
            "holiday_mode": data.holiday_mode,
            "away_mode": data.away_mode,
            "power_limitation": data.power_limitation,
            "outdoor_temp": data.outdoor_temp,
            "heat_sources": data.heat_sources,
            "dhw_circuits": data.dhw_circuits,
            "heating_circuits": data.heating_circuits,
            "ventilation": data.ventilation,
            "zones": data.zones,
            "flame_indication": data.flame_indication,
            "energy_history": data.energy_history,
            "hourly_energy_history": data.hourly_energy_history,
            "energy_gas_unit": data.energy_gas_unit,
            "indoor_humidity": data.indoor_humidity,
            "devices": data.devices,
        }
        if "pool" in BHCDeviceK40.__dataclass_fields__:
            kwargs["pool"] = getattr(data, "pool", None)
        # Solar thermal circuits: added in homecom_alt after the pinned minimum,
        # so probe the dataclass the same way as pool to stay compatible.
        if "solar_circuits" in BHCDeviceK40.__dataclass_fields__:
            kwargs["solar_circuits"] = getattr(data, "solar_circuits", None)
        return BHCDeviceK40(**kwargs)


class BoschComModuleCoordinatorWddw2(BoschComModuleCoordinatorBase[BHCDeviceWddw2]):
    """A coordinator to manage the fetching of BoschCom data."""

    def _build_device_data(self, data: BHCDeviceWddw2) -> BHCDeviceWddw2:
        """Build WDDW2 device data."""
        # A wddw2 is a standalone water heater, so an update without DHW
        # circuits can only be a transient cloud failure that the library
        # swallowed as empty data (issue #175). Fail the refresh instead:
        # at setup this becomes ConfigEntryNotReady (HA retries with a fresh
        # API client), at runtime the last good data is kept. Do NOT copy
        # this guard to K40: heating-only k40 systems legitimately have no
        # DHW circuits (issue #174).
        if not data.dhw_circuits:
            raise UpdateFailed(
                f"Device {self.unique_id}: wddw2 update returned no DHW circuits, "
                "treating as transient cloud failure"
            )
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


# Reconnect this far ahead of the access token's expiry. The MQTT password *is*
# the access token, so the broker drops the session when it expires. The margin
# must exceed homecom_alt's 5-minute check_jwt() window, otherwise the forced
# refresh would hand back the same soon-to-expire token.
BACON_RECONNECT_MARGIN = timedelta(minutes=10)

# Never schedule a reconnect closer than this, so a short-lived or already
# expiring token cannot spin up a tight reconnect loop.
BACON_RECONNECT_MIN_DELAY = timedelta(minutes=1)


class BoschComModuleCoordinatorBaconRac(DataUpdateCoordinator[BHCDeviceBaconRac]):
    """Coordinator for a Matter/Bacon-commissioned RAC device (MQTT shadow).

    Unlike the pointt (REST) coordinators these devices push their state over an
    MQTT device-shadow. A single :class:`BaconMqttClient` is shared across all
    bacon devices of the entry; live shadow updates are pushed straight into the
    coordinator, while the periodic refresh doubles as a keep-alive/reconnect and
    handles OAuth token rotation.

    Because the MQTT password is the access token, the session has the token's
    lifetime (~60 min). A reconnect is therefore scheduled ahead of expiry
    (BACON_RECONNECT_MARGIN) rather than waiting for the broker to refuse a stale
    credential, and a refusal that does happen is treated as a transport failure:
    only a failed OAuth refresh may ask the user to re-authenticate.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        bhc: HomeComBaconRac,
        device: dict,
        firmware: dict,
        entry: ConfigEntry,
        client: BaconMqttClient,
        token_manager: HomeComAlt,
        lock: asyncio.Lock,
        auth_provider: bool,
    ) -> None:
        """Initialize the bacon coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_UPDATE_INTERVAL,
            always_update=True,
        )
        self.bhc = bhc
        self.client = client
        self.token_manager = token_manager
        self._lock = lock
        self.auth_provider = auth_provider
        self.unique_id = device["deviceId"]
        self.device = device
        self.entry = entry
        self.firmware = firmware["value"]
        self._unsub_reconnect: CALLBACK_TYPE | None = None
        entry.async_on_unload(self._cancel_scheduled_reconnect)

        # Seed the name from the last-known title persisted on the entry so a
        # reload whose first shadow lacks customTitle keeps the friendly name
        # instead of falling back to Boschcom_bacon_rac_<serial>.
        persisted_title = (entry.data.get(CONF_BACON_TITLES) or {}).get(self.unique_id)
        self.device_info = DeviceInfo(
            serial_number=self.unique_id,
            identifiers={(DOMAIN, self.unique_id)},
            name=persisted_title
            or "Boschcom_" + device["deviceType"] + "_" + device["deviceId"],
            sw_version=self.firmware,
            manufacturer=MANUFACTURER,
        )

        client.register_listener(self.unique_id, self._handle_push)

    @callback
    def _handle_push(self, state: dict) -> None:
        """Push a live shadow update from MQTT into the coordinator."""
        self.async_set_updated_data(self._build(state))

    def _build(self, state: dict) -> BHCDeviceBaconRac:
        # Shadow update/accepted messages can be partial deltas (or carry only
        # the desired branch). Merge onto the last known state so a partial
        # message never wipes fields such as tempSetpoint or customTitle.
        prev = self.data
        reported = {
            **(prev.reported if prev and prev.reported else {}),
            **(state.get("reported") or {}),
        }
        desired = {
            **(prev.desired if prev and prev.desired else {}),
            **(state.get("desired") or {}),
        }
        title = reported.get("customTitle")
        if title:
            clean = title.split("%|")[0].strip()
            if clean:
                self.device_info["name"] = clean
                self._persist_title(clean)
        return BHCDeviceBaconRac(
            device=self.device,
            firmware=self.firmware,
            reported=reported,
            desired=desired,
            # From the push-only "topics" channel rather than the shadow, so each
            # stays None until the device has published it. sensor carries
            # roomTemperature, which the shadow does not have at all.
            sensor=self.bhc.sensor,
            metadata=self.bhc.metadata,
            info=self.bhc.info,
        )

    def _persist_title(self, title: str) -> None:
        """Persist the friendly name on the entry so it survives a reload."""
        titles = dict(self.entry.data.get(CONF_BACON_TITLES) or {})
        if titles.get(self.unique_id) == title:
            return
        titles[self.unique_id] = title
        new_data = {**self.entry.data, CONF_BACON_TITLES: titles}
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)

    def _persist_tokens(self) -> None:
        """Persist rotated tokens on the entry for the other coordinators."""
        if self.token_manager.token == self.entry.data.get(
            CONF_TOKEN
        ) and self.token_manager.refresh_token == self.entry.data.get(CONF_REFRESH):
            return
        new_data = dict(self.entry.data)
        new_data[CONF_TOKEN] = self.token_manager.token
        new_data[CONF_REFRESH] = self.token_manager.refresh_token
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        _LOGGER.debug("Device_Id: %s, persisted refreshed auth tokens", self.unique_id)

    async def _async_session_token(self, *, force_refresh: bool = False) -> str | None:
        """Return the access token to open the MQTT session with.

        Only the ``auth_provider`` coordinator rotates the OAuth token (a single
        owner — refresh tokens are single-use). Others reuse the token persisted
        on the config entry, which the token owner keeps fresh, so ``force_refresh``
        is a no-op for them. The caller must hold ``self._lock``: a rotation and
        the reconnect that consumes it have to be one critical section.

        A dead refresh token is the *only* failure that warrants bothering the
        user, so it is the only one that starts a re-authentication.
        """
        if not self.auth_provider:
            return self.entry.data.get(CONF_TOKEN)
        try:
            await self.token_manager.get_token(force=force_refresh)
        except AuthFailedError as err:
            self.entry.async_start_reauth(self.hass)
            raise UpdateFailed("Re-authentication required") from err
        self._persist_tokens()
        return self.token_manager.token

    def _token_outlives_session(self, token: str | None) -> bool:
        """Whether ``token`` expires later than the one now in use.

        Reconnecting with the token the session already holds buys nothing, so a
        non-owner (which cannot rotate) uses this to skip a pointless reconnect
        until the token owner has published a fresher one on the entry.
        """
        if not token:
            return False
        session_expires_at = self.client.token_expires_at
        if session_expires_at is None:
            return True
        token_expires_at = decode_jwt_exp(token)
        return token_expires_at is None or token_expires_at > session_expires_at

    async def _async_connect(self, token: str | None) -> None:
        """Open a new MQTT session with ``token``. Caller must hold the lock."""
        sub = decode_jwt_sub(token)
        if not sub:
            raise UpdateFailed("Could not derive user id from token")
        await self.client.async_connect(token, sub)
        self._schedule_reconnect()

    @callback
    def _schedule_reconnect(self) -> None:
        """Arm the reconnect that keeps the session ahead of token expiry.

        Fires BACON_RECONNECT_MARGIN before the token the session was opened
        with expires, never sooner than BACON_RECONNECT_MIN_DELAY from now.
        Called after every successful connect, so the timer always tracks the
        credential currently in use.
        """
        self._cancel_scheduled_reconnect()
        expires_at = self.client.token_expires_at
        if expires_at is None:
            return
        when = max(
            expires_at - BACON_RECONNECT_MARGIN,
            dt_util.utcnow() + BACON_RECONNECT_MIN_DELAY,
        )
        self._unsub_reconnect = async_track_point_in_utc_time(
            self.hass, self._handle_scheduled_reconnect, when
        )

    @callback
    def _cancel_scheduled_reconnect(self) -> None:
        """Cancel a pending reconnect. Also the entry's unload hook."""
        if self._unsub_reconnect is not None:
            self._unsub_reconnect()
            self._unsub_reconnect = None

    @callback
    def _handle_scheduled_reconnect(self, now: datetime) -> None:
        """Hand the due reconnect over to a task; the timer callback is sync."""
        self._unsub_reconnect = None
        self.entry.async_create_background_task(
            self.hass,
            self._async_scheduled_reconnect(),
            name=f"{DOMAIN} bacon reconnect {self.unique_id}",
        )

    async def _async_scheduled_reconnect(self) -> None:
        """Replace the session before the broker drops it as unauthorized."""
        try:
            async with self._lock:
                expires_at = self.client.token_expires_at
                if (
                    expires_at is not None
                    and dt_util.utcnow() < expires_at - BACON_RECONNECT_MARGIN
                ):
                    # Every bacon coordinator arms a timer but they share one
                    # session: another has already renewed it.
                    return
                token = await self._async_session_token(force_refresh=True)
                if not self._token_outlives_session(token):
                    return
                _LOGGER.debug(
                    "Device_Id: %s, reconnecting bacon MQTT ahead of token expiry",
                    self.unique_id,
                )
                await self._async_connect(token)
        except (
            ApiError,
            AuthFailedError,
            InvalidSensorDataError,
            NotRespondingError,
            TimeoutError,
            UpdateFailed,
        ) as err:
            # The periodic refresh still reconnects reactively, so a failure
            # here only costs the head start.
            _LOGGER.debug(
                "Device_Id: %s, scheduled bacon reconnect failed: %s",
                self.unique_id,
                err,
            )
        finally:
            # Re-arm in every case, including the skips above: the floor keeps a
            # repeated failure down to one attempt per BACON_RECONNECT_MIN_DELAY.
            self._schedule_reconnect()

    async def _ensure_connected(self) -> None:
        """Ensure the shared MQTT client is connected, refreshing the token.

        A refused CONNACK means the access token that doubles as the MQTT
        password is stale — a transport failure, not a dead OAuth session. It is
        answered with one forced rotation and a single retry; only a rotation
        that itself fails asks the user to re-authenticate.
        """
        if self.client.is_connected:
            # The session is usually opened during entry setup, before this
            # coordinator exists, so arm the pre-expiry reconnect for it here.
            if self._unsub_reconnect is None:
                self._schedule_reconnect()
            return
        async with self._lock:
            if self.client.is_connected:
                return
            try:
                await self._async_connect(await self._async_session_token())
            except MqttNotAuthorizedError:
                _LOGGER.debug(
                    "Device_Id: %s, bacon MQTT refused the token, forcing a refresh",
                    self.unique_id,
                )
                token = await self._async_session_token(force_refresh=True)
                try:
                    await self._async_connect(token)
                except MqttNotAuthorizedError as retry_err:
                    raise UpdateFailed(
                        "Bacon MQTT rejected the refreshed access token"
                    ) from retry_err

    async def _async_update_data(self) -> BHCDeviceBaconRac:
        """Refresh via a shadow get (also reconnects if the session dropped)."""
        try:
            await self._ensure_connected()
            state = await self.bhc.async_update()
        except MqttNotAuthorizedError as err:
            # Never a reauth: the OAuth refresh token is fine, only the MQTT
            # password (the access token) was stale. Let HA retry the poll.
            raise UpdateFailed(err) from err
        except AuthFailedError as err:
            self.entry.async_start_reauth(self.hass)
            raise UpdateFailed("Re-authentication required") from err
        except (
            ApiError,
            InvalidSensorDataError,
            NotRespondingError,
            TimeoutError,
        ) as err:
            raise UpdateFailed(err) from err
        data = self._build(state)
        self._async_withdraw_reauth()
        return data

    @callback
    def _async_withdraw_reauth(self) -> None:
        """Drop a re-authentication request that data has since disproved.

        A repair raised for what turned out to be a transport failure used to sit
        there for as long as the user ignored it, while the integration worked
        perfectly. Any reauth flow still in progress for this entry is aborted as
        soon as an update succeeds. Aborting a flow does not clear the repair
        issue it raised, so that is removed too — the same pair core does when it
        withdraws a reauth itself.
        """
        for flow in self.hass.config_entries.flow.async_progress_by_handler(
            DOMAIN,
            match_context={
                "source": SOURCE_REAUTH,
                "entry_id": self.entry.entry_id,
            },
        ):
            if "flow_id" not in flow:
                continue
            try:
                self.hass.config_entries.flow.async_abort(flow["flow_id"])
            except UnknownFlow:
                continue
            ir.async_delete_issue(
                self.hass,
                HOMEASSISTANT_DOMAIN,
                f"config_entry_reauth_{self.entry.domain}_{self.entry.entry_id}",
            )
            _LOGGER.debug(
                "Device_Id: %s, withdrew stale re-authentication request",
                self.unique_id,
            )
