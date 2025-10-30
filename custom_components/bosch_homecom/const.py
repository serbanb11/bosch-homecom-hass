"""Constants."""

from __future__ import annotations

from datetime import timedelta
from typing import Final
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature, UnitOfPressure, UnitOfVolumeFlowRate, PERCENTAGE


DOMAIN = "bosch_homecom"
DEFAULT_UPDATE_INTERVAL: Final = timedelta(seconds=15)
MANUFACTURER: Final = "Bosch"

MODEL = {
    "rac": "Residential Air Conditioning",
    "k30": "Bosch boiler",
    "k40": "Bosch boiler",
    "wddw2": "Bosch Water Heater",
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

CONF_DEVICES: Final = "devices"
CONF_REFRESH: Final = "refresh"

BOSCH_SENSOR_DESCRIPTORS = {
    "wddw2": [
        {
            "key": "operation_mode",
            "path": ["dhw_circuits", "dhw1", "operationMode"],
            "name": "DHW Operation Mode",
            "device_class": None,
            "unit": None,
            "state_class": None,
        },
        {
            "key": "air_box_temperature",
            "path": ["dhw_circuits", "dhw1", "airBoxTemperature"],
            "name": "Air Box Temperature",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": "measurement",
        },
        {
            "key": "inlet_temperature",
            "path": ["dhw_circuits", "dhw1", "inletTemperature"],
            "name": "DHW Inlet Temperature",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": "measurement",
        },
        {
            "key": "outlet_temperature",
            "path": ["dhw_circuits", "dhw1", "outletTemperature"],
            "name": "DHW Outlet Temperature",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": "measurement",
        },
        {
            "key": "water_flow",
            "path": ["dhw_circuits", "dhw1", "waterFlow"],
            "name": "DHW Water Flow",
            "device_class": None,
            "unit": None,  # a API já devolve "l/min" na unidade do nó
            "state_class": "measurement",
        },
        # No WDDW2 o contador de arranques vem como nbStarts dentro do dhw1
        {
            "key": "heat_source_starts",
            "path": ["dhw_circuits", "dhw1", "nbStarts"],
            "name": "Heat Source Starts",
            "device_class": None,
            "unit": None,
            "state_class": "total_increasing",
        },
    ]
}
