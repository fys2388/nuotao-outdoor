"""Scheduler entrypoint: ``python -m app.scheduler``.

Runs the M5.5 Alert Scheduler as a standalone process with graceful
shutdown: SIGTERM/SIGINT stop the loop between ticks (an in-flight
evaluation pass is never interrupted mid-way). The scheduler only opens
alerts; it never executes business actions.
"""

import asyncio
import logging
import signal

from app.core.database import async_session_factory
from app.core.logging import setup_logging
from app.services.alert_scheduler import AlertScheduler


def main() -> None:
    """Start the alert scheduler and block until interrupted."""
    setup_logging()
    logger = logging.getLogger(__name__)
    scheduler = AlertScheduler(session_factory=async_session_factory)

    async def _run() -> None:
        await scheduler.start()
        logger.info("alert scheduler process ready")
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGTERM, stop.set)
        except (NotImplementedError, RuntimeError):
            # Windows: SIGTERM is not supported - rely on SIGINT/KeyboardInterrupt.
            pass
        try:
            loop.add_signal_handler(signal.SIGINT, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
        await stop.wait()
        await scheduler.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("alert scheduler process stopped")


if __name__ == "__main__":
    main()
