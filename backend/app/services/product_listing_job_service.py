"""Async product listing jobs backed by Redis.

The confirm-list operation may take a long time due to:
1. AI image generation (if images are missing)
2. Vision quality checks
3. WC API calls
4. Image uploads to WC Media Library

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

from app.services.product_pipeline_service import (
    confirm_and_list,
    upsert_local_listed_product,
)
from app.core.workspace import DEFAULT_WORKSPACE_ID

logger = logging.getLogger(__name__)

JOB_PREFIX = "nuotao:product-listing:"
JOB_TTL_SECONDS = 86400

_background_tasks: set[asyncio.Task[Any]] = set()


def _job_key(job_id: str) -> str:
    return f"{JOB_PREFIX}{job_id}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def create_job(
    redis: Redis,
    *,
    pipeline_result: dict[str, Any],
    status: str = "publish",
    force: bool = False,
) -> dict[str, Any]:
    """Persist a new pending job and schedule its background execution."""
    job_id = str(uuid4())
    job = {
        "job_id": job_id,
        "status": "pending",
        "pipeline_result": pipeline_result,
        "status_param": status,
        "force": force,
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
        logger.error("Failed to read product listing job %s: %s", job_id, exc)
        raise
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        logger.error("Product listing job %s contains invalid JSON", job_id)
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
    """Background task that executes the confirm-and-list operation."""
    from app.core.database import async_session_factory

    job = await get_job(redis, job_id)
    if not job:
        logger.error("Job %s not found", job_id)
        return

    await _update_job(redis, job_id, status="running", started_at=_now())

    try:
        pipeline_result = job.get("pipeline_result", {})
        status_param = job.get("status_param", "publish")
        force = job.get("force", False)

        # Create a database session
        async with async_session_factory() as db:
            # Check V3.0 gate
            listing_data = (
                (pipeline_result or {}).get("data", {}).get("steps", {})
                .get("listing_data", {}).get("data", {})
            )
            sku = str(listing_data.get("sku") or "").strip()
            gate_override_notice = None

            if sku:
                from app.models.product import Product
                from sqlalchemy import select
                from app.services.product_pipeline_service import FUNNEL_REJECTED

                row = (
                    await db.execute(
                        select(Product.funnel_stage, Product.reject_reasons).where(
                            Product.workspace_id == DEFAULT_WORKSPACE_ID,
                            Product.sku == sku,
                            Product.deleted_at.is_(None),
                        )
                    )
                ).first()
                if row is not None and row.funnel_stage == FUNNEL_REJECTED:
                    hard_reasons = [
                        item.get("detail") or item.get("rule_id")
                        for item in (row.reject_reasons or [])
                        if isinstance(item, dict)
                    ]
                    if hard_reasons:
                        detail = "；".join(str(item) for item in hard_reasons if item) or "触发一票否决"
                        logger.warning("confirm-list hard-veto rejected for sku=%s: %s", sku, detail)
                        await _update_job(
                            redis, job_id,
                            status="failed",
                            error=f"V3.0 一票否决，禁止上架：{detail}",
                            finished_at=_now(),
                        )
                        return
                    gate_override_notice = (
                        "该商品 Nuotao Score 低于 65（AI 评级 Reject，无一票否决红线），"
                        "已由人工确认放行；建议先在候选池补全成本/供应商数据后重评。"
                    )
                    logger.info(
                        "confirm-list low-score human override for sku=%s (no hard veto)", sku
                    )

            # Execute the confirm-and-list operation
            result = await confirm_and_list(
                pipeline_result,
                status=status_param,
                force=force,
                session=db,
            )

            if gate_override_notice and result.get("success"):
                result["gate_override_warning"] = gate_override_notice

            # Upsert to local product database
            if result.get("success") and listing_data:
                try:
                    data_section = (pipeline_result or {}).get("data", {})
                    product_info = data_section.get("product_info") or {}
                    source_url = (
                        product_info.get("source_url")
                        or product_info.get("url")
                        or product_info.get("source_1688_url")
                        or ""
                    )
                    local = await upsert_local_listed_product(
                        db,
                        listing_data,
                        result,
                        DEFAULT_WORKSPACE_ID,
                        source="pipeline",
                        source_url=source_url,
                    )
                    result["local_product_id"] = local.get("product_id")
                    result["local_created"] = local.get("created")
                except Exception as upsert_err:
                    logger.error("Local product upsert failed for sku=%s: %s", sku, upsert_err)
                    result["local_upsert_error"] = str(upsert_err)

            await _update_job(
                redis, job_id,
                status="completed",
                data=result,
                finished_at=_now(),
            )
            await db.commit()

    except Exception as e:
        logger.error("Confirm list job error: %s", str(e))
        await _update_job(
            redis, job_id,
            status="failed",
            error=str(e),
            finished_at=_now(),
        )
