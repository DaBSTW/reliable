"""Pure comparison logic: does a listing satisfy a watch, and should we (re)notify."""

import hashlib
from datetime import UTC, datetime, timedelta

from src.db import Watch
from src.sources.base import ServerListing


def matches(listing: ServerListing, watch: Watch) -> bool:
    """Return True when the listing satisfies every non-null filter in the watch."""
    if not listing.in_stock:
        return False
    if watch.cpu_pattern and watch.cpu_pattern.casefold() not in listing.cpu.casefold():
        return False
    if watch.ram_min_gb is not None and listing.ram_gb < watch.ram_min_gb:
        return False
    if watch.storage_pattern and watch.storage_pattern.casefold() not in listing.storage.casefold():
        return False
    if watch.location and _normalize_location(watch.location) != _normalize_location(
        listing.location
    ):
        return False
    return watch.price_max_usd is None or listing.price_usd <= watch.price_max_usd


def _normalize_location(raw: str) -> str:
    return raw.strip().casefold()


def compute_match_hash(product_ids: list[str]) -> str:
    """Stable hash identifying a set of matched listings, for dedup purposes."""
    canonical = ",".join(sorted(product_ids))
    return hashlib.sha256(canonical.encode()).hexdigest()


def should_notify(watch: Watch, match_hash: str, renotify_hours: int, now: datetime) -> bool:
    """Decide whether a fresh match should trigger a notification for this watch."""
    if match_hash != watch.last_match_hash:
        return True
    if watch.last_notified_at is None:
        return True
    last_notified = datetime.fromisoformat(watch.last_notified_at).replace(tzinfo=UTC)
    return now - last_notified >= timedelta(hours=renotify_hours)
