"""Domain-specific exceptions, raised instead of bare Exception."""


class ReliableWatchError(Exception):
    """Base class for every error raised by this codebase."""


class ConfigError(ReliableWatchError):
    """A required setting is missing or has an invalid value."""


class InventoryUnavailableError(ReliableWatchError):
    """The active InventorySource could not fetch data (network, HTTP, auth)."""


class ParseError(ReliableWatchError):
    """A listing or watch filter could not be parsed from raw input."""


class WatchFilterError(ReliableWatchError):
    """The user supplied an invalid /watch filter."""
