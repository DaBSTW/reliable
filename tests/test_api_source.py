"""Tests for the API source parser — runs against a static fixture, no real network."""

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.errors import InventoryUnavailableError, ParseError
from src.sources.api_source import (
    ApiSource,
    _parse_ram_gb,
    _parse_storage,
    _split_detail_lines,
    parse_server,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "api_servers_sample.json"


def _load_raw_servers() -> list[SimpleNamespace]:
    raw = json.loads(FIXTURE_PATH.read_text())
    return [
        SimpleNamespace(
            Product_Id=item["Product_Id"],
            Description=item["Description"],
            Detail=item["Detail"],
            Data_Center=item["Data_Center"],
            Recurring_1_Month=Decimal(item["Recurring_1_Month"]),
            Stock=item["Stock"],
        )
        for item in raw
    ]


def test_split_detail_lines_strips_br_tags_and_whitespace():
    lines = _split_detail_lines("AMD Epyc 4545P<br />\r\n256 GB DDR5 RAM<br/>\r\n4 TB NVMe")

    assert lines == ["AMD Epyc 4545P", "256 GB DDR5 RAM", "4 TB NVMe"]


def test_parse_ram_gb_finds_the_ram_line():
    assert _parse_ram_gb(["AMD Epyc", "256 GB DDR5 RAM", "4 TB NVMe"]) == 256


def test_parse_ram_gb_raises_when_no_line_matches():
    with pytest.raises(ParseError):
        _parse_ram_gb(["AMD Epyc", "plenty of RAM"])


def test_parse_storage_joins_every_matching_line():
    lines = ["CPU", "128 GB RAM", "2 TB NVMe (PCIe 4x)", "2 TB NVMe (PCIe 2x)", "Miami DC"]

    assert _parse_storage(lines) == "2 TB NVMe (PCIe 4x), 2 TB NVMe (PCIe 2x)"


def test_parse_server_maps_an_in_stock_listing():
    raw = _load_raw_servers()[0]

    listing = parse_server(raw)

    assert listing.product_id == "425"
    assert listing.cpu == "AMD Epyc 4545P"
    assert listing.ram_gb == 256
    assert listing.storage == "4 TB NVMe (PCIe 4.0)"
    assert listing.location == "NL"
    assert listing.price_usd == Decimal("279.0000")
    assert listing.in_stock is True


def test_parse_server_marks_zero_stock_as_out_of_stock():
    raw = _load_raw_servers()[1]

    listing = parse_server(raw)

    assert listing.in_stock is False


def test_parse_server_returns_none_when_ram_is_unparseable():
    raw = _load_raw_servers()[2]

    assert parse_server(raw) is None


def test_parse_server_returns_none_when_product_id_is_missing():
    raw = _load_raw_servers()[3]

    assert parse_server(raw) is None


class _FakeService:
    def __init__(self, result: SimpleNamespace) -> None:
        self._result = result

    def ServersList(self) -> SimpleNamespace:  # noqa: N802 -- mirrors the SOAP operation name
        return self._result


class _FakeClient:
    def __init__(self, result: SimpleNamespace) -> None:
        self.service = _FakeService(result)


async def test_get_available_servers_returns_parsed_in_stock_and_out_of_stock_listings(
    monkeypatch,
):
    result = SimpleNamespace(
        Result=True,
        Message="ok",
        ServerDetailsList=SimpleNamespace(Server_Details=_load_raw_servers()),
    )
    monkeypatch.setattr("src.sources.api_source.Client", lambda _url: _FakeClient(result))
    source = ApiSource()

    listings = await source.get_available_servers()

    assert [listing.product_id for listing in listings] == ["425", "284"]


async def test_get_available_servers_raises_when_api_reports_failure(monkeypatch):
    result = SimpleNamespace(
        Result=False, Message="temporarily unavailable", ServerDetailsList=None
    )
    monkeypatch.setattr("src.sources.api_source.Client", lambda _url: _FakeClient(result))
    source = ApiSource()

    with pytest.raises(InventoryUnavailableError):
        await source.get_available_servers()
