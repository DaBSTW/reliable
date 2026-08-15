"""Entrypoint: starts the bot, the scheduler and the poller in one event loop."""

import asyncio
import logging
import signal
from datetime import datetime

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram.ext import Application as TelegramApplication
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ExtBot, JobQueue

from src.bot.auth import Auth
from src.bot.handlers import Handlers
from src.config import Config, load_config
from src.db import Database
from src.notifier import Notifier
from src.poller import PollCycle
from src.sources.api_source import ApiSource
from src.sources.base import InventorySource
from src.sources.fallback_source import FallbackInventorySource
from src.sources.scraper_source import ScraperSource

logger = logging.getLogger(__name__)

# ApplicationBuilder's default generics (python-telegram-bot's own type, not ours).
BotData = dict[str, object]
Application = TelegramApplication[
    ExtBot[None],
    ContextTypes.DEFAULT_TYPE,
    BotData,
    BotData,
    BotData,
    JobQueue[ContextTypes.DEFAULT_TYPE],
]

POLL_JOB_ID = "inventory_poll"


def _build_source(config: Config, client: httpx.AsyncClient) -> InventorySource:
    scraper = ScraperSource(client)
    if config.inventory_source == "scraper":
        return scraper
    return FallbackInventorySource(ApiSource(), scraper)


def _build_telegram_application(config: Config, handlers: Handlers) -> Application:
    application = ApplicationBuilder().token(config.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("watch", handlers.watch))
    application.add_handler(CommandHandler("list", handlers.list_watches))
    application.add_handler(CommandHandler("remove", handlers.remove))
    application.add_handler(CommandHandler("stock", handlers.stock))
    application.add_handler(CommandHandler("status", handlers.status))
    application.add_handler(CommandHandler("approve", handlers.approve))
    return application


def _next_poll_in_seconds(scheduler: AsyncIOScheduler) -> int | None:
    job = scheduler.get_job(POLL_JOB_ID)
    if job is None or job.next_run_time is None:
        return None
    delta = job.next_run_time - datetime.now(job.next_run_time.tzinfo)
    return max(int(delta.total_seconds()), 0)


async def run() -> None:
    config = load_config()
    logging.basicConfig(level=config.log_level)
    logger.info("started", extra={"inventory_source": config.inventory_source})

    db = await Database.connect(config.db_path)
    auth = Auth(db)
    await auth.bootstrap_admin(config.admin_chat_id)

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.set)

    scheduler = AsyncIOScheduler()
    try:
        async with httpx.AsyncClient() as client:
            source = _build_source(config, client)
            handlers = Handlers(db, auth, source, lambda: _next_poll_in_seconds(scheduler))
            application = _build_telegram_application(config, handlers)
            notifier = Notifier(application.bot)
            poll_cycle = PollCycle(
                db, source, notifier, config.renotify_hours, config.admin_chat_id
            )
            scheduler.add_job(
                poll_cycle.run,
                IntervalTrigger(seconds=config.poll_interval_seconds),
                id=POLL_JOB_ID,
                next_run_time=datetime.now(),
            )
            scheduler.start()

            async with application:
                await application.start()
                assert application.updater is not None
                await application.updater.start_polling()
                await shutdown.wait()
                logger.info("shutting down")
                await application.updater.stop()
                await application.stop()
    finally:
        scheduler.shutdown(wait=False)
        await db.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
