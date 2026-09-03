"""Image generation service (M6): task lifecycle, cost guard, audit.

Orchestrates the pluggable ``integrations/image_gen.py`` gateway. Enforces
the monthly budget guard (``agent_budget``), persists task rows, and writes
audit events. High-cost models (>¥0.15/img) require approval before use.

Agent access: only through this service's whitelist functions; agents never
call the integration layer directly (AGENTS.md §2.3).
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select

from app.integrations import image_gen as image_gen_gateway
from app.models.image_gen import USE_CASES, ImageGenerationTask

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# Budget guard: default monthly limit in CNY (overridable via env).
DEFAULT_MONTHLY_BUDGET_CNY = Decimal("100.00")
# High-cost threshold: models above this require approval.
HIGH_COST_THRESHOLD_CNY = Decimal("0.15")
# Local storage directory for generated images (fallback when no object storage).
IMAGE_STORAGE_DIR = os.getenv("IMAGE_STORAGE_DIR", "data/generated_images")


class ImageGenServiceError(Exception):
    """Raised when the image generation service cannot fulfill a request."""


def get_image_gen_status() -> dict[str, Any]:
    """Return service status, available models, and budget config."""
    return {
        "service": "image_generation",
        "status": "operational",
        "available_models": image_gen_gateway.list_available_models(),
        "default_model": "wan2.7-image",
        "monthly_budget_cny": float(DEFAULT_MONTHLY_BUDGET_CNY),
        "high_cost_threshold_cny": float(HIGH_COST_THRESHOLD_CNY),
        "storage_dir": IMAGE_STORAGE_DIR,
        "use_cases": list(USE_CASES),
    }


async def get_monthly_spend(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    year: int | None = None,
    month: int | None = None,
) -> Decimal:
    """Return total image generation spend for a workspace in a month (CNY)."""
    now = datetime.now(UTC)
    y = year or now.year
    m = month or now.month
    start = datetime(y, m, 1, tzinfo=UTC)
    end = datetime(y + 1, 1, 1, tzinfo=UTC) if m == 12 else datetime(y, m + 1, 1, tzinfo=UTC)

    stmt = (
        select(ImageGenerationTask)
        .where(
            ImageGenerationTask.workspace_id == workspace_id,
            ImageGenerationTask.created_at >= start,
            ImageGenerationTask.created_at < end,
            ImageGenerationTask.status.in_(["generated", "approved", "published"]),
        )
    )
    result = await session.execute(stmt)
    tasks = result.scalars().all()
    return sum((t.cost_cny for t in tasks), Decimal("0"))


async def check_budget(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    requested_model: str,
) -> dict[str, Any]:
    """Check whether a generation request is within budget.

    Returns dict with ``allowed``, ``reason``, ``monthly_spend``, ``budget``.
    """
    budget = DEFAULT_MONTHLY_BUDGET_CNY
    spend = await get_monthly_spend(session, workspace_id=workspace_id)
    cost = Decimal(str(image_gen_gateway.get_model_cost(requested_model)))

    if spend + cost > budget:
        return {
            "allowed": False,
            "reason": f"monthly budget exceeded: spend={spend} budget={budget}",
            "monthly_spend": float(spend),
            "budget": float(budget),
            "requested_cost": float(cost),
        }

    requires_approval = cost > HIGH_COST_THRESHOLD_CNY
    return {
        "allowed": True,
        "requires_approval": requires_approval,
        "monthly_spend": float(spend),
        "budget": float(budget),
        "requested_cost": float(cost),
    }


async def create_generation_task(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    prompt: str,
    product_id: UUID | None = None,
    use_case: str = "main_image",
    model: str = "wan2.7-image",
    width: int = 1024,
    height: int = 1024,
    negative_prompt: str | None = None,
    trace_id: str | None = None,
) -> ImageGenerationTask:
    """Create a pending image generation task (does not call the API yet)."""
    if use_case not in USE_CASES:
        raise ImageGenServiceError(f"invalid use_case: {use_case}; must be one of {USE_CASES}")

    ws = workspace_id or DEFAULT_WORKSPACE_ID
    task = ImageGenerationTask(
        id=uuid4(),
        workspace_id=ws,
        product_id=product_id,
        prompt=prompt,
        negative_prompt=negative_prompt,
        use_case=use_case,
        requested_model=model,
        width=width,
        height=height,
        status="pending",
        trace_id=trace_id,
    )
    session.add(task)
    await session.flush()
    return task


async def execute_generation_task(
    session: AsyncSession,
    *,
    task_id: UUID,
    workspace_id: UUID | None = None,
) -> ImageGenerationTask:
    """Execute a pending task: call the gateway, persist result, update cost.

    Enforces budget check before calling the API. On failure, retries are
    handled by the gateway's fallback chain; the task status is set to
    ``failed`` with the error message.
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    stmt = select(ImageGenerationTask).where(
        ImageGenerationTask.id == task_id,
        ImageGenerationTask.workspace_id == ws,
    )
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise ImageGenServiceError(f"task not found: {task_id}")
    if task.status not in ("pending", "failed"):
        raise ImageGenServiceError(f"task already in status {task.status}; cannot execute")

    # Budget guard
    budget_check = await check_budget(session, workspace_id=ws, requested_model=task.requested_model)
    if not budget_check["allowed"]:
        task.status = "failed"
        task.error_message = budget_check["reason"]
        await session.flush()
        return task

    task.status = "generating"
    await session.flush()

    try:
        gen_result = await image_gen_gateway.generate_image(
            prompt=task.prompt,
            model=task.requested_model,
            width=task.width,
            height=task.height,
            negative_prompt=task.negative_prompt,
        )
        task.actual_model = gen_result.model
        task.cost_cny = Decimal(str(gen_result.cost_cny))
        task.image_url = gen_result.image_url

        # Persist base64 image to local storage if available
        if gen_result.image_b64:
            saved_path = await _save_image_locally(task.id, gen_result.image_b64)
            task.image_path = saved_path

        task.status = "generated"
        task.error_message = None
    except Exception as exc:
        task.status = "failed"
        task.error_message = str(exc)[:2000]
        task.retry_count += 1
        logger.exception("[image_gen] task %s failed", task.id)

    await session.flush()

    # Audit event
    from app.services import event_service
    await event_service.create_event(
        session,
        workspace_id=ws,
        event_type="image_gen.task_completed",
        entity_type="image_generation_task",
        entity_id=str(task.id),
        payload={
            "status": task.status,
            "model": task.actual_model or task.requested_model,
            "cost_cny": float(task.cost_cny),
            "use_case": task.use_case,
        },
        trace_id=task.trace_id,
    )

    return task


async def generate_image_and_save(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    prompt: str,
    product_id: UUID | None = None,
    use_case: str = "main_image",
    model: str = "wan2.7-image",
    width: int = 1024,
    height: int = 1024,
    negative_prompt: str | None = None,
    trace_id: str | None = None,
) -> ImageGenerationTask:
    """Convenience: create task + execute in one call (for API / Agent use)."""
    task = await create_generation_task(
        session,
        workspace_id=workspace_id,
        prompt=prompt,
        product_id=product_id,
        use_case=use_case,
        model=model,
        width=width,
        height=height,
        negative_prompt=negative_prompt,
        trace_id=trace_id,
    )
    return await execute_generation_task(session, task_id=task.id, workspace_id=workspace_id)


async def approve_image(
    session: AsyncSession,
    *,
    task_id: UUID,
    approved_by: str,
    workspace_id: UUID | None = None,
) -> ImageGenerationTask:
    """Approve a generated image for production use (human-in-the-loop)."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    stmt = select(ImageGenerationTask).where(
        ImageGenerationTask.id == task_id,
        ImageGenerationTask.workspace_id == ws,
    )
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise ImageGenServiceError(f"task not found: {task_id}")
    if task.status != "generated":
        raise ImageGenServiceError(f"only generated images can be approved; current status: {task.status}")

    task.status = "approved"
    task.approved_by = approved_by
    task.approved_at = datetime.now(UTC)
    await session.flush()
    return task


async def reject_image(
    session: AsyncSession,
    *,
    task_id: UUID,
    workspace_id: UUID | None = None,
) -> ImageGenerationTask:
    """Reject a generated image."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    stmt = select(ImageGenerationTask).where(
        ImageGenerationTask.id == task_id,
        ImageGenerationTask.workspace_id == ws,
    )
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise ImageGenServiceError(f"task not found: {task_id}")
    task.status = "rejected"
    await session.flush()
    return task


async def list_tasks(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    status: str | None = None,
    use_case: str | None = None,
    product_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List image generation tasks with filters."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    stmt = select(ImageGenerationTask).where(ImageGenerationTask.workspace_id == ws)
    if status:
        stmt = stmt.where(ImageGenerationTask.status == status)
    if use_case:
        stmt = stmt.where(ImageGenerationTask.use_case == use_case)
    if product_id:
        stmt = stmt.where(ImageGenerationTask.product_id == product_id)
    stmt = stmt.order_by(desc(ImageGenerationTask.created_at)).limit(limit).offset(offset)

    result = await session.execute(stmt)
    tasks = result.scalars().all()

    return {
        "tasks": [_task_to_dict(t) for t in tasks],
        "total": len(tasks),
        "limit": limit,
        "offset": offset,
    }


async def get_task(
    session: AsyncSession,
    *,
    task_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Get a single task by ID."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    stmt = select(ImageGenerationTask).where(
        ImageGenerationTask.id == task_id,
        ImageGenerationTask.workspace_id == ws,
    )
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    return _task_to_dict(task) if task else None


def _task_to_dict(task: ImageGenerationTask) -> dict[str, Any]:
    """Serialize a task row to a JSON-safe dict."""
    return {
        "id": str(task.id),
        "product_id": str(task.product_id) if task.product_id else None,
        "prompt": task.prompt,
        "use_case": task.use_case,
        "requested_model": task.requested_model,
        "actual_model": task.actual_model,
        "width": task.width,
        "height": task.height,
        "status": task.status,
        "image_url": task.image_url,
        "image_path": task.image_path,
        "cost_cny": float(task.cost_cny),
        "error_message": task.error_message,
        "retry_count": task.retry_count,
        "approved_by": task.approved_by,
        "approved_at": task.approved_at.isoformat() if task.approved_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "trace_id": task.trace_id,
    }


async def _save_image_locally(task_id: UUID, image_b64: str) -> str | None:
    """Save a base64-encoded image to the local storage directory.

    Returns the relative path, or None on failure (non-fatal — the API URL
    is still available in the task row).
    """
    try:
        import base64
        os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)
        # Determine extension from base64 header (default to .png for SVG mock)
        ext = ".png"
        if image_b64.startswith("data:image/"):
            header = image_b64.split(",")[0]
            if "svg" in header:
                ext = ".svg"
            elif "jpeg" in header or "jpg" in header:
                ext = ".jpg"
            elif "webp" in header:
                ext = ".webp"
            b64_data = image_b64.split(",", 1)[1] if "," in image_b64 else image_b64
        else:
            b64_data = image_b64

        filename = f"{task_id}{ext}"
        filepath = os.path.join(IMAGE_STORAGE_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(b64_data))
        return filepath
    except Exception:
        logger.exception("[image_gen] failed to save image locally for task %s", task_id)
        return None
