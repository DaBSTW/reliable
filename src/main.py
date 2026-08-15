"""Entrypoint: starts the bot, the scheduler and the poller in one event loop."""

import asyncio
import logging
import signal

import httpx
from telegram.ext import Application as TelegramApplication
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ExtBot, JobQueue

from src.bot.auth import Auth
from src.bot.handlers import Handlers
from src.config import Config, load_config
from src.db import Database
from src.sources.base import InventorySource
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


def _build_source(config: Config, client: httpx.AsyncClient) -> InventorySource:
    if config.inventory_source == "api":
        # Fase 5: api_source.py needs a verified WSDL/credentials before it can replace this.
        logger.warning("api source not yet available, falling back to scraper")
    return ScraperSource(client)


def _build_application(config: Config, handlers: Handlers) -> Application:
    application = ApplicationBuilder().token(config.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("watch", handlers.watch))
    application.add_handler(CommandHandler("list", handlers.list_watches))
    application.add_handler(CommandHandler("remove", handlers.remove))
    application.add_handler(CommandHandler("stock", handlers.stock))
    application.add_handler(CommandHandler("status", handlers.status))
    application.add_handler(CommandHandler("approve", handlers.approve))
    return application


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

    try:
        async with httpx.AsyncClient() as client:
            source = _build_source(config, client)
            handlers = Handlers(db, auth, source, next_poll_in_seconds=lambda: None)
            application = _build_application(config, handlers)

            async with application:
                await application.start()
                assert application.updater is not None
                await application.updater.start_polling()
                await shutdown.wait()
                logger.info("shutting down")
                await application.updater.stop()
                await application.stop()
    finally:
        await db.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
