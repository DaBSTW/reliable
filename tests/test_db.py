"""Tests for src.db against a throwaway SQLite file — no network involved."""

from decimal import Decimal

import pytest

from src.db import Database


@pytest.fixture
async def db(tmp_path):
    database = await Database.connect(str(tmp_path / "watches.db"))
    yield database
    await database.close()


async def test_create_watch_returns_it_with_an_assigned_id(db):
    watch = await db.create_watch(
        chat_id=42,
        label="test",
        cpu_pattern="E3-1230",
        ram_min_gb=32,
        storage_pattern=None,
        location="NYC",
        price_max_usd=Decimal("80"),
    )

    assert watch.id > 0


async def test_list_watches_for_chat_only_returns_that_chats_active_watches(db):
    await db.create_watch(
        chat_id=1,
        label=None,
        cpu_pattern=None,
        ram_min_gb=None,
        storage_pattern=None,
        location=None,
        price_max_usd=None,
    )
    await db.create_watch(
        chat_id=2,
        label=None,
        cpu_pattern=None,
        ram_min_gb=None,
        storage_pattern=None,
        location=None,
        price_max_usd=None,
    )

    watches = await db.list_watches_for_chat(1)

    assert [w.chat_id for w in watches] == [1]


async def test_deactivate_watch_removes_it_from_active_listing(db):
    watch = await db.create_watch(
        chat_id=1,
        label=None,
        cpu_pattern=None,
        ram_min_gb=None,
        storage_pattern=None,
        location=None,
        price_max_usd=None,
    )

    await db.deactivate_watch(watch.id, chat_id=1)

    assert await db.list_watches_for_chat(1) == []


async def test_deactivate_watch_rejects_a_different_owner(db):
    watch = await db.create_watch(
        chat_id=1,
        label=None,
        cpu_pattern=None,
        ram_min_gb=None,
        storage_pattern=None,
        location=None,
        price_max_usd=None,
    )

    deactivated = await db.deactivate_watch(watch.id, chat_id=999)

    assert deactivated is False


async def test_mark_notified_persists_the_match_hash(db):
    watch = await db.create_watch(
        chat_id=1,
        label=None,
        cpu_pattern=None,
        ram_min_gb=None,
        storage_pattern=None,
        location=None,
        price_max_usd=None,
    )

    await db.mark_notified(watch.id, "abc123")
    reloaded = await db.get_watch(watch.id)

    assert reloaded.last_match_hash == "abc123"


async def test_record_poll_is_readable_via_last_poll(db):
    await db.record_poll(source="scraper", success=True, listings=7, error=None)

    entry = await db.last_poll()

    assert entry.listings == 7


async def test_approved_user_is_authorized(db):
    await db.approve_user(555, username="alice")

    assert await db.is_authorized(555) is True


async def test_unknown_chat_id_is_not_authorized(db):
    assert await db.is_authorized(999) is False


async def test_ensure_admin_bootstrapped_grants_admin(db):
    await db.ensure_admin_bootstrapped(777)

    assert await db.is_admin(777) is True
