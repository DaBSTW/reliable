"""Tests for src.bot.handlers — fake Update/Context, no real Telegram API calls."""

from decimal import Decimal

import pytest

from src.bot import messages
from src.bot.auth import Auth
from src.bot.handlers import Handlers, WatchFilterError, parse_watch_filters
from src.db import Database
from src.sources.base import ServerListing


class FakeChat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, chat_id: int) -> None:
        self.effective_chat = FakeChat(chat_id)
        self.message = FakeMessage()


class FakeContext:
    def __init__(self, args: list[str] | None = None) -> None:
        self.args = args


class FakeSource:
    def __init__(self, listings: list[ServerListing]) -> None:
        self._listings = listings

    async def get_available_servers(self) -> list[ServerListing]:
        return self._listings


LISTING = ServerListing(
    product_id="1",
    description="E3-1230, 32GB",
    cpu="Intel Xeon E3-1230v2",
    ram_gb=32,
    storage="2x480GB SSD",
    location="NYC",
    price_usd=Decimal("69.00"),
    in_stock=True,
    url="https://example.invalid/1",
)


@pytest.fixture
async def wired(tmp_path):
    db = await Database.connect(str(tmp_path / "watches.db"))
    auth = Auth(db)
    await auth.approve(111, username="tester")
    handlers = Handlers(db, auth, FakeSource([LISTING]), next_poll_in_seconds=lambda: 120)
    yield handlers
    await db.close()


async def test_start_replies_welcome_for_authorized_user(wired):
    update = FakeUpdate(111)

    await wired.start(update, FakeContext())

    assert update.message.replies == [messages.WELCOME]


async def test_start_rejects_unauthorized_user(wired):
    update = FakeUpdate(999)

    await wired.start(update, FakeContext())

    assert update.message.replies == [messages.NOT_AUTHORIZED]


async def test_watch_creates_a_watch_and_confirms_it(wired):
    update = FakeUpdate(111)

    await wired.watch(update, FakeContext(["cpu=E3-1230", "ram=32", "precio=80"]))

    assert "Watch #1" in update.message.replies[0]


async def test_watch_with_unknown_filter_replies_with_parse_error(wired):
    update = FakeUpdate(111)

    await wired.watch(update, FakeContext(["potato=yes"]))

    assert "No entendí ese filtro" in update.message.replies[0]


async def test_list_watches_is_empty_before_any_watch_is_created(wired):
    update = FakeUpdate(111)

    await wired.list_watches(update, FakeContext())

    assert update.message.replies == [messages.WATCH_LIST_EMPTY]


async def test_list_watches_shows_a_created_watch(wired):
    await wired.watch(FakeUpdate(111), FakeContext(["loc=NYC"]))
    update = FakeUpdate(111)

    await wired.list_watches(update, FakeContext())

    assert "#1" in update.message.replies[0]


async def test_remove_without_a_valid_id_replies_with_usage(wired):
    update = FakeUpdate(111)

    await wired.remove(update, FakeContext(["not-a-number"]))

    assert update.message.replies == [messages.REMOVE_USAGE]


async def test_remove_deactivates_an_owned_watch(wired):
    await wired.watch(FakeUpdate(111), FakeContext(["loc=NYC"]))
    update = FakeUpdate(111)

    await wired.remove(update, FakeContext(["1"]))

    assert update.message.replies == [messages.WATCH_REMOVED.format(watch_id=1)]


async def test_remove_rejects_a_watch_owned_by_someone_else(wired):
    await wired.watch(FakeUpdate(111), FakeContext(["loc=NYC"]))
    other_chat_update = FakeUpdate(222)
    await wired._auth.approve(222, username=None)

    await wired.remove(other_chat_update, FakeContext(["1"]))

    assert other_chat_update.message.replies == [messages.WATCH_NOT_FOUND]


async def test_stock_lists_available_servers(wired):
    update = FakeUpdate(111)

    await wired.stock(update, FakeContext())

    assert "Intel Xeon E3-1230v2" in update.message.replies[0]


async def test_status_reports_watch_count_and_next_poll(wired):
    await wired.watch(FakeUpdate(111), FakeContext([]))
    update = FakeUpdate(111)

    await wired.status(update, FakeContext())

    text = update.message.replies[0]
    assert "Watches activos: 1" in text
    assert "Próximo poll: en 2 min" in text


async def test_approve_rejects_non_admin(wired):
    update = FakeUpdate(111)

    await wired.approve(update, FakeContext(["333"]))

    assert update.message.replies == [messages.APPROVE_ONLY_ADMIN]


async def test_approve_authorizes_target_chat_id_for_admin():
    db = await Database.connect(":memory:")
    auth = Auth(db)
    await auth.bootstrap_admin(111)
    handlers = Handlers(db, auth, FakeSource([]), next_poll_in_seconds=lambda: None)
    update = FakeUpdate(111)

    await handlers.approve(update, FakeContext(["333"]))

    assert await auth.is_authorized(333) is True
    await db.close()


def test_parse_watch_filters_accepts_all_known_keys():
    filters_ = parse_watch_filters(
        ["cpu=E5-2680", "ram=64", "disco=NVMe", "loc=LA", "precio=120", "nombre=proyecto-x"]
    )

    assert filters_.cpu_pattern == "E5-2680"
    assert filters_.ram_min_gb == 64
    assert filters_.price_max_usd == Decimal("120")


def test_parse_watch_filters_rejects_unknown_key():
    with pytest.raises(WatchFilterError):
        parse_watch_filters(["potato=yes"])


def test_parse_watch_filters_rejects_non_integer_ram():
    with pytest.raises(WatchFilterError):
        parse_watch_filters(["ram=lots"])


def test_parse_watch_filters_rejects_non_numeric_price():
    with pytest.raises(WatchFilterError):
        parse_watch_filters(["precio=cheap"])


def test_parse_watch_filters_with_no_args_matches_anything():
    filters_ = parse_watch_filters([])

    assert filters_ == parse_watch_filters([])
