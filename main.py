import asyncio
import logging
import signal

import database as db
from bot import build_app
from sheets_parser import fetch_all_events
from scheduler import init_scheduler, get_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    await db.init_db()
    logger.info("Database initialized.")

    bot_app = build_app()

    # Initial schedule load — non-fatal if it fails
    try:
        events = await asyncio.to_thread(fetch_all_events)
        if events:
            await db.replace_events(events)
            await db.log_sync(len(events))
            logger.info("Initial schedule loaded: %d events.", len(events))
        else:
            logger.warning("Initial schedule load returned 0 events.")
    except Exception:
        logger.exception("Initial schedule load failed. Bot will run with empty schedule.")

    await init_scheduler(bot_app.bot)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    async with bot_app:
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Concierge bot polling started.")
        try:
            await stop_event.wait()
        finally:
            get_scheduler().shutdown(wait=False)
            await bot_app.updater.stop()
            await bot_app.stop()


if __name__ == "__main__":
    asyncio.run(main())
