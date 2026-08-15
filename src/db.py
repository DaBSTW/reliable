"""SQLite persistence for watches, poll history and authorized users."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id          INTEGER NOT NULL,
    label            TEXT,
    cpu_pattern      TEXT,
    ram_min_gb       INTEGER,
    storage_pattern  TEXT,
    location         TEXT,
    price_max_usd    TEXT,
    active           BOOLEAN NOT NULL DEFAULT 1,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_notified_at TIMESTAMP,
    last_match_hash  TEXT
);

CREATE TABLE IF NOT EXISTS poll_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source   TEXT NOT NULL,
    success  BOOLEAN NOT NULL,
    listings INTEGER NOT NULL,
    error    TEXT
);

CREATE TABLE IF NOT EXISTS authorized_users (
    chat_id  INTEGER PRIMARY KEY,
    username TEXT,
    is_admin BOOLEAN NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class Watch:
    id: int
    chat_id: int
    label: str | None
    cpu_pattern: str | None
    ram_min_gb: int | None
    storage_pattern: str | None
    location: str | None
    price_max_usd: Decimal | None
    active: bool
    created_at: str
    last_notified_at: str | None
    last_match_hash: str | None


@dataclass(frozen=True)
class PollLogEntry:
    id: int
    ts: str
    source: str
    success: bool
    listings: int
    error: str | None


def _row_to_watch(row: aiosqlite.Row) -> Watch:
    price = row["price_max_usd"]
    return Watch(
        id=row["id"],
        chat_id=row["chat_id"],
        label=row["label"],
        cpu_pattern=row["cpu_pattern"],
        ram_min_gb=row["ram_min_gb"],
        storage_pattern=row["storage_pattern"],
        location=row["location"],
        price_max_usd=Decimal(price) if price is not None else None,
        active=bool(row["active"]),
        created_at=row["created_at"],
        last_notified_at=row["last_notified_at"],
        last_match_hash=row["last_match_hash"],
    )


def _row_to_poll_log(row: aiosqlite.Row) -> PollLogEntry:
    return PollLogEntry(
        id=row["id"],
        ts=row["ts"],
        source=row["source"],
        success=bool(row["success"]),
        listings=row["listings"],
        error=row["error"],
    )


class Database:
    """Thin async wrapper around a single SQLite connection."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    @classmethod
    async def connect(cls, db_path: str) -> "Database":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(db_path)
        connection.row_factory = aiosqlite.Row
        db = cls(connection)
        await db._init_schema()
        return db

    async def close(self) -> None:
        await self._connection.close()

    async def _init_schema(self) -> None:
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()

    # -- watches --------------------------------------------------------------

    async def create_watch(
        self,
        chat_id: int,
        label: str | None,
        cpu_pattern: str | None,
        ram_min_gb: int | None,
        storage_pattern: str | None,
        location: str | None,
        price_max_usd: Decimal | None,
    ) -> Watch:
        cursor = await self._connection.execute(
            """
            INSERT INTO watches
                (chat_id, label, cpu_pattern, ram_min_gb, storage_pattern, location, price_max_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                label,
                cpu_pattern,
                ram_min_gb,
                storage_pattern,
                location,
                str(price_max_usd) if price_max_usd is not None else None,
            ),
        )
        await self._connection.commit()
        assert cursor.lastrowid is not None
        watch = await self.get_watch(cursor.lastrowid)
        assert watch is not None
        return watch

    async def get_watch(self, watch_id: int) -> Watch | None:
        cursor = await self._connection.execute("SELECT * FROM watches WHERE id = ?", (watch_id,))
        row = await cursor.fetchone()
        return _row_to_watch(row) if row is not None else None

    async def list_watches_for_chat(self, chat_id: int) -> list[Watch]:
        cursor = await self._connection.execute(
            "SELECT * FROM watches WHERE chat_id = ? AND active = 1 ORDER BY id", (chat_id,)
        )
        rows = await cursor.fetchall()
        return [_row_to_watch(row) for row in rows]

    async def list_active_watches(self) -> list[Watch]:
        cursor = await self._connection.execute("SELECT * FROM watches WHERE active = 1")
        rows = await cursor.fetchall()
        return [_row_to_watch(row) for row in rows]

    async def deactivate_watch(self, watch_id: int, chat_id: int) -> bool:
        """Deactivate a watch owned by `chat_id`. Returns False if missing or not owned."""
        cursor = await self._connection.execute(
            "UPDATE watches SET active = 0 WHERE id = ? AND chat_id = ? AND active = 1",
            (watch_id, chat_id),
        )
        await self._connection.commit()
        return cursor.rowcount > 0

    async def mark_notified(self, watch_id: int, match_hash: str) -> None:
        await self._connection.execute(
            "UPDATE watches SET last_notified_at = CURRENT_TIMESTAMP, last_match_hash = ? "
            "WHERE id = ?",
            (match_hash, watch_id),
        )
        await self._connection.commit()

    # -- poll_log ---------------------------------------------------------------

    async def record_poll(
        self, source: str, success: bool, listings: int, error: str | None
    ) -> None:
        await self._connection.execute(
            "INSERT INTO poll_log (source, success, listings, error) VALUES (?, ?, ?, ?)",
            (source, success, listings, error),
        )
        await self._connection.commit()

    async def last_poll(self) -> PollLogEntry | None:
        cursor = await self._connection.execute("SELECT * FROM poll_log ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
        return _row_to_poll_log(row) if row is not None else None

    async def recent_polls(self, limit: int) -> list[PollLogEntry]:
        cursor = await self._connection.execute(
            "SELECT * FROM poll_log ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [_row_to_poll_log(row) for row in rows]

    # -- authorized_users ---------------------------------------------------------

    async def is_authorized(self, chat_id: int) -> bool:
        cursor = await self._connection.execute(
            "SELECT 1 FROM authorized_users WHERE chat_id = ?", (chat_id,)
        )
        return await cursor.fetchone() is not None

    async def is_admin(self, chat_id: int) -> bool:
        cursor = await self._connection.execute(
            "SELECT is_admin FROM authorized_users WHERE chat_id = ?", (chat_id,)
        )
        row = await cursor.fetchone()
        return bool(row["is_admin"]) if row is not None else False

    async def approve_user(
        self, chat_id: int, username: str | None, is_admin: bool = False
    ) -> None:
        await self._connection.execute(
            "INSERT INTO authorized_users (chat_id, username, is_admin) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET username = excluded.username",
            (chat_id, username, is_admin),
        )
        await self._connection.commit()

    async def ensure_admin_bootstrapped(self, admin_chat_id: int) -> None:
        """Idempotently register the configured admin as an authorized admin user."""
        await self._connection.execute(
            "INSERT INTO authorized_users (chat_id, is_admin) VALUES (?, 1) "
            "ON CONFLICT(chat_id) DO UPDATE SET is_admin = 1",
            (admin_chat_id,),
        )
        await self._connection.commit()
