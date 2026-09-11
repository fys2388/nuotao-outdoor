"""Background worker process: Agent Worker + Alert Scheduler.

Run this alongside the API server to consume AI agent tasks and evaluate
alerts on a schedule.

Usage:
    python run_worker.py
"""
from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.logging import setup_logging
from app.services.alert_scheduler import AlertScheduler
from app.worker.agent_worker import run_worker

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


async def main() -> None:
    """Start the alert scheduler, then run the worker loop."""
    stop_event = asyncio.Event()

    def _handle_signal(signum: int) -> None:
        logger.info("received signal %s, shutting down worker", signum)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal, sig)
        except NotImplementedError:
            pass

    # Start alert scheduler in the background
    scheduler = AlertScheduler(session_factory=async_session_factory)
    await scheduler.start()
    logger.info("alert scheduler started (enabled=%s)", scheduler.enabled)

    # Run worker loop (blocks until stop_event is set)
    logger.info("starting agent worker (concurrency=%s)", settings.worker_concurrency)
    await run_worker(stop_event=stop_event)

    logger.info("worker stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
