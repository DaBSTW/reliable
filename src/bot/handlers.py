"""Telegram command handlers. Validate input, delegate to db/auth, format output."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.bot import access_requests, messages, watch_wizard
from src.bot.auth import Auth
from src.bot.watch_filters import parse_watch_filters
from src.db import Database, Watch
from src.errors import WatchFilterError
from src.sources.base import InventorySource

logger = logging.getLogger(__name__)

# Internal callback_data protocol for inline buttons — never shown to the user.
_CALLBACK_MENU_MAIN = "menu:main"
_CALLBACK_MENU_LIST = "menu:list"
_CALLBACK_MENU_STOCK = "menu:stock"
_CALLBACK_MENU_STATUS = "menu:status"
_CALLBACK_REMOVE_PREFIX = "remove:"


class Handlers:
    """Telegram command handlers, wired explicitly with their dependencies."""

    def __init__(
        self,
        db: Database,
        auth: Auth,
        source: InventorySource,
        next_poll_in_seconds: Callable[[], int | None],
        admin_chat_id: int,
    ) -> None:
        self._db = db
        self._auth = auth
        self._source = source
        self._next_poll_in_seconds = next_poll_in_seconds
        self._started_at = datetime.now(UTC)
        self._wizard = watch_wizard.WizardController(
            db, source, watch_wizard.WizardStore(), _main_menu_keyboard
        )
        self._access_requests = access_requests.AccessRequests(auth, admin_chat_id)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = _chat_id(update)
        if not await self._auth.is_authorized(chat_id):
            await _reply(update, messages.ACCESS_REQUESTED)
            await self._access_requests.notify_admin(update, context, chat_id)
            return
        await _reply(update, messages.WELCOME, _main_menu_keyboard())

    async def watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = _chat_id(update)
        if not await self._require_authorized(update, chat_id):
            return
        try:
            filters_ = parse_watch_filters(context.args or [])
        except WatchFilterError as exc:
            await _reply(update, messages.WATCH_PARSE_ERROR.format(error=str(exc)))
            return
        watch = await self._db.create_watch(
            chat_id=chat_id,
            label=filters_.label,
            cpu_pattern=filters_.cpu_pattern,
            ram_min_gb=filters_.ram_min_gb,
            storage_pattern=filters_.storage_pattern,
            location=filters_.location,
            price_max_usd=filters_.price_max_usd,
        )
        summary = messages.format_watch_summary(watch)
        await _reply(
            update,
            messages.WATCH_CREATED.format(watch_id=watch.id, summary=summary),
            _main_menu_keyboard(),
        )

    async def list_watches(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = _chat_id(update)
        if not await self._require_authorized(update, chat_id):
            return
        text, markup = await self._build_watch_list(chat_id)
        await _reply(update, text, markup)

    async def remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = _chat_id(update)
        if not await self._require_authorized(update, chat_id):
            return
        args = context.args or []
        if len(args) != 1 or not args[0].lstrip("-").isdigit():
            await _reply(update, messages.REMOVE_USAGE)
            return
        watch_id = int(args[0])
        removed = await self._db.deactivate_watch(watch_id, chat_id)
        if not removed:
            await _reply(update, messages.WATCH_NOT_FOUND)
            return
        await _reply(update, messages.WATCH_REMOVED.format(watch_id=watch_id))

    async def stock(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update, _chat_id(update)):
            return
        await _reply(update, await self._build_stock_text(), _main_menu_keyboard())

    async def status(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update, _chat_id(update)):
            return
        await _reply(update, await self._build_status_text(), _main_menu_keyboard())

    async def approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = _chat_id(update)
        if not await self._auth.is_admin(chat_id):
            await _reply(update, messages.APPROVE_ONLY_ADMIN)
            return
        args = context.args or []
        if len(args) != 1:
            await _reply(update, messages.APPROVE_USAGE)
            return
        try:
            target_chat_id = int(args[0])
        except ValueError:
            await _reply(update, messages.APPROVE_INVALID_CHAT_ID)
            return
        await self._auth.approve(target_chat_id, username=None)
        await _reply(update, messages.APPROVE_SUCCESS.format(chat_id=target_chat_id))

    async def on_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        assert query is not None
        await query.answer()
        chat_id = _chat_id(update)
        data = query.data or ""
        if not await self._auth.is_authorized(chat_id):
            await query.edit_message_text(messages.NOT_AUTHORIZED)
            return
        if access_requests.is_approve_callback(data):
            await self._access_requests.handle_callback(query, context, chat_id, data)
        elif watch_wizard.is_wizard_callback(data):
            await self._wizard.handle_callback(query, chat_id)
        elif data == _CALLBACK_MENU_MAIN:
            await query.edit_message_text(messages.WELCOME, reply_markup=_main_menu_keyboard())
        elif data == _CALLBACK_MENU_LIST or data.startswith(_CALLBACK_REMOVE_PREFIX):
            if data.startswith(_CALLBACK_REMOVE_PREFIX):
                await self._remove_via_button(data, chat_id)
            text, markup = await self._build_watch_list(chat_id)
            await query.edit_message_text(text, reply_markup=markup)
        elif data == _CALLBACK_MENU_STOCK:
            await query.edit_message_text(
                await self._build_stock_text(), reply_markup=_main_menu_keyboard()
            )
        elif data == _CALLBACK_MENU_STATUS:
            await query.edit_message_text(
                await self._build_status_text(), reply_markup=_main_menu_keyboard()
            )
        else:
            logger.warning("unknown callback_data", extra={"data": data})

    async def on_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = _chat_id(update)
        if not await self._auth.is_authorized(chat_id):
            return
        if await self._wizard.handle_text(update, context):
            return
        await _reply(update, messages.TEXT_HINT, _main_menu_keyboard())

    async def _remove_via_button(self, data: str, chat_id: int) -> None:
        raw_id = data.removeprefix(_CALLBACK_REMOVE_PREFIX)
        if not raw_id.isdigit():
            logger.warning("malformed remove callback_data", extra={"data": data})
            return
        await self._db.deactivate_watch(int(raw_id), chat_id)

    async def _build_watch_list(self, chat_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
        watches = await self._db.list_watches_for_chat(chat_id)
        if not watches:
            return messages.WATCH_LIST_EMPTY, _main_menu_keyboard()
        lines = [messages.WATCH_LIST_HEADER]
        lines.extend(
            messages.WATCH_LIST_ITEM.format(
                watch_id=watch.id, summary=messages.format_watch_summary(watch)
            )
            for watch in watches
        )
        return "\n".join(lines), _watch_list_keyboard(watches)

    async def _build_stock_text(self) -> str:
        listings = await self._source.get_available_servers()
        in_stock = [listing for listing in listings if listing.in_stock]
        if not in_stock:
            return messages.STOCK_EMPTY
        lines = [messages.STOCK_HEADER]
        lines.extend(messages.format_stock_item(listing) for listing in in_stock)
        return "\n\n".join(lines)

    async def _build_status_text(self) -> str:
        poll_line = await self._format_poll_line()
        active_watches = len(await self._db.list_active_watches())
        uptime = _format_timedelta(datetime.now(UTC) - self._started_at)
        text = messages.STATUS_TEMPLATE.format(
            poll_line=poll_line, active_watches=active_watches, uptime=uptime
        )
        next_in = self._next_poll_in_seconds()
        if next_in is not None:
            text += messages.STATUS_NEXT_POLL.format(minutes=max(next_in // 60, 0))
        return text

    async def _require_authorized(self, update: Update, chat_id: int) -> bool:
        if await self._auth.is_authorized(chat_id):
            return True
        await _reply(update, messages.NOT_AUTHORIZED)
        return False

    async def _format_poll_line(self) -> str:
        last_poll = await self._db.last_poll()
        if last_poll is None:
            return messages.STATUS_NO_POLL_YET
        ago = _format_timedelta(datetime.now(UTC) - _parse_timestamp(last_poll.ts))
        if last_poll.success:
            return messages.STATUS_POLL_OK.format(
                ago=ago, source=last_poll.source, listings=last_poll.listings
            )
        return messages.STATUS_POLL_FAILED.format(
            ago=ago, source=last_poll.source, error=last_poll.error or "?"
        )


def _chat_id(update: Update) -> int:
    assert update.effective_chat is not None
    return update.effective_chat.id


async def _reply(
    update: Update, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    assert update.message is not None
    await update.message.reply_text(text, reply_markup=reply_markup)


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    messages.BUTTON_NEW_WATCH, callback_data=watch_wizard.CALLBACK_NEW
                )
            ],
            [InlineKeyboardButton(messages.BUTTON_LIST, callback_data=_CALLBACK_MENU_LIST)],
            [InlineKeyboardButton(messages.BUTTON_STOCK, callback_data=_CALLBACK_MENU_STOCK)],
            [InlineKeyboardButton(messages.BUTTON_STATUS, callback_data=_CALLBACK_MENU_STATUS)],
        ]
    )


def _watch_list_keyboard(watches: list[Watch]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                messages.BUTTON_REMOVE.format(watch_id=watch.id),
                callback_data=f"{_CALLBACK_REMOVE_PREFIX}{watch.id}",
            )
        ]
        for watch in watches
    ]
    rows.append(
        [InlineKeyboardButton(messages.BUTTON_MAIN_MENU, callback_data=_CALLBACK_MENU_MAIN)]
    )
    return InlineKeyboardMarkup(rows)


def _parse_timestamp(raw: str) -> datetime:
    return datetime.fromisoformat(raw).replace(tzinfo=UTC)


def _format_timedelta(delta: timedelta) -> str:
    total_minutes = int(delta.total_seconds() // 60)
    days, rem_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(rem_minutes, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}min"
    return f"{minutes}min" if minutes else "menos de 1min"
