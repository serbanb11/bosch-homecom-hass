"""Bhc exceptions."""


class BhcError(Exception):
    """Base class for BHC errors."""

    def __init__(self, status: str) -> None:
        """Initialize."""
        super().__init__(status)
        self.status = status


class ApiError(BhcError):
    """Raised when request ended in error."""


class NotRespondingError(BhcError):
    """Raised when device is not responding."""


class AuthFailedError(BhcError):
    """Raised if auth fails."""


class InvalidSensorDataError(BhcError):
    """Raised when sensor data is invalid."""
