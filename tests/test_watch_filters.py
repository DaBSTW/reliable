"""Tests for src.bot.watch_filters — pure parsing, no bot/db involved."""

from decimal import Decimal

import pytest

from src.bot.watch_filters import parse_watch_filters
from src.errors import WatchFilterError


def test_parse_watch_filters_accepts_all_known_keys():
    filters_ = parse_watch_filters(
        ["cpu=E5-2680", "ram=64", "disco=NVMe", "loc=LA", "precio=120", "nombre=proyecto-x"]
    )

    assert filters_.cpu_pattern == "E5-2680"
    assert filters_.ram_min_gb == 64
    assert filters_.price_max_usd == Decimal("120")


def test_parse_watch_filters_rejects_unknown_key():
    with pytest.raises(WatchFilterError):
        parse_watch_filters(["potato=yes"])


def test_parse_watch_filters_rejects_non_integer_ram():
    with pytest.raises(WatchFilterError):
        parse_watch_filters(["ram=lots"])


def test_parse_watch_filters_rejects_non_numeric_price():
    with pytest.raises(WatchFilterError):
        parse_watch_filters(["precio=cheap"])


def test_parse_watch_filters_with_no_args_matches_anything():
    filters_ = parse_watch_filters([])

    assert filters_ == parse_watch_filters([])
