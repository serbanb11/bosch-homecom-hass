"""Native dehumidifier platform for the Bosch 6000i and 8000i for the local HomeCom extension."""

from __future__ import annotations

from .dehumidifier import BoschComDehumidifier, async_setup_dehumidifier_entities

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Expose identified dehumidifiers using the already authenticated coordinator."""
    async_setup_dehumidifier_entities(
        hass,
        config_entry,
        async_add_entities,
        lambda coordinator: [BoschComDehumidifier(coordinator)],
    )
