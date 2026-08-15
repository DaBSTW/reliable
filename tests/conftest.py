"""Shared test fixtures and factories."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.db import Watch
from src.sources.base import ServerListing

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_sample_listings() -> list[ServerListing]:
    raw = json.loads((FIXTURES_DIR / "sample_inventory.json").read_text())
    return [
        ServerListing(
            product_id=item["product_id"],
            description=item["description"],
            cpu=item["cpu"],
            ram_gb=item["ram_gb"],
            storage=item["storage"],
            location=item["location"],
            price_usd=Decimal(item["price_usd"]),
            in_stock=item["in_stock"],
            url=item["url"],
        )
        for item in raw
    ]


def make_watch(
    *,
    watch_id: int = 1,
    chat_id: int = 111,
    label: str | None = None,
    cpu_pattern: str | None = None,
    ram_min_gb: int | None = None,
    storage_pattern: str | None = None,
    location: str | None = None,
    price_max_usd: Decimal | None = None,
    active: bool = True,
    created_at: str | None = None,
    last_notified_at: str | None = None,
    last_match_hash: str | None = None,
) -> Watch:
    return Watch(
        id=watch_id,
        chat_id=chat_id,
        label=label,
        cpu_pattern=cpu_pattern,
        ram_min_gb=ram_min_gb,
        storage_pattern=storage_pattern,
        location=location,
        price_max_usd=price_max_usd,
        active=active,
        created_at=created_at or datetime.now(UTC).isoformat(),
        last_notified_at=last_notified_at,
        last_match_hash=last_match_hash,
    )


@pytest.fixture
def sample_listings() -> list[ServerListing]:
    return load_sample_listings()
