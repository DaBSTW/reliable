"""Chat-id whitelist and admin approval, backed by the authorized_users table."""

from src.db import Database


class Auth:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def is_authorized(self, chat_id: int) -> bool:
        return await self._db.is_authorized(chat_id)

    async def is_admin(self, chat_id: int) -> bool:
        return await self._db.is_admin(chat_id)

    async def approve(self, chat_id: int, username: str | None) -> None:
        await self._db.approve_user(chat_id, username)

    async def bootstrap_admin(self, admin_chat_id: int) -> None:
        await self._db.ensure_admin_bootstrapped(admin_chat_id)
