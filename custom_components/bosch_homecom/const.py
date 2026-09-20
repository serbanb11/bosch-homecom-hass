"""Constants."""

from __future__ import annotations

from datetime import timedelta
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
}

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

BOSCH_SENSOR_DESCRIPTORS = {
    "wddw2": [
        {
            "key": "operation_mode",
            "translation_key": "dhw_operation_mode",
            "path": ["dhw_circuits", "dhw1", "operationMode"],
            "name": "Operation Mode",
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
# proving the appliance is reachable. At the default 60 s interval this holds the
# cloud-backed entities at their last value for ~5 minutes instead of dropping
# them to unavailable, then gives up so staleness stays bounded. Local-only
# entities are unaffected — they keep updating from the LAN throughout.
MAX_CLOUD_FAILURES_WITH_LOCAL: Final = 5
