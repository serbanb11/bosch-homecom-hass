# Bosch HomeCom Easy for Home Assistant

[![version](https://img.shields.io/github/manifest-json/v/serbanb11/bosch-homecom-hass?filename=custom_components%2Fbosch_homecom%2Fmanifest.json&color=slateblue)](https://github.com/serbanb11/bosch-homecom-hass/releases/latest)
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg?logo=HomeAssistantCommunityStore&logoColor=white)](https://github.com/hacs/integration)

A Home Assistant custom integration for Bosch HomeCom Easy-connected appliances. Cloud-polling, pure async, automatic token refresh.

> **Disclaimer:** This project is not affiliated with Bosch or Home Assistant.

## Supported Devices

| Device Type | Examples |
|-------------|----------|
| **RAC** | Climate Class 3000i\*, 5000i, 6000i |
| **K30 / K40** | Bosch boilers, Buderus Logatherm WLW 186i (MX300) |
| **ICOM** | IVT Aero Series heat pumps |
| **RRC2** | Bosch thermostats |
| **WDDW2** | Hydronext 5700s water heaters |

\* Midea-based Climate Class 3000i and 7000i are **not** supported.

## Installation

### HACS (Recommended)

1. In HACS, go to **Integrations** > **Custom repositories**
2. Add `https://github.com/serbanb11/bosch-homecom-hass` as an **Integration**
3. Search for **Bosch HomeCom** and download
4. Restart Home Assistant

### Manual

Copy `custom_components/bosch_homecom/` into your Home Assistant `config/custom_components/` directory and restart.

## Setup

The integration requires an authorization code from the Bosch SingleKey ID login flow.

1. Go to **Settings** > **Devices & Services** > **Add Integration** > **Bosch HomeCom**
2. Enter your SingleKey ID **username**
3. Open the [authorization URL](https://singlekey-id.com/auth/connect/authorize?state=nKqS17oMAxqUsQpMznajIr&nonce=5yPvyTqMS3iPb4c8RfGJg1&code_challenge=Fc6eY3uMBJkFqa4VqcULuLuKC5Do70XMw7oa_Pxafw0&redirect_uri=com.bosch.tt.dashtt.pointt://app/login&client_id=762162C0-FA2D-4540-AE66-6489F189FADC&response_type=code&prompt=login&scope=openid+email+profile+offline_access+pointt.gateway.claiming+pointt.gateway.removal+pointt.gateway.list+pointt.gateway.users+pointt.gateway.resource.dashapp+pointt.castt.flow.token-exchange+bacon+hcc.tariff.read&code_challenge_method=S256&style_id=tt_bsch) in a private browser window
4. Open the **Network** tab in Developer Tools (`F12`), then log in with your credentials
5. After the redirect fails (expected), find the request containing `code=` in the Network tab and copy the code value (ends in `-1`)

   ![Authorization Code](./img/login.png)

6. Paste the code into Home Assistant and select your devices

> **Tip:** Use a private/incognito window and complete setup quickly -- the code is single-use and expires fast.

## What You Get

| Platform | RAC | K30/K40/ICOM/RRC2 | WDDW2 |
|----------|-----|---------------------|-------|
| Climate | HVAC modes, fan, swing, presets | Heating circuits with away mode | -- |
| Water Heater | -- | Operation mode | Operation mode + target temp |
| Select | Airflow, programs | DHW/HC modes, away, holiday | -- |
| Sensor | Notifications | Notifications, DHW, HC, heat source, outdoor temp | Notifications, temperatures, flow |
| Switch | Plasmacluster | -- | -- |
| Fan | -- | Ventilation zones | -- |

## Documentation

See the **[Wiki](https://github.com/serbanb11/bosch-homecom-hass/wiki)** for full documentation:

- [Authentication details](https://github.com/serbanb11/bosch-homecom-hass/wiki/Authentication) -- step-by-step with screenshots
- [Entities reference](https://github.com/serbanb11/bosch-homecom-hass/wiki/Entities-Reference) -- complete entity list per device type
- [Custom services](https://github.com/serbanb11/bosch-homecom-hass/wiki/Custom-Services) -- DHW temperature, extra hot water, custom API queries
- [Template sensors](https://github.com/serbanb11/bosch-homecom-hass/wiki/Template-Sensors) -- energy tracking templates
- [Lovelace cards](https://github.com/serbanb11/bosch-homecom-hass/wiki/Lovelace-Cards) -- dashboard examples
- [Troubleshooting](https://github.com/serbanb11/bosch-homecom-hass/wiki/Troubleshooting) -- common issues and debug logging

## Acknowledgements

Special thanks to [RonNabuurs](https://github.com/RonNabuurs) for his valuable work on integrating **K30** support.
