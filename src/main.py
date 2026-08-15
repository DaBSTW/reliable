"""Entrypoint: starts the bot, the scheduler and the poller in one event loop."""

import asyncio
import logging

from src.config import load_config

logger = logging.getLogger(__name__)


async def run() -> None:
    config = load_config()
    logging.basicConfig(level=config.log_level)
    logger.info("started", extra={"inventory_source": config.inventory_source})


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
