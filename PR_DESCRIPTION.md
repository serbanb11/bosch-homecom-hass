# Add support for Matter/"Bacon"-commissioned RAC air conditioners (cloud MQTT device-shadow)

## Problem

Bosch Climate AC units that are commissioned through the HomeCom Easy app **over Matter**
(serial numbers like `86DM-580-…`) never show up in this integration. Device discovery
reads only the pointt `/gateways/` endpoint, which returns an empty list for these units —
they are not pointt gateways. Setup therefore completes with **0 devices** and the user is
told (issue #115) to "use Matter instead". This affects the Climate 3000i/5000i/6000i family
when added via the app's Matter/BLE pairing flow.

These devices are instead managed by Bosch's **"bacon"** backend and controlled over an
AWS-IoT-style **device shadow via MQTT 5 (WebSocket)** — the same channel the official app uses.

## What this PR does

Adds a parallel discovery + control path for these devices, alongside the existing pointt
REST path (fully additive; the pointt flow is unchanged and degrades gracefully if the bacon
discovery call fails).

- **Discovery**: `GET https://claiming.euc1.bacon.bosch-tt-cw.com/v1/users/self/devices`
  returns the user's Matter device serials. They are surfaced in the config-flow device
  picker as `deviceType: "bacon_rac"`.
- **Transport**: one shared MQTT 5 / WebSocket connection per config entry to
  `wss://broker.euc1.bacon.bosch-tt-cw.com:443/mqtt`.
- **State**: read via the shadow `get` topic; live changes pushed via `update/accepted`.
- **Control**: publish `{"state":{"desired":{…}}}` to the shadow `update` topic.
- **Entity**: a `climate` entity per unit (power, hvac mode, target temperature, fan speed, swing).

## Reverse-engineered protocol (verified live)

- ClientID **must** be a 64-char lowercase hex string (otherwise CONNACK `Not authorized`).
- WebSocket upgrade headers: `Authorization: Bearer <accessToken>` and
  `User-Agent: DashApp/<ver> (Android-Release)`.
- MQTT CONNECT: username = the JWT `sub` claim, password = the raw access token
  (the same SingleKey OIDC token already managed by this integration; scope must include `bacon`).
- Topics: `users/{sub}/devices/{serial}/shadows/state/{get|update}[/accepted|/rejected]`.
- RAC shadow fields: `powerEnabled`, `opMode` (`cool|heat|auto|dry|fan`),
  `fanSpeed` (`auto|quiet|low|medium|high|turbo`), `tempSetpoint` (°C int),
  `hSwingEnabled`, `vSwingEnabled`, plus `fullPowerEnabled`/`sleepEnabled`/`ionizerEnabled`/…
  `reported.customTitle` carries the friendly name.

## Files

**`homecom_alt` (library, bumped to 1.7.0):**
- `bacon.py` (new): `async_get_bacon_devices`, `BaconMqttClient`, `HomeComBaconRac`, `decode_jwt_sub`, `generate_client_id`.
- `const.py`: bacon broker/claim/topic constants.
- `model.py`: `BHCDeviceBaconRac`.
- `pyproject.toml`: `paho-mqtt>=2.0` dependency.
- `tests/test_bacon.py`.

**`bosch-homecom-hass` (integration, bumped to 1.4.0):**
- `config_flow.py`: merge bacon devices into discovery.
- `__init__.py`: shared `BaconMqttClient`, one coordinator per bacon device.
- `coordinator.py`: `BoschComModuleCoordinatorBaconRac` (MQTT push + periodic keep-alive/reconnect + single-owner token rotation).
- `climate.py`: `BoschComBaconRacClimate`.
- `const.py`: `bacon_rac` model label, `CONF_BACON_CLIENT_ID`.
- `manifest.json`: requirement `homecom_alt>=1.7.0`.

## Notes / limitations

- Only RAC (air conditioners) is implemented so far. The bacon backend also serves DHW and
  air-purifier shadows with the same transport; those can follow.
- Token ownership: refresh tokens are single-use, so exactly one coordinator "owns" the
  refresh (the pointt auth-provider if present, otherwise the first bacon coordinator);
  the rest reuse the token persisted on the config entry.
- A stable 64-hex `client_id` is generated once and persisted on the entry so the HA
  connection never collides with the phone app's client id.
