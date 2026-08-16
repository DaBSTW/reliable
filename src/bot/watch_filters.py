"""Parses the /watch key=value syntax into typed filters."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from src.errors import WatchFilterError

# Mirrors the /watch syntax documented in README.md and SPECS.md §8.
_WATCH_FILTER_KEYS = {"cpu", "ram", "disco", "loc", "precio", "nombre"}


@dataclass(frozen=True)
class WatchFilters:
    label: str | None = None
    cpu_pattern: str | None = None
    ram_min_gb: int | None = None
    storage_pattern: str | None = None
    location: str | None = None
    price_max_usd: Decimal | None = None


def parse_watch_filters(args: list[str]) -> WatchFilters:
    """Parse `key=value` tokens into typed watch filters."""
    raw = _tokenize(args)
    ram_raw = raw.get("ram")
    price_raw = raw.get("precio")
    return WatchFilters(
        label=raw.get("nombre"),
        cpu_pattern=raw.get("cpu"),
        ram_min_gb=_positive_int(ram_raw, "ram") if ram_raw is not None else None,
        storage_pattern=raw.get("disco"),
        location=raw.get("loc"),
        price_max_usd=_positive_decimal(price_raw, "precio") if price_raw is not None else None,
    )


def _tokenize(args: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in args:
        if "=" not in token:
            raise WatchFilterError(f"invalid token {token!r}, expected key=value")
        raw_key, raw_value = token.split("=", 1)
        key = raw_key.strip().casefold()
        value = raw_value.strip()
        if key not in _WATCH_FILTER_KEYS:
            raise WatchFilterError(f"unknown filter {raw_key!r}")
        if not value:
            raise WatchFilterError(f"empty value for filter {raw_key!r}")
        result[key] = value
    return result


def _positive_int(raw: str, key: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise WatchFilterError(f"{key} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise WatchFilterError(f"{key} must be positive, got {raw!r}")
    return value


def _positive_decimal(raw: str, key: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise WatchFilterError(f"{key} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise WatchFilterError(f"{key} must be positive, got {raw!r}")
    return value
