"""Sends Telegram notifications for watch matches and admin alerts."""

import logging

from telegram import Bot
from telegram.error import TelegramError

from src.bot import messages
from src.db import Watch
from src.sources.base import ServerListing

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def notify_match(self, watch: Watch, listing: ServerListing) -> None:
        await self._send(watch.chat_id, messages.format_match_notification(watch, listing))

    async def notify_admin(self, admin_chat_id: int, text: str) -> None:
        await self._send(admin_chat_id, text)

    async def _send(self, chat_id: int, text: str) -> None:
        try:
            await self._bot.send_message(chat_id=chat_id, text=text)
        except TelegramError as exc:
            logger.warning(
                "notification send failed",
                extra={"chat_id": _mask_chat_id(chat_id), "error": str(exc)},
            )


def _mask_chat_id(chat_id: int) -> str:
    raw = str(chat_id)
    return raw[:3] + "..." if len(raw) > 3 else raw
