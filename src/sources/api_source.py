"""SOAP inventory source — ReliableSite's Inventory API.

Fase 5 of SPECS §11 assumed credentials would be needed; inspecting the live WSDL during
this work showed `ServersList` takes no input and is reachable with no authentication at
all, so this talks to the real API directly. CPU/RAM/storage aren't separate fields —
they're parsed out of the free-text `Detail` field (see `_split_detail_lines`).
"""

import asyncio
import logging
import re
from decimal import Decimal
from typing import Any

from zeep import Client
from zeep.exceptions import Error as ZeepError
from zeep.transports import Transport

from src.errors import InventoryUnavailableError, ParseError
from src.sources.base import InventorySource, ServerListing

logger = logging.getLogger(__name__)

DEFAULT_WSDL_URL = "http://api.reliablesite.net/inventory.svc?wsdl"
WSDL_FETCH_TIMEOUT_SECONDS = 15
OPERATION_TIMEOUT_SECONDS = 15

RAM_PATTERN = re.compile(r"(\d+)\s*GB\s*(?:DDR\d[A-Z]*\s*)?(?:ECC\s*)?RAM", re.IGNORECASE)
STORAGE_KEYWORDS = ("NVMe", "SSD", "HDD")


def _split_detail_lines(detail: str) -> list[str]:
    return [line.strip() for line in re.split(r"<br\s*/?>", detail) if line.strip()]


def _parse_ram_gb(lines: list[str]) -> int:
    for line in lines:
        match = RAM_PATTERN.search(line)
        if match:
            return int(match.group(1))
    raise ParseError(f"could not find RAM in detail lines: {lines!r}")


def _parse_storage(lines: list[str]) -> str:
    storage_lines = [line for line in lines if any(keyword in line for keyword in STORAGE_KEYWORDS)]
    if not storage_lines:
        raise ParseError(f"could not find storage in detail lines: {lines!r}")
    return ", ".join(storage_lines)


def parse_server(raw: Any) -> ServerListing | None:
    """Convert one dynamic `Server_Details` SOAP object into a typed ServerListing."""
    product_id = raw.Product_Id
    if not product_id:
        logger.warning("api server missing product id, skipping")
        return None
    lines = _split_detail_lines(raw.Detail or "")
    if not lines:
        logger.warning("api server has no parseable detail", extra={"product_id": product_id})
        return None
    try:
        ram_gb = _parse_ram_gb(lines)
        storage = _parse_storage(lines)
    except ParseError as exc:
        logger.warning(
            "api field parse failed", extra={"product_id": product_id, "error": str(exc)}
        )
        return None
    return ServerListing(
        product_id=str(product_id),
        description=raw.Description or "",
        cpu=lines[0],
        ram_gb=ram_gb,
        storage=storage,
        location=raw.Data_Center or "",
        price_usd=Decimal(raw.Recurring_1_Month),
        in_stock=bool(raw.Stock and raw.Stock > 0),
        url=None,
    )


class ApiSource(InventorySource):
    """ReliableSite's Inventory API (SOAP/WCF). Publicly reachable, no credentials needed."""

    name = "api"

    def __init__(self, wsdl_url: str = DEFAULT_WSDL_URL) -> None:
        self._wsdl_url = wsdl_url
        self._client: Client | None = None

    async def get_available_servers(self) -> list[ServerListing]:
        client = await self._get_client()
        try:
            result = await asyncio.to_thread(client.service.ServersList)
        except ZeepError as exc:
            raise InventoryUnavailableError(f"api call failed: {exc}") from exc
        if not result.Result:
            raise InventoryUnavailableError(f"api returned failure: {result.Message}")
        raw_servers = result.ServerDetailsList.Server_Details if result.ServerDetailsList else []
        return [listing for raw in raw_servers if (listing := parse_server(raw)) is not None]

    async def _get_client(self) -> Client:
        if self._client is None:
            # zeep ships no type stubs, hence the ignore.
            transport = Transport(
                timeout=WSDL_FETCH_TIMEOUT_SECONDS, operation_timeout=OPERATION_TIMEOUT_SECONDS
            )  # type: ignore[no-untyped-call]
            try:
                # zeep raises a mix of requests/lxml errors while fetching and parsing the WSDL.
                self._client = await asyncio.to_thread(Client, self._wsdl_url, transport=transport)
            except Exception as exc:
                raise InventoryUnavailableError(f"could not load WSDL: {exc}") from exc
        return self._client
