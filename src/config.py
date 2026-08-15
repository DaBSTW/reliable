"""Loads and validates configuration from the environment.

The only module allowed to read `os.environ`.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from src.errors import ConfigError

VALID_INVENTORY_SOURCES = ("api", "scraper")

DEFAULT_POLL_INTERVAL_SECONDS = 600
DEFAULT_RENOTIFY_HOURS = 6
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_INVENTORY_SOURCE = "api"


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    admin_chat_id: int
    inventory_source: str
    reliablesite_api_user: str | None
    reliablesite_api_key: str | None
    poll_interval_seconds: int
    renotify_hours: int
    db_path: str
    log_path: str
    log_level: str


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"missing required environment variable: {name}")
    return value


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def load_config(env_file: Path | None = None) -> Config:
    """Load configuration from `.env` (if present) and the process environment."""
    load_dotenv(dotenv_path=env_file, override=False)

    telegram_bot_token = _require("TELEGRAM_BOT_TOKEN")

    admin_chat_id_raw = _require("ADMIN_CHAT_ID")
    try:
        admin_chat_id = int(admin_chat_id_raw)
    except ValueError as exc:
        raise ConfigError(f"ADMIN_CHAT_ID must be an integer, got {admin_chat_id_raw!r}") from exc

    inventory_source = os.environ.get("INVENTORY_SOURCE", DEFAULT_INVENTORY_SOURCE).strip()
    if inventory_source not in VALID_INVENTORY_SOURCES:
        raise ConfigError(
            f"INVENTORY_SOURCE must be one of {VALID_INVENTORY_SOURCES}, got {inventory_source!r}"
        )

    return Config(
        telegram_bot_token=telegram_bot_token,
        admin_chat_id=admin_chat_id,
        inventory_source=inventory_source,
        reliablesite_api_user=os.environ.get("RELIABLESITE_API_USER") or None,
        reliablesite_api_key=os.environ.get("RELIABLESITE_API_KEY") or None,
        poll_interval_seconds=_int_env("POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS),
        renotify_hours=_int_env("RENOTIFY_HOURS", DEFAULT_RENOTIFY_HOURS),
        db_path=os.environ.get("DB_PATH", "data/watches.db"),
        log_path=os.environ.get("LOG_PATH", "logs/app.log"),
        log_level=os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper(),
    )
