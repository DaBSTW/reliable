"""End-to-end poll cycle tests: source -> matcher -> notifier, no real network."""

from decimal import Decimal

import pytest

from src.db import Database
from src.errors import InventoryUnavailableError
from src.poller import CONSECUTIVE_FAILURE_ALERT_THRESHOLD, STALLED_POLL_ALERT_MINUTES, PollCycle
from src.sources.base import ServerListing

LISTING = ServerListing(
    product_id="1001",
    description="E3-1230, 32GB",
    cpu="Intel Xeon E3-1230v2",
    ram_gb=32,
    storage="2x480GB SSD",
    location="NYC",
    price_usd=Decimal("69.00"),
    in_stock=True,
    url="https://example.invalid/1001",
)


class FakeSource:
    name = "fake"

    def __init__(
        self, listings: list[ServerListing] | None = None, error: Exception | None = None
    ) -> None:
        self._listings = listings or []
        self._error = error

    async def get_available_servers(self) -> list[ServerListing]:
        if self._error is not None:
            raise self._error
        return self._listings


class FakeNotifier:
    def __init__(self) -> None:
        self.matches: list[tuple[int, str]] = []
        self.admin_alerts: list[str] = []

    async def notify_match(self, watch, listing) -> None:
        self.matches.append((watch.id, listing.product_id))

    async def notify_admin(self, _admin_chat_id: int, text: str) -> None:
        self.admin_alerts.append(text)


@pytest.fixture
async def db(tmp_path):
    database = await Database.connect(str(tmp_path / "watches.db"))
    yield database
    await database.close()


async def test_run_records_successful_poll(db):
    notifier = FakeNotifier()
    cycle = PollCycle(db, FakeSource([LISTING]), notifier, renotify_hours=6, admin_chat_id=1)

    await cycle.run()

    last_poll = await db.last_poll()
    assert (last_poll.success, last_poll.listings) == (True, 1)


async def test_run_notifies_a_matching_watch(db):
    await db.create_watch(
        chat_id=42,
        label=None,
        cpu_pattern="E3-1230",
        ram_min_gb=None,
        storage_pattern=None,
        location=None,
        price_max_usd=None,
    )
    notifier = FakeNotifier()
    cycle = PollCycle(db, FakeSource([LISTING]), notifier, renotify_hours=6, admin_chat_id=1)

    await cycle.run()

    assert notifier.matches == [(1, "1001")]


async def test_run_does_not_notify_a_non_matching_watch(db):
    await db.create_watch(
        chat_id=42,
        label=None,
        cpu_pattern="E5-2680",
        ram_min_gb=None,
        storage_pattern=None,
        location=None,
        price_max_usd=None,
    )
    notifier = FakeNotifier()
    cycle = PollCycle(db, FakeSource([LISTING]), notifier, renotify_hours=6, admin_chat_id=1)

    await cycle.run()

    assert notifier.matches == []


async def test_two_consecutive_polls_with_the_same_stock_notify_once(db):
    await db.create_watch(
        chat_id=42,
        label=None,
        cpu_pattern="E3-1230",
        ram_min_gb=None,
        storage_pattern=None,
        location=None,
        price_max_usd=None,
    )
    notifier = FakeNotifier()
    cycle = PollCycle(db, FakeSource([LISTING]), notifier, renotify_hours=6, admin_chat_id=1)

    await cycle.run()
    await cycle.run()

    assert notifier.matches == [(1, "1001")]


async def test_run_records_a_failed_poll_on_inventory_unavailable(db):
    notifier = FakeNotifier()
    cycle = PollCycle(
        db,
        FakeSource(error=InventoryUnavailableError("boom")),
        notifier,
        renotify_hours=6,
        admin_chat_id=1,
    )

    await cycle.run()

    last_poll = await db.last_poll()
    assert (last_poll.success, last_poll.error) == (False, "boom")


async def test_admin_is_not_alerted_before_the_failure_threshold(db):
    notifier = FakeNotifier()
    cycle = PollCycle(
        db,
        FakeSource(error=InventoryUnavailableError("boom")),
        notifier,
        renotify_hours=6,
        admin_chat_id=1,
    )

    for _ in range(CONSECUTIVE_FAILURE_ALERT_THRESHOLD - 1):
        await cycle.run()

    assert notifier.admin_alerts == []


async def test_admin_is_alerted_after_the_failure_threshold(db):
    notifier = FakeNotifier()
    cycle = PollCycle(
        db,
        FakeSource(error=InventoryUnavailableError("boom")),
        notifier,
        renotify_hours=6,
        admin_chat_id=1,
    )

    for _ in range(CONSECUTIVE_FAILURE_ALERT_THRESHOLD):
        await cycle.run()

    assert any("boom" in alert for alert in notifier.admin_alerts)


async def test_admin_is_alerted_when_polling_has_been_stalled_too_long(db):
    await db.record_poll(source="fake", success=True, listings=1, error=None)
    await db._connection.execute(
        "UPDATE poll_log SET ts = datetime('now', ?)",
        (f"-{STALLED_POLL_ALERT_MINUTES + 1} minutes",),
    )
    await db._connection.commit()
    notifier = FakeNotifier()
    cycle = PollCycle(
        db,
        FakeSource(error=InventoryUnavailableError("still down")),
        notifier,
        renotify_hours=6,
        admin_chat_id=1,
    )

    await cycle.run()

    assert any("sin poder consultar" in alert for alert in notifier.admin_alerts)
