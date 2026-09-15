"""Async product import jobs backed by Redis.

The 1688 import may wait for a Newton Agent long-running task, which can exceed
entry-gateway request limits. The API therefore returns a job id immediately
and the browser polls the persisted job state.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis

from app.services.product_pipeline_service import import_and_analyze_from_1688

logger = logging.getLogger(__name__)

JOB_PREFIX = "nuotao:product-import:"
JOB_TTL_SECONDS = 86400

_background_tasks: set[asyncio.Task[Any]] = set()


def _job_key(job_id: str) -> str:
    return f"{JOB_PREFIX}{job_id}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def create_job(
    redis: Redis,
    *,
    url_or_id: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    """Persist a new pending job and schedule its background execution."""
    job_id = str(uuid4())
    job = {
        "job_id": job_id,
        "status": "pending",
        "url_or_id": url_or_id,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
        "data": None,
        "error": None,
    }
    await _save_job(redis, job)
    _schedule_job(redis, job_id)
    return job


async def get_job(redis: Redis, job_id: str) -> dict[str, Any] | None:
    """Read a job snapshot; corrupt or expired jobs are treated as missing."""
    try:
        raw = await redis.get(_job_key(job_id))
    except Exception as exc:
        logger.error("Failed to read product import job %s: %s", job_id, exc)
        raise
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        logger.error("Product import job %s contains invalid JSON", job_id)
        return None
    return payload if isinstance(payload, dict) else None


async def _save_job(redis: Redis, job: dict[str, Any]) -> None:
    await redis.set(
        _job_key(str(job["job_id"])),
        json.dumps(job, ensure_ascii=False, default=str),
        ex=JOB_TTL_SECONDS,
    )


async def _update_job(redis: Redis, job_id: str, **changes: Any) -> None:
    job = await get_job(redis, job_id)
    if not job:
        return
    job.update(changes)
    await _save_job(redis, job)


async def _run_job(redis: Redis, job_id: str) -> None:
    job = await get_job(redis, job_id)
    if not job:
        return

    await _update_job(redis, job_id, status="running", started_at=_now())
    try:
        result = await import_and_analyze_from_1688(
            str(job["url_or_id"]),
            temperature=float(job.get("temperature", 0.3)),
            max_tokens=int(job.get("max_tokens", 2000)),
        )
        if result.get("success"):
            await _update_job(
                redis,
                job_id,
                status="succeeded",
                data=result.get("data"),
                error=None,
                finished_at=_now(),
            )
        else:
            await _update_job(
                redis,
                job_id,
                status="failed",
                data=result.get("data"),
                error=result.get("error") or "导入或分析失败",
                finished_at=_now(),
            )
    except Exception as exc:
        logger.exception("Product import job %s failed", job_id)
        await _update_job(
            redis,
            job_id,
            status="failed",
            data=None,
            error=str(exc),
            finished_at=_now(),
        )


def _schedule_job(redis: Redis, job_id: str) -> None:
    task = asyncio.create_task(_run_job(redis, job_id), name=f"product-import-{job_id}")
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
