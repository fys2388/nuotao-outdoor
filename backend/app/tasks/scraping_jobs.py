"""Scraping background/scheduled jobs (M5.16, compliance-gated).

Wraps :func:`app.services.scraping.run_scrape_job` so it can be enqueued
through the existing task queue. This module deliberately contains no business
logic - it only opens a DB session and delegates. Scraping stays disabled by
default (``SCRAPING_ENABLED=false``); the service refuses to run otherwise.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.core.database import async_session_factory
from app.services import scraping

logger = logging.getLogger(__name__)


async def run_scrape_job_task(
    *, workspace_id: UUID, urls: list[str], trace_id: str | None = None
) -> scraping.ScrapeJobResult:
    """Run a scraping job in a dedicated session (task-queue entry point)."""
    async with async_session_factory() as session:
        return await scraping.run_scrape_job(
            session,
            workspace_id=workspace_id,
            urls=urls,
            trace_id=trace_id,
        )
