"""Type definitions for BHC."""

from dataclasses import dataclass


@dataclass
class ConnectionOptions:
    """Options for BHC."""

    username: str | None = None
    token: str | None = None
    refresh_token: str | None = None
    code: str | None = None
    auth_provider: bool = False


@dataclass(frozen=True)
class BHCDeviceGeneric:
    """Data class for Generic device."""

    device: str | None
    firmware: list | None
    notifications: list | None


@dataclass(frozen=True)
class BHCDeviceRac:
    """Data class for BHC device."""

    device: str | None
    firmware: list | None
    notifications: list | None
    stardard_functions: list | None
    advanced_functions: list | None
    switch_programs: list | None


@dataclass(frozen=True)
class BHCDeviceK40:
    """Data class for K40 and K30 BHC device."""

    device: str | None
    firmware: list | None
    notifications: list | None
    holiday_mode: list | None
    away_mode: list | None
    power_limitation: list | None
    outdoor_temp: list | None
    heat_sources: list | None
    dhw_circuits: list | None
    heating_circuits: list | None
    ventilation: list | None


@dataclass(frozen=True)
class BHCDeviceWddw2:
    """Data class for wddw2 BHC device."""

    device: str | None
    firmware: list | None
    notifications: list | None
    dhw_circuits: list | None
