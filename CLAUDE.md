# CLAUDE.md - Bosch HomeCom Home Assistant Integration

## Project Overview

Home Assistant custom component for Bosch HomeCom Easy-connected appliances. Cloud-polling integration (`iot_class: cloud_polling`) using the `homecom_alt` library for API communication via Bosch SingleKey ID OAuth2 authentication.

**Domain:** `bosch_homecom`
**Source:** `custom_components/bosch_homecom/`

## Supported Device Types

| Type | Model | Coordinator | API Client |
|------|-------|-------------|------------|
| `rac` | Residential Air Conditioning | `BoschComModuleCoordinatorRac` | `HomeComRac` |
| `k30`, `k40` | Bosch boiler | `BoschComModuleCoordinatorK40` | `HomeComK40` |
| `icom` | Bosch Heat Pump | `BoschComModuleCoordinatorK40` | `HomeComK40` |
| `rrc2` | Bosch Thermostat | `BoschComModuleCoordinatorK40` | `HomeComK40` |
| `wddw2` | Bosch Water Heater | `BoschComModuleCoordinatorWddw2` | `HomeComWddw2` |

## Architecture

### Data Flow

1. `config_flow.py` — Multi-step auth: username -> browser OAuth code -> device selection
2. `__init__.py` — Creates one coordinator per selected device, registers custom services
3. `coordinator.py` — `DataUpdateCoordinator` subclasses poll the API (default 60s, configurable 15-3600s via options flow)
4. Entity files — `CoordinatorEntity` subclasses read from `coordinator.data` and write via `coordinator.bhc`

### Platforms

Six entity platforms in `PLATFORMS`: `climate`, `fan`, `select`, `sensor`, `switch`, `water_heater`.

Each platform's `async_setup_entry` iterates coordinators, checks `deviceType`, and creates entities accordingly.

### Coordinator Pattern

All four coordinator classes (`Generic`, `Rac`, `K40`, `Wddw2`) in `coordinator.py` follow identical structure:
- Inherit `DataUpdateCoordinator[BHCDevice*]`
- Store `self.bhc` (API client), `self.unique_id`, `self.device`, `self.entry`, `self.auth_provider`
- `_async_update_data()` refreshes tokens (if `auth_provider`), calls `self.bhc.async_update()`, returns typed data object
- Token refresh persists to config entry via `hass.config_entries.async_update_entry()`
- Catches `ApiError`, `InvalidSensorDataError`, `RetryError` -> `UpdateFailed`; `AuthFailedError` triggers reauth

### Entity Pattern

All entities:
- Inherit `CoordinatorEntity` + platform entity (e.g., `ClimateEntity`)
- Set `_attr_has_entity_name = True`, `_attr_should_poll = False`
- Use `_attr_unique_id = f"{coordinator.unique_id}-{field}-{suffix}"`
- Use `_attr_translation_key` for names
- Implement `_handle_coordinator_update()` -> `self.set_attr()` + `self.async_write_ha_state()`
- Control methods call `self.coordinator.bhc.async_*()` then `self.coordinator.async_request_refresh()`

### Services (registered in `async_setup`)

- `set_dhw_tempreture` — Set DHW temperature for a level
- `set_dhw_extrahot_water` — Control extra hot water charge mode/duration
- `get_custom_path_service` — Query arbitrary API paths (returns response)

## Key Files

| File | Purpose |
|------|---------|
| `__init__.py` | Entry point: coordinator creation, service registration, options listener |
| `coordinator.py` | 4 coordinator classes (Generic, Rac, K40, Wddw2) |
| `config_flow.py` | ConfigFlow (user/browser/devices steps), OptionsFlow, reauth/reconfigure |
| `const.py` | Constants, device model map, attribute names, sensor descriptors, login URL |
| `climate.py` | `BoschComRacClimate` (AC), `BoschComK40Climate` (heating circuits) |
| `sensor.py` | Notification, DHW, HC, heat source, ventilation, outdoor temp sensors |
| `select.py` | Airflow, program, DHW mode, HC mode, away/holiday selects |
| `switch.py` | Plasmacluster air purification (RAC only) |
| `fan.py` | Ventilation fan (K30/K40/ICOM) |
| `water_heater.py` | K40 and WDDW2 water heater entities |
| `diagnostics.py` | Config entry diagnostics |
| `strings.json` | UI strings (config flow, options, errors, entity translations) |

## Code Conventions

- `from __future__ import annotations` in all files
- Type hints use Python 3.10+ union syntax (`str | None`)
- Async throughout; all HA-facing methods are `async def`
- `@callback` decorator on synchronous coordinator update handlers
- `_LOGGER = logging.getLogger(__name__)` per module
- `PARALLEL_UPDATES = 1` in entity platform files
- Private attributes prefixed with `_` (e.g., `self._operationMode`)
- Data extraction uses `entry.get("key", {}).get("value")` pattern with nested dicts from API
- Import order: `__future__` -> stdlib -> third-party (`homecom_alt`, `homeassistant`) -> local (`.const`, `.coordinator`)

## Build and Test

### Dependencies

- Runtime: `homecom_alt>=1.4.16`
- Test: `pytest`, `pytest-cov`, `pytest-homeassistant-custom-component`, `coverage`, `ruff`, `black`, `isort`

### Running Tests

```bash
# Run tests with coverage
pytest --cov=custom_components --cov-report=term-missing tests

# Via tox
tox -e py312    # tests
tox -e lint     # flake8 + isort + black
tox -e type     # mypy
```

### Test Structure

- `tests/conftest.py` — Fixtures: `auto_enable_custom_integrations`, `mock_config_flow`, `whitelist_pycares_shutdown_thread`
- `tests/test_config_flow.py` — Config flow step tests
- `tests/test_coordinator.py` — Coordinator update and error handling tests
- `tests/test_init.py` — Integration setup tests
- Tests use `pytest-homeassistant-custom-component` for HA test infrastructure
- `asyncio_mode = auto` in setup.cfg (no need for `@pytest.mark.asyncio`)

### Linting Config (setup.cfg)

- **flake8:** max line length 88, ignores E501/W503/E203/D202/W504
- **isort:** 88 char lines, `force_sort_within_sections`, skips `__init__.py`
- **mypy:** Python 3.13, `ignore_errors = true`, `ignore_missing_imports = true`
- **black:** 88 char line length (implicit from isort config)

## Config Entry Data Shape

```python
{
    "username": str,          # SingleKey ID username
    "code": str,              # OAuth authorization code
    "token": str,             # Access token (refreshed automatically)
    "refresh": str,           # Refresh token (persisted on change)
    "devices": {              # Selected devices
        "{deviceId}_{deviceType}": bool,
    }
}
```

Options: `{"update_seconds": int}` (default 60)

## Common Pitfalls

- API responses may contain `None` for nested fields (e.g., `entry["operationMode"]` can be `None`). Always guard with null checks before calling `.get()`.
- The first coordinator in the list is the `auth_provider` responsible for token refresh. Others reuse the shared session.
- Device types `k30`, `k40`, `icom`, `rrc2` all use the same `K40` coordinator and API client but may have different data available.
- Entity unique IDs embed the device ID and zone/circuit field — changing these breaks existing entities.
- `CONF_DEVICES` key format is `{deviceId}_{deviceType}` (underscore-separated).
