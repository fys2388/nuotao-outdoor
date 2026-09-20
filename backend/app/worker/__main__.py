"""Entrypoint: ``python -m app.worker`` starts the resident agent worker.

Production behavior (M5.5):

- ``AGENT_WORKER_ID`` pins the worker identity (required when scaling);
  without it a unique ``worker-{hostname}-{pid}`` id is generated so
  horizontal scaling never collides in the heartbeat registry.
- SIGTERM/SIGINT trigger a graceful shutdown: the loop stops claiming new
  messages, finishes the current task, ACKs it, then heartbeats offline.
"""

import asyncio
import contextlib
import logging
import os
import signal
import socket

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.worker.agent_worker import run_worker
from app.worker.bootstrap import register_builtin_executors


def _resolve_worker_id() -> str:
    """Return the pinned worker id or generate a unique one."""
    pinned = os.environ.get("AGENT_WORKER_ID")
    if pinned:
        return pinned
    return f"worker-{socket.gethostname()}-{os.getpid()}"


def main() -> None:
    """Run the worker until interrupted (graceful on SIGTERM/SIGINT)."""
    # Bind every built-in agent to its production executor. Unknown agents
    # still fall back to the generic LLM executor.
    register_builtin_executors()
    setup_logging()
    logger = logging.getLogger(__name__)
    worker_id = _resolve_worker_id()
    settings = get_settings()
    settings.worker_id = worker_id  # run_worker reads the settings default
    stop_event = asyncio.Event()
    logger.info(
        "starting agent worker id=%s concurrency=%s", worker_id, settings.worker_concurrency
    )

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, stop_event.set)
                # Windows: SIGTERM is unavailable; KeyboardInterrupt still
                # propagates and asyncio.run cancels the worker task.
        await run_worker(worker_id=worker_id, stop_event=stop_event)
        logger.info("agent worker %s stopped gracefully", worker_id)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("agent worker stopped")


if __name__ == "__main__":
    main()
