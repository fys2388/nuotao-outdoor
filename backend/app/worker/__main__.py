"""Entrypoint: ``python -m app.worker`` starts the resident agent worker."""

import asyncio
import logging

from app.core.logging import setup_logging
from app.worker.agent_worker import register_executor, run_worker
from app.worker.product_analyst_executor import product_analyst_executor


def main() -> None:
    """Run the worker until interrupted."""
    # M5.2: bind the Product Analyst agent to its executor; other agents fall
    # back to the generic LLM executor.
    register_executor("product_analyst", product_analyst_executor)
    setup_logging()
    logging.getLogger(__name__).info("starting agent worker")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("agent worker stopped")


if __name__ == "__main__":
    main()
