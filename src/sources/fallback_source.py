"""Wraps a primary source and switches to a fallback after repeated failures."""

import logging

from src.errors import InventoryUnavailableError
from src.sources.base import InventorySource, ServerListing

logger = logging.getLogger(__name__)

DEFAULT_FAILURE_THRESHOLD = 3


class FallbackInventorySource(InventorySource):
    """Uses `primary` until it fails `failure_threshold` times in a row, then `fallback`."""

    def __init__(
        self,
        primary: InventorySource,
        fallback: InventorySource,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._failure_threshold = failure_threshold
        self._consecutive_failures = 0
        self._on_fallback = False

    @property
    def name(self) -> str:
        return self._fallback.name if self._on_fallback else self._primary.name

    async def get_available_servers(self) -> list[ServerListing]:
        if self._on_fallback:
            return await self._fallback.get_available_servers()
        try:
            listings = await self._primary.get_available_servers()
        except InventoryUnavailableError:
            self._consecutive_failures += 1
            logger.warning(
                "primary source failed",
                extra={
                    "primary": self._primary.name,
                    "consecutive_failures": self._consecutive_failures,
                },
            )
            if self._consecutive_failures >= self._failure_threshold:
                logger.warning(
                    "switching to fallback source",
                    extra={"primary": self._primary.name, "fallback": self._fallback.name},
                )
                self._on_fallback = True
                return await self._fallback.get_available_servers()
            raise
        else:
            self._consecutive_failures = 0
            return listings
