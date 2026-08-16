"""Button-driven onboarding: notify the admin when an unauthorized user hits /start."""

import logging

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from src.bot import messages
from src.bot.auth import Auth

logger = logging.getLogger(__name__)

_CALLBACK_PREFIX = "approve:"


def is_approve_callback(data: str) -> bool:
    return data.startswith(_CALLBACK_PREFIX)


class AccessRequests:
    """Notifies the admin of new /start attempts and handles their approve button."""

    def __init__(self, auth: Auth, admin_chat_id: int) -> None:
        self._auth = auth
        self._admin_chat_id = admin_chat_id

    async def notify_admin(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int
    ) -> None:
        username = update.effective_user.username if update.effective_user else None
        text = messages.APPROVE_REQUEST_FOR_ADMIN.format(
            chat_id=chat_id, username=f" (@{username})" if username else ""
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        messages.BUTTON_APPROVE, callback_data=f"{_CALLBACK_PREFIX}{chat_id}"
                    )
                ]
            ]
        )
        try:
            await context.bot.send_message(self._admin_chat_id, text, reply_markup=keyboard)
        except TelegramError as exc:
            logger.warning("admin access-request notification failed", extra={"error": str(exc)})

    async def handle_callback(
        self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, chat_id: int, data: str
    ) -> None:
        if not await self._auth.is_admin(chat_id):
            await query.edit_message_text(messages.APPROVE_ONLY_ADMIN)
            return
        raw_id = data.removeprefix(_CALLBACK_PREFIX)
        if not raw_id.lstrip("-").isdigit():
            logger.warning("malformed approve callback_data", extra={"data": data})
            return
        target_chat_id = int(raw_id)
        await self._auth.approve(target_chat_id, username=None)
        await query.edit_message_text(
            messages.APPROVE_DONE_FOR_ADMIN.format(chat_id=target_chat_id)
        )
        try:
            await context.bot.send_message(target_chat_id, messages.APPROVE_NOTIFY_USER)
        except TelegramError as exc:
            logger.warning("user approval notification failed", extra={"error": str(exc)})
