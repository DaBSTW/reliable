"""Tests for src.bot.handlers — fake Update/Context, no real Telegram API calls."""

from decimal import Decimal

import pytest

from src.bot import messages
from src.bot.auth import Auth
from src.bot.handlers import Handlers
from src.db import Database
from src.sources.base import ServerListing


class FakeChat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []
        self.reply_markups: list[object] = []

    async def reply_text(self, text: str, reply_markup: object = None) -> None:
        self.replies.append(text)
        self.reply_markups.append(reply_markup)


class FakeCallbackQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.answered = False
        self.edits: list[str] = []
        self.edit_markups: list[object] = []

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup: object = None) -> None:
        self.edits.append(text)
        self.edit_markups.append(reply_markup)


class FakeUpdate:
    def __init__(self, chat_id: int, callback_data: str | None = None) -> None:
        self.effective_chat = FakeChat(chat_id)
        self.message = FakeMessage()
        self.callback_query = (
            FakeCallbackQuery(callback_data) if callback_data is not None else None
        )


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


async def test_start_shows_a_main_menu_keyboard(wired):
    update = FakeUpdate(111)

    await wired.start(update, FakeContext())

    assert update.message.reply_markups[0] is not None


async def test_list_watches_attaches_a_remove_button_per_watch(wired):
    await wired.watch(FakeUpdate(111), FakeContext(["loc=NYC"]))
    update = FakeUpdate(111)

    await wired.list_watches(update, FakeContext())

    markup = update.message.reply_markups[0]
    assert markup.inline_keyboard[0][0].callback_data == "remove:1"


async def test_callback_menu_list_edits_message_with_watch_list(wired):
    await wired.watch(FakeUpdate(111), FakeContext(["loc=NYC"]))
    update = FakeUpdate(111, callback_data="menu:list")

    await wired.on_callback_query(update, FakeContext())

    assert update.callback_query.answered is True
    assert "#1" in update.callback_query.edits[0]


async def test_callback_menu_stock_edits_message_with_stock(wired):
    update = FakeUpdate(111, callback_data="menu:stock")

    await wired.on_callback_query(update, FakeContext())

    assert "Intel Xeon E3-1230v2" in update.callback_query.edits[0]


async def test_callback_menu_status_edits_message_with_status(wired):
    update = FakeUpdate(111, callback_data="menu:status")

    await wired.on_callback_query(update, FakeContext())

    assert "Estado del sistema" in update.callback_query.edits[0]


async def test_callback_remove_deactivates_the_watch_and_refreshes_the_list(wired):
    await wired.watch(FakeUpdate(111), FakeContext(["loc=NYC"]))
    update = FakeUpdate(111, callback_data="remove:1")

    await wired.on_callback_query(update, FakeContext())

    assert update.callback_query.edits[0] == messages.WATCH_LIST_EMPTY


async def test_callback_rejects_unauthorized_user(wired):
    update = FakeUpdate(999, callback_data="menu:list")

    await wired.on_callback_query(update, FakeContext())

    assert update.callback_query.edits == [messages.NOT_AUTHORIZED]
