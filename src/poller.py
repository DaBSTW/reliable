"""Poll cycle: fetch inventory, match it against active watches, notify, log."""

import logging
import uuid
from datetime import UTC, datetime

from src.bot import messages
from src.db import Database
from src.errors import InventoryUnavailableError
from src.matcher import compute_match_hash, matches, should_notify
from src.notifier import Notifier
from src.sources.base import InventorySource, ServerListing

logger = logging.getLogger(__name__)

CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 3
STALLED_POLL_ALERT_MINUTES = 30


class PollCycle:
    """Orchestrates one poll: source -> matcher vs. active watches -> notifier."""

    def __init__(
        self,
        db: Database,
        source: InventorySource,
        notifier: Notifier,
        renotify_hours: int,
        admin_chat_id: int,
    ) -> None:
        self._db = db
        self._source = source
        self._notifier = notifier
        self._renotify_hours = renotify_hours
        self._admin_chat_id = admin_chat_id

    async def run(self) -> None:
        cycle_id = uuid.uuid4().hex[:8]
        logger.info("poll cycle started", extra={"cycle_id": cycle_id, "source": self._source.name})
        try:
            listings = await self._source.get_available_servers()
        except InventoryUnavailableError as exc:
            await self._handle_failure(cycle_id, str(exc))
            return
        await self._db.record_poll(
            source=self._source.name, success=True, listings=len(listings), error=None
        )
        await self._notify_matches(cycle_id, listings)
        logger.info("poll cycle finished", extra={"cycle_id": cycle_id, "listings": len(listings)})

    async def _notify_matches(self, cycle_id: str, listings: list[ServerListing]) -> None:
        now = datetime.now(UTC)
        for watch in await self._db.list_active_watches():
            matched = [listing for listing in listings if matches(listing, watch)]
            if not matched:
                continue
            match_hash = compute_match_hash([listing.product_id for listing in matched])
            if not should_notify(watch, match_hash, self._renotify_hours, now):
                continue
            await self._notifier.notify_match(watch, matched[0])
            await self._db.mark_notified(watch.id, match_hash)
            logger.info(
                "match notified",
                extra={
                    "cycle_id": cycle_id,
                    "watch_id": watch.id,
                    "product_id": matched[0].product_id,
                },
            )

    async def _handle_failure(self, cycle_id: str, error: str) -> None:
        await self._db.record_poll(source=self._source.name, success=False, listings=0, error=error)
        logger.warning("poll cycle failed", extra={"cycle_id": cycle_id, "error": error})
        await self._alert_admin_if_unhealthy()

    async def _alert_admin_if_unhealthy(self) -> None:
        recent = await self._db.recent_polls(CONSECUTIVE_FAILURE_ALERT_THRESHOLD)
        if len(recent) >= CONSECUTIVE_FAILURE_ALERT_THRESHOLD and not any(
            p.success for p in recent
        ):
            await self._notifier.notify_admin(
                self._admin_chat_id,
                messages.ADMIN_ALERT_POLL_FAILING.format(
                    consecutive_failures=CONSECUTIVE_FAILURE_ALERT_THRESHOLD,
                    source=recent[0].source,
                    error=recent[0].error or "?",
                ),
            )
        stalled_minutes = await self._minutes_since_last_success()
        if stalled_minutes is not None and stalled_minutes >= STALLED_POLL_ALERT_MINUTES:
            await self._notifier.notify_admin(
                self._admin_chat_id,
                messages.ADMIN_ALERT_POLL_STALLED.format(minutes=int(stalled_minutes)),
            )

    async def _minutes_since_last_success(self) -> float | None:
        last_success = await self._db.last_successful_poll()
        if last_success is None:
            return None
        elapsed = datetime.now(UTC) - datetime.fromisoformat(last_success.ts).replace(tzinfo=UTC)
        return elapsed.total_seconds() / 60
