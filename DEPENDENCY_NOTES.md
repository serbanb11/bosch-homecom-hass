# Dependency Notes

## homecom_alt library (required for this branch)

The `feature/explore-k40-endpoints` branch adds entities that currently use
`coordinator.async_put_extra_endpoint()` for the 2 endpoints not yet in
`homecom_alt`:

- `/heatSources/additionalHeater/operationMode`
- `/system/silentMode/enabled`

A corresponding PR has been prepared for `homecom_alt`:
- Branch: `feature/additional-heater-silent-mode` on `homecom_alt`
- Adds: `BOSCHCOM_ENDPOINT_HS_ADDITIONAL_HEATER`, `BOSCHCOM_ENDPOINT_SILENT_MODE`
- Adds: `async_get/put_additional_heater_mode()`, `async_get/put_silent_mode()`

### Merge order

1. **First**: Merge & release `homecom_alt` with the new endpoints
2. **Then**: Update this integration to use the library methods directly
   (replace `async_put_extra_endpoint` with `bhc.async_put_additional_heater_mode`)
3. Bump `homecom_alt` version requirement in this repo

### Local development (testing before library release)

```bash
pip install -e /path/to/homecom_alt
```

This installs the local library with the new endpoints, allowing the
integration to be tested end-to-end before the PyPI release.
