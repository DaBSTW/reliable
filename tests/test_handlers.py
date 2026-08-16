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


class FakeUser:
    def __init__(self, username: str | None) -> None:
        self.username = username


class FakeMessage:
    def __init__(self, message_id: int = 1) -> None:
        self.message_id = message_id
        self.replies: list[str] = []
        self.reply_markups: list[object] = []

    async def reply_text(self, text: str, reply_markup: object = None) -> None:
        self.replies.append(text)
        self.reply_markups.append(reply_markup)


class FakeCallbackQuery:
    def __init__(self, data: str, message: FakeMessage) -> None:
        self.data = data
        self.message = message
        self.answered = False
        self.edits: list[str] = []
        self.edit_markups: list[object] = []

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup: object = None) -> None:
        self.edits.append(text)
        self.edit_markups.append(reply_markup)


class FakeUpdate:
    def __init__(
        self,
        chat_id: int,
        callback_data: str | None = None,
        text: str | None = None,
        username: str | None = None,
    ) -> None:
        self.effective_chat = FakeChat(chat_id)
        self.effective_user = FakeUser(username)
        self.message = FakeMessage()
        self.message.text = text
        self.callback_query = (
            FakeCallbackQuery(callback_data, self.message) if callback_data is not None else None
        )


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []
        self.sent_markups: list[object] = []
        self.edited_messages: list[tuple[int, int, str]] = []
        self.edited_markups: list[object] = []

    async def send_message(self, chat_id: int, text: str, reply_markup: object = None) -> None:
        self.sent_messages.append((chat_id, text))
        self.sent_markups.append(reply_markup)

    async def edit_message_text(
        self, text: str, chat_id: int, message_id: int, reply_markup: object = None
    ) -> None:
        self.edited_messages.append((chat_id, message_id, text))
        self.edited_markups.append(reply_markup)


class FakeContext:
    def __init__(self, args: list[str] | None = None) -> None:
        self.args = args
        self.bot = FakeBot()


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
    try:
        auth = Auth(db)
        await auth.approve(111, username="tester")
        handlers = Handlers(
            db,
            auth,
            FakeSource([LISTING]),
            next_poll_in_seconds=lambda: 120,
            admin_chat_id=999999,
        )
        yield handlers
    finally:
        await db.close()


async def test_start_replies_welcome_for_authorized_user(wired):
    update = FakeUpdate(111)

    await wired.start(update, FakeContext())

    assert update.message.replies == [messages.WELCOME]


async def test_start_rejects_unauthorized_user(wired):
    update = FakeUpdate(999)

    await wired.start(update, FakeContext())

    assert update.message.replies == [messages.ACCESS_REQUESTED]


async def test_start_notifies_the_admin_with_an_approve_button(wired):
    update = FakeUpdate(999, username="newbie")
    context = FakeContext()

    await wired.start(update, context)

    admin_chat_id, text = context.bot.sent_messages[0]
    assert admin_chat_id == 999999
    assert "999" in text
    assert "@newbie" in text


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
    try:
        auth = Auth(db)
        await auth.bootstrap_admin(111)
        handlers = Handlers(
            db, auth, FakeSource([]), next_poll_in_seconds=lambda: None, admin_chat_id=111
        )
        update = FakeUpdate(111)

        await handlers.approve(update, FakeContext(["333"]))

        assert await auth.is_authorized(333) is True
    finally:
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


async def test_approve_callback_authorizes_and_notifies_the_new_user():
    db = await Database.connect(":memory:")
    try:
        auth = Auth(db)
        await auth.bootstrap_admin(111)
        handlers = Handlers(
            db, auth, FakeSource([]), next_poll_in_seconds=lambda: None, admin_chat_id=111
        )
        update = FakeUpdate(111, callback_data="approve:333")
        context = FakeContext()

        await handlers.on_callback_query(update, context)

        assert await auth.is_authorized(333) is True
        assert update.callback_query.edits[0] == messages.APPROVE_DONE_FOR_ADMIN.format(chat_id=333)
        assert context.bot.sent_messages == [(333, messages.APPROVE_NOTIFY_USER)]
    finally:
        await db.close()


async def test_approve_callback_rejects_non_admin(wired):
    update = FakeUpdate(111, callback_data="approve:333")

    await wired.on_callback_query(update, FakeContext())

    assert update.callback_query.edits == [messages.APPROVE_ONLY_ADMIN]


async def test_wizard_new_shows_the_filter_menu(wired):
    update = FakeUpdate(111, callback_data="wiz:new")

    await wired.on_callback_query(update, FakeContext())

    assert "sin filtros" in update.callback_query.edits[0]


async def test_wizard_pick_ram_shows_presets(wired):
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:new"), FakeContext())
    update = FakeUpdate(111, callback_data="wiz:pick:ram")

    await wired.on_callback_query(update, FakeContext())

    buttons = [b.text for row in update.callback_query.edit_markups[0].inline_keyboard for b in row]
    assert "32" in buttons


async def test_wizard_picking_a_ram_preset_updates_the_summary(wired):
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:new"), FakeContext())
    update = FakeUpdate(111, callback_data="wiz:val:ram:32")

    await wired.on_callback_query(update, FakeContext())

    assert "RAM: ≥32GB" in update.callback_query.edits[-1]


async def test_wizard_back_returns_to_the_filter_menu(wired):
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:new"), FakeContext())
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:pick:ram"), FakeContext())
    update = FakeUpdate(111, callback_data="wiz:back")

    await wired.on_callback_query(update, FakeContext())

    assert "sin filtros" in update.callback_query.edits[-1]


async def test_wizard_cancel_clears_state_and_shows_main_menu(wired):
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:new"), FakeContext())
    update = FakeUpdate(111, callback_data="wiz:cancel")

    await wired.on_callback_query(update, FakeContext())

    assert update.callback_query.edits[-1] == messages.WIZARD_CANCELLED


async def test_wizard_callback_without_active_state_reports_expired(wired):
    update = FakeUpdate(111, callback_data="wiz:val:ram:32")

    await wired.on_callback_query(update, FakeContext())

    assert update.callback_query.edits == [messages.WIZARD_EXPIRED]


async def test_wizard_cpu_pick_goes_straight_to_a_text_prompt(wired):
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:new"), FakeContext())
    update = FakeUpdate(111, callback_data="wiz:pick:cpu")

    await wired.on_callback_query(update, FakeContext())

    assert update.callback_query.edits[-1] == messages.WIZARD_ASK_CPU_TEXT


async def test_wizard_text_reply_fills_in_the_cpu_filter(wired):
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:new"), FakeContext())
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:pick:cpu"), FakeContext())
    update = FakeUpdate(111, text="E3-1230")
    context = FakeContext()

    await wired.on_text_message(update, context)

    assert context.bot.edited_messages[0][2].find("CPU: E3-1230") != -1


async def test_text_message_without_an_active_wizard_shows_a_hint(wired):
    update = FakeUpdate(111, text="hello")

    await wired.on_text_message(update, FakeContext())

    assert update.message.replies == [messages.TEXT_HINT]


async def test_wizard_remove_button_clears_a_filter(wired):
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:new"), FakeContext())
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:val:ram:32"), FakeContext())
    update = FakeUpdate(111, callback_data="wiz:rm:ram")

    await wired.on_callback_query(update, FakeContext())

    assert "sin filtros" in update.callback_query.edits[-1]


async def test_wizard_create_persists_the_watch_and_clears_state(wired):
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:new"), FakeContext())
    await wired.on_callback_query(FakeUpdate(111, callback_data="wiz:val:ram:64"), FakeContext())
    update = FakeUpdate(111, callback_data="wiz:create")

    await wired.on_callback_query(update, FakeContext())

    watches = await wired._db.list_watches_for_chat(111)
    assert watches[0].ram_min_gb == 64
    assert "Watch #" in update.callback_query.edits[-1]
