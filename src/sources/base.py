"""Inventory source contract, shared by the API and scraper implementations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ServerListing:
    product_id: str
    description: str
    cpu: str
    ram_gb: int
    storage: str
    location: str
    price_usd: Decimal
    in_stock: bool
    url: str | None = None


class InventorySource(ABC):
    """A way to fetch current dedicated-server availability from ReliableSite."""

    name: str

    @abstractmethod
    async def get_available_servers(self) -> list[ServerListing]:
        """Return every in-stock listing currently offered."""
