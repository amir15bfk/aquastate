"""Typed exceptions used across providers, calculators, and the API."""


class HydroDataError(Exception):
    """Base class for recoverable hydrological data problems."""


class MissingDataError(HydroDataError):
    """A required series or observation is absent."""


class ConfigurationError(HydroDataError):
    """Configuration is invalid or internally inconsistent."""


class ProviderUnavailable(HydroDataError):
    """A live provider cannot run without credentials or network."""


class ScenarioValidationError(HydroDataError):
    """A scenario override is out of bounds or unserializable."""
