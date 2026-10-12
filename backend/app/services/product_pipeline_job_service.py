"""Async product pipeline run jobs backed by Redis.

The product pipeline run operation may take a long time due to:
1. AI product analysis (LLM calls)
2. Main image generation (AI image gen)
3. Prompt generation
4. Listing data generation
5. V3.0 selection gate evaluation

This can exceed gateway request limits (Cloudflare 100s timeout).
The API returns a job id immediately and the browser polls the persisted job state.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.product_pipeline_service import run_pipeline

logger = logging.getLogger(__name__)

JOB_PREFIX = "nuotao:product-pipeline:"
JOB_TTL_SECONDS = 86400

_background_tasks: set[asyncio.Task[Any]] = set()


def _job_key(job_id: str) -> str:
    return f"{JOB_PREFIX}{job_id}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def create_job(
    redis: Redis,
    *,
    product_info: dict[str, Any],
    auto_list: bool = False,
    include_images: bool = False,
) -> dict[str, Any]:
    """Persist a new pending job and schedule its background execution."""
    job_id = str(uuid4())
    job = {
        "job_id": job_id,
        "status": "pending",
        "product_info": product_info,
        "auto_list": auto_list,
        "include_images": include_images,
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
        "data": None,
        "error": None,
    }
    await _save_job(redis, job)
    _schedule_job(redis, job_id)
    return job


async def get_job(
    redis: Redis, job_id: str,
) -> dict[str, Any] | None:
    """Read a job snapshot; corrupt or expired jobs are treated as missing."""
    try:
        raw = await redis.get(_job_key(job_id))
    except Exception as exc:
        logger.error("Failed to read product pipeline job %s: %s", job_id, exc)
        raise
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        logger.error("Product pipeline job %s contains invalid JSON", job_id)
        return None
    return payload if isinstance(payload, dict) else None


async def _save_job(
    redis: Redis, job: dict[str, Any],
) -> None:
    await redis.set(
        _job_key(str(job["job_id"])),
        json.dumps(job, ensure_ascii=False, default=str),
        ex=JOB_TTL_SECONDS,
    )


async def _update_job(
    redis: Redis, job_id: str, **changes: Any,
) -> None:
    job = await get_job(redis, job_id)
    if not job:
        return
    job.update(changes)
    await _save_job(redis, job)


def _schedule_job(redis: Redis, job_id: str) -> None:
    task = asyncio.create_task(_run_job(redis, job_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _run_job(redis: Redis, job_id: str) -> None:
    """Background task that executes the product pipeline run operation."""
    from app.core.database import async_session_factory

    job = await get_job(redis, job_id)
    if not job:
        logger.error("Job %s not found", job_id)
        return

    await _update_job(redis, job_id, status="running", started_at=_now())

    try:
        product_info = job.get("product_info", {})
        auto_list = job.get("auto_list", False)
        include_images = job.get("include_images", False)

        # Create a database session
        async with async_session_factory() as db:
            # Execute the pipeline run operation
            result = await run_pipeline(
                product_info,
                auto_list=auto_list,
                include_images=include_images,
                session=db,
            )

            # Commit the database session
            await db.commit()

            await _update_job(
                redis, job_id,
                status="completed",
                data=result,
                finished_at=_now(),
            )

    except Exception as e:
        logger.error("Pipeline run job error: %s", str(e))
        await _update_job(
            redis, job_id,
            status="failed",
            error=str(e),
            finished_at=_now(),
        )
