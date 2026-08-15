"""Tests for src.matcher — pure logic, no network, no database."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.matcher import compute_match_hash, matches, should_notify
from src.sources.base import ServerListing
from tests.conftest import make_watch


def _find(listings: list[ServerListing], product_id: str) -> ServerListing:
    return next(listing for listing in listings if listing.product_id == product_id)


def test_watch_with_matching_cpu_location_and_price_matches_listing(sample_listings):
    listing = _find(sample_listings, "1001")
    watch = make_watch(cpu_pattern="E3-1230v2", location="NYC", price_max_usd=Decimal("80"))

    result = matches(listing, watch)

    assert result is True


def test_watch_with_ram_min_matches_listing_with_more_ram(sample_listings):
    listing = _find(sample_listings, "1002")
    watch = make_watch(ram_min_gb=32)

    result = matches(listing, watch)

    assert result is True


def test_watch_with_ram_min_rejects_listing_with_less_ram(sample_listings):
    listing = _find(sample_listings, "1003")
    watch = make_watch(ram_min_gb=32)

    result = matches(listing, watch)

    assert result is False


def test_watch_with_unmatched_cpu_pattern_has_no_match(sample_listings):
    listing = _find(sample_listings, "1001")
    watch = make_watch(cpu_pattern="E7-8890")

    result = matches(listing, watch)

    assert result is False


def test_watch_with_price_below_listing_price_has_no_match(sample_listings):
    listing = _find(sample_listings, "1001")
    watch = make_watch(price_max_usd=Decimal("50"))

    result = matches(listing, watch)

    assert result is False


def test_watch_with_null_filters_matches_any_in_stock_listing(sample_listings):
    listing = _find(sample_listings, "1004")
    watch = make_watch()

    result = matches(listing, watch)

    assert result is True


def test_out_of_stock_listing_never_matches(sample_listings):
    listing = _find(sample_listings, "1005")
    watch = make_watch()

    result = matches(listing, watch)

    assert result is False


def test_should_notify_when_no_previous_notification():
    watch = make_watch(last_notified_at=None, last_match_hash=None)
    match_hash = compute_match_hash(["1001"])

    result = should_notify(watch, match_hash, renotify_hours=6, now=datetime.now(UTC))

    assert result is True


def test_should_not_notify_same_match_within_renotify_window():
    now = datetime.now(UTC)
    match_hash = compute_match_hash(["1001"])
    watch = make_watch(
        last_notified_at=(now - timedelta(hours=1)).isoformat(),
        last_match_hash=match_hash,
    )

    result = should_notify(watch, match_hash, renotify_hours=6, now=now)

    assert result is False


def test_should_notify_same_match_after_renotify_window_elapses():
    now = datetime.now(UTC)
    match_hash = compute_match_hash(["1001"])
    watch = make_watch(
        last_notified_at=(now - timedelta(hours=7)).isoformat(),
        last_match_hash=match_hash,
    )

    result = should_notify(watch, match_hash, renotify_hours=6, now=now)

    assert result is True


def test_should_notify_when_matched_listings_change():
    now = datetime.now(UTC)
    watch = make_watch(
        last_notified_at=(now - timedelta(minutes=5)).isoformat(),
        last_match_hash=compute_match_hash(["1001"]),
    )

    result = should_notify(watch, compute_match_hash(["1001", "1006"]), renotify_hours=6, now=now)

    assert result is True


def test_match_hash_is_stable_regardless_of_product_id_order():
    first = compute_match_hash(["1001", "1006"])
    second = compute_match_hash(["1006", "1001"])

    assert first == second
