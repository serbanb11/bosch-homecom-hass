"""HomeCom coordinator."""

from __future__ import annotations

from abc import abstractmethod
import asyncio
import dataclasses
from datetime import date, datetime, timedelta
import logging
import re
from typing import Any, TypeVar

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import (
    CALLBACK_TYPE,
    DOMAIN as HOMEASSISTANT_DOMAIN,
    HomeAssistant,
    callback,
)
from homeassistant.data_entry_flow import UnknownFlow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homecom_alt import (
    ApiError,
    AuthFailedError,
    BaconMqttClient,
    BHCDeviceBacon,
    BHCDeviceCommodule,
    BHCDeviceGeneric,
    BHCDeviceIcom,
    BHCDeviceK40,
    BHCDeviceK40Local,
    BHCDeviceRac,
    BHCDeviceRrc2,
    BHCDeviceWddw2,
    BHCLocalModule,
    HomeComAlt,
    HomeComBaconDevice,
    HomeComK40Local,
    HomeComK40LocalFirst,
    HomeComRac,
    InvalidSensorDataError,
    MqttNotAuthorizedError,
    NotRespondingError,
    decode_jwt_exp,
    decode_jwt_sub,
)
from tenacity import RetryError

from .bacon import humanize_appliance_type
from .const import (
    BACON_MODE_FIELDS,
    BACON_RECONNECT_MARGIN,
    BACON_RECONNECT_MIN_DELAY,
    BACON_TOPIC_META,
    BACON_TOPICS_PREFIX,
    CLOUD_AUTH_FAILURES_BEFORE_REFRESH,
    CONF_BACON_TITLES,
    CONF_REFRESH,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    HC_TUNE_ENDPOINTS,
    HC_TUNE_POLL_INTERVAL,
    ICOM_HC_TUNE_KEYS,
    K40_HC_TUNE_KEYS,
    LAST_KNOWN_GOOD_MAX_AGE,
    LAST_KNOWN_GOOD_SKIP,
    LOCAL_CIRCUIT_FALLBACKS,
    LOCAL_DHW_CIRCUIT,
    LOCAL_DHW_KEYS,
    LOCAL_FLAME_STATUS,
    LOCAL_GATEWAY_BRAND,
    LOCAL_GATEWAY_HW_VERSION,
    LOCAL_GATEWAY_IDENTITY,
    LOCAL_GATEWAY_MACS,
    LOCAL_HC_CIRCUIT,
    LOCAL_HC_KEYS,
    LOCAL_HC_STATUS_TO_MODE,
    LOCAL_HEAT_SOURCES,
    LOCAL_MODULES_POLL_INTERVAL,
    LOCAL_NOTIFICATIONS,
    LOCAL_OUTDOOR_TEMP,
    MANUFACTURER,
    MAX_CLOUD_FAILURES_HELD,
    MAX_CLOUD_FAILURES_WITH_LOCAL,
    RECORDING_PATHS,
    RECORDINGS_POLL_INTERVAL,
    RECORDINGS_PREVIOUS_DAY_TRIES,
    WDDW2_HEALTH_STATUS_PATH,
    WDDW2_RECORDINGS_POLL_INTERVAL,
    WDDW2_WATER_TODAY_KEY,
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
        # Consecutive failed refreshes served from the last good data, see
        # _hold_last_data.
        self._held_failures = 0

        self.device_info = DeviceInfo(
            serial_number=self.unique_id,
            identifiers={(DOMAIN, self.unique_id)},
            name="Boschcom_" + device["deviceType"] + "_" + device["deviceId"],
            sw_version=firmware["value"],
            manufacturer=MANUFACTURER,
        )

    async def _async_update_data(self) -> T:
        """Update data via library."""
        await self._async_refresh_tokens()

        try:
            data = await self.bhc.async_update(self.unique_id)
            built = self._build_device_data(data)
        except (
            ApiError,
            InvalidSensorDataError,
            RetryError,
            NotRespondingError,
            UpdateFailed,
        ) as error:
            return self._hold_last_data(error)

        self._held_failures = 0
        return built

    def _hold_last_data(self, error: Exception) -> T:
        """Serve the last good data through a short run of failed refreshes.

        A single timed-out ``/bulk`` call used to flip every entity of the
        device to unavailable for one poll, about once an hour (#193). Up to
        MAX_CLOUD_FAILURES_HELD consecutive failures are ridden out on the
        previous data instead, logged so an outage stays visible. Past that,
        and on the first refresh (nothing to serve yet), the failure is raised
        and keeps being raised until a refresh succeeds.
        """
        if self.data is None or self._held_failures >= MAX_CLOUD_FAILURES_HELD:
            raise UpdateFailed(error) from error
        self._held_failures += 1
        _LOGGER.info(
            "Device_Id: %s, cloud update failed (%s/%s), keeping the last values: %s",
            self.unique_id,
            self._held_failures,
            MAX_CLOUD_FAILURES_HELD,
            error,
        )
        return self.data

    async def _async_refresh_tokens(self) -> None:
        """Refresh the cloud tokens and persist a rotation on the entry.

        Only the ``auth_provider`` coordinator does this; the others reuse the
        shared session. A failed refresh is the one failure that starts a reauth.
        """
        if not self.auth_provider:
            return
        try:
            await self.bhc.get_token()
        except AuthFailedError:
            self.entry.async_start_reauth(self.hass)
            raise UpdateFailed("Re-authentication required") from None
        except (ApiError, NotRespondingError, RetryError, TimeoutError) as error:
            # The token endpoint was unreachable or answered with a server error
            # (e.g. a DNS timeout or a 5xx), so the refresh token was not spent. A normal failed refresh, retried on
            # the next poll -- not an "unexpected error" with a traceback.
            raise UpdateFailed(f"Token refresh failed: {error}") from error
        self._async_persist_tokens()

    @callback
    def _async_persist_tokens(self) -> None:
        """Store a rotated token pair on the entry."""
        if self.bhc.token != self.entry.data.get(
            CONF_TOKEN
        ) or self.bhc.refresh_token != self.entry.data.get(CONF_REFRESH):
            new_data = dict(self.entry.data)
            new_data[CONF_TOKEN] = self.bhc.token
            new_data[CONF_REFRESH] = self.bhc.refresh_token
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            _LOGGER.debug(
                "Device_Id: %s, persisted refreshed auth tokens", self.unique_id
            )

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


class _LastKnownGoodMixin:
    """Fill fields the cloud nulled with their last known value, for a while.

    The library swallows a failed or partial bulk response into ``None``/empty
    values instead of raising, so a refresh "succeeds" carrying holes. Works on
    three shapes: a plain field, a dict of resource nodes (``heat_sources``) and
    a list of circuit references matched by ``id`` (``dhw_circuits``).
    """

    def _keep_last_known_good(self, new):
        prev = self.data
        held: dict[tuple, datetime] = getattr(self, "_lkg_held_since", {})
        self._lkg_held_since = held
        if prev is None:
            return new
        now = dt_util.utcnow()

        def resolve(path: tuple, new_value, prev_value):
            """Return the value to serve for ``path``."""
            if new_value not in (None, {}, []):
                held.pop(path, None)
                return new_value
            if prev_value in (None, {}, []):
                return new_value
            since = held.setdefault(path, now)
            if now - since > LAST_KNOWN_GOOD_MAX_AGE:
                return new_value
            _LOGGER.debug(
                "Device_Id: %s, %s missing from the cloud response, keeping the "
                "last known value",
                self.unique_id,
                "/".join(map(str, path)),
            )
            return prev_value

        def merge_node_dict(path: tuple, new_dict: dict, prev_dict: dict) -> None:
            for key, prev_value in prev_dict.items():
                new_dict[key] = resolve((*path, key), new_dict.get(key), prev_value)

        changes = {}
        for field in dataclasses.fields(new):
            name = field.name
            if name in LAST_KNOWN_GOOD_SKIP:
                continue
            new_value = getattr(new, name)
            prev_value = getattr(prev, name, None)
            if (
                isinstance(new_value, list)
                and new_value
                and isinstance(prev_value, list)
            ):
                prev_by_id = {
                    ref.get("id"): ref for ref in prev_value if isinstance(ref, dict)
                }
                for ref in new_value:
                    prev_ref = (
                        prev_by_id.get(ref.get("id")) if isinstance(ref, dict) else None
                    )
                    if prev_ref:
                        merge_node_dict((name, ref.get("id")), ref, prev_ref)
            elif (
                isinstance(new_value, dict)
                and new_value
                and isinstance(prev_value, dict)
            ):
                merge_node_dict((name,), new_value, prev_value)
            else:
                resolved = resolve((name,), new_value, prev_value)
                if resolved is not new_value:
                    changes[name] = resolved
        return dataclasses.replace(new, **changes) if changes else new


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

    Coordinators that set ``HC_TUNE_KEYS`` also fetch those HC_TUNE_ENDPOINTS
    heating-circuit settings into ``extra_data``, every HC_TUNE_POLL_INTERVAL.
    """

    EXTRA_KEYS = ("additional_heater", "silent_mode", "dhw_charge_duration")
    # Which HC_TUNE_ENDPOINTS settings to fetch; none by default.
    HC_TUNE_KEYS: tuple[str, ...] = ()

    def __init__(self, *args, **kwargs) -> None:
        """Initialize coordinator with the extra-endpoint cache."""
        super().__init__(*args, **kwargs)
        self.extra_data: dict[str, dict | None] = {}
        self.recordings: dict[str, float] = {}
        self._last_recordings_fetch = None
        # The local day the values in ``recordings`` belong to, and how often
        # the previous day has been read since midnight (see _fetch_recordings).
        self._recordings_day: date | None = None
        self._previous_day_reads = 0
        self._last_hc_tune_fetch = None

    async def _async_update_data(self):
        """Update via library, then fetch the standalone endpoints."""
        data = await super()._async_update_data()
        await self._fetch_extra_endpoints()
        await self._fetch_hc_tune()
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

    async def _fetch_hc_tune(self) -> None:
        """Fetch the HC_TUNE_ENDPOINTS settings, rate-limited.

        These are installer-style settings that rarely change, so polling them
        every tick would only add cloud requests. A resource the device lacks
        answers 403/404, which the library returns as ``None``: that is stored
        and produces no entity. A failing request keeps the last good value.
        """
        if not self.HC_TUNE_KEYS:
            return
        now = dt_util.utcnow()
        if (
            self._last_hc_tune_fetch is not None
            and now - self._last_hc_tune_fetch < HC_TUNE_POLL_INTERVAL
        ):
            return

        answered = False
        for key in self.HC_TUNE_KEYS:
            getter = HC_TUNE_ENDPOINTS[key][0]
            try:
                result = await getattr(self.bhc, getter)(self.unique_id, "hc1")
            except (
                ApiError,
                InvalidSensorDataError,
                NotRespondingError,
                RetryError,
                TimeoutError,
            ):
                _LOGGER.debug(
                    "Device %s: endpoint %s failed, keeping last value",
                    self.unique_id,
                    key,
                )
                continue
            answered = True
            self.extra_data[key] = result if result else None
        # Only an outage that failed every request retries on the next tick.
        if answered:
            self._last_hc_tune_fetch = now

    async def async_set_hc_tune(self, key: str, value: float | str) -> None:
        """Write one HC_TUNE_ENDPOINTS setting and re-read them all.

        The next refresh bypasses HC_TUNE_POLL_INTERVAL so the entity shows what
        the device accepted rather than the value from up to 15 minutes ago.
        """
        setter = HC_TUNE_ENDPOINTS[key][1]
        try:
            await getattr(self.bhc, setter)(self.unique_id, "hc1", value)
        except (ApiError, NotRespondingError, RetryError, TimeoutError) as err:
            raise HomeAssistantError(f"Could not set {key} to {value}: {err}") from err
        self._last_hc_tune_fetch = None
        await self.async_request_refresh()

    async def _fetch_recordings(self) -> None:
        """Fetch /recordings/heatSources/* time-series (hourly, rate-limited).

        Runs at most once per RECORDINGS_POLL_INTERVAL. The bulk endpoint
        accepts up to 30 paths per call — 21 fits. Each entry of
        RECORDING_PATHS has its own aggregation mode:
            ``sum`` -> sum of ``y`` (kWh counters)
            ``avg`` -> sum(y) / sum(c) (sensor sample averages)
            ``minute_sum`` -> sum(y) / 60 (icom per-minute sample sums)

        Bosch fills the hourly buckets with a 1-2 h lag, so at midnight the
        day's last hour is not in yet and used to be lost (#178). The first
        reads after midnight therefore finish the previous day: its total stays
        on the sensors until its last bucket has arrived, or
        RECORDINGS_PREVIOUS_DAY_TRIES reads have passed, and today's values
        follow on the next poll.
        """
        now = dt_util.utcnow()
        if (
            self._last_recordings_fetch is not None
            and now - self._last_recordings_fetch < RECORDINGS_POLL_INTERVAL
        ):
            return

        today = dt_util.now().date()
        day = today
        if self._recordings_day == today - timedelta(days=1):
            day = self._recordings_day
        paths = [
            f"/recordings/heatSources/{suffix}?interval={day.isoformat()}"
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

        complete = self._store_recordings(result or {}, day)
        if day == today:
            self._recordings_day = today
            return
        self._previous_day_reads += 1
        if complete or self._previous_day_reads >= RECORDINGS_PREVIOUS_DAY_TRIES:
            # The previous day's final values are on the sensors for this poll;
            # today's are read on the next one rather than in an hour.
            self._recordings_day = today
            self._previous_day_reads = 0
            self._last_recordings_fetch = None

    def _store_recordings(self, result: dict, day: date) -> bool:
        """Aggregate a bulk answer for ``day`` into ``recordings``.

        Returns whether the day is complete: every recording that answered has
        samples in the day's last hour. Depending on the device an unpopulated
        hour is either missing or carries ``c: 0``, so both are checked.
        """
        # Compare in UTC: two datetimes in the same zone subtract by wall clock,
        # which would make every day 24 hours, DST changes included.
        hours = round(
            (
                dt_util.as_utc(dt_util.start_of_local_day(day + timedelta(days=1)))
                - dt_util.as_utc(dt_util.start_of_local_day(day))
            ).total_seconds()
            / 3600
        )
        answered = False
        complete = True
        for suffix, meta in RECORDING_PATHS.items():
            path = f"/recordings/heatSources/{suffix}?interval={day.isoformat()}"
            payload = result.get(path)
            if not isinstance(payload, dict):
                # Endpoint not supported on this device (404/403) or unexpected shape.
                # Keep previous good value if any.
                continue
            recording = payload.get("recording") or []
            if not isinstance(recording, list):
                continue
            answered = True
            last = recording[hours - 1] if len(recording) >= hours else None
            if not isinstance(last, dict) or not _has_samples(last):
                complete = False
            y_sum = 0.0
            c_sum = 0
            for item in recording:
                # Skip future / unpopulated hour slots. Some devices (e.g.
                # Buderus Logatherm WLW166i) return {"c": 0, "y": 1.0} for
                # every not-yet-populated hour of the current day; without
                # this guard both ``sum`` and ``avg`` aggregations would
                # count those placeholders as real samples. Reported by
                # @ombuyse in PR #155.
                if not isinstance(item, dict) or not _has_samples(item):
                    continue
                y = item.get("y")
                if isinstance(y, (int, float)):
                    y_sum += y
                c_sum += int(item["c"])
            if meta["agg"] == "avg":
                if c_sum > 0:
                    self.recordings[meta["key"]] = round(y_sum / c_sum, 2)
            elif meta["agg"] == "minute_sum":
                self.recordings[meta["key"]] = round(y_sum / 60, 3)
            else:  # "sum"
                self.recordings[meta["key"]] = round(y_sum, 3)
        return answered and complete


def _has_samples(bucket: dict) -> bool:
    """Return whether a recording bucket holds samples (``c > 0``)."""
    c = bucket.get("c")
    return isinstance(c, (int, float)) and c > 0


@callback
def _async_registry_device(
    hass: HomeAssistant, entry: ConfigEntry, unique_id: str
) -> dr.DeviceEntry | None:
    """Return the device's registry entry, if it has one.

    Home Assistant 2026.8 added the lookup scoped to the config entry, and
    2026.11 deprecates async_get_device, which stops working in 2027.8.
    Older releases only have async_get_device.
    """
    registry = dr.async_get(hass)
    identifier = (DOMAIN, unique_id)
    if hasattr(registry, "async_get_device_by_identifier"):
        return registry.async_get_device_by_identifier(identifier, entry.entry_id)
    return registry.async_get_device(identifiers={identifier})


def _async_update_registry_device(
    hass: HomeAssistant, entry: ConfigEntry, unique_id: str, **changes: Any
) -> None:
    """Apply ``changes`` to the device's registry entry, if it has one."""
    device = _async_registry_device(hass, entry, unique_id)
    if device is not None:
        dr.async_get(hass).async_update_device(device.id, **changes)


def local_module_key(module: BHCLocalModule, index: int) -> str:
    """Identify a gateway module by its bus address, stable across reordering.

    Without a bus address the hardware ident, then the inventory position, is
    used. Never the serial: identifiers end up in registry files and logs.
    """
    identity = [value for value in (module.bus_id, module.token) if value is not None]
    if not identity:
        identity = [module.hw_ident or f"index-{index}"]
    return re.sub(r"[^a-zA-Z0-9_-]", "_", "-".join(identity))


def _overlay_local(data: BHCDeviceK40, local: BHCDeviceK40Local | None) -> BHCDeviceK40:
    """Return ``data`` with every value the gateway also served replaced by it.

    Each local payload is merged over the cloud one rather than swapped in, so
    keys only the cloud sends (``allowedValues`` and the like) survive.
    """
    resources = getattr(local, "resources", None) or {}
    if not resources:
        return data

    def merged(node, path: str, fallbacks: tuple[str, ...] = ()):
        payload = next(
            (
                resources[candidate]
                for candidate in (path, *fallbacks)
                if isinstance(resources.get(candidate), dict)
            ),
            None,
        )
        if payload is None:
            return node
        return {**node, **payload} if isinstance(node, dict) else dict(payload)

    modes = {
        LOCAL_DHW_CIRCUIT: getattr(local, "dhw_mode", None),
        LOCAL_HC_CIRCUIT: LOCAL_HC_STATUS_TO_MODE.get(
            getattr(local, "hc_status", None)
        ),
    }

    def circuits(refs, keys: tuple[str, ...]):
        if not isinstance(refs, list):
            return refs
        result = []
        for ref in refs:
            if isinstance(ref, dict) and isinstance(ref.get("id"), str):
                ref = dict(ref)
                for key in keys:
                    ref[key] = merged(
                        ref.get(key),
                        f"{ref['id']}/{key}",
                        LOCAL_CIRCUIT_FALLBACKS.get((ref["id"], key), ()),
                    )
                if mode := modes.get(ref["id"]):
                    node = ref.get("operationMode")
                    ref["operationMode"] = {
                        **(node if isinstance(node, dict) else {}),
                        "value": mode,
                    }
            result.append(ref)
        return result

    heat_sources = dict(data.heat_sources or {})
    for key, path in LOCAL_HEAT_SOURCES.items():
        # Neither transport has it: leave the key out rather than adding an
        # empty node, so "not reported" stays distinguishable.
        if (node := merged(heat_sources.get(key), path)) is not None:
            heat_sources[key] = node

    flame = data.flame_indication
    if isinstance(flame, dict):
        flame = merged(flame, LOCAL_FLAME_STATUS)

    notifications = data.notifications
    if notifications is None:
        local_errors = (resources.get(LOCAL_NOTIFICATIONS) or {}).get("values")
        if isinstance(local_errors, list):
            notifications = local_errors

    return dataclasses.replace(
        data,
        notifications=notifications,
        outdoor_temp=merged(data.outdoor_temp, LOCAL_OUTDOOR_TEMP),
        heat_sources=heat_sources,
        flame_indication=flame,
        dhw_circuits=circuits(data.dhw_circuits, LOCAL_DHW_KEYS),
        heating_circuits=circuits(data.heating_circuits, LOCAL_HC_KEYS),
    )


def _cloud_skeleton(
    device: dict, previous: BHCDeviceK40 | None, local: BHCDeviceK40Local
) -> BHCDeviceK40:
    """Build an empty cloud payload for the known circuits.

    Used when there is no cloud data to lay the local readings over (setup
    without the cloud) or when it is too old to show. Everything only the cloud
    has stays empty, so those entities report no value instead of a stale one.
    The circuits are the ones the cloud last listed plus any the gateway reports.
    """
    circuits: dict[str, set[str]] = {"dhwCircuits": set(), "heatingCircuits": set()}
    for refs in (
        getattr(previous, "dhw_circuits", None),
        getattr(previous, "heating_circuits", None),
    ):
        for ref in refs if isinstance(refs, list) else []:
            ref_id = ref.get("id") if isinstance(ref, dict) else None
            if isinstance(ref_id, str) and ref_id.split("/")[1:2] in (
                ["dhwCircuits"],
                ["heatingCircuits"],
            ):
                circuits[ref_id.split("/")[1]].add(ref_id)
    for path in getattr(local, "resources", None) or {}:
        parts = path.split("/")
        if len(parts) > 3 and parts[1] in circuits:
            circuits[parts[1]].add(f"/{parts[1]}/{parts[2]}")
    return BHCDeviceK40(
        device=device,
        firmware=getattr(previous, "firmware", None),
        notifications=None,
        holiday_mode=None,
        away_mode=None,
        power_limitation=None,
        outdoor_temp=None,
        heat_sources={},
        dhw_circuits=[{"id": c} for c in sorted(circuits["dhwCircuits"])],
        heating_circuits=[{"id": c} for c in sorted(circuits["heatingCircuits"])],
        ventilation=None,
        zones=None,
        flame_indication=None,
        energy_history=None,
        hourly_energy_history=None,
        indoor_humidity=None,
        devices=None,
    )


class BoschComModuleCoordinatorK40(
    _K40ExtraEndpointsMixin,
    _LastKnownGoodMixin,
    BoschComModuleCoordinatorBase[BHCDeviceK40],
):
    """A coordinator to manage the fetching of BoschCom data.

    Optionally reads the appliance over the K 40 RF Local API in parallel with
    the cloud. Local access is read-only and does not cover everything the cloud
    does (no operationMode, no per-level DHW setpoints, no zones), so it
    *supplements* rather than replaces the cloud data:

    * ``self.data`` is the cloud payload with the gateway's readings laid over
      it (see :func:`_overlay_local`): values both transports serve come from
      the gateway, everything else from the cloud, in the same entities.
    * ``self.local_data`` carries the local payload and powers the local-only
      entities, which therefore stay live through a cloud outage.
    * When the cloud fails, rejects its token or the token cannot be refreshed,
      **and** the local transport answers, the overlaid values stay live; the
      cloud-only ones keep their last state for ``MAX_CLOUD_FAILURES_WITH_LOCAL``
      refreshes and are empty after that. Without a local transport the
      behaviour is unchanged: the refresh fails immediately.
    """

    HC_TUNE_KEYS = K40_HC_TUNE_KEYS

    def __init__(
        self,
        hass: HomeAssistant,
        bhc: HomeComRac,
        device: list,
        firmware: dict,
        entry: ConfigEntry,
        auth_provider: bool,
        local_client: HomeComK40Local | None = None,
    ) -> None:
        """Initialize, optionally with a local transport."""
        super().__init__(hass, bhc, device, firmware, entry, auth_provider)
        self.local_client = local_client
        self.local_first = (
            HomeComK40LocalFirst(local_client, bhc) if local_client else None
        )
        self.local_data = None
        self.local_source: str | None = None
        self.local_healthy = False
        # The gateway's module inventory, see _fetch_local_modules.
        self.local_modules: tuple[BHCLocalModule, ...] | None = None
        # String values of LOCAL_GATEWAY_IDENTITY, by resource path.
        self.local_gateway_identity: dict[str, str] = {}
        self._last_local_modules_fetch: datetime | None = None
        self._cloud_failures = 0
        # Consecutive cloud 401s from the update itself, see
        # _async_cloud_auth_failed.
        self._cloud_auth_failures = 0
        # A forced refresh was accepted during the current run of 401s, and
        # whether the resulting cloud-outage warning was logged already.
        self._cloud_auth_refreshed = False
        self._cloud_auth_outage_warned = False
        # Set once this coordinator started the reauth flow. The login stays
        # unusable until the user re-authenticates, which reloads the entry.
        self._cloud_auth_rejected = False
        # True when the entry was set up without the cloud (see __init__).
        self.cloud_setup_pending = False

    async def _async_update_data(self) -> BHCDeviceK40:
        """Update from the cloud, and from the local gateway when configured."""
        if self.local_first is None:
            return await super()._async_update_data()
        if self._cloud_auth_rejected:
            return await self._async_update_local_only()

        try:
            await self._async_refresh_tokens()
        except UpdateFailed:
            # No usable cloud token this cycle: either SingleKey rejected the
            # refresh (reauth already started) or its endpoint was unreachable.
            # The gateway does not need that token, so serve it alone instead
            # of taking the whole device down with the cloud.
            return await self._async_update_local_only()

        try:
            update = await self.local_first.async_update(self.unique_id)
        except AuthFailedError:
            return await self._async_cloud_auth_failed()
        except (
            ApiError,
            InvalidSensorDataError,
            RetryError,
            NotRespondingError,
        ) as error:
            # Both transports failed. The payload never arrives on this path, so
            # take the health from the policy object or the local-only sensors
            # would keep presenting their last reading as live.
            self._cloud_failures += 1
            self._cloud_auth_failures = 0
            self.local_healthy = self.local_first.local_healthy
            self._async_notify_local_listeners()
            raise UpdateFailed(error) from error

        self._cloud_auth_failures = 0
        self._cloud_auth_refreshed = False
        self._cloud_auth_outage_warned = False
        self.local_data = update.local
        self.local_source = update.source
        self.local_healthy = update.local_healthy
        await self._fetch_local_modules()

        if update.cloud is not None:
            self._cloud_failures = 0
            if self.cloud_setup_pending:
                # Set up from the gateway alone: the cloud-only entities were
                # never created. Reload once so they are.
                self.cloud_setup_pending = False
                self.hass.config_entries.async_schedule_reload(self.entry.entry_id)
            data = _overlay_local(self._build_device_data(update.cloud), update.local)
        else:
            # Cloud failed while the gateway answered locally, so the appliance
            # is demonstrably fine and this is a cloud-side problem.
            self._cloud_failures += 1
            data = self._local_data_or_fail(
                update.local, update.cloud_error or "Cloud update failed"
            )

        # These are the _K40ExtraEndpointsMixin steps. This method bypasses the
        # mixin's _async_update_data to drive the local transport, so they have
        # to be invoked here or the additionalHeater / silentMode /
        # dhwChargeDuration entities and the recordings would silently stop
        # updating whenever local access is enabled. All cache on failure.
        await self._fetch_extra_endpoints()
        await self._fetch_hc_tune()
        await self._fetch_recordings()
        return data

    async def _async_cloud_auth_failed(self) -> BHCDeviceK40:
        """Serve the gateway while the cloud rejects the token (#221).

        A single 401 can be the shared token being rotated, so it starts no
        reauth. A run of them can mean SingleKey revoked the session while the
        token still looks valid, so every ``CLOUD_AUTH_FAILURES_BEFORE_REFRESH``
        polls the token is refreshed by force. Only a rejected refresh starts
        the reauth flow, as in the base coordinator.

        If SingleKey accepts the refresh, the login is fine and the 401s are
        the HomeCom API refusing a valid token; a browser re-login would only
        hand back the same kind of token. That is treated as a cloud outage:
        the gateway keeps being served, the cloud-only values expire through
        the usual hold, a warning is logged once, and the refresh is forced
        again every ``CLOUD_AUTH_FAILURES_BEFORE_REFRESH`` polls.

        The gateway is read again here because the local-first update drops
        its local result when it raises the cloud's auth error. That costs one
        extra local read per poll while the 401s last.
        """
        self._cloud_auth_failures += 1
        if self._cloud_auth_refreshed and not self._cloud_auth_outage_warned:
            self._cloud_auth_outage_warned = True
            _LOGGER.warning(
                "Device_Id: %s, the cloud refuses a freshly refreshed token; "
                "treating it as a cloud outage and serving the gateway's local "
                "readings until the cloud accepts it again",
                self.unique_id,
            )
        if self._cloud_auth_failures % CLOUD_AUTH_FAILURES_BEFORE_REFRESH == 0:
            if await self._async_force_token_refresh():
                self._cloud_auth_refreshed = True
        return await self._async_update_local_only()

    async def _async_force_token_refresh(self) -> bool:
        """Have the auth provider refresh the shared cloud token by force.

        The provider is the entry's first device, which need not be this
        gateway: a commodule listed before it, for instance. Returns whether
        SingleKey issued a new token pair.
        """
        provider: BoschComModuleCoordinatorBase | None = self
        if not self.auth_provider:
            provider = next(
                (
                    coordinator
                    for coordinator in getattr(self.entry, "runtime_data", None) or []
                    if isinstance(coordinator, BoschComModuleCoordinatorBase)
                    and coordinator.auth_provider
                ),
                None,
            )
        if provider is None:
            return False
        try:
            await provider.bhc.get_token(force=True)
        except AuthFailedError:
            self._async_reject_cloud_auth()
            return False
        except (
            ApiError,
            InvalidSensorDataError,
            NotRespondingError,
            RetryError,
            TimeoutError,
        ) as error:
            _LOGGER.debug(
                "Device_Id: %s, forced token refresh failed: %s",
                self.unique_id,
                error,
            )
            return False
        provider._async_persist_tokens()
        return True

    @callback
    def _async_reject_cloud_auth(self) -> None:
        """Start the reauth flow and stop asking the cloud until it is done."""
        if self._cloud_auth_rejected:
            return
        self._cloud_auth_rejected = True
        _LOGGER.warning(
            "Device_Id: %s, SingleKey rejected the token refresh; serving the "
            "gateway's local readings until you re-authenticate",
            self.unique_id,
        )
        self.entry.async_start_reauth(self.hass)

    async def _async_update_local_only(self) -> BHCDeviceK40:
        """Serve an update from the gateway alone while the cloud token is unusable.

        Bypasses the local-first policy on purpose: that runs the cloud client
        too, whose own token check would only fail again. The extra cloud
        endpoints are skipped for the same reason.
        """
        local = None
        if not self.local_first.local_disabled:
            try:
                local = await self.local_client.async_update()
            except (
                ApiError,
                AuthFailedError,
                InvalidSensorDataError,
                RetryError,
                NotRespondingError,
                TimeoutError,
            ) as error:
                _LOGGER.debug(
                    "Device_Id: %s, local update failed while the cloud token "
                    "is unusable: %s",
                    self.unique_id,
                    error,
                )
        self._cloud_failures += 1
        self.local_data = local
        self.local_source = "local" if local is not None else None
        self.local_healthy = local is not None
        await self._fetch_local_modules()
        return self._local_data_or_fail(local, "No usable cloud token")

    async def _fetch_local_modules(self) -> None:
        """Read the gateway's module inventory, at most once a day.

        Only while local access works: an unhealthy gateway would fail the read
        anyway. A failed read is retried on the next poll; a gateway without the
        resource counts as read, so it is not asked again for a day.
        """
        if self.local_client is None or not self.local_healthy:
            return
        now = dt_util.utcnow()
        if (
            self._last_local_modules_fetch is not None
            and now - self._last_local_modules_fetch < LOCAL_MODULES_POLL_INTERVAL
        ):
            return
        try:
            modules = await self.local_client.async_get_modules()
            identity = await self.local_client.async_get_resources(
                LOCAL_GATEWAY_IDENTITY
            )
        except (ApiError, AuthFailedError, NotRespondingError, TimeoutError) as error:
            _LOGGER.debug(
                "Device_Id: %s, reading the gateway's module inventory failed: %s",
                self.unique_id,
                error,
            )
            return
        self._last_local_modules_fetch = now
        self.local_gateway_identity = {
            path: value
            for path, payload in identity.items()
            if isinstance(value := payload.get("value"), str) and value
        }
        if modules is None:
            return
        self.local_modules = modules
        self._apply_appliance_model(modules)
        self.async_sync_module_devices()

    @callback
    def _apply_appliance_model(self, modules: tuple[BHCLocalModule, ...]) -> None:
        """Name the appliance the gateway reports as the device's model.

        The appliance is the first module with a product name that is not the
        gateway itself, e.g. "Compress CS6800iAW 12 E". Entities created later
        read device_info; an existing registry entry is updated in place.
        """
        model = next(
            (m.product_name for m in modules if m.product_name and not m.is_gateway),
            None,
        )
        if model is None or self.device_info.get("model") == model:
            return
        self.device_info["model"] = model
        _async_update_registry_device(
            self.hass, self.entry, self.unique_id, model=model
        )

    def module_device_identifier(self, module: BHCLocalModule, index: int) -> str:
        """Registry identifier of a module's sub-device."""
        return f"{self.unique_id}-module-{local_module_key(module, index)}"

    @callback
    def async_sync_module_devices(self) -> None:
        """Register each gateway module as a device connected via the appliance.

        A heat pump is several modules (indoor unit, outdoor unit, gateway),
        each with its own model and firmware; the registry shows them on their
        own device pages. Modules gone from the latest inventory lose this
        entry. Waits for the appliance's device, which setup creates after the
        first refresh; setup calls this again then.
        """
        modules = self.local_modules
        if modules is None or (
            _async_registry_device(self.hass, self.entry, self.unique_id) is None
        ):
            return
        registry = dr.async_get(self.hass)
        identity = self.local_gateway_identity
        current = set()
        for index, module in enumerate(modules):
            identifier = (DOMAIN, self.module_device_identifier(module, index))
            current.add(identifier)
            gateway: dict[str, Any] = {}
            if module.is_gateway:
                gateway["hw_version"] = identity.get(LOCAL_GATEWAY_HW_VERSION)
                gateway["connections"] = {
                    (dr.CONNECTION_NETWORK_MAC, dr.format_mac(mac))
                    for path in LOCAL_GATEWAY_MACS
                    if (mac := identity.get(path)) and mac.strip("0:")
                }
            registry.async_get_or_create(
                config_entry_id=self.entry.entry_id,
                identifiers={identifier},
                via_device=(DOMAIN, self.unique_id),
                manufacturer=identity.get(LOCAL_GATEWAY_BRAND, MANUFACTURER),
                **gateway,
                name=module.product_name or module.hw_ident or f"Module {index + 1}",
                model=module.product_name,
                model_id=module.hw_ident,
                sw_version=module.version,
                serial_number=module.product_serial or module.module_serial,
            )
        prefix = f"{self.unique_id}-module-"
        for device in dr.async_entries_for_config_entry(registry, self.entry.entry_id):
            ours = {
                i
                for i in device.identifiers
                if i[0] == DOMAIN and i[1].startswith(prefix)
            }
            if ours and not ours & current:
                registry.async_update_device(
                    device.id, remove_config_entry_id=self.entry.entry_id
                )

    def _local_data_or_fail(
        self, local: BHCDeviceK40Local | None, cloud_error: str
    ) -> BHCDeviceK40:
        """Serve the gateway's readings in the existing entities.

        Values the Local API also serves (temperatures, pressure, modulation,
        heat demand, DHW and heating-circuit status) keep updating. Values only
        the cloud has keep their last state for ``MAX_CLOUD_FAILURES_WITH_LOCAL``
        polls and are empty after that, or straight away when there is no
        cloud data yet (setup without the cloud). Without local data the
        refresh fails as before.
        """
        if local is None:
            self._async_notify_local_listeners()
            raise UpdateFailed(cloud_error)
        if self.data is not None and (
            self._cloud_failures <= MAX_CLOUD_FAILURES_WITH_LOCAL
        ):
            base = self.data
        else:
            if self._cloud_failures == MAX_CLOUD_FAILURES_WITH_LOCAL + 1:
                _LOGGER.warning(
                    "Device_Id: %s, no cloud data for %s polls (%s); showing "
                    "only the gateway's local readings until the cloud is back",
                    self.unique_id,
                    self._cloud_failures,
                    cloud_error,
                )
            base = _cloud_skeleton(self.device, self.data, local)
        return _overlay_local(base, local)

    @callback
    def _async_notify_local_listeners(self) -> None:
        """Push fresh local readings out while the refresh itself is failing.

        DataUpdateCoordinator only notifies listeners on the first of a run of
        failed refreshes, so during a long cloud outage the local-only sensors
        stopped updating yet stayed available. After that first failure nobody
        else tells them, so do it here; cloud-backed entities just re-write
        themselves as unavailable.
        """
        if not self.last_update_success:
            self.async_update_listeners()

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
        return self._keep_last_known_good(BHCDeviceK40(**kwargs))


def _sum_recording(payload: Any) -> float | None:
    """Return the sum of a recording's ``y`` buckets, or None without buckets.

    The daily water recording lists one bucket per hour with the litres drawn
    in that hour under ``y``; ``c`` is the observation count, not a multiplier.
    The author of #220 checked the sum against the app's daily figure.
    """
    if not isinstance(payload, dict):
        return None
    recording = payload.get("recording")
    if not isinstance(recording, list) or not recording:
        return None
    litres = sum(
        float(item["y"])
        for item in recording
        if isinstance(item, dict) and isinstance(item.get("y"), (int, float))
    )
    return round(litres, 2)


class BoschComModuleCoordinatorWddw2(BoschComModuleCoordinatorBase[BHCDeviceWddw2]):
    """A coordinator to manage the fetching of BoschCom data.

    Besides the library's bulk update it reads, every
    WDDW2_RECORDINGS_POLL_INTERVAL, today's DHW water recording into
    ``recordings`` (the same cache shape the K40 recordings use) and
    ``/system/healthStatus`` into ``health_status``. Both reads are optional:
    a transport failure keeps the previous values and retries on the next
    poll, and a device that does not serve them never fills them, so the
    sensors built on them stay pending (see sensor.py) instead of sitting
    unknown for the life of the install.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize, with the recordings and health status caches empty."""
        super().__init__(*args, **kwargs)
        self.recordings: dict[str, float] = {}
        self.health_status: dict | None = None
        self._last_recordings_fetch: datetime | None = None
        self._recordings_day: str | None = None

    async def _async_update_data(self) -> BHCDeviceWddw2:
        """Update via the library, then the slower optional reads."""
        data = await super()._async_update_data()
        await self._fetch_recordings()
        return data

    async def _fetch_recordings(self) -> None:
        """Read today's water recording and the health status, rate-limited."""
        now = dt_util.utcnow()
        today = dt_util.now().strftime("%Y-%m-%d")
        if today != self._recordings_day:
            # A new day: yesterday's total must not be shown as today's, so
            # drop it until today's recording has been read, and read it now.
            self.recordings.pop(WDDW2_WATER_TODAY_KEY, None)
            self._recordings_day = today
            self._last_recordings_fetch = None
        if (
            self._last_recordings_fetch is not None
            and now - self._last_recordings_fetch < WDDW2_RECORDINGS_POLL_INTERVAL
        ):
            return

        water_path = f"/recordings/dhwCircuits/dhw1/sensor/water?interval={today}"
        try:
            # Two calls, as verified on hardware: whether the bulk endpoint
            # accepts a recording and a resource in one request is unknown.
            health = await self.bhc.async_request_bulk(
                self.unique_id, [WDDW2_HEALTH_STATUS_PATH]
            )
            water = await self.bhc.async_request_bulk(self.unique_id, [water_path])
        except (
            ApiError,
            InvalidSensorDataError,
            NotRespondingError,
            RetryError,
            TimeoutError,
        ):
            # Transport failure: keep the last values and leave the timestamp
            # unset so the next regular poll retries straight away.
            _LOGGER.debug(
                "Device %s: recordings fetch failed, keeping last values",
                self.unique_id,
            )
            return
        self._last_recordings_fetch = now

        node = (health or {}).get(WDDW2_HEALTH_STATUS_PATH)
        if isinstance(node, dict) and node.get("value") is not None:
            self.health_status = node
        litres = _sum_recording((water or {}).get(water_path))
        if litres is not None:
            self.recordings[WDDW2_WATER_TODAY_KEY] = litres

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
    _K40ExtraEndpointsMixin,
    _LastKnownGoodMixin,
    BoschComModuleCoordinatorBase[BHCDeviceIcom],
):
    """A coordinator for icom heat pumps (subset of K40 endpoint surface)."""

    HC_TUNE_KEYS = ICOM_HC_TUNE_KEYS

    def _build_device_data(self, data: BHCDeviceIcom) -> BHCDeviceIcom:
        """Build icom device data."""
        return self._keep_last_known_good(
            BHCDeviceIcom(
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


class BoschComModuleCoordinatorBaconRac(DataUpdateCoordinator[BHCDeviceBacon]):
    """Coordinator for a Matter/Bacon-commissioned device (MQTT shadow).

    Serves both bacon families — RAC air conditioners (``bacon_rac``) and air
    purifiers (``bacon_ap``): the shadow, the push-only topics and the token
    handling are identical, only ``bhc`` and the entities differ.

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
        bhc: HomeComBaconDevice,
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
        self._default_name = (
            "Boschcom_" + device["deviceType"] + "_" + device["deviceId"]
        )
        self.device_info = DeviceInfo(
            serial_number=self.unique_id,
            identifiers={(DOMAIN, self.unique_id)},
            name=persisted_title or self._default_name,
            sw_version=self.firmware,
            manufacturer=MANUFACTURER,
        )

        # Whether the cached topics/meta predates the last mode change seen in
        # the shadow. The device republishes meta with different ``ro`` flags
        # after a mode change, but the shadow delta announcing the change lands
        # first, so until the new meta arrives the cached one describes the mode
        # the unit just left. Entities must not block a write on it (#164).
        self.meta_stale = False

        client.register_listener(self.unique_id, self._handle_push)
        client.register_raw_listener(self._handle_topic)
        entry.async_on_unload(lambda: client.remove_raw_listener(self._handle_topic))

    @callback
    def _handle_push(self, state: dict) -> None:
        """Push a live shadow update from MQTT into the coordinator."""
        self.async_set_updated_data(self._build(state))

    @callback
    def _handle_topic(self, serial: str | None, path: str, payload: Any) -> None:
        """Refresh entities when this device publishes on its topics channel.

        topics/{meta,sensor,info} have no request verb, so nothing polls them.
        Without this hook their payloads were only sampled on the next shadow
        push or the next 60 s poll, which left a feature switch read-only, the
        fan control hidden and the room temperature stale for up to a minute
        after a mode change (#164). The library has already cached the payload
        when this runs, so a rebuild from the unchanged shadow picks it up.
        """
        if serial != self.unique_id or not path.startswith(BACON_TOPICS_PREFIX):
            return
        if path == BACON_TOPIC_META:
            self.meta_stale = False
        if self.data is None:
            # Before the first refresh there is no shadow to rebuild from; the
            # first _build reads the cached topics itself.
            return
        self.async_set_updated_data(self._build({}))

    def _build(self, state: dict) -> BHCDeviceBacon:
        # Shadow update/accepted messages can be partial deltas (or carry only
        # the desired branch). Merge onto the last known state so a partial
        # message never wipes fields such as tempSetpoint or customTitle.
        # An explicit null is the shadow's delete-attribute marker — some
        # firmware nulls the mode-locked feature fields while the unit is off,
        # which flipped every feature switch to unknown a few minutes after
        # setup (#164). Keep the last known value instead.
        prev = self.data
        prev_reported = prev.reported if prev and prev.reported else {}
        reported = {
            **prev_reported,
            **{k: v for k, v in (state.get("reported") or {}).items() if v is not None},
        }
        if prev is not None and any(
            reported.get(key) != prev_reported.get(key) for key in BACON_MODE_FIELDS
        ):
            # The cached meta now describes the previous mode; a fresh
            # topics/meta publish (_handle_topic) clears this.
            self.meta_stale = True
        desired = {
            **(prev.desired if prev and prev.desired else {}),
            **{k: v for k, v in (state.get("desired") or {}).items() if v is not None},
        }
        info = self.bhc.info
        self._sync_versions(info)
        title = reported.get("customTitle")
        if title:
            clean = title.split("%|")[0].strip()
            if clean:
                self.device_info["name"] = clean
                self._persist_title(clean)
        elif self.device_info.get("name") == self._default_name:
            # Air purifiers carry no customTitle; name them after the appliance
            # type topics/info reports (``air_4000i`` -> "Air 4000i") rather
            # than Boschcom_bacon_ap_<serial>. A later customTitle still wins.
            appliance = (info or {}).get("appliance")
            appliance_name = humanize_appliance_type(
                appliance.get("type") if isinstance(appliance, dict) else None
            )
            if appliance_name:
                self.device_info["name"] = appliance_name
        return BHCDeviceBacon(
            device=self.device,
            firmware=self.firmware,
            reported=reported,
            desired=desired,
            # From the push-only "topics" channel rather than the shadow, so each
            # stays None until the device has published it. sensor carries
            # roomTemperature, which the shadow does not have at all.
            sensor=self.bhc.sensor,
            metadata=self.bhc.metadata,
            info=info,
        )

    def _sync_versions(self, info: dict | None) -> None:
        """Put the gateway's firmware and hardware versions on the device.

        The pointt firmware lookup does not know Matter devices, so the device
        was registered with "unknown". topics/info carries the real versions
        (``gateway.firmwareVersion`` / ``hardwareVersion``); once it has
        arrived they replace the placeholder, on the device registry entry too,
        since Home Assistant only reads an entity's device_info when it is added.
        """
        gateway = (info or {}).get("gateway") if isinstance(info, dict) else None
        if not isinstance(gateway, dict):
            return
        versions = {
            "sw_version": gateway.get("firmwareVersion"),
            "hw_version": gateway.get("hardwareVersion"),
        }
        changes = {
            key: value
            for key, value in versions.items()
            if isinstance(value, str) and value and self.device_info.get(key) != value
        }
        if not changes:
            return
        self.device_info.update(changes)
        _async_update_registry_device(self.hass, self.entry, self.unique_id, **changes)

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

    async def _async_update_data(self) -> BHCDeviceBacon:
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
