"""Tests for the scraper source — runs against a static HTML fixture, no real network."""

from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from src.errors import InventoryUnavailableError, ParseError
from src.sources.scraper_source import (
    ScraperSource,
    _backoff_seconds,
    _parse_price_usd,
    _parse_ram_gb,
    parse_listings,
)

FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "specials_page.html").read_text()


def test_parse_listings_extracts_every_well_formed_card():
    listings = parse_listings(FIXTURE_HTML)

    assert [listing.product_id for listing in listings] == ["2001", "2002"]


def test_parse_listings_skips_card_with_missing_field():
    listings = parse_listings(FIXTURE_HTML)

    assert "2003" not in [listing.product_id for listing in listings]


def test_parse_listings_skips_card_with_unparseable_ram():
    listings = parse_listings(FIXTURE_HTML)

    assert "2004" not in [listing.product_id for listing in listings]


def test_parse_listings_maps_fields_correctly():
    listings = parse_listings(FIXTURE_HTML)

    first = listings[0]
    assert (first.cpu, first.ram_gb, first.price_usd, first.location) == (
        "Intel Xeon E3-1230v2",
        32,
        Decimal("69.00"),
        "New York City, NY",
    )


def test_parse_ram_gb_extracts_the_number():
    assert _parse_ram_gb("64GB DDR3") == 64


def test_parse_ram_gb_raises_on_unparseable_input():
    with pytest.raises(ParseError):
        _parse_ram_gb("plenty")


def test_parse_price_usd_strips_dollar_sign_and_thousands_separator():
    assert _parse_price_usd("$1,199.00/mo") == Decimal("1199.00")


def test_parse_price_usd_raises_on_unparseable_input():
    with pytest.raises(ParseError):
        _parse_price_usd("call for pricing")


def test_backoff_seconds_doubles_each_attempt():
    assert (_backoff_seconds(1), _backoff_seconds(2), _backoff_seconds(3)) == (30.0, 60.0, 120.0)


def test_backoff_seconds_is_capped():
    assert _backoff_seconds(10) == 900.0


async def test_get_available_servers_retries_after_a_403_then_succeeds(monkeypatch):
    monkeypatch.setattr("src.sources.scraper_source.asyncio.sleep", _instant_sleep)
    responses = iter([httpx.Response(403), httpx.Response(200, text=FIXTURE_HTML)])
    transport = httpx.MockTransport(lambda _request: next(responses))

    async with httpx.AsyncClient(transport=transport) as client:
        source = ScraperSource(client, url="https://example.invalid/specials")
        listings = await source.get_available_servers()

    assert [listing.product_id for listing in listings] == ["2001", "2002"]


async def test_get_available_servers_gives_up_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr("src.sources.scraper_source.asyncio.sleep", _instant_sleep)
    transport = httpx.MockTransport(lambda _request: httpx.Response(503))

    async with httpx.AsyncClient(transport=transport) as client:
        source = ScraperSource(client, url="https://example.invalid/specials")
        with pytest.raises(InventoryUnavailableError):
            await source.get_available_servers()


async def test_get_available_servers_raises_immediately_on_non_retryable_status(monkeypatch):
    monkeypatch.setattr("src.sources.scraper_source.asyncio.sleep", _instant_sleep)
    transport = httpx.MockTransport(lambda _request: httpx.Response(500))

    async with httpx.AsyncClient(transport=transport) as client:
        source = ScraperSource(client, url="https://example.invalid/specials")
        with pytest.raises(InventoryUnavailableError):
            await source.get_available_servers()


async def _instant_sleep(_seconds: float) -> None:
    return None
