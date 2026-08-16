"""Button-driven state machine for building a /watch step by step, with no typing required."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.bot import messages
from src.bot.watch_filters import parse_watch_filters
from src.db import Database
from src.errors import InventoryUnavailableError, WatchFilterError
from src.sources.base import InventorySource

logger = logging.getLogger(__name__)

RAM_PRESETS_GB = (16, 32, 64, 128, 256)
PRICE_PRESETS_USD = (50, 100, 150, 300, 500)
STORAGE_PRESETS = ("SSD", "NVMe", "HDD")

# Filter keys mirror the /watch syntax (README.md, SPECS.md §8) and this module's own
# callback_data namespace. Order controls how filter buttons are laid out.
FILTER_KEYS = ("cpu", "ram", "disco", "loc", "precio", "nombre")
FILTER_LABELS = {
    "cpu": messages.WIZARD_FILTER_CPU,
    "ram": messages.WIZARD_FILTER_RAM,
    "disco": messages.WIZARD_FILTER_STORAGE,
    "loc": messages.WIZARD_FILTER_LOCATION,
    "precio": messages.WIZARD_FILTER_PRICE,
    "nombre": messages.WIZARD_FILTER_LABEL,
}
TEXT_ENTRY_KEYS = ("cpu", "nombre")

CALLBACK_NEW = "wiz:new"
CALLBACK_CREATE = "wiz:create"
CALLBACK_CANCEL = "wiz:cancel"
CALLBACK_BACK = "wiz:back"
_PICK_PREFIX = "wiz:pick:"
_TEXT_PREFIX = "wiz:text:"
_VALUE_PREFIX = "wiz:val:"
_REMOVE_PREFIX = "wiz:rm:"
_DATA_PREFIXES = (_PICK_PREFIX, _TEXT_PREFIX, _VALUE_PREFIX, _REMOVE_PREFIX)


@dataclass
class WizardState:
    """One chat's in-progress watch. `message_id` lets a later text reply edit it back."""

    chat_id: int
    message_id: int
    filters: dict[str, str] = field(default_factory=dict)
    awaiting_text_for: str | None = None


class WizardStore:
    """Per-chat wizard state, held in memory for the life of the process."""

    def __init__(self) -> None:
        self._states: dict[int, WizardState] = {}

    def start(self, chat_id: int, message_id: int) -> WizardState:
        state = WizardState(chat_id=chat_id, message_id=message_id)
        self._states[chat_id] = state
        return state

    def get(self, chat_id: int) -> WizardState | None:
        return self._states.get(chat_id)

    def clear(self, chat_id: int) -> None:
        self._states.pop(chat_id, None)


def is_wizard_callback(data: str) -> bool:
    return (
        data == CALLBACK_NEW
        or data in (CALLBACK_CREATE, CALLBACK_CANCEL, CALLBACK_BACK)
        or data.startswith(_DATA_PREFIXES)
    )


def _pick(key: str) -> str:
    return f"{_PICK_PREFIX}{key}"


def _text(key: str) -> str:
    return f"{_TEXT_PREFIX}{key}"


def _value(key: str, value: str) -> str:
    return f"{_VALUE_PREFIX}{key}:{value}"


def _remove(key: str) -> str:
    return f"{_REMOVE_PREFIX}{key}"


def _menu_content(state: WizardState) -> tuple[str, InlineKeyboardMarkup]:
    summary = messages.format_wizard_filters(state.filters)
    text = f"{messages.WIZARD_INTRO}\n\n{messages.WIZARD_SUMMARY.format(summary=summary)}"
    return text, _menu_keyboard(state)


def _menu_keyboard(state: WizardState) -> InlineKeyboardMarkup:
    rows = []
    for key in FILTER_KEYS:
        label = FILTER_LABELS[key]
        if key in state.filters:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"{label}: {state.filters[key]}", callback_data=_pick(key)
                    ),
                    InlineKeyboardButton("🗑️", callback_data=_remove(key)),
                ]
            )
        else:
            rows.append([InlineKeyboardButton(label, callback_data=_pick(key))])
    rows.append([InlineKeyboardButton(messages.BUTTON_CREATE_WATCH, callback_data=CALLBACK_CREATE)])
    rows.append([InlineKeyboardButton(messages.BUTTON_CANCEL, callback_data=CALLBACK_CANCEL)])
    return InlineKeyboardMarkup(rows)


def _preset_keyboard(key: str, values: tuple[str, ...]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(value, callback_data=_value(key, value))] for value in values]
    rows.append([InlineKeyboardButton(messages.BUTTON_CUSTOM_VALUE, callback_data=_text(key))])
    rows.append(_back_and_cancel_row())
    return InlineKeyboardMarkup(rows)


def _text_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([_back_and_cancel_row()])


def _back_and_cancel_row() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(messages.BUTTON_BACK, callback_data=CALLBACK_BACK),
        InlineKeyboardButton(messages.BUTTON_CANCEL, callback_data=CALLBACK_CANCEL),
    ]


class WizardController:
    """Owns the button-driven watch-creation flow: prompts, presets, and finalization."""

    def __init__(
        self,
        db: Database,
        source: InventorySource,
        store: WizardStore,
        main_menu_keyboard: Callable[[], InlineKeyboardMarkup],
    ) -> None:
        self._db = db
        self._source = source
        self._store = store
        self._main_menu_keyboard = main_menu_keyboard

    async def handle_callback(self, query: CallbackQuery, chat_id: int) -> None:
        data = query.data or ""
        if data == CALLBACK_NEW:
            assert query.message is not None
            new_state = self._store.start(chat_id, query.message.message_id)
            await self._render_menu(query, new_state)
            return
        state: WizardState | None = self._store.get(chat_id)
        if state is None:
            await query.edit_message_text(
                messages.WIZARD_EXPIRED, reply_markup=self._main_menu_keyboard()
            )
            return
        await self._route(query, state, data)

    async def _route(self, query: CallbackQuery, state: WizardState, data: str) -> None:
        if data == CALLBACK_CANCEL:
            self._store.clear(state.chat_id)
            await query.edit_message_text(
                messages.WIZARD_CANCELLED, reply_markup=self._main_menu_keyboard()
            )
        elif data == CALLBACK_BACK:
            await self._render_menu(query, state)
        elif data == CALLBACK_CREATE:
            await self._create(query, state)
        elif data.startswith(_PICK_PREFIX):
            await self._prompt_for(query, state, data.removeprefix(_PICK_PREFIX))
        elif data.startswith(_REMOVE_PREFIX):
            state.filters.pop(data.removeprefix(_REMOVE_PREFIX), None)
            await self._render_menu(query, state)
        elif data.startswith(_TEXT_PREFIX):
            await self._ask_text(query, state, data.removeprefix(_TEXT_PREFIX))
        elif data.startswith(_VALUE_PREFIX):
            key, _, value = data.removeprefix(_VALUE_PREFIX).partition(":")
            state.filters[key] = value
            await self._render_menu(query, state)

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Consume a plain-text reply if a wizard is waiting for one. Returns True if handled."""
        assert update.effective_chat is not None
        chat_id = update.effective_chat.id
        state = self._store.get(chat_id)
        if state is None or state.awaiting_text_for is None:
            return False
        assert update.message is not None and update.message.text is not None
        value = update.message.text.strip()
        key = state.awaiting_text_for
        if not value:
            await context.bot.edit_message_text(
                messages.WIZARD_INVALID_VALUE.format(error="el valor no puede estar vacío"),
                chat_id=state.chat_id,
                message_id=state.message_id,
                reply_markup=_text_prompt_keyboard(),
            )
            return True
        state.filters[key] = value
        state.awaiting_text_for = None
        text, markup = _menu_content(state)
        await context.bot.edit_message_text(
            text, chat_id=state.chat_id, message_id=state.message_id, reply_markup=markup
        )
        return True

    async def _render_menu(self, query: CallbackQuery, state: WizardState) -> None:
        state.awaiting_text_for = None
        text, markup = _menu_content(state)
        await query.edit_message_text(text, reply_markup=markup)

    async def _prompt_for(self, query: CallbackQuery, state: WizardState, key: str) -> None:
        if key in TEXT_ENTRY_KEYS:
            await self._ask_text(query, state, key)
        elif key == "ram":
            await query.edit_message_text(
                messages.WIZARD_ASK_RAM,
                reply_markup=_preset_keyboard("ram", tuple(str(gb) for gb in RAM_PRESETS_GB)),
            )
        elif key == "precio":
            await query.edit_message_text(
                messages.WIZARD_ASK_PRICE,
                reply_markup=_preset_keyboard(
                    "precio", tuple(str(usd) for usd in PRICE_PRESETS_USD)
                ),
            )
        elif key == "disco":
            await query.edit_message_text(
                messages.WIZARD_ASK_STORAGE, reply_markup=_preset_keyboard("disco", STORAGE_PRESETS)
            )
        elif key == "loc":
            await self._prompt_location(query)

    async def _prompt_location(self, query: CallbackQuery) -> None:
        try:
            listings = await self._source.get_available_servers()
        except InventoryUnavailableError:
            listings = []
        locations = tuple(
            sorted(
                {listing.location for listing in listings if listing.in_stock and listing.location}
            )
        )
        if not locations:
            await query.edit_message_text(
                messages.WIZARD_ASK_LOCATION_UNAVAILABLE, reply_markup=_text_prompt_keyboard()
            )
            return
        await query.edit_message_text(
            messages.WIZARD_ASK_LOCATION, reply_markup=_preset_keyboard("loc", locations)
        )

    async def _ask_text(self, query: CallbackQuery, state: WizardState, key: str) -> None:
        state.awaiting_text_for = key
        prompt = messages.WIZARD_ASK_CPU_TEXT if key == "cpu" else messages.WIZARD_ASK_LABEL_TEXT
        await query.edit_message_text(prompt, reply_markup=_text_prompt_keyboard())

    async def _create(self, query: CallbackQuery, state: WizardState) -> None:
        tokens = [f"{key}={value}" for key, value in state.filters.items()]
        try:
            filters_ = parse_watch_filters(tokens)
        except WatchFilterError as exc:
            logger.warning("wizard produced invalid filters", extra={"error": str(exc)})
            text, markup = _menu_content(state)
            await query.edit_message_text(
                messages.WIZARD_INVALID_VALUE.format(error=str(exc)) + "\n\n" + text,
                reply_markup=markup,
            )
            return
        watch = await self._db.create_watch(
            chat_id=state.chat_id,
            label=filters_.label,
            cpu_pattern=filters_.cpu_pattern,
            ram_min_gb=filters_.ram_min_gb,
            storage_pattern=filters_.storage_pattern,
            location=filters_.location,
            price_max_usd=filters_.price_max_usd,
        )
        self._store.clear(state.chat_id)
        summary = messages.format_watch_summary(watch)
        await query.edit_message_text(
            messages.WATCH_CREATED.format(watch_id=watch.id, summary=summary),
            reply_markup=self._main_menu_keyboard(),
        )
