"""Entrypoint: ``python -m app.worker`` starts the resident agent worker."""

import asyncio
import logging

from app.core.logging import setup_logging
from app.worker.agent_worker import run_worker


def main() -> None:
    """Run the worker until interrupted."""
    setup_logging()
    logging.getLogger(__name__).info("starting agent worker")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("agent worker stopped")


if __name__ == "__main__":
    main()
