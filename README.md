# Alternative Home Connect Integration for Home Assistant

[![version](https://img.shields.io/github/manifest-json/v/serbanb11/bosch-homecom-hass?filename=custom_components%2Fbosch_homecom%2Fmanifest.json&color=slateblue)](https://github.com/serbanb11/bosch-homecom-hass/releases/latest)
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg?logo=HomeAssistantCommunityStore&logoColor=white)](https://github.com/hacs/integration)


This project is an integration for Bosch Home Comfort enabled appliances compatible with Bosch Home Comfort. It is not affiliated with either BSH or Home Assistant.

***At the moment this integration was tested only with Bosch Climate Class 6000i.***

</br>

# Main features
This integration has the following features:
* Retrieve an authentication token based on username and password from singlekey-id.com
* Refresh token if expired
* All the entities are dynamically read from the API and reflect true capabilities of the appliance.
* The state of all entities is updated in real time with a cloud push type integration.
* Using pure async implementation for reduced load on the platform.
* Read devices notifications

</br>

# Installation instructions
## Bosch Home
Before installing the integration you need to install Bosch HomeCom Easy APP and configure your devices.

### Installation
The easiest way, if you are using HACS, is to install it through [HACS](https://hacs.xyz/).
For manual installation, copy the bosch_homecom folder and all of its contents into your Home Assistant's custom_components folder. This folder is usually inside your /config folder. If you are running Hass.io, use SAMBA to copy the folder over. If you are running Home Assistant Supervised, the custom_components folder might be located at /usr/share/hassio/homeassistant. You may need to create the custom_components folder and then copy the bosch_homecom folder and all of its contents into it.

A dialog box will popup asking you to input your Bosch HomeCom Easy APP username and password. 