"""Tests for FallbackInventorySource — switches to fallback after repeated failures."""

from contextlib import suppress

from src.errors import InventoryUnavailableError
from src.sources.fallback_source import FallbackInventorySource


class _StubSource:
    def __init__(self, name: str, listings=None, error: Exception | None = None) -> None:
        self.name = name
        self._listings = listings or []
        self._error = error
        self.calls = 0

    async def get_available_servers(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._listings


async def test_uses_primary_while_it_succeeds():
    primary = _StubSource("api", listings=["a"])
    fallback = _StubSource("scraper")
    source = FallbackInventorySource(primary, fallback, failure_threshold=3)

    listings = await source.get_available_servers()

    assert listings == ["a"]
    assert source.name == "api"


async def test_stays_on_primary_below_the_failure_threshold():
    primary = _StubSource("api", error=InventoryUnavailableError("down"))
    fallback = _StubSource("scraper", listings=["b"])
    source = FallbackInventorySource(primary, fallback, failure_threshold=3)

    for _ in range(2):
        with suppress(InventoryUnavailableError):
            await source.get_available_servers()

    assert fallback.calls == 0
    assert source.name == "api"


async def test_switches_to_fallback_after_reaching_the_threshold():
    primary = _StubSource("api", error=InventoryUnavailableError("down"))
    fallback = _StubSource("scraper", listings=["b"])
    source = FallbackInventorySource(primary, fallback, failure_threshold=3)

    for _ in range(2):
        with suppress(InventoryUnavailableError):
            await source.get_available_servers()
    listings = await source.get_available_servers()

    assert listings == ["b"]
    assert source.name == "scraper"


async def test_stays_on_fallback_once_switched_even_if_still_called():
    primary = _StubSource("api", error=InventoryUnavailableError("down"))
    fallback = _StubSource("scraper", listings=["b"])
    source = FallbackInventorySource(primary, fallback, failure_threshold=1)

    with suppress(InventoryUnavailableError):
        await source.get_available_servers()
    await source.get_available_servers()
    await source.get_available_servers()

    assert primary.calls == 1
    assert fallback.calls == 3


async def test_a_success_resets_the_failure_counter():
    primary = _StubSource("api", listings=["a"])
    fallback = _StubSource("scraper")
    source = FallbackInventorySource(primary, fallback, failure_threshold=2)
    source._consecutive_failures = 1

    await source.get_available_servers()

    assert source._consecutive_failures == 0
