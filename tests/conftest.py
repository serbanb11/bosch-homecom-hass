"""Fixtures for testing."""

import threading

import pytest

from custom_components.bosch_homecom.config_flow import BoschHomecomConfigFlow


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return


@pytest.fixture
def mock_config_flow():
    """Fixture to mock the config flow."""
    return BoschHomecomConfigFlow()


@pytest.fixture(autouse=True)
def whitelist_pycares_shutdown_thread():
    """Make the plugin ignore pycares' background thread."""
    yield
    for t in threading.enumerate():
        if "_run_safe_shutdown_loop" in t.name:
            # The plugin already ignores threads starting with 'waitpid-'
            t.name = f"waitpid-{t.ident}"
