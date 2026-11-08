"""Constants."""

from __future__ import annotations

from datetime import timedelta
import re
from typing import Final

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature, UnitOfVolumeFlowRate

DOMAIN = "bosch_homecom"
DEFAULT_UPDATE_INTERVAL: Final = timedelta(seconds=60)
MANUFACTURER: Final = "Bosch"

CONF_UPDATE_SECONDS: Final = "update_seconds"

# Default window for capture_raw_service. The bacon "topics" channel is push-only
# and the device's own publish interval is 1800 s, so a shorter default would
# usually return nothing and read as "the data does not exist".
CAPTURE_RAW_DEFAULT_SECONDS: Final = 120
CAPTURE_RAW_MAX_SECONDS: Final = 2100
CONF_BRAND_BUDERUS: Final = "brand_buderus"
MIN_UPDATE_SECONDS: Final = 15  # avoids spam
MAX_UPDATE_SECONDS: Final = 3600  # 1 hour

MODEL = {
    "rac": "Residential Air Conditioning",
    "k30": "Bosch boiler",
    "k40": "Bosch boiler",
    "wddw2": "Bosch Water Heater",
    "icom": "Bosch Heat Pump",
    "rrc2": "Bosch Thermostat",
    "commodule": "Bosch EV Charger",
    "bacon_rac": "Residential Air Conditioning (Matter)",
    "bacon_ap": "Air purifier (Matter)",
}

# Matter/Bacon device types. Discovery types every bacon serial as bacon_rac (the
# claiming endpoint only returns serials), so entry keys are always
# "{serial}_bacon_rac"; the real type is resolved after the MQTT connect.
BACON_RAC_TYPE: Final = "bacon_rac"
BACON_AP_TYPE: Final = "bacon_ap"
BACON_DEVICE_TYPES: Final = (BACON_RAC_TYPE, BACON_AP_TYPE)

ATTR_NOTIFICATIONS = "notifications"
ATTR_FIRMWARE = "fw"
ATTR_MODE = "operationMode"
ATTR_SPEED = "fanSpeed"
ATTR_HORIZONTAL = "airFlowHorizontal"
ATTR_VERTICAL = "airFlowVertical"
ATTR_TEMP = "temperatureSetpoint"
ATTR_ROOM_TEMP = "roomTemperature"
ATTR_AIR_PURIFICATION = "airPurificationMode"
ATTR_FULL_POWER = "fullPowerMode"
ATTR_ECO_MODE = "ecoMode"
ATTR_TIMERS_ON = "timersOn"
ATTR_TIMERS_OFF = "timersOff"

SINGLEKEY_LOGIN_URL = "https://singlekey-id.com/auth/connect/authorize?state=nKqS17oMAxqUsQpMznajIr&nonce=5yPvyTqMS3iPb4c8RfGJg1&code_challenge=Fc6eY3uMBJkFqa4VqcULuLuKC5Do70XMw7oa_Pxafw0&redirect_uri=com.bosch.tt.dashtt.pointt://app/login&client_id=762162C0-FA2D-4540-AE66-6489F189FADC&response_type=code&prompt=login&scope=openid+email+profile+offline_access+pointt.gateway.claiming+pointt.gateway.removal+pointt.gateway.list+pointt.gateway.users+pointt.gateway.resource.dashapp+pointt.castt.flow.token-exchange+bacon+hcc.tariff.read&code_challenge_method=S256&style_id=tt_bsch"

SINGLEKEY_LOGIN_URL_BUDERUS = "https://singlekey-id.com/auth/connect/authorize?state=nKqS17oMAxqUsQpMznajIr&nonce=5yPvyTqMS3iPb4c8RfGJg1&code_challenge=Fc6eY3uMBJkFqa4VqcULuLuKC5Do70XMw7oa_Pxafw0&redirect_uri=com.buderus.tt.dashtt://app/login&client_id=762162C0-FA2D-4540-AE66-6489F189FADC&response_type=code&prompt=login&scope=openid+email+profile+offline_access+pointt.gateway.claiming+pointt.gateway.removal+pointt.gateway.list+pointt.gateway.users+pointt.gateway.resource.dashapp+pointt.castt.flow.token-exchange+bacon+hcc.tariff.read&code_challenge_method=S256&style_id=tt_bud"

CONF_DEVICES: Final = "devices"
CONF_REFRESH: Final = "refresh"
CONF_WB_LABEL: Final = "wb_label"
CONF_BACON_CLIENT_ID: Final = "bacon_client_id"
CONF_BACON_REGION: Final = "bacon_region"
# Last-known friendly names (customTitle) per bacon device id, persisted so a
# reload with an incomplete first shadow doesn't reset the device name.
CONF_BACON_TITLES: Final = "bacon_titles"
DEFAULT_WB_LABEL: Final = "Wallbox"

# Report an active client to the bacon backend every five minutes like the app
# does; without it the backend stops relaying topics/sensor and the Matter
# sensors go stale for days (#203, confirmed with a rejected-vs-accepted
# control). Kept as a flag so the behaviour can be switched off in one place.
BACON_PRESENCE_HEARTBEAT: Final = True


def api_value_to_state_key(value: str) -> str:
    """Turn a camelCase API value into a translatable state key.

    hassfest only accepts lowercase slugs as state translation keys, so
    wddw2 operation modes such as ``handWash`` are exposed as ``hand_wash``.
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


BOSCH_SENSOR_DESCRIPTORS = {
    "wddw2": [
        {
            "key": "fan_speed",
            "translation_key": "dhw_fan_speed",
            "path": ["dhw_circuits", "dhw1", "fanSpeed"],
            "name": "Fan Speed",
            "device_class": None,
            "unit": "rpm",
            "state_class": "measurement",
            "entity_category": "diagnostic",
        },
        {
            "key": "operation_mode",
            "translation_key": "dhw_operation_mode",
            "path": ["dhw_circuits", "dhw1", "operationMode"],
            "name": "Operation Mode",
            "state_key": True,
            "device_class": None,
            "unit": None,
            "state_class": None,
        },
        {
            "key": "air_box_temperature",
            "translation_key": "dhw_air_box_temperature",
            "path": ["dhw_circuits", "dhw1", "airBoxTemperature"],
            "name": "Air Box Temperature",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": "measurement",
        },
        {
            "key": "inlet_temperature",
            "translation_key": "dhw_inlet_temperature",
            "path": ["dhw_circuits", "dhw1", "inletTemperature"],
            "name": "Inlet Temperature",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": "measurement",
        },
        {
            "key": "outlet_temperature",
            "translation_key": "dhw_outlet_temperature",
            "path": ["dhw_circuits", "dhw1", "outletTemperature"],
            "name": "Outlet Temperature",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": "measurement",
        },
        {
            "key": "water_flow",
            "translation_key": "dhw_water_flow",
            "path": ["dhw_circuits", "dhw1", "waterFlow"],
            "name": "Water Flow",
            "device_class": None,
            "unit": UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
            "state_class": "measurement",
        },
        {
            "key": "heat_source_starts",
            "translation_key": "dhw_heat_source_starts",
            "path": ["dhw_circuits", "dhw1", "nbStarts"],
            "name": "Heat Source Starts",
            "device_class": None,
            "unit": None,
            "state_class": "total_increasing",
            "entity_category": "diagnostic",
        },
    ]
}

WDDW2_NOTIFICATION_CODES: dict[str, str] = {
    "E01": "High temperature",
    "E07": "Air bubbles detected",
    "E10": "Self-test failed",
    "E13": "Water flow measurement failure",
}


# --- K 40 RF Local API (optional, read-only LAN access) ---------------------
# Opt-in per gateway. Stored in entry.data under CONF_LOCAL as
# {device_id: {CONF_LOCAL_HOST: str, CONF_LOCAL_TOKEN: str}} so a multi-gateway
# setup can enable it for some gateways and not others. The token is a
# credential and never expires, hence entry.data rather than entry.options.
CONF_LOCAL: Final = "local"
CONF_LOCAL_HOST: Final = "local_host"
CONF_LOCAL_TOKEN: Final = "local_token"  # noqa: S105 - config key, not a secret
# The gateway's id for that token, needed to revoke it again. Its token store is
# small and answers 507 once full, so tokens must not be left behind.
CONF_LOCAL_TOKEN_ID: Final = "local_token_id"  # noqa: S105 - config key
LOCAL_CLIENT_NAME: Final = "home-assistant"
CONF_LOCAL_LOGIN: Final = "local_login"
CONF_LOCAL_PASSWORD: Final = "local_password"  # noqa: S105 - config key
CONF_LOCAL_GATEWAY: Final = "local_gateway"
CONF_LOCAL_REMOVE: Final = "local_remove"

# How many consecutive cloud failures to ride out while the local transport is
# proving the appliance is reachable. At the default 60 s interval the values
# only the cloud has keep their last state for ~5 minutes, then go empty so
# staleness stays bounded. Values the gateway also serves keep updating
# throughout, in the same entities.
MAX_CLOUD_FAILURES_WITH_LOCAL: Final = 5

# How many consecutive failed cloud refreshes to ride out on the last good data
# before the entities go unavailable, on every device type. The Bosch cloud
# times out a single /bulk call roughly once an hour (#193), and each blip took
# every entity of the device down for one poll. At the default 60 s interval
# this bounds the staleness to ~2 minutes, then gives up so a real outage still
# shows. The first refresh is never held: without data there is nothing to
# serve, and setup must still fail with ConfigEntryNotReady.
MAX_CLOUD_FAILURES_HELD: Final = 2

# How many consecutive cloud 401s a gateway with local access rides out before
# the shared cloud token is refreshed by force (#221), and how often that is
# repeated while the 401s go on. A single 401 can be the token being rotated; a
# run of them can mean SingleKey revoked the session while the token still
# looks valid, which the expiry check never notices. Only a rejected refresh
# starts the reauth flow. If the refresh is accepted and the 401s continue, it
# is a cloud outage, not a login problem. The gateway readings stay live
# throughout.
CLOUD_AUTH_FAILURES_BEFORE_REFRESH: Final = 3


# --- Coordinator: extra cloud endpoints and recordings ---------------------
RECORDINGS_POLL_INTERVAL = timedelta(hours=1)

# The WDDW2 coordinator re-reads today's water recording and the health status
# at this cadence. Both move slowly (the recording gains a bucket per hour, the
# health status changes on a fault), and five minutes keeps the daily figure
# close to the app's while adding two requests per interval, not per poll.
WDDW2_RECORDINGS_POLL_INTERVAL = timedelta(minutes=5)
WDDW2_WATER_TODAY_KEY = "dhw_water_today"
WDDW2_HEALTH_STATUS_PATH = "/system/healthStatus"
HC_TUNE_POLL_INTERVAL = timedelta(minutes=15)

# Weather-compensation / underfloor-heating settings of heating circuit hc1,
# as extra_data key -> (homecom_alt getter, setter). Exposed as number and
# select entities; each coordinator reads only its HC_TUNE_KEYS.
# Requires homecom_alt>=1.8.2.
HC_TUNE_ENDPOINTS: dict[str, tuple[str, str]] = {
    "hc1_max_flow_temp": ("async_get_hc_max_flow_temp", "async_set_hc_max_flow_temp"),
    "hc1_suwi_threshold": (
        "async_get_hc_suwi_threshold",
        "async_set_hc_suwi_threshold",
    ),
    "hc1_control_type": ("async_get_hc_control_type", "async_put_hc_control_type"),
    "hc1_comfort2": (
        "async_get_hc_temp_level_comfort2",
        "async_set_hc_temp_level_comfort2",
    ),
    "hc1_eco": ("async_get_hc_temp_level_eco", "async_set_hc_temp_level_eco"),
    "hc1_heat_curve_min": (
        "async_get_hc_heat_curve_min",
        "async_set_hc_heat_curve_min",
    ),
    "hc1_heat_curve_max": (
        "async_get_hc_heat_curve_max",
        "async_set_hc_heat_curve_max",
    ),
}

K40_HC_TUNE_KEYS = (
    "hc1_max_flow_temp",
    "hc1_suwi_threshold",
    "hc1_control_type",
    "hc1_comfort2",
    "hc1_eco",
)

# icom gateways are quick to rate-limit (#110, #120), so they read only what an
# outdoor-reset heat pump without a room sensor needs to be adjusted: its heat
# curve and the summer/winter threshold. Three requests per HC_TUNE_POLL_INTERVAL.
ICOM_HC_TUNE_KEYS = ("hc1_suwi_threshold", "hc1_heat_curve_min", "hc1_heat_curve_max")

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
#   ``minute_sum`` -> ``sum(y) / 60``. The icom ``total/energyMonitoring/*``
#             branch stores each hour as a sum of per-minute samples (``c``
#             is the sample count, 59 or 60). ``y`` is a multiple of 60 even
#             when ``c`` is 59, so the hour's energy is ``y / 60`` kWh (#178).
#
# An icom has the ``total/energyMonitoring/*`` branch and no ``emon`` branch,
# a K40 the reverse, so both are requested in the same bulk call and the
# unsupported family simply drops out. Both map onto the same keys, hence the
# same entities. A device serving both (none known) would keep the later entry.
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
    # icom heat pumps (#178): the same totals under a different branch, with
    # per-minute sample sums. consumedEnergy has no emon counterpart.
    "total/energyMonitoring/compressor": {
        "key": "energy_compressor_total",
        "agg": "minute_sum",
    },
    "total/energyMonitoring/eheater": {
        "key": "energy_eheater_total",
        "agg": "minute_sum",
    },
    "total/energyMonitoring/outputProduced": {
        "key": "heat_produced_total",
        "agg": "minute_sum",
    },
    "total/energyMonitoring/consumedEnergy": {
        "key": "energy_consumed_total",
        "agg": "minute_sum",
    },
}


# How long a field the cloud stopped delivering is served from its last known
# value. The cloud has been seen answering 200 with single fields nulled
# (dhw1 operationMode, the per-level setpoints) for 90 minutes while everything
# around them stayed fresh (#182). These are settings that rarely change, so a
# bounded hold beats flipping the entity to unknown; past the bound the null is
# passed on so staleness cannot go unnoticed.
LAST_KNOWN_GOOD_MAX_AGE = timedelta(minutes=15)

# Never held: an empty notifications list is a real value (they were cleared),
# and device/firmware are set by the coordinator itself.
LAST_KNOWN_GOOD_SKIP = frozenset({"device", "firmware", "notifications"})


# --- Coordinator: K 40 RF Local API overlay ----------------------------------
# Values the K 40 RF Local API serves in the same payload format as the cloud.
# Cloud resource paths are the local ones prefixed with ``/resource``.
LOCAL_OUTDOOR_TEMP = "/system/sensors/temperatures/outdoor_t1"
LOCAL_HEAT_SOURCES: dict[str, str] = {
    "actualSupplyTemperature": "/heatSources/actualSupplyTemperature",
    "returnTemperature": "/heatSources/returnTemperature",
    "actualModulation": "/heatSources/actualModulation",
    "actualHeatDemand": "/heatSources/actualHeatDemand",
    "systemPressure": "/heatSources/systemPressure",
    "starts": "/heatSources/hs1/numberOfStarts",
    "totalWorkingTime": "/heatSources/workingTime/totalSystem",
}
# Per-circuit keys, read from ``{circuit id}/{key}``, e.g. /dhwCircuits/dhw1/actualTemp.
LOCAL_DHW_KEYS = ("actualTemp", "currentTemperatureLevel", "chargeRemainingTime")
LOCAL_HC_KEYS = ("currentSuWiMode", "currentRoomSetpoint")
# The Local API has no operationMode resource. The library derives the DHW one
# from overallStatus (``dhw_mode``); the heating circuit's is derived the same
# way here. Statuses without a mode (away, holiday, boost, ...) map to nothing.
LOCAL_HC_STATUS_TO_MODE: dict[str, str] = {
    "heating_auto": "auto",
    "heating_manual_on": "manual",
    "heating_manual_off": "off",
}
LOCAL_DHW_CIRCUIT = "/dhwCircuits/dhw1"
LOCAL_HC_CIRCUIT = "/heatingCircuits/hc1"


# --- Coordinator: bacon (Matter/MQTT) reconnect and shadow fields -----------
# Reconnect this far ahead of the access token's expiry. The MQTT password *is*
# the access token, so the broker drops the session when it expires. The margin
# must exceed homecom_alt's 5-minute check_jwt() window, otherwise the forced
# refresh would hand back the same soon-to-expire token.
BACON_RECONNECT_MARGIN = timedelta(minutes=10)

# Never schedule a reconnect closer than this, so a short-lived or already
# expiring token cannot spin up a tight reconnect loop.
BACON_RECONNECT_MIN_DELAY = timedelta(minutes=1)

# Shadow fields whose change makes the cached topics/meta describe the wrong
# mode: the device republishes meta with new ``ro`` flags after either moves.
BACON_MODE_FIELDS: tuple[str, ...] = ("powerEnabled", "opMode")

# The push-only channel; its payloads are never polled, only pushed (#164).
BACON_TOPICS_PREFIX = "topics/"
BACON_TOPIC_META = "topics/meta"
