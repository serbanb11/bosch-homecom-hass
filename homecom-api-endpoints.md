# HomeCom API Endpoints by Device Type

Base URL: `https://pointt-api.bosch-thermotechnology.com/pointt-api/api/v1/`
Auth: `Authorization: Bearer <access_token>`
All resource paths prefixed with `gateways/{gatewayId}/resource` unless noted otherwise.

---

## Common Endpoints (All Device Types)

### Device Management (no `/resource` prefix)

| Method | Path | Description |
|--------|------|-------------|
| GET | `gateways/` | List all paired gateways/devices |
| GET | `gateways/{gatewayId}` | Get single device details |
| GET | `gateways/{gatewayId}/partnumber` | Get device part number |
| POST | `gateways/` | Pair new device |
| DELETE | `gateways/{gatewayId}` | Unpair device |

### Bulk Operations

| Method | Path | Description |
|--------|------|-------------|
| POST | `bulk` | Batch read/write multiple resources |

### Gateway Info

| Method | Path | Description |
|--------|------|-------------|
| GET | `/gateway/uuid` | Gateway UUID |
| GET | `/gateway/versionFirmware` | Gateway firmware version |
| GET | `/gateway/versionHardware` | Gateway hardware version |
| GET | `/gateway/DateTime` | Gateway date/time |
| PUT | `/gateway/DateTime` | Set date/time |
| GET | `/gateway/serialId` | Gateway serial ID |
| GET | `/gateway/wifi/ssid` | WiFi SSID |
| GET | `/gateway/wifi/mac` | WiFi MAC address |
| GET | `/gateway/tzInfo/timeZone` | Timezone |
| PUT | `/gateway/tzInfo/timeZone` | Set timezone |
| PUT | `/gateway/update/triggerRequest` | Trigger data sync |
| PUT | `/gateway/factoryReset` | Factory reset |

### Notifications

| Method | Path | Description |
|--------|------|-------------|
| GET | `/notifications` | Alerts and notifications |

---

## RAC (Room Air Conditioning) — deviceType: `rac`

### PointT REST API — Real-time Control

#### Air Conditioning State (GET)

| Path | Description |
|------|-------------|
| `/airConditioning/standardFunctions` | Current state: mode, fan, setpoint, air flows, AC control, timers |
| `/airConditioning/advancedFunctions` | Advanced functions state (quiet, powerful, eco, etc.) |

#### Air Conditioning Control (PUT)

| Path | Body Type | Description |
|------|-----------|-------------|
| `/airConditioning/acControl` | PutStringModel | Turn AC on/off |
| `/airConditioning/operationMode` | PutStringModel | Set mode (cool/heat/auto/dry/fan) |
| `/airConditioning/fanSpeed` | PutStringModel | Set fan speed |
| `/airConditioning/temperatureSetpoint` | PutFloatModel | Set target temperature |
| `/airConditioning/airFlowHorizontal` | PutStringModel | Set horizontal vane |
| `/airConditioning/airFlowVertical` | PutStringModel | Set vertical vane |
| `/airConditioning/quickAirFlows` | PutStringModel | Set quick air flow preset |
| `/airConditioning/{advancedFunction}` | PutStringModel | Toggle advanced function (dynamic path) |
| `/airConditioning/timers/{timer}` | PutFloatModel | Set timer value (dynamic path) |

#### Schedules

| Method | Path | Body Type | Description |
|--------|------|-----------|-------------|
| GET | `/airConditioning/switchPrograms/list` | - | List programs |
| GET | `/airConditioning/switchPrograms/program{programId}` | - | Get specific program |
| GET | `/airConditioning/switchPrograms/activeProgram` | - | Active program |
| GET | `/airConditioning/switchPrograms/configuration` | - | Schedule config (min/max, modes, fans) |
| GET | `/airConditioning/switchPrograms/enabled` | - | Scheduling enabled? |
| GET | `/airConditioning/switchPrograms/temporarySetting/enabled` | - | Temporary override active? |
| PUT | `/airConditioning/switchPrograms/program{programId}` | PutRacSwitchPoints | Update program |
| PUT | `/airConditioning/switchPrograms/activeProgram` | PutStringModel | Set active program |
| PUT | `/airConditioning/switchPrograms/enabled` | PutStringModel | Enable/disable scheduling |
| PUT | `/airConditioning/switchPrograms/temporarySetting/enabled` | PutStringModel | Disable temp override |

#### PV/Solar Mode

| Method | Path | Body Type | Description |
|--------|------|-----------|-------------|
| GET | `/pv/enable` | - | PV mode status |
| PUT | `/pv/enable` | PutStringModel | Enable/disable PV mode |

### Bacon GraphQL API — Energy Consumption

**Endpoint:** `https://history.euc1.bacon.bosch-tt-cw.com/graphql`

| Query Name | Interval | Variables | Description |
|------------|----------|-----------|-------------|
| `getRacTotalConsumptions` | DAILY/MONTHLY/YEARLY | serialNumbers, currentTimestamp, currentTimeZoneOffset, firstDayOfWeek | Today/month/year totals |
| `getRacHourlyExtendedConsumptions` | HOURLY | serialNumbers, start, end, currentTimeZoneOffset, firstDayOfWeek, nextToken | Hourly breakdown (paginated) |
| `getRacDailyExtendedConsumptions` | DAILY | serialNumbers, start, end, currentTimeZoneOffset, firstDayOfWeek | Daily breakdown |
| `getRacMonthlyExtendedConsumptions` | MONTHLY | serialNumbers, start, end, currentTimeZoneOffset, firstDayOfWeek | Monthly breakdown (paginated) |
| `getRacDailySensorValues` | DAILY | serialNumbers, start, end, currentTimeZoneOffset, firstDayOfWeek | Room temperature history |
| `getRacHourlySensorValues` | HOURLY | serialNumbers, start, end, currentTimeZoneOffset, firstDayOfWeek, nextToken | Hourly temperature |
| `getRacMonthlySensorValues` | MONTHLY | serialNumbers, start, end, currentTimeZoneOffset, firstDayOfWeek | Monthly temperature |
| `getRacLimitedComparisonsQuery` | - | serialNumbers, timestamps | Period comparisons (limited) |
| `getRacExtendedComparisonsQuery` | - | serialNumbers, start, end | Period comparisons (extended) |

**GraphQL resolver:** `cumulateRacEmonRecords` (consumption) / `cumulateRacBaseRecords` (sensors)

**Response fields (consumption):** `timestamp`, `totalElectricalEnergyConsumptionHeat`, `totalElectricalEnergyConsumptionCool`, `totalElectricalEnergyConsumptionDry`, `totalElectricalEnergyConsumptionFan`

**Response fields (sensor):** `timestamp`, `roomTemperature`

---

## WDDW2 (Water Heater/Boiler) — deviceType: `wddw2`

### DHW Circuit (`/dhwCircuits/dhw1/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/dhwCircuits/dhw1/operationMode` | Current mode |
| PUT | `/dhwCircuits/dhw1/operationMode` | Set mode (ON/OFF/Auto/Eco) |
| GET | `/dhwCircuits/dhw1/currentSetpoint` | Temperature setpoint |
| PUT | `/dhwCircuits/dhw1/currentSetpoint` | Set temperature |
| GET | `/dhwCircuits/dhw1/manualsetpoint` | Manual setpoint |
| PUT | `/dhwCircuits/dhw1/manualsetpoint` | Set manual setpoint |
| GET | `/dhwCircuits/dhw1/operationSetpoints` | Available setpoints |
| GET | `/dhwCircuits/dhw1/charge` | Charge status |
| GET | `/dhwCircuits/dhw1/safetyTemperature` | Safety temp limit |
| PUT | `/dhwCircuits/dhw1/safetyTemperature` | Set safety temp |
| GET | `/dhwCircuits/dhw1/recirculation/enabled` | Recirculation on/off |
| PUT | `/dhwCircuits/dhw1/recirculation/enabled` | Toggle recirculation |
| GET | `/dhwCircuits/dhw1/switchPrograms/program1` | Schedule |
| PUT | `/dhwCircuits/dhw1/switchPrograms/program1` | Set schedule |
| GET | `/dhwCircuits/dhw1/learningWeek` | Learning week |
| GET | `/dhwCircuits/dhw1/tdMode` | Thermal disinfection |
| PUT | `/dhwCircuits/dhw1/tdMode` | Set thermal disinfection |
| GET | `/dhwCircuits/dhw1/numberOfShowersAvailable` | Shower counter |
| GET | `/dhwCircuits/dhw1/outletTemperature` | Outlet temp |
| GET | `/dhwCircuits/dhw1/inletTemperature` | Inlet temp |
| GET | `/dhwCircuits/dhw1/waterTotalConsumption` | Total water consumed |
| GET | `/dhwCircuits/dhw1/friwaPrimaryPumpModulation` | FRIWA pump modulation |
| GET | `/dhwCircuits/dhw1/currentFriwaSupplyTemperature` | FRIWA supply temp |
| GET | `/dhwCircuits/dhw1/outTemp` | Outlet temp (alt) |
| GET | `/dhwCircuits/dhw1/volumeFlow` | Water flow rate |
| GET | `/dhwCircuits/dhw1/reduceTempOnAlarm` | Alarm temp reduction |
| PUT | `/dhwCircuits/dhw1/reduceTempOnAlarm` | Set alarm temp reduction |
| GET | `/dhwCircuits/dhw1/monitorValues` | All monitor values |

### DHW Sensors

| Method | Path | Description |
|--------|------|-------------|
| GET | `/dhwCircuits/dhw1/sensor/heatExchangerTemperature` | Heat exchanger temp |
| GET | `/dhwCircuits/dhw1/sensor/heatExchangerFlueGasTemperature` | Flue gas temp |
| GET | `/dhwCircuits/dhw1/sensor/exhaustFlueGasTemperature` | Exhaust gas temp |
| GET | `/dhwCircuits/dhw1/sensor/airBoxTemperature` | Air box temp |
| GET | `/dhwCircuits/dhw1/sensor/atmosphericPressure` | Atmospheric pressure |
| GET | `/dhwCircuits/dhw1/sensor/fanSpeed` | Fan speed |
| GET | `/dhwCircuits/dhw1/sensor/gasFlow` | Gas flow |
| GET | `/dhwCircuits/dhw1/sensor/waterFlow` | Water flow |
| GET | `/dhwCircuits/dhw1/sensor/externalTankTemperature` | External tank temp |

### Heat Sources

| Method | Path | Description |
|--------|------|-------------|
| GET | `/heatSources/hs1/actualPower` | Current power |
| GET | `/heatSources/hs1/powerPercentage` | Power % |
| GET | `/heatSources/hs1/operationHours` | Operation hours |
| GET | `/heatSources/hs1/numberOfStarts` | Start count |
| GET | `/heatSources/electricityTotalConsumption` | Lifetime electricity |
| GET | `/heatSources/gasTotalConsumption` | Lifetime gas |

### Recordings / Consumption History

| Method | Path | Query | Description |
|--------|------|-------|-------------|
| GET | `/recordings/dhwCircuits/dhw1/sensor/water` | `?interval={interval}` | Water history |
| GET | `/recordings/heatSources/hs1/sensor/electricity` | `?interval={interval}` | Electricity history |
| GET | `/recordings/heatSources/hs1/sensor/gas` | `?interval={interval}` | Gas history |
| GET | `/recordings/dhwCircuits/dhw1/actualTemp` | `?interval={interval}` | DHW temp history |

`interval`: `DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/system/appliance/enabled` | Appliance on/off |
| PUT | `/system/appliance/enabled` | Enable/disable |
| GET | `/system/appliance/model` | Model info |
| GET | `/system/appliance/versionFirmware` | Firmware version |
| GET | `/system/brand` | Brand |
| GET | `/system/bus` | Bus info |
| GET | `/system/systemOfUnits` | Units (°C/°F) |
| PUT | `/system/systemOfUnits` | Set units |
| GET | `/system/holidayMode` | Holiday mode |

---

## ICOM — deviceType: `icom`

### Heating Circuits (`/heatingCircuits/hc{N}/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/heatingCircuits` | List available circuits |
| GET | `/heatingCircuits/hc{N}/activeSwitchProgram` | Active program |
| GET | `/heatingCircuits/hc{N}/controlType` | Control type |
| GET | `/heatingCircuits/hc{N}/currentRoomSetpoint` | Room setpoint |
| GET | `/heatingCircuits/hc{N}/currentSuWiMode` | Summer/Winter mode |
| GET | `/heatingCircuits/hc{N}/holidayMode/activated` | Holiday mode |
| GET | `/heatingCircuits/hc{N}/manualRoomSetpoint` | Manual setpoint |
| GET | `/heatingCircuits/hc{N}/operationMode` | Operation mode |
| GET | `/heatingCircuits/hc{N}/roomtemperature` | Room temp reading |
| GET | `/heatingCircuits/hc{N}/suWiSwitchMode` | SuWi switch mode |
| GET | `/heatingCircuits/hc{N}/switchPrograms/A` | Program A |
| GET | `/heatingCircuits/hc{N}/switchPrograms/B` | Program B |
| GET | `/heatingCircuits/hc{N}/switchProgramMode` | Program mode |
| GET | `/heatingCircuits/hc{N}/temperatureLevels` | Temp level presets |
| GET | `/heatingCircuits/hc{N}/temperatureLevels/comfort2` | Comfort2 level |
| GET | `/heatingCircuits/hc{N}/temperatureLevels/eco` | Eco level |
| GET | `/heatingCircuits/hc{N}/temporaryRoomSetpoint` | Temp override |
| GET | `/heatingCircuits/hc{N}/cooling/roomTempSetpoint` | Cooling setpoint |

### DHW Circuits

| Method | Path | Description |
|--------|------|-------------|
| GET | `/dhwCircuits` | List DHW circuits |
| GET | `/dhwCircuits/dhw{N}/holidayMode/activated` | DHW holiday mode |

### Heat Sources

| Method | Path | Description |
|--------|------|-------------|
| GET | `/heatSources/hs1/type` | Heat source type |
| GET | `/heatSources/info` | Heat sources info |

### Solar Circuits

| Method | Path | Description |
|--------|------|-------------|
| GET | `/solarCircuits` | List solar circuits |

### Ventilation

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ventilation/zone1/exhaustFanLevel` | Fan speed level |
| GET | `/ventilation/zone1/operationMode` | Operation mode |

### Holiday Modes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/system/holidayModes/hm{N}/dhwMode` | DHW mode during holiday |
| GET | `/system/holidayModes/hm{N}/fixTemperature` | Fixed temp |
| GET | `/system/holidayModes/hm{N}/hcMode` | HC mode during holiday |
| GET | `/system/holidayModes/hm{N}/startStop` | Start/stop dates |

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/system/bus` | Bus type |
| GET | `/system/busReq?emsData=0804840401` | Country/region EMS |
| GET | `/system/info` | System info |

---

## K30/K40 (ConnectKey Heat Pump) — deviceType: `k30` / `k40`

### Heating Circuits (`/heatingCircuits/hc{N}/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/heatingCircuits` | List circuits |
| GET/PUT | `/heatingCircuits/hc{N}/activeSwitchProgram` | Active program |
| GET | `/heatingCircuits/hc{N}/actualSupplyTemperature` | Supply temp |
| GET | `/heatingCircuits/hc{N}/actualTemp` | Actual temp |
| GET/PUT | `/heatingCircuits/hc{N}/awayTemperature` | Away temp |
| GET/PUT | `/heatingCircuits/hc{N}/boostDuration` | Boost duration |
| GET/PUT | `/heatingCircuits/hc{N}/boostMode` | Boost on/off |
| GET/PUT | `/heatingCircuits/hc{N}/boostTemperature` | Boost temp |
| GET | `/heatingCircuits/hc{N}/boostRemainingTime` | Boost time left |
| GET | `/heatingCircuits/hc{N}/controlType` | Control type |
| GET/PUT | `/heatingCircuits/hc{N}/cooling/operationMode` | Cooling mode |
| GET/PUT | `/heatingCircuits/hc{N}/cooling/roomTempSetpoint` | Cooling setpoint |
| GET/PUT | `/heatingCircuits/hc{N}/cooling/temperatureLevels/on` | Cooling on temp |
| GET/PUT | `/heatingCircuits/hc{N}/cooling/outdoorThreshold` | Outdoor threshold |
| GET | `/heatingCircuits/hc{N}/cooling/controlType` | Cooling control |
| GET | `/heatingCircuits/hc{N}/currentRoomSetpoint` | Room setpoint |
| GET | `/heatingCircuits/hc{N}/currentSetpoint` | Current setpoint |
| GET | `/heatingCircuits/hc{N}/currentTemperatureLevel` | Current temp level |
| GET | `/heatingCircuits/hc{N}/currentSuWiMode` | Summer/Winter |
| GET | `/heatingCircuits/hc{N}/heatCoolMode` | Heat/cool mode |
| GET | `/heatingCircuits/hc{N}/heatingType` | Heating type |
| GET/PUT | `/heatingCircuits/hc{N}/manualRoomSetpoint` | Manual setpoint |
| GET | `/heatingCircuits/hc{N}/manualsetpoint` | Manual setpoint (alt) |
| GET | `/heatingCircuits/hc{N}/maxTemperatureReached` | Max temp reached |
| GET/PUT | `/heatingCircuits/hc{N}/name` | Circuit name |
| GET/PUT | `/heatingCircuits/hc{N}/openWindowDetection/enabled` | Open window detect |
| GET | `/heatingCircuits/hc{N}/openWindowDetection/status` | Window status |
| GET/PUT | `/heatingCircuits/hc{N}/operationMode` | Operation mode |
| GET | `/heatingCircuits/hc{N}/operationSetpoints` | Available setpoints |
| GET | `/heatingCircuits/hc{N}/pumpModulation` | Pump modulation |
| GET | `/heatingCircuits/hc{N}/roomtemperature` | Room temp |
| GET/PUT | `/heatingCircuits/hc{N}/setpointOptimization` | Setpoint optimization |
| GET/PUT | `/heatingCircuits/hc{N}/suWiSwitchMode` | SuWi switch mode |
| GET/PUT | `/heatingCircuits/hc{N}/suWiThreshold` | SuWi threshold |
| GET/PUT | `/heatingCircuits/hc{N}/suWiCoolingThreshold` | Cooling threshold |
| GET/PUT | `/heatingCircuits/hc{N}/switchPrograms/{name}` | Switch program |
| GET/PUT | `/heatingCircuits/hc{N}/switchProgramMode` | Program mode |
| GET/PUT | `/heatingCircuits/hc{N}/switchPrograms/name{name}` | Named program |
| GET | `/heatingCircuits/hc{N}/temperatureLevels` | Temp levels |
| GET/PUT | `/heatingCircuits/hc{N}/temperatureLevels/{level}` | Specific temp level |
| GET/PUT | `/heatingCircuits/hc{N}/temperatureLevels/high` | High temp level |
| GET/PUT | `/heatingCircuits/hc{N}/temporaryRoomSetpoint` | Temp override |

### DHW Circuits (`/dhwCircuits/dhw{N}/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/dhwCircuits` | List DHW circuits |
| GET | `/dhwCircuits/dhw{N}/actualTemp` | Actual temp |
| GET/PUT | `/dhwCircuits/dhw{N}/charge` | Charge / trigger charge |
| GET/PUT | `/dhwCircuits/dhw{N}/chargeDuration` | Charge duration |
| GET | `/dhwCircuits/dhw{N}/chargeRemainingTime` | Charge time left |
| GET | `/dhwCircuits/dhw{N}/currentTemperatureLevel` | Current temp level |
| GET | `/dhwCircuits/dhw{N}/dhwType` | DHW type |
| GET/PUT | `/dhwCircuits/dhw{N}/name` | DHW name |
| GET | `/dhwCircuits/dhw{N}/operationMode` | Operation mode |
| GET | `/dhwCircuits/dhw{N}/outTemp` | Outlet temp |
| GET/PUT | `/dhwCircuits/dhw{N}/singleChargeSetpoint` | Single charge setpoint |
| GET | `/dhwCircuits/dhw{N}/switchProgram/A` | Switch program A |
| GET | `/dhwCircuits/dhw{N}/temperatureLevels/eco` | Eco level |
| GET | `/dhwCircuits/dhw{N}/temperatureLevels/high` | High level |
| GET | `/dhwCircuits/dhw{N}/temperatureLevels/low` | Low level |
| GET | `/dhwCircuits/dhw{N}/temperatureLevels/off` | Off level |
| GET | `/dhwCircuits/dhw{N}/dhwTankBottomTemperature` | Tank bottom temp |

### Heat Sources

| Method | Path | Description |
|--------|------|-------------|
| GET | `/heatSources/actualHeatDemand` | Heat demand |
| GET | `/heatSources/actualModulation` | Modulation |
| GET | `/heatSources/actualSupplyTemperature` | Supply temp |
| GET | `/heatSources/chStatus` | CH status |
| GET | `/heatSources/currentEmergencyMode` | Emergency mode |
| GET | `/heatSources/emStatus` | EM status |
| GET | `/heatSources/hs1/activefailure` | Active failure |
| GET | `/heatSources/hs1/failurelist` | Failure list |
| GET | `/heatSources/hs1/heatPumpType` | Heat pump type |
| GET | `/heatSources/hs1/type` | Source type |
| GET | `/heatSources/hs1/numberOfStarts` | Start count |
| GET/PUT | `/heatSources/additionalHeater/operationMode` | Aux heater mode |
| GET | `/heatSources/info` | Heat sources info |
| GET | `/heatSources/returnTemperature` | Return temp |
| GET | `/heatSources/workingTime/totalSystem` | Total working time |
| GET | `/heatSources/systemPressure` | System pressure |
| GET | `/heatSources/systemPressureRange` | Pressure range |
| GET | `/heatSources/standbyMode` | Standby mode |
| GET | `/heatSources/emon/{consumptionType}` | Lifetime energy consumption |
| GET | `/heatSources/hybrid/activeHeatSource` | Active source (hybrid) |
| GET | `/heatSources/hybrid/controlStrategy` | Control strategy (hybrid) |
| GET | `/heatSources/hybrid/outdoorStatus` | Outdoor status (hybrid) |
| GET | `/heatSources/hybrid/outdoorVariant` | Outdoor variant (hybrid) |
| GET | `/heatSources/hybrid/reminderDate` | Service reminder |
| GET | `/heatSources/hybrid/reminderEnable` | Reminder enabled |
| GET | `/heatSources/hybrid/reminderLapsed` | Reminder lapsed |
| GET/PUT | `/heatSources/poolSetpointTemperature` | Pool setpoint |
| GET/PUT | `/heatSources/poolStatus` | Pool status |
| GET | `/heatSources/poolTemperature` | Pool temp |

### Solar Circuits

| Method | Path | Description |
|--------|------|-------------|
| GET | `/solarCircuits` | List solar circuits |
| GET | `/solarCircuits/sc{N}/collectorTemperature` | Collector temp |
| GET | `/solarCircuits/sc{N}/dhwTankBottomTemperature` | Tank bottom temp |
| GET | `/solarCircuits/sc{N}/maxCylinderTemperature` | Max cylinder temp |
| GET | `/solarCircuits/sc{N}/dhwTankTemperature` | Tank temp |
| GET | `/solarCircuits/sc{N}/solarYield` | Solar yield |

### Ventilation

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ventilation/zone1` | Full zone data |
| GET | `/ventilation/zone1/exhaustFanLevel` | Fan level |
| GET | `/ventilation/zone1/filter/remainingTime` | Filter remaining |
| GET/PUT | `/ventilation/zone1/filter/maxRunTime` | Filter max run time |
| PUT | `/ventilation/zone1/filter/resetRunTime` | Reset filter timer |
| GET | `/ventilation/zone1/maxIndoorAirQuality` | Max air quality |
| GET | `/ventilation/zone1/maxRelativeHumidity` | Max humidity |
| GET/PUT | `/ventilation/zone1/operationMode` | Operation mode |
| GET | `/ventilation/zone1/sensors/supplyTemp` | Supply temp |
| GET/PUT | `/ventilation/zone1/switchPrograms/cp` | Switch program |
| GET | `/ventilation/zone1/ventilationLevels` | Ventilation levels |

### Holiday Modes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/holidayMode/activeModes` | Active holidays |
| GET | `/holidayMode/configuration` | Config |
| GET | `/holidayMode/list` | List all |
| POST | `/holidayMode` | Create holiday |
| PUT | `/holidayMode/{id}` | Update holiday |
| DELETE | `/holidayMode/{id}` | Delete holiday |
| GET | `/system/holidayModes/hm{N}/assignedTo` | Assigned circuits |
| PUT | `/system/holidayModes/hm{N}/assignedTo` | Set assigned circuits |
| GET/PUT | `/system/holidayModes/hm{N}/dhwMode` | DHW mode |
| GET/PUT | `/system/holidayModes/hm{N}/fixTemperature` | Fixed temp |
| GET/PUT | `/system/holidayModes/hm{N}/hcMode` | HC mode |
| GET/PUT | `/system/holidayModes/hm{N}/startStop` | Start/stop dates |
| PUT | `/system/holidayModes/hm{N}/delete` | Delete holiday |

### RF Devices (Thermostats/Sensors)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/devices/list` | List paired RF devices |
| GET | `/devices/inclusionWhitelist` | Whitelist |
| GET | `/devices/device{N}/assignedHC` | Assigned circuit |
| GET | `/devices/device{N}/battery` | Battery level |
| GET/PUT | `/devices/device{N}/name` | Device name |
| GET | `/devices/device{N}/productName` | Product name |
| GET | `/devices/device{N}/sgtin` | SGTIN |
| GET | `/devices/device{N}/signal` | Signal strength |
| GET | `/devices/device{N}/type` | Device type |
| GET | `/devices/device{N}/versionFirmware` | Firmware |

### PV/Solar Integration

| Method | Path | Description |
|--------|------|-------------|
| GET | `/pv/list` | PV inverter list |
| GET/PUT | `/pv/enable` | PV mode on/off |
| GET | `/pv/commissioning/inverterInfo` | Inverter info |
| GET/PUT | `/pv/commissioning/state` | Commissioning state |
| PUT | `/pv/commissioning/params` | Set PV params |
| PUT | `/pv/commissioning/enable` | Enable commissioning |

### Silent Mode

| Method | Path | Description |
|--------|------|-------------|
| GET/PUT | `/system/silentMode/enabled` | Enabled |
| GET/PUT | `/system/silentMode/startTime` | Start time |
| GET/PUT | `/system/silentMode/stopTime` | Stop time |
| GET/PUT | `/system/silentMode/powerReduction` | Power reduction |

### Season Optimizer

| Method | Path | Description |
|--------|------|-------------|
| GET/PUT | `/system/seasonOptimizer/mode` | Mode |
| GET/PUT | `/system/seasonOptimizer/coolingThreshold` | Cooling threshold |
| GET/PUT | `/system/seasonOptimizer/heatingThreshold` | Heating threshold |

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/system/brand` | Brand |
| GET | `/system/country` | Country |
| GET/PUT | `/system/bus` | Bus type |
| GET/PUT | `/system/dateTime` | Date/time |
| GET | `/system/healthStatus` | Health status |
| GET | `/system/info` | System info |
| GET/PUT | `/system/appliance/model` | Model |
| GET | `/system/appliance/versionFirmware` | Firmware |
| GET/PUT | `/system/awayMode/enabled` | Away mode |
| GET | `/system/energyTariff/electricity` | Electricity tariff |
| GET | `/system/energyTariff/gas` | Gas tariff |
| GET | `/system/energyTariff/oil` | Oil tariff |
| GET | `/system/energyTariff/pv` | PV tariff |
| GET | `/system/iSRC/installationStatus` | iSRC installation |
| GET | `/system/iSRC/supportStatus` | iSRC support |
| GET | `/system/powerGuard/active` | Power guard |
| GET | `/system/powerLimitation/active` | Power limitation |
| GET | `/system/sensors/temperatures/chimney` | Chimney temp |
| GET | `/system/sensors/temperatures/outdoor_t1` | Outdoor temp |
| GET | `/system/sensors/temperatures/return` | Return temp |
| GET | `/system/sensors/temperatures/supply_t1` | Supply temp |
| GET | `/system/sensors/temperatures/supply_t1_setpoint` | Supply setpoint |
| GET | `/system/busReq?emsData=0804840401` | EMS data |

### Gateway (additional)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/gateway/dataProcessing/status` | Data processing |
| GET/PUT | `/gateway/logging/userAcceptance` | Logging consent |
| GET | `/gateway/eth/ip/ipv4` | Ethernet IPv4 |
| GET | `/gateway/eth/ip/ipv6` | Ethernet IPv6 |
| GET | `/gateway/eth/mac` | Ethernet MAC |
| GET | `/gateway/wifi/ip/ipv4` | WiFi IPv4 |
| GET | `/gateway/wifi/ip/ipv6` | WiFi IPv6 |

### Recordings / Energy Monitoring

| Method | Path | Query | Description |
|--------|------|-------|-------------|
| GET | `/recordings/heatSources/hs1/sensor/electricity` | `?interval=` | Electricity sensor |
| GET | `/recordings/heatSources/hs1/sensor/gas` | `?interval=` | Gas sensor |
| GET | `/recordings/heatSources/actualCHPower` | `?interval=` | CH power |
| GET | `/recordings/heatSources/actualDHWPower` | `?interval=` | DHW power |
| GET | `/recordings/heatSources/actualPower` | `?interval=` | Total power |
| GET | `/recordings/heatSources/actualSupplyTemperature` | `?interval=` | Supply temp |
| GET | `/recordings/heatSources/emon/total/burner` | `?interval=` | Total burner |
| GET | `/recordings/heatSources/emon/total/electricity` | `?interval=` | Total electricity |
| GET | `/recordings/heatSources/emon/total/solar` | `?interval=` | Total solar |
| GET | `/recordings/heatSources/emon/{domain}/burner` | `?interval=` | Domain burner |
| GET | `/recordings/heatSources/emon/{domain}/compressor` | `?interval=` | Domain compressor |
| GET | `/recordings/heatSources/emon/{domain}/eheater` | `?interval=` | Domain e-heater |
| GET | `/recordings/heatSources/emon/{domain}/electricity` | `?interval=` | Domain electricity |
| GET | `/recordings/heatSources/emon/{domain}/outputProduced` | `?interval=` | Domain output |
| GET | `/recordings/heatSources/total/energyMonitoring/consumedEnergy` | `?interval=` | Total consumed |
| GET | `/recordings/heatSources/total/energyMonitoring/outputProduced` | `?interval=` | Total output |
| GET | `/recordings/heatSources/total/energyMonitoring/compressor` | `?interval=` | Total compressor |
| GET | `/recordings/heatSources/total/energyMonitoring/eheater` | `?interval=` | Total e-heater |
| GET | `/recordings/heatSources/hs2/emon/{domain}/outputProduced` | `?interval=` | HS2 output (hybrid) |
| GET | `/recordings/heatSources/system/sensors/temperatures/outdoor_t1` | `?interval=` | Outdoor temp |
| GET | `/recordings/system/heatSources/hs1/actualPower` | `?interval=` | HS1 actual power |
| GET | `/recordings/dhwCircuits/dhw1/actualTemp` | `?interval=` | DHW temp |
| GET | `/recordings/dhwCircuits/dhw1/sensor/water` | `?interval=` | Water consumption |
| GET | `/recordings/solarCircuits/sc1/collectorTemperature` | `?interval=` | Solar collector |
| GET | `/recordings/solarCircuits/sc1/solarYield` | `?interval=` | Solar yield |
| GET | `/recordings/{circuitId}/roomtemperature` | `?interval=` | Room temp |
| GET | `/recordings/{circuitId}/actualTemp` | `?interval=` | Actual temp |

`{domain}`: `ch` (central heating), `dhw` (domestic hot water), `pool`, `cooling`, `ventilation`, `total`

---

## RRC2 (Remeha Remote Control) — deviceType: `rrc2`

### Zones

| Method | Path | Description |
|--------|------|-------------|
| GET | `/zones` | List zones |
| GET | `/zones/list` | Zone list |
| GET | `/zones/{zoneId}/zoneTemperatureActual` | Actual temp |
| GET | `/zones/{zoneId}/zoneTemperatureHeatingSetpoint` | Heating setpoint |
| GET | `/zones/{zoneId}/icon` | Zone icon |
| GET | `/zones/{zoneId}/name` | Zone name |

### Heating/DHW

| Method | Path | Description |
|--------|------|-------------|
| GET | `/hc/{hcId}/actualTemperature` | HC actual temp |
| GET | `/hc/{hcId}/controlKey` | Control key |
| GET | `/dhw/{dhwId}/actualTemperature` | DHW actual temp |
| GET | `/dhw/{dhwId}/hotWaterSystem` | Hot water system |

### Gateway

| Method | Path | Description |
|--------|------|-------------|
| GET | `/gateway/uuid` | UUID |
| GET | `/gateway/time/current` | Current time |
| GET | `/gateway/time/timeZone` | Timezone |
| GET | `/gateway/wizardStepsDone` | Setup wizard status |

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/system/location/coordinates` | Location |

---

## Water Softener — deviceType: `watersoftener`

### Water Softener Circuit (`/swCircuits/sw1/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/swCircuits/sw1/holidayMode/enabled` | Holiday mode |
| GET | `/swCircuits/sw1/regeneration/enabled` | Regeneration enabled |
| GET | `/swCircuits/sw1/regeneration/phase` | Current phase |
| GET | `/swCircuits/sw1/regeneration/singleRegAppoint` | Single regen appointment |
| GET | `/swCircuits/sw1/regeneration/timeUntilNext` | Time until next regen |
| GET | `/swCircuits/sw1/regeneration/totalProgressStatus` | Progress status |
| GET | `/swCircuits/sw1/regeneration/totalRemainingTime` | Remaining time |
| GET | `/swCircuits/sw1/regeneration/log` | Regeneration log |
| GET | `/swCircuits/sw1/sensor/availableWater` | Available water |
| GET | `/swCircuits/sw1/sensor/saltLevel` | Salt level |
| GET | `/swCircuits/sw1/sensor/saltLevelAlarm` | Salt alarm |
| GET | `/swCircuits/sw1/sensor/waterFlow` | Water flow |

### Recordings

| Method | Path | Query | Description |
|--------|------|-------|-------------|
| GET | `/recordings/swCircuits/sw1/sensor/water` | `?interval=31D` | 31-day water history |
| GET | `/recordings/swCircuits/sw1/sensor/water` | `?interval=24M` | 24-month water history |

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/system/appliance/versionFirmware` | Firmware |
| GET | `/system/appliance/model` | Model |
| GET | `/system/brand` | Brand |

---

## Commodule / Commodule2 (Wallbox) — deviceType: `commodule` / `commodule2`

### Commodule (Local WiFi Setup)

Base URL: `https://192.168.0.1:443` (device AP) or `https://192.168.0.1:4443`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/gateway/wifi/apList` | List WiFi networks |
| GET | `/gateway/wifi/apList?refresh` | Refresh WiFi list |
| PUT | `/gateway/wifi/ap` | Set WiFi config |
| GET | `/openSourceInfo/list` | OSS license list |
| GET | `/openSourceInfo/{deviceModelId}` | OSS info for model |
| GET | `/gateway/thirdPartyLicenseInformation` | Third-party licenses |

### Commodule2 / Wallbox (via PointT gateway)

All paths: `gateways/{gatewayId}/resource/...`

#### Gateway Info

| Method | Path | Description |
|--------|------|-------------|
| GET | `/gateway/brand` | Brand |
| GET | `/gateway/uuid` | UUID |
| GET | `/gateway/wifi/mac` | WiFi MAC |
| GET | `/gateway/wifi/state` | WiFi state |
| GET | `/gateway/eth0/mac` | Ethernet MAC |
| GET | `/gateway/eth0/state` | Ethernet state |

#### Wallbox Status (GET)

| Path | Description |
|------|-------------|
| `/rest/v1/cp0/info/brand` | Wallbox brand |
| `/rest/v1/cp0/info/extmeterCurrentMaximum` | External meter max current |
| `/rest/v1/cp0/info/paragraph14a` | Grid-friendly charging configured |
| `/rest/v1/cp0/info/relaisAvailable` | Relays available |
| `/rest/v1/cp{N}/conf` | Configuration |
| `/rest/v1/cp{N}/conf/wallboxMode` | Wallbox mode |
| `/rest/v1/cp{N}/info` | Info (firmware version, etc.) |
| `/rest/v1/cp{N}/telemetry` | Telemetry |
| `/rest/v1/cp{N}/telemetry/wbState` | Wallbox state |
| `/rest/v1/cp{N}/telemetry/emStatus` | Energy manager status |
| `/rest/v1/cp0/telemetry/extInputState` | Grid-friendly charging active |
| `/rest/v1/cp0/telemetry/extmeterState` | External meter state |
| `/rest/v1/cp0/telemetry/forceActive` | Force active state |
| `/rest/v1/cp0/conf/auth` | Auth status |
| `/rest/v1/cp0/conf/locked` | Lock status |
| `/rest/v1/cp0/conf/chargingStrategy` | Charging strategy |
| `/rest/v1/cp0/conf/currency` | Currency |
| `/rest/v1/cp0/conf/price` | Electricity price |
| `/rest/v1/cp0/conf/feedinPrice` | Feed-in price |
| `/rest/v1/cp0/conf/rfid` | RFID cards |
| `/rest/v1/cp0/conf/rfid/secure` | RFID security |
| `/rest/v1/cp0/conf/strategy/filterTime` | Filter time |
| `/rest/v1/cp0/conf/strategy/powerOffset` | Power offset |
| `/rest/v1/cp0/conf/overloadProtection/currentLimit` | Phase currents |
| `/rest/v1/cp0/conf/overloadProtection/currentLimiter` | Current limiter |
| `/rest/v1/cp0/conf/overloadProtection/powerLimit` | Power limit |
| `/rest/v1/cp0/conf/overloadProtection/powerLimiter` | Power limiter |
| `/rest/v1/cp0/conf/solarSurplus/supplementEnable` | Solar surplus |
| `/rest/v1/cp0/conf/solarSurplus/supplementLimit` | Supplement limit |
| `/rest/v1/cp0/conf/solarSurplus/supplementThreshold` | Supplement threshold |
| `/rest/v1/cp0/energyhistory` | Consumption history |
| `/rest/v1/cp0/chargelog` | Charge logs |

#### Wallbox Commands (POST)

| Path | Body | Description |
|------|------|-------------|
| `/rest/v1/cp0/cmd/start` | WallboxCommandModel | Start charging |
| `/rest/v1/cp0/cmd/pause` | WallboxCommandModel | Stop/pause |
| `/rest/v1/cp0/cmd/authenticate` | WallboxCommandModel | Authenticate charging |
| `/rest/v1/cp0/cmd/limit` | WallboxLimitCommandModel | Set charge limit |
| `/rest/v1/cp0/cmd/force/limit` | WallboxLimitCommandModel | Force charge limit |
| `/rest/v1/cp0/cmd/force/limitReset` | - | Reset forced limit |
| `/rest/v1/cp0/cmd/rfid/teachIn` | - | Teach in RFID card |

#### Wallbox Configuration (PUT)

| Path | Body | Description |
|------|------|-------------|
| `/rest/v1/cp0/conf/auth` | PutStringModel | Set auth |
| `/rest/v1/cp0/conf/locked` | PutStringModel | Set lock |
| `/rest/v1/cp0/conf/label` | PutStringModel | Set card name |
| `/rest/v1/cp0/conf/chargingStrategy` | PutStringModel | Set strategy |
| `/rest/v1/cp0/conf/currency` | PutStringModel | Set currency |
| `/rest/v1/cp0/conf/price` | PutFloatModel | Set price |
| `/rest/v1/cp0/conf/feedinPrice` | PutFloatModel | Set feed-in price |
| `/rest/v1/cp0/conf/rfid` | ExtendedRFIDCardListModel | Config RFID |
| `/rest/v1/cp0/conf/rfid/secure` | PutStringModel | Set RFID security |
| `/rest/v1/cp0/conf/strategy/filterTime` | PutFloatModel | Set filter time |
| `/rest/v1/cp0/conf/strategy/powerOffset` | PutFloatModel | Set power offset |
| `/rest/v1/cp0/conf/overloadProtection/currentLimit` | TypedList | Set phase currents |
| `/rest/v1/cp0/conf/overloadProtection/currentLimiter` | PutStringModel | Set limiter |
| `/rest/v1/cp0/conf/overloadProtection/powerLimit` | PutFloatModel | Set power limit |
| `/rest/v1/cp0/conf/overloadProtection/powerLimiter` | PutStringModel | Set limiter |
| `/rest/v1/cp0/conf/solarSurplus/supplementEnable` | PutStringModel | Set solar |
| `/rest/v1/cp0/conf/solarSurplus/supplementLimit` | PutFloatModel | Set limit |
| `/rest/v1/cp0/conf/solarSurplus/supplementThreshold` | PutFloatModel | Set threshold |

#### Wallbox Delete

| Method | Path | Description |
|--------|------|-------------|
| DELETE | `/rest/v1/cp0/conf/rfid` | Delete RFID card |

#### Authenticated Charging Flow (firmware >= 5.1.0)

```
1. GET  .../cp{N}/info                     → check firmware version
2. POST .../cp0/cmd/authenticate           → {"name": "<authName>"}
3. POST .../cp0/cmd/start                  → {"name": "<authName>"}
4. GET  .../cp{N}/telemetry + conf         → check limit override needed
5. POST .../cp0/cmd/limit                  → (if needed, limit=6)
```
