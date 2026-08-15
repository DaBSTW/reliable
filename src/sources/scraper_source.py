"""HTML scraping fallback for ReliableSite inventory, used when the API is unavailable."""

import asyncio
import logging
import re
from decimal import Decimal, InvalidOperation

import httpx
from selectolax.parser import HTMLParser

from src.errors import InventoryUnavailableError, ParseError
from src.sources.base import InventorySource, ServerListing

logger = logging.getLogger(__name__)

DEFAULT_SPECIALS_URL = "https://www.reliablesite.net/dedicated-servers/specials.aspx"
DEFAULT_TIMEOUT_SECONDS = 15.0
BACKOFF_BASE_SECONDS = 30.0
BACKOFF_CAP_SECONDS = 900.0
MAX_ATTEMPTS = 5
RETRYABLE_STATUS_CODES = {403, 429, 503}

# ReliableSite returns 403 without a browser-like Accept-Language header.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

RAM_PATTERN = re.compile(r"(\d+)\s*GB", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"\$?\s*([\d,]+\.?\d*)")


def _backoff_seconds(attempt: int) -> float:
    delay = BACKOFF_BASE_SECONDS * (2.0 ** (attempt - 1))
    return min(delay, BACKOFF_CAP_SECONDS)


def _parse_ram_gb(raw: str) -> int:
    match = RAM_PATTERN.search(raw)
    if match is None:
        raise ParseError(f"could not parse RAM from {raw!r}")
    return int(match.group(1))


def _parse_price_usd(raw: str) -> Decimal:
    match = PRICE_PATTERN.search(raw)
    if match is None:
        raise ParseError(f"could not parse price from {raw!r}")
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation as exc:
        raise ParseError(f"unparseable price {raw!r}") from exc


def parse_listings(html: str) -> list[ServerListing]:
    """Parse the specials page into ServerListing records.

    Assumes one `.server-card` per listing (see tests/fixtures/specials_page.html).
    The real markup could not be inspected during design — reliablesite.net serves a
    Cloudflare challenge to automated requests (SPECS §3.2) — so these selectors must
    be verified against production HTML before this source is trusted.
    """
    tree = HTMLParser(html)
    listings: list[ServerListing] = []
    for card in tree.css(".server-card"):
        product_id = card.attributes.get("data-product-id")
        if not product_id:
            logger.warning("scraper card missing product id, skipping")
            continue
        cpu_node = card.css_first(".server-cpu")
        ram_node = card.css_first(".server-ram")
        storage_node = card.css_first(".server-storage")
        location_node = card.css_first(".server-location")
        price_node = card.css_first(".server-price")
        if not (cpu_node and ram_node and storage_node and location_node and price_node):
            logger.warning(
                "scraper card missing a required field", extra={"product_id": product_id}
            )
            continue
        try:
            ram_gb = _parse_ram_gb(ram_node.text())
            price_usd = _parse_price_usd(price_node.text())
        except ParseError as exc:
            logger.warning(
                "scraper field parse failed",
                extra={"product_id": product_id, "error": str(exc)},
            )
            continue
        cpu = cpu_node.text(strip=True)
        storage = storage_node.text(strip=True)
        link_node = card.css_first("a")
        listings.append(
            ServerListing(
                product_id=product_id,
                description=f"{cpu}, {storage}",
                cpu=cpu,
                ram_gb=ram_gb,
                storage=storage,
                location=location_node.text(strip=True),
                price_usd=price_usd,
                in_stock=True,
                url=link_node.attributes.get("href") if link_node else None,
            )
        )
    return listings


class ScraperSource(InventorySource):
    """Fetches and parses the public specials page. Backoff on 403/429/503."""

    name = "scraper"

    def __init__(self, client: httpx.AsyncClient, url: str = DEFAULT_SPECIALS_URL) -> None:
        self._client = client
        self._url = url

    async def get_available_servers(self) -> list[ServerListing]:
        html = await self._fetch_with_retry()
        return parse_listings(html)

    async def _fetch_with_retry(self) -> str:
        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._client.get(
                    self._url, headers=BROWSER_HEADERS, timeout=DEFAULT_TIMEOUT_SECONDS
                )
            except httpx.TransportError as exc:
                last_error = exc
                logger.warning(
                    "scraper request failed", extra={"attempt": attempt, "error": str(exc)}
                )
            else:
                if response.status_code == httpx.codes.OK:
                    return response.text
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    raise InventoryUnavailableError(
                        f"unexpected status {response.status_code} from scraper"
                    )
                last_error = InventoryUnavailableError(f"scraper got status {response.status_code}")
                logger.warning(
                    "scraper got retryable status",
                    extra={"attempt": attempt, "status": response.status_code},
                )
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(_backoff_seconds(attempt))
        raise InventoryUnavailableError("scraper exhausted retries") from last_error
