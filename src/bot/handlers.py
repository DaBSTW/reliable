"""Telegram command handlers. Validate input, delegate to db/auth, format output."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from telegram import Update
from telegram.ext import ContextTypes

from src.bot import messages
from src.bot.auth import Auth
from src.db import Database
from src.errors import WatchFilterError
from src.sources.base import InventorySource

logger = logging.getLogger(__name__)

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


class Handlers:
    """Telegram command handlers, wired explicitly with their dependencies."""

    def __init__(
        self,
        db: Database,
        auth: Auth,
        source: InventorySource,
        next_poll_in_seconds: Callable[[], int | None],
    ) -> None:
        self._db = db
        self._auth = auth
        self._source = source
        self._next_poll_in_seconds = next_poll_in_seconds
        self._started_at = datetime.now(UTC)

    async def start(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update, _chat_id(update)):
            return
        await _reply(update, messages.WELCOME)

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
        await _reply(update, messages.WATCH_CREATED.format(watch_id=watch.id, summary=summary))

    async def list_watches(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = _chat_id(update)
        if not await self._require_authorized(update, chat_id):
            return
        watches = await self._db.list_watches_for_chat(chat_id)
        if not watches:
            await _reply(update, messages.WATCH_LIST_EMPTY)
            return
        lines = [messages.WATCH_LIST_HEADER]
        lines.extend(
            messages.WATCH_LIST_ITEM.format(
                watch_id=watch.id, summary=messages.format_watch_summary(watch)
            )
            for watch in watches
        )
        await _reply(update, "\n".join(lines))

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
        listings = await self._source.get_available_servers()
        in_stock = [listing for listing in listings if listing.in_stock]
        if not in_stock:
            await _reply(update, messages.STOCK_EMPTY)
            return
        lines = [messages.STOCK_HEADER]
        lines.extend(messages.format_stock_item(listing) for listing in in_stock)
        await _reply(update, "\n\n".join(lines))

    async def status(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update, _chat_id(update)):
            return
        poll_line = await self._format_poll_line()
        active_watches = len(await self._db.list_active_watches())
        uptime = _format_timedelta(datetime.now(UTC) - self._started_at)
        text = messages.STATUS_TEMPLATE.format(
            poll_line=poll_line, active_watches=active_watches, uptime=uptime
        )
        next_in = self._next_poll_in_seconds()
        if next_in is not None:
            text += messages.STATUS_NEXT_POLL.format(minutes=max(next_in // 60, 0))
        await _reply(update, text)

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


async def _reply(update: Update, text: str) -> None:
    assert update.message is not None
    await update.message.reply_text(text)


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
