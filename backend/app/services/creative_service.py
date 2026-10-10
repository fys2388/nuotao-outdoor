"""Creative Studio service layer (v0.17 C0).

Orchestrates the Creative Studio data model: briefs, assets, generation
runs, and reviews.  All operations are workspace-scoped and auditable.

This service wraps the Creative Gateway for actual AI operations and
persists lifecycle records.  Agent access is only through this service's
whitelist functions (AGENTS.md §2.3).

Key invariants:
- Every asset is traceable to a brief, product, and generation run
- QC must pass before an asset can be APPROVED
- All state transitions are recorded in creative_reviews
- Cost is tracked per generation run in CNY
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.integrations import creative_gateway
from app.integrations.creative_gateway import CreativeRequest
from app.integrations.image_gen import DEFAULT_MODEL as DEFAULT_IMAGE_MODEL
from app.integrations.image_gen import ImageGenError, list_available_models
from app.models.creative import (
    ASSET_STATUSES,
    ASSET_SOURCE_TYPES,
    BRIEF_STATUSES,
    BRIEF_TYPES,
    GENERATION_STATUSES,
    PROMPT_TEMPLATE_STATUSES,
    CreativeBrief,
    CreativeGenerationRun,
    CreativePromptTemplate,
    CreativeReview,
    CreativeStudioAsset,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.product import Product
    from app.models.creative import CreativeAutomationWorkflow

logger = logging.getLogger(__name__)

# Default workspace (M1: single workspace)
DEFAULT_WORKSPACE = DEFAULT_WORKSPACE_ID

# Budget guard: default monthly limit in CNY (overridable via env).
DEFAULT_MONTHLY_BUDGET_CNY = Decimal("200.00")
IMAGE_STORAGE_DIR = os.getenv("IMAGE_STORAGE_DIR", "data/generated_images")


class CreativeServiceError(Exception):
    """Raised when a Creative Studio operation cannot be completed."""


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def _validate_enum(value: str, valid: tuple[str, ...], name: str) -> None:
    """Raise if value is not in the valid tuple."""
    if value not in valid:
        raise CreativeServiceError(
            f"Invalid {name}: '{value}'; must be one of {valid}"
        )


# ---------------------------------------------------------------------------
# Brief CRUD
# ---------------------------------------------------------------------------


async def create_brief(
    session: "AsyncSession",
    *,
    workspace_id: UUID | None = None,
    product_id: UUID | None = None,
    listing_id: UUID | None = None,
    brief_type: str = "product_hero",
    objective: str | None = None,
    target_market: str | None = None,
    channel: str | None = None,
    visual_style: str | None = None,
    required_assets: list[dict[str, Any]] | None = None,
    constraints: dict[str, Any] | None = None,
    created_by: str | None = None,
    trace_id: str | None = None,
) -> CreativeBrief:
    """Create a new creative brief."""
    _validate_enum(brief_type, BRIEF_TYPES, "brief_type")

    ws = workspace_id or DEFAULT_WORKSPACE
    brief = CreativeBrief(
        id=uuid4(),
        workspace_id=ws,
        product_id=product_id,
        listing_id=listing_id,
        brief_type=brief_type,
        objective=objective,
        target_market=target_market,
        channel=channel,
        visual_style=visual_style,
        required_assets=required_assets or [],
        constraints=constraints or {},
        status="DRAFT",
        created_by=created_by,
        trace_id=trace_id,
    )
    session.add(brief)
    await session.flush()
    return brief


async def get_brief(
    session: "AsyncSession",
    *,
    brief_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Get a brief by ID."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeBrief).where(
        CreativeBrief.id == brief_id,
        CreativeBrief.workspace_id == ws,
    )
    result = await session.execute(stmt)
    brief = result.scalar_one_or_none()
    return _brief_to_dict(brief) if brief else None


async def list_briefs(
    session: "AsyncSession",
    *,
    workspace_id: UUID | None = None,
    status: str | None = None,
    product_id: UUID | None = None,
    brief_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List briefs with filters."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeBrief).where(CreativeBrief.workspace_id == ws)
    if status:
        stmt = stmt.where(CreativeBrief.status == status)
    if product_id:
        stmt = stmt.where(CreativeBrief.product_id == product_id)
    if brief_type:
        stmt = stmt.where(CreativeBrief.brief_type == brief_type)
    stmt = stmt.order_by(desc(CreativeBrief.created_at)).limit(limit).offset(offset)

    result = await session.execute(stmt)
    briefs = result.scalars().all()
    return {
        "briefs": [_brief_to_dict(b) for b in briefs],
        "total": len(briefs),
        "limit": limit,
        "offset": offset,
    }


async def update_brief_status(
    session: "AsyncSession",
    *,
    brief_id: UUID,
    status: str,
    workspace_id: UUID | None = None,
    updated_by: str | None = None,
    trace_id: str | None = None,
) -> CreativeBrief:
    """Update a brief's status."""
    _validate_enum(status, BRIEF_STATUSES, "status")

    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeBrief).where(
        CreativeBrief.id == brief_id,
        CreativeBrief.workspace_id == ws,
    )
    result = await session.execute(stmt)
    brief = result.scalar_one_or_none()
    if not brief:
        raise CreativeServiceError(f"Brief not found: {brief_id}")

    brief.status = status
    if status == "COMPLETED" and updated_by:
        brief.approved_by = updated_by
        brief.approved_at = datetime.now(UTC)
    await session.flush()
    return brief


# ---------------------------------------------------------------------------
# Generation Run
# ---------------------------------------------------------------------------


async def create_generation_run(
    session: "AsyncSession",
    *,
    workspace_id: UUID | None = None,
    product_id: UUID | None = None,
    brief_id: UUID | None = None,
    operation: str = "generate",
    provider: str | None = None,
    model: str | None = None,
    input_asset_ids: list[str] | None = None,
    prompt_template_id: str | None = None,
    prompt_version: str | None = None,
    parameters: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> CreativeGenerationRun:
    """Create a queued generation run.

    P0-5: Uses dedup_key for idempotency. If a run with the same
    dedup_key already exists, returns the existing run instead of
    creating a duplicate.
    """
    import hashlib
    import json

    ws = workspace_id or DEFAULT_WORKSPACE

    # P0-5: Calculate dedup_key for idempotency
    # Key components: workspace_id, brief_id, operation, input_asset_ids, model, parameters
    dedup_components = {
        "workspace_id": str(ws),
        "brief_id": str(brief_id) if brief_id else None,
        "operation": operation,
        "input_asset_ids": sorted(input_asset_ids or []),
        "model": model,
        "parameters": json.dumps(parameters or {}, sort_keys=True),
    }
    dedup_key = hashlib.sha256(
        json.dumps(dedup_components, sort_keys=True).encode()
    ).hexdigest()[:64]

    # P0-5: Check for existing run with same dedup_key
    stmt = select(CreativeGenerationRun).where(
        CreativeGenerationRun.dedup_key == dedup_key,
        CreativeGenerationRun.workspace_id == ws,
    )
    result = await session.execute(stmt)
    existing_run = result.scalar_one_or_none()
    if existing_run:
        logger.info(
            f"[creative_service] Returning existing run {existing_run.id} "
            f"for dedup_key={dedup_key[:16]}..."
        )
        return existing_run

    run = CreativeGenerationRun(
        id=uuid4(),
        workspace_id=ws,
        product_id=product_id,
        brief_id=brief_id,
        operation=operation,
        provider=provider,
        model=model,
        input_asset_ids=input_asset_ids or [],
        prompt_template_id=prompt_template_id,
        prompt_version=prompt_version,
        parameters=parameters or {},
        status="QUEUED",
        trace_id=trace_id,
        dedup_key=dedup_key,
    )
    session.add(run)
    await session.flush()
    return run


async def get_generation_run(
    session: "AsyncSession",
    *,
    run_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Get a generation run by ID."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeGenerationRun).where(
        CreativeGenerationRun.id == run_id,
        CreativeGenerationRun.workspace_id == ws,
    )
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()
    return _run_to_dict(run) if run else None


async def list_generation_runs(
    session: "AsyncSession",
    *,
    workspace_id: UUID | None = None,
    status: str | None = None,
    product_id: UUID | None = None,
    brief_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List generation runs with filters."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeGenerationRun).where(CreativeGenerationRun.workspace_id == ws)
    if status:
        stmt = stmt.where(CreativeGenerationRun.status == status)
    if product_id:
        stmt = stmt.where(CreativeGenerationRun.product_id == product_id)
    if brief_id:
        stmt = stmt.where(CreativeGenerationRun.brief_id == brief_id)
    stmt = stmt.order_by(desc(CreativeGenerationRun.created_at)).limit(limit).offset(offset)

    result = await session.execute(stmt)
    runs = result.scalars().all()
    return {
        "runs": [_run_to_dict(r) for r in runs],
        "total": len(runs),
        "limit": limit,
        "offset": offset,
    }


async def execute_generation(
    session: "AsyncSession",
    *,
    run_id: UUID,
    workspace_id: UUID | None = None,
    prompt: str,
    model: str = DEFAULT_IMAGE_MODEL,
    width: int = 1024,
    height: int = 1024,
    reference_image: str | None = None,
    negative_prompt: str | None = None,
    trace_id: str | None = None,
) -> CreativeGenerationRun:
    """Execute a generation run: call gateway, persist result, create asset.

    This is the core C1 vertical slice: create run -> execute -> save
    asset -> QC -> human review.
    """
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeGenerationRun).where(
        CreativeGenerationRun.id == run_id,
        CreativeGenerationRun.workspace_id == ws,
    )
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise CreativeServiceError(f"Run not found: {run_id}")
    if run.status not in ("QUEUED", "FAILED"):
        raise CreativeServiceError(
            f"Run already in status {run.status}; cannot execute"
        )

    run.status = "RUNNING"
    run.model = model
    await session.flush()

    request = CreativeRequest(
        prompt=prompt,
        operation=run.operation,
        model=model,
        width=width,
        height=height,
        reference_image=reference_image,
        negative_prompt=negative_prompt,
        trace_id=trace_id,
    )

    try:
        gen_result = await creative_gateway.execute_creative_operation(request)

        run.status = "SUCCEEDED"
        run.provider = gen_result.provider
        run.model = gen_result.model
        run.latency_ms = gen_result.latency_ms
        run.actual_cost = Decimal(str(gen_result.cost_cny))
        run.estimated_cost = Decimal(str(gen_result.cost_cny))
        run.error_code = None
        run.error_message = None
        run.completed_at = datetime.now(UTC)

        # Create a creative asset from the result
        asset = await _create_asset_from_result(
            session,
            run=run,
            result=gen_result,
            workspace_id=ws,
        )
        run.output_asset_ids = [str(asset.id)]

        await session.flush()

    except ImageGenError as exc:
        run.status = "FAILED"
        run.error_code = "IMAGE_GEN_ERROR"
        run.error_message = str(exc)[:2000]
        run.completed_at = datetime.now(UTC)
        logger.exception("[creative] run %s failed", run_id)
        await session.flush()

    # Audit event
    from app.services import event_service
    await event_service.create_event(
        session,
        workspace_id=ws,
        event_type="creative.generation_completed",
        entity_type="creative_generation_run",
        entity_id=str(run.id),
        payload={
            "status": run.status,
            "operation": run.operation,
            "model": run.model,
            "cost_cny": float(run.actual_cost) if run.actual_cost else 0,
            "latency_ms": run.latency_ms,
        },
        trace_id=run.trace_id,
        commit=False,
    )

    return run


# ---------------------------------------------------------------------------
# Creative Asset
# ---------------------------------------------------------------------------


async def _create_asset_from_result(
    session: "AsyncSession",
    *,
    run: CreativeGenerationRun,
    result: creative_gateway.CreativeResult,
    workspace_id: UUID,
) -> CreativeStudioAsset:
    """Create a creative asset from a generation result."""
    asset_id = uuid4()

    # Save image to local storage if base64 is available
    storage_key = None
    if result.image_b64:
        storage_key = await _save_asset_locally(asset_id, result.image_b64)

    # Determine preview URL
    preview_url = result.image_url
    if storage_key:
        preview_url = f"/api/v1/creative/assets/{asset_id}/image"

    # Parse image dimensions if available
    width = None
    height = None
    ratio = None
    if result.raw_response:
        width = result.raw_response.get("width")
        height = result.raw_response.get("height")
        if width and height:
            ratio = _compute_ratio(width, height)

    asset = CreativeStudioAsset(
        id=asset_id,
        workspace_id=workspace_id,
        product_id=run.product_id,
        brief_id=run.brief_id,
        asset_type=run.operation,
        source_type="AI_GENERATED",
        storage_key=storage_key,
        preview_url=preview_url,
        width=width,
        height=height,
        ratio=ratio,
        mime_type="image/png",
        generation_run_id=run.id,
        version=1,
        status="GENERATED",
        quality_result={},
        compliance_result={},
        created_by="system",
        trace_id=run.trace_id,
    )
    session.add(asset)
    await session.flush()
    return asset


async def create_asset(
    session: "AsyncSession",
    *,
    workspace_id: UUID | None = None,
    product_id: UUID | None = None,
    brief_id: UUID | None = None,
    parent_asset_id: UUID | None = None,
    asset_type: str = "hero_image",
    source_type: str = "ORIGINAL",
    storage_key: str | None = None,
    preview_url: str | None = None,
    width: int | None = None,
    height: int | None = None,
    ratio: str | None = None,
    mime_type: str | None = None,
    generation_run_id: UUID | None = None,
    version: int = 1,
    status: str = "DRAFT",
    quality_result: dict[str, Any] | None = None,
    compliance_result: dict[str, Any] | None = None,
    created_by: str | None = None,
    trace_id: str | None = None,
) -> CreativeStudioAsset:
    """Create a creative asset (e.g. imported or manually uploaded)."""
    _validate_enum(source_type, ASSET_SOURCE_TYPES, "source_type")
    _validate_enum(status, ASSET_STATUSES, "status")

    ws = workspace_id or DEFAULT_WORKSPACE
    asset = CreativeStudioAsset(
        id=uuid4(),
        workspace_id=ws,
        product_id=product_id,
        brief_id=brief_id,
        parent_asset_id=parent_asset_id,
        asset_type=asset_type,
        source_type=source_type,
        storage_key=storage_key,
        preview_url=preview_url,
        width=width,
        height=height,
        ratio=ratio,
        mime_type=mime_type,
        generation_run_id=generation_run_id,
        version=version,
        status=status,
        quality_result=quality_result or {},
        compliance_result=compliance_result or {},
        created_by=created_by,
        trace_id=trace_id,
    )
    session.add(asset)
    await session.flush()
    return asset


async def get_asset(
    session: "AsyncSession",
    *,
    asset_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Get an asset by ID."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeStudioAsset).where(
        CreativeStudioAsset.id == asset_id,
        CreativeStudioAsset.workspace_id == ws,
    )
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    return _asset_to_dict(asset) if asset else None


async def list_assets(
    session: "AsyncSession",
    *,
    workspace_id: UUID | None = None,
    status: str | None = None,
    product_id: UUID | None = None,
    brief_id: UUID | None = None,
    source_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List assets with filters."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeStudioAsset).where(CreativeStudioAsset.workspace_id == ws)
    if status:
        stmt = stmt.where(CreativeStudioAsset.status == status)
    if product_id:
        stmt = stmt.where(CreativeStudioAsset.product_id == product_id)
    if brief_id:
        stmt = stmt.where(CreativeStudioAsset.brief_id == brief_id)
    if source_type:
        stmt = stmt.where(CreativeStudioAsset.source_type == source_type)
    stmt = stmt.order_by(desc(CreativeStudioAsset.created_at)).limit(limit).offset(offset)

    result = await session.execute(stmt)
    assets = result.scalars().all()
    return {
        "assets": [_asset_to_dict(a) for a in assets],
        "total": len(assets),
        "limit": limit,
        "offset": offset,
    }


async def update_asset(
    session: "AsyncSession",
    *,
    asset_id: UUID,
    workspace_id: UUID | None = None,
    status: str | None = None,
    quality_result: dict[str, Any] | None = None,
    compliance_result: dict[str, Any] | None = None,
    reviewed_by: str | None = None,
    approved_at: datetime | None = None,
    preview_url: str | None = None,
    wc_pushed_at: datetime | None = None,
    wc_media_id: str | None = None,
) -> CreativeStudioAsset:
    """Update a creative asset.

    P0-6: Supports updating wc_pushed_at and wc_media_id for WooCommerce tracking.
    """
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeStudioAsset).where(
        CreativeStudioAsset.id == asset_id,
        CreativeStudioAsset.workspace_id == ws,
    )
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    if not asset:
        raise CreativeServiceError(f"Asset not found: {asset_id}")

    if status is not None:
        asset.status = status
    if quality_result is not None:
        asset.quality_result = quality_result
    if compliance_result is not None:
        asset.compliance_result = compliance_result
    if reviewed_by is not None:
        asset.reviewed_by = reviewed_by
    if approved_at is not None:
        asset.approved_at = approved_at
    if preview_url is not None:
        asset.preview_url = preview_url
    if wc_pushed_at is not None:
        asset.wc_pushed_at = wc_pushed_at
    if wc_media_id is not None:
        asset.wc_media_id = wc_media_id

    await session.flush()
    return asset


# ---------------------------------------------------------------------------
# Quality Check
# ---------------------------------------------------------------------------


async def run_quality_check(
    session: "AsyncSession",
    *,
    asset_id: UUID,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Run quality check on an asset.

    C0 skeleton: basic checks (file exists, dimensions valid).
    C1 will add: AI-based quality scoring, product fidelity check.
    """
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeStudioAsset).where(
        CreativeStudioAsset.id == asset_id,
        CreativeStudioAsset.workspace_id == ws,
    )
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    if not asset:
        raise CreativeServiceError(f"Asset not found: {asset_id}")

    # Basic QC checks
    checks: list[dict[str, Any]] = []
    passed = True

    # Check 1: file exists
    if asset.storage_key:
        checks.append({"check": "file_exists", "passed": True, "detail": asset.storage_key})
    else:
        checks.append({"check": "file_exists", "passed": False, "detail": "No storage key"})
        passed = False

    # Check 2: dimensions
    if asset.width and asset.height:
        checks.append({
            "check": "dimensions",
            "passed": True,
            "detail": f"{asset.width}x{asset.height}",
        })
    else:
        checks.append({"check": "dimensions", "passed": False, "detail": "No dimensions"})
        passed = False

    # Check 3: source type
    if asset.source_type in ASSET_SOURCE_TYPES:
        checks.append({"check": "source_type", "passed": True, "detail": asset.source_type})
    else:
        checks.append({"check": "source_type", "passed": False, "detail": asset.source_type})
        passed = False

    qc_result = {
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "checks": checks,
        "checked_at": datetime.now(UTC).isoformat(),
        "checked_by": "qc_bot_v1",
    }

    asset.quality_result = qc_result
    if passed:
        asset.status = "QC_PASSED"
    else:
        asset.status = "REJECTED"

    await session.flush()

    # Record review
    review = CreativeReview(
        id=uuid4(),
        workspace_id=ws,
        asset_id=asset.id,
        review_type="quality_check",
        reviewer_type="AI",
        result="approved" if passed else "rejected",
        reasons=qc_result,
        reviewer_id="qc_bot_v1",
        trace_id=trace_id,
    )
    session.add(review)
    await session.flush()

    return qc_result


# ---------------------------------------------------------------------------
# Human Review
# ---------------------------------------------------------------------------


async def review_asset(
    session: "AsyncSession",
    *,
    asset_id: UUID,
    result: str,
    reasons: list[str] | None = None,
    reviewer_id: str,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> CreativeStudioAsset:
    """Record a human review decision on an asset."""
    if result not in ("approved", "rejected"):
        raise CreativeServiceError(f"Invalid review result: {result}")

    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeStudioAsset).where(
        CreativeStudioAsset.id == asset_id,
        CreativeStudioAsset.workspace_id == ws,
    )
    result_obj = await session.execute(stmt)
    asset = result_obj.scalar_one_or_none()
    if not asset:
        raise CreativeServiceError(f"Asset not found: {asset_id}")

    # Check that QC passed before approving
    if result == "approved":
        if asset.status not in ("QC_PASSED", "PENDING_REVIEW"):
            raise CreativeServiceError(
                f"Asset must pass QC before approval; current status: {asset.status}"
            )

    asset.status = "APPROVED" if result == "approved" else "REJECTED"
    asset.reviewed_by = reviewer_id
    if result == "approved":
        asset.approved_at = datetime.now(UTC)

    await session.flush()

    # Record review
    review = CreativeReview(
        id=uuid4(),
        workspace_id=ws,
        asset_id=asset.id,
        review_type="human_review",
        reviewer_type="HUMAN",
        result=result,
        reasons=reasons or [],
        reviewer_id=reviewer_id,
        trace_id=trace_id,
    )
    session.add(review)
    await session.flush()

    # Audit event
    from app.services import event_service
    await event_service.create_event(
        session,
        workspace_id=ws,
        event_type="creative.asset_reviewed",
        entity_type="creative_asset",
        entity_id=str(asset.id),
        payload={
            "result": result,
            "reviewer": reviewer_id,
            "asset_type": asset.asset_type,
        },
        trace_id=trace_id,
        commit=False,
    )

    return asset


async def list_reviews(
    session: "AsyncSession",
    *,
    workspace_id: UUID | None = None,
    asset_id: UUID | None = None,
    review_type: str | None = None,
    result: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List creative reviews."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativeReview).where(CreativeReview.workspace_id == ws)
    if asset_id:
        stmt = stmt.where(CreativeReview.asset_id == asset_id)
    if review_type:
        stmt = stmt.where(CreativeReview.review_type == review_type)
    if result:
        stmt = stmt.where(CreativeReview.result == result)
    stmt = stmt.order_by(desc(CreativeReview.created_at)).limit(limit).offset(offset)

    result_obj = await session.execute(stmt)
    reviews = result_obj.scalars().all()
    return {
        "reviews": [_review_to_dict(r) for r in reviews],
        "total": len(reviews),
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Cost Tracking
# ---------------------------------------------------------------------------


async def get_monthly_cost(
    session: "AsyncSession",
    *,
    workspace_id: UUID | None = None,
    year: int | None = None,
    month: int | None = None,
) -> Decimal:
    """Return total creative generation cost for a month."""
    now = datetime.now(UTC)
    y = year or now.year
    m = month or now.month
    start = datetime(y, m, 1, tzinfo=UTC)
    end = datetime(y + 1, 1, 1, tzinfo=UTC) if m == 12 else datetime(y, m + 1, 1, tzinfo=UTC)

    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = (
        select(CreativeGenerationRun.actual_cost)
        .where(
            CreativeGenerationRun.workspace_id == ws,
            CreativeGenerationRun.created_at >= start,
            CreativeGenerationRun.created_at < end,
            CreativeGenerationRun.status == "SUCCEEDED",
        )
    )
    result = await session.execute(stmt)
    costs = result.scalars().all()
    return sum((c for c in costs if c), Decimal("0"))


async def check_budget(
    session: "AsyncSession",
    *,
    workspace_id: UUID | None = None,
    requested_cost: Decimal | None = None,
) -> dict[str, Any]:
    """Check whether a generation is within the monthly budget."""
    ws = workspace_id or DEFAULT_WORKSPACE
    spend = await get_monthly_cost(session, workspace_id=ws)
    cost = requested_cost or Decimal("0")

    if spend + cost > DEFAULT_MONTHLY_BUDGET_CNY:
        return {
            "allowed": False,
            "reason": f"monthly budget exceeded: spend={spend} budget={DEFAULT_MONTHLY_BUDGET_CNY}",
            "monthly_spend": float(spend),
            "budget": float(DEFAULT_MONTHLY_BUDGET_CNY),
            "requested_cost": float(cost),
        }
    return {
        "allowed": True,
        "monthly_spend": float(spend),
        "budget": float(DEFAULT_MONTHLY_BUDGET_CNY),
        "requested_cost": float(cost),
    }


# ---------------------------------------------------------------------------
# Status / Discovery
# ---------------------------------------------------------------------------


def get_creative_status() -> dict[str, Any]:
    """Return Creative Studio service status and capabilities."""
    return {
        "service": "creative_studio",
        "version": "0.17.0",
        "status": "operational",
        "operations": creative_gateway.list_operations(),
        "image_models": list_available_models(),
        "monthly_budget_cny": float(DEFAULT_MONTHLY_BUDGET_CNY),
        "storage_dir": IMAGE_STORAGE_DIR,
    }


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _brief_to_dict(brief: CreativeBrief) -> dict[str, Any]:
    return {
        "id": str(brief.id),
        "product_id": str(brief.product_id) if brief.product_id else None,
        "listing_id": str(brief.listing_id) if brief.listing_id else None,
        "brief_type": brief.brief_type,
        "objective": brief.objective,
        "target_market": brief.target_market,
        "channel": brief.channel,
        "visual_style": brief.visual_style,
        "required_assets": brief.required_assets,
        "constraints": brief.constraints,
        "status": brief.status,
        "created_by": brief.created_by,
        "approved_by": brief.approved_by,
        "approved_at": brief.approved_at.isoformat() if brief.approved_at else None,
        "created_at": brief.created_at.isoformat() if brief.created_at else None,
        "updated_at": brief.updated_at.isoformat() if brief.updated_at else None,
        "trace_id": brief.trace_id,
    }


def _asset_to_dict(asset: CreativeStudioAsset) -> dict[str, Any]:
    return {
        "id": str(asset.id),
        "product_id": str(asset.product_id) if asset.product_id else None,
        "brief_id": str(asset.brief_id) if asset.brief_id else None,
        "parent_asset_id": str(asset.parent_asset_id) if asset.parent_asset_id else None,
        "asset_type": asset.asset_type,
        "source_type": asset.source_type,
        "storage_key": asset.storage_key,
        "preview_url": asset.preview_url,
        "width": asset.width,
        "height": asset.height,
        "ratio": asset.ratio,
        "mime_type": asset.mime_type,
        "generation_run_id": str(asset.generation_run_id) if asset.generation_run_id else None,
        "version": asset.version,
        "status": asset.status,
        "quality_result": asset.quality_result,
        "compliance_result": asset.compliance_result,
        "created_by": asset.created_by,
        "reviewed_by": asset.reviewed_by,
        "approved_at": asset.approved_at.isoformat() if asset.approved_at else None,
        "wc_pushed_at": asset.wc_pushed_at.isoformat() if asset.wc_pushed_at else None,
        "wc_media_id": asset.wc_media_id,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
        "trace_id": asset.trace_id,
    }


def _run_to_dict(run: CreativeGenerationRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "product_id": str(run.product_id) if run.product_id else None,
        "brief_id": str(run.brief_id) if run.brief_id else None,
        "operation": run.operation,
        "provider": run.provider,
        "model": run.model,
        "input_asset_ids": run.input_asset_ids,
        "prompt_template_id": run.prompt_template_id,
        "prompt_version": run.prompt_version,
        "parameters": run.parameters,
        "output_asset_ids": run.output_asset_ids,
        "status": run.status,
        "provider_request_id": run.provider_request_id,
        "latency_ms": run.latency_ms,
        "input_units": run.input_units,
        "output_units": run.output_units,
        "estimated_cost": float(run.estimated_cost) if run.estimated_cost else None,
        "actual_cost": float(run.actual_cost) if run.actual_cost else None,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "trace_id": run.trace_id,
        "dedup_key": run.dedup_key,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _review_to_dict(review: CreativeReview) -> dict[str, Any]:
    return {
        "id": str(review.id),
        "asset_id": str(review.asset_id),
        "review_type": review.review_type,
        "reviewer_type": review.reviewer_type,
        "result": review.result,
        "reasons": review.reasons,
        "reviewer_id": review.reviewer_id,
        "created_at": review.created_at.isoformat() if review.created_at else None,
        "trace_id": review.trace_id,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_ratio(width: int, height: int) -> str:
    """Compute a simplified aspect ratio string."""
    if width == height:
        return "1:1"
    if width > height:
        # Landscape
        if width / height > 2:
            return "16:9"
        return "4:3"
    else:
        # Portrait
        if height / width > 2:
            return "9:16"
        return "3:4"


async def _save_asset_locally(asset_id: UUID, image_b64: str) -> str | None:
    """Save a base64-encoded image to the local storage directory."""
    try:
        import base64
        os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)
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

        filename = f"{asset_id}{ext}"
        filepath = os.path.join(IMAGE_STORAGE_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(b64_data))
        return filepath
    except Exception:
        logger.exception("[creative] failed to save asset locally for %s", asset_id)
        return None


# ===========================================================================
# C1: Creative Workspace — Product Master → Creative Studio
# ===========================================================================


async def get_workspace(
    session: "AsyncSession",
    *,
    product_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Get the Creative Workspace state for a product.

    Returns product info, briefs, assets, generation runs, and reviews
    all aggregated into a single workspace view.
    """
    from app.models.product import Product

    ws = workspace_id or DEFAULT_WORKSPACE

    # Get product
    stmt = select(Product).where(
        Product.id == product_id,
        Product.workspace_id == ws,
        Product.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise CreativeServiceError(f"Product not found: {product_id}")

    # Get briefs
    briefs_result = await list_briefs(
        session, workspace_id=ws, product_id=product_id, limit=50
    )

    # Get assets
    assets_result = await list_assets(
        session, workspace_id=ws, product_id=product_id, limit=100
    )

    # Get generation runs
    runs_result = await list_generation_runs(
        session, workspace_id=ws, product_id=product_id, limit=50
    )

    # Count approved assets
    approved_count = sum(
        1 for a in assets_result["assets"] if a["status"] == "APPROVED"
    )

    # Count pending review
    pending_review_count = sum(
        1 for a in assets_result["assets"] if a["status"] == "PENDING_REVIEW"
    )

    return {
        "product": {
            "id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "description": product.description,
            "category": product.category,
            "brand": product.brand,
            "target_market": product.target_market,
            "status": product.status,
            "mastered_at": product.mastered_at.isoformat() if product.mastered_at else None,
            "tags": product.tags,
            "attributes": product.attributes,
        },
        "summary": {
            "total_briefs": briefs_result["total"],
            "total_assets": assets_result["total"],
            "approved_assets": approved_count,
            "pending_review": pending_review_count,
            "total_runs": runs_result["total"],
        },
        "briefs": briefs_result["briefs"],
        "assets": assets_result["assets"],
        "runs": runs_result["runs"],
    }


async def create_brief_from_product(
    session: "AsyncSession",
    *,
    product_id: UUID,
    workspace_id: UUID | None = None,
    objective: str | None = None,
    channel: str | None = None,
    target_market: str | None = None,
    visual_style: str | None = None,
    created_by: str | None = None,
    trace_id: str | None = None,
) -> CreativeBrief:
    """Auto-generate a creative brief from product data.

    Reads product attributes, target market, and category to derive
    required asset types and visual style recommendations.
    """
    from app.models.product import Product

    ws = workspace_id or DEFAULT_WORKSPACE

    stmt = select(Product).where(
        Product.id == product_id,
        Product.workspace_id == ws,
        Product.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise CreativeServiceError(f"Product not found: {product_id}")

    # Derive brief parameters from product data
    product_market = target_market or product.target_market or "US"
    product_channel = channel or "independent"
    product_style = visual_style or _derive_visual_style(product)
    product_objective = objective or (
        f"Generate creative assets for {product.name} targeting {product_market} market"
    )

    # Derive required assets based on product category
    required_assets = _derive_required_assets(product)

    brief = await create_brief(
        session,
        workspace_id=ws,
        product_id=product_id,
        brief_type="product_hero",
        objective=product_objective,
        target_market=product_market,
        channel=product_channel,
        visual_style=product_style,
        required_assets=required_assets,
        constraints={
            "budget_cny": 5.00,
            "max_retries": 2,
            "approval_required": True,
        },
        created_by=created_by or "workspace_auto",
        trace_id=trace_id,
    )

    return brief


def _derive_visual_style(product: "Product") -> str:
    """Derive visual style from product attributes."""
    attrs = product.attributes or {}
    style_keywords = []

    if product.category:
        cat = product.category.lower()
        if "outdoor" in cat or "camping" in cat:
            style_keywords.append("outdoor lifestyle")
        elif "fitness" in cat or "sport" in cat:
            style_keywords.append("active fitness")
        elif "home" in cat:
            style_keywords.append("modern home")

    if attrs.get("color"):
        style_keywords.append(str(attrs["color"]))
    if attrs.get("material"):
        style_keywords.append(str(attrs["material"]))

    if style_keywords:
        return ", ".join(style_keywords)
    return "clean product photography, studio lighting"


def _derive_required_assets(product: "Product") -> list[dict[str, Any]]:
    """Derive required asset types from product category and attributes."""
    assets = []
    cat = (product.category or "").lower()

    # Hero image (always required)
    assets.append({
        "type": "hero_image",
        "count": 1,
        "aspect_ratio": "1:1",
        "description": "Main product image with clean background",
    })

    # Lifestyle image (for outdoor/fitness products)
    if any(k in cat for k in ("outdoor", "camping", "fitness", "sport")):
        assets.append({
            "type": "lifestyle_scene",
            "count": 1,
            "aspect_ratio": "4:3",
            "description": "Product in natural outdoor setting",
        })

    # Detail image (always)
    assets.append({
        "type": "detail_scene",
        "count": 1,
        "aspect_ratio": "1:1",
        "description": "Close-up product detail shot",
    })

    # Banner (for B2C listing)
    assets.append({
        "type": "banner",
        "count": 1,
        "aspect_ratio": "16:9",
        "description": "Listing banner with product and key selling points",
    })

    return assets


async def add_asset_to_listing(
    session: "AsyncSession",
    *,
    asset_id: UUID,
    listing_job_id: UUID,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Add an approved asset to a listing job's asset set.

    Only APPROVED assets can be added to a listing. The asset URL is
    injected into the listing job's payload for WooCommerce publishing.
    """
    from app.models.listing_job import ListingJob

    ws = workspace_id or DEFAULT_WORKSPACE

    # Verify asset is approved
    asset = await get_asset(session, asset_id=asset_id, workspace_id=ws)
    if not asset:
        raise CreativeServiceError(f"Asset not found: {asset_id}")
    if asset["status"] != "APPROVED":
        raise CreativeServiceError(
            f"Asset must be APPROVED before adding to listing; current status: {asset['status']}"
        )

    # Get listing job
    stmt = select(ListingJob).where(
        ListingJob.id == listing_job_id,
        ListingJob.workspace_id == ws,
    )
    result = await session.execute(stmt)
    listing_job = result.scalar_one_or_none()
    if not listing_job:
        raise CreativeServiceError(f"Listing job not found: {listing_job_id}")

    # Add asset to listing payload
    payload = listing_job.payload or {}
    image_assets = payload.get("creative_assets", [])
    image_assets.append({
        "asset_id": str(asset_id),
        "preview_url": asset["preview_url"],
        "storage_key": asset["storage_key"],
        "asset_type": asset["asset_type"],
        "version": asset["version"],
        "approved_at": asset["approved_at"],
    })
    payload["creative_assets"] = image_assets

    # If this is the first hero image, also set it as the main image
    if asset["asset_type"] == "hero_image" and not payload.get("images"):
        if asset["preview_url"]:
            payload["images"] = [
                {"src": asset["preview_url"], "alt": asset.get("asset_type", "product image")}
            ]

    listing_job.payload = payload
    await session.flush()

    return {
        "listing_job_id": str(listing_job_id),
        "asset_id": str(asset_id),
        "total_assets": len(image_assets),
        "payload_updated": True,
    }


async def get_listing_assets(
    session: "AsyncSession",
    *,
    listing_job_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Get all creative assets attached to a listing job."""
    from app.models.listing_job import ListingJob

    ws = workspace_id or DEFAULT_WORKSPACE

    stmt = select(ListingJob).where(
        ListingJob.id == listing_job_id,
        ListingJob.workspace_id == ws,
    )
    result = await session.execute(stmt)
    listing_job = result.scalar_one_or_none()
    if not listing_job:
        raise CreativeServiceError(f"Listing job not found: {listing_job_id}")

    payload = listing_job.payload or {}
    return {
        "listing_job_id": str(listing_job_id),
        "status": listing_job.status,
        "creative_assets": payload.get("creative_assets", []),
        "images": payload.get("images", []),
    }


# ===================================================================
# Prompt Template Registry (C2)
# ===================================================================


async def create_prompt_template(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    template_key: str,
    name: str,
    description: str | None = None,
    asset_type: str = "hero_image",
    category: str = "general",
    prompt_text: str,
    variables: dict[str, Any] | None = None,
    default_parameters: dict[str, Any] | None = None,
    version: str = "1.0.0",
    status: str = "DRAFT",
    quality_score: float | None = None,
    created_by: str | None = None,
    trace_id: str | None = None,
) -> CreativePromptTemplate:
    """Create a new prompt template."""
    ws = workspace_id or DEFAULT_WORKSPACE

    if status not in PROMPT_TEMPLATE_STATUSES:
        raise CreativeServiceError(f"Invalid status: {status}")

    template = CreativePromptTemplate(
        id=uuid4(),
        workspace_id=ws,
        template_key=template_key,
        name=name,
        description=description,
        asset_type=asset_type,
        category=category,
        prompt_text=prompt_text,
        variables=variables or {},
        default_parameters=default_parameters or {},
        version=version,
        status=status,
        quality_score=Decimal(str(quality_score)) if quality_score else None,
        usage_count=0,
        created_by=created_by,
        trace_id=trace_id,
    )
    session.add(template)
    await session.flush()
    return template


async def get_prompt_template(
    session: AsyncSession,
    *,
    template_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Get a prompt template by ID."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativePromptTemplate).where(
        CreativePromptTemplate.id == template_id,
        CreativePromptTemplate.workspace_id == ws,
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if not template:
        return None
    return _prompt_template_to_dict(template)


async def get_prompt_template_by_key(
    session: AsyncSession,
    *,
    template_key: str,
    workspace_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Get a prompt template by its key."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativePromptTemplate).where(
        CreativePromptTemplate.template_key == template_key,
        CreativePromptTemplate.workspace_id == ws,
        CreativePromptTemplate.status == "ACTIVE",
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if not template:
        return None
    return _prompt_template_to_dict(template)


async def list_prompt_templates(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    category: str | None = None,
    asset_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List prompt templates with optional filters."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativePromptTemplate).where(
        CreativePromptTemplate.workspace_id == ws
    )
    if category:
        stmt = stmt.where(CreativePromptTemplate.category == category)
    if asset_type:
        stmt = stmt.where(CreativePromptTemplate.asset_type == asset_type)
    if status:
        stmt = stmt.where(CreativePromptTemplate.status == status)
    stmt = stmt.order_by(CreativePromptTemplate.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    templates = result.scalars().all()
    return {
        "templates": [_prompt_template_to_dict(t) for t in templates],
        "total": len(templates),
        "limit": limit,
        "offset": offset,
    }


async def update_prompt_template(
    session: AsyncSession,
    *,
    template_id: UUID,
    workspace_id: UUID | None = None,
    name: str | None = None,
    description: str | None = None,
    prompt_text: str | None = None,
    variables: dict[str, Any] | None = None,
    default_parameters: dict[str, Any] | None = None,
    version: str | None = None,
    status: str | None = None,
    quality_score: float | None = None,
    trace_id: str | None = None,
) -> CreativePromptTemplate:
    """Update an existing prompt template."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativePromptTemplate).where(
        CreativePromptTemplate.id == template_id,
        CreativePromptTemplate.workspace_id == ws,
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if not template:
        raise CreativeServiceError(f"Template not found: {template_id}")

    if name is not None:
        template.name = name
    if description is not None:
        template.description = description
    if prompt_text is not None:
        template.prompt_text = prompt_text
    if variables is not None:
        template.variables = variables
    if default_parameters is not None:
        template.default_parameters = default_parameters
    if version is not None:
        template.version = version
    if status is not None:
        if status not in PROMPT_TEMPLATE_STATUSES:
            raise CreativeServiceError(f"Invalid status: {status}")
        template.status = status
    if quality_score is not None:
        template.quality_score = Decimal(str(quality_score))

    await session.flush()
    return template


async def archive_prompt_template(
    session: AsyncSession,
    *,
    template_id: UUID,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> CreativePromptTemplate:
    """Archive a prompt template (soft delete)."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativePromptTemplate).where(
        CreativePromptTemplate.id == template_id,
        CreativePromptTemplate.workspace_id == ws,
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if not template:
        raise CreativeServiceError(f"Template not found: {template_id}")

    template.status = "ARCHIVED"
    await session.flush()
    return template


async def increment_usage_count(
    session: AsyncSession,
    *,
    template_id: UUID,
    workspace_id: UUID | None = None,
) -> None:
    """Increment the usage count for a prompt template."""
    ws = workspace_id or DEFAULT_WORKSPACE
    stmt = select(CreativePromptTemplate).where(
        CreativePromptTemplate.id == template_id,
        CreativePromptTemplate.workspace_id == ws,
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template:
        template.usage_count = (template.usage_count or 0) + 1
        await session.flush()


def render_prompt(
    template: dict[str, Any],
    variables: dict[str, Any],
) -> str:
    """Render a prompt template by substituting variables.

    Uses simple string replacement: ``{variable_name}`` is replaced
    with the corresponding value from the variables dict.
    """
    prompt_text = template["prompt_text"]
    template_vars = template.get("variables", {})

    # Merge template defaults with provided variables
    merged_vars = {**template_vars, **variables}

    # Substitute {var_name} placeholders
    result = prompt_text
    for key, value in merged_vars.items():
        placeholder = "{" + key + "}"
        result = result.replace(placeholder, str(value))

    return result


def _prompt_template_to_dict(template: CreativePromptTemplate) -> dict[str, Any]:
    """Serialize a prompt template to a JSON-safe dict."""
    return {
        "id": str(template.id),
        "template_key": template.template_key,
        "name": template.name,
        "description": template.description,
        "asset_type": template.asset_type,
        "category": template.category,
        "prompt_text": template.prompt_text,
        "variables": template.variables or {},
        "default_parameters": template.default_parameters or {},
        "version": template.version,
        "status": template.status,
        "quality_score": float(template.quality_score) if template.quality_score else None,
        "usage_count": template.usage_count,
        "created_by": template.created_by,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


# ===================================================================
# Batch Generation Pipeline (C3)
# ===================================================================


async def generate_brief_assets(
    session: AsyncSession,
    *,
    brief_id: UUID,
    workspace_id: UUID | None = None,
    model: str = DEFAULT_IMAGE_MODEL,
    execute_immediately: bool = True,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Batch generate all assets required by a CreativeBrief.

    Reads the brief's required_assets, finds matching prompt templates
    by asset_type, renders prompts with product data, and creates
    generation runs for each asset.

    If execute_immediately=True, runs are executed synchronously.
    Otherwise, runs are queued for background processing.

    Returns a summary with all created runs and assets.
    """
    ws = workspace_id or DEFAULT_WORKSPACE

    # Get the brief
    stmt = select(CreativeBrief).where(
        CreativeBrief.id == brief_id,
        CreativeBrief.workspace_id == ws,
    )
    result = await session.execute(stmt)
    brief = result.scalar_one_or_none()
    if not brief:
        raise CreativeServiceError(f"Brief not found: {brief_id}")

    # Get product data for prompt rendering
    product_data: dict[str, Any] = {}
    if brief.product_id:
        from app.models.product import Product

        product_stmt = select(Product).where(
            Product.id == brief.product_id,
            Product.workspace_id == ws,
        )
        product_result = await session.execute(product_stmt)
        product = product_result.scalar_one_or_none()
        if product:
            product_data = {
                "product_name": product.name,
                "product_sku": product.sku,
                "product_category": product.category,
                "product_brand": product.brand,
                "product_description": product.description,
                "target_market": product.target_market,
                "weight_kg": str(product.weight_kg) if product.weight_kg else None,
                "tags": json.dumps(product.tags, ensure_ascii=False) if product.tags else None,
                "attributes": json.dumps(product.attributes, ensure_ascii=False) if product.attributes else None,
            }

    # Get required assets from the brief
    required_assets: list[dict[str, Any]] = brief.required_assets or []
    if not required_assets:
        raise CreativeServiceError("Brief has no required_assets defined")

    created_runs: list[dict[str, Any]] = []
    created_assets: list[dict[str, Any]] = []
    total_cost = Decimal("0")

    for asset_spec in required_assets:
        asset_type = asset_spec.get("asset_type", "hero_image")
        count = asset_spec.get("count", 1)

        for _ in range(count):
            # Find a matching prompt template by asset_type
            # Category lives on the Product, not on CreativeBrief (the brief
            # only carries brief_type/objective/target_market/channel). Reading
            # brief.category raised AttributeError and aborted every creative
            # generation run. product_data is already loaded above.
            template_data = await _find_template_for_asset_type(
                session,
                asset_type=asset_type,
                category=product_data.get("product_category"),
                workspace_id=ws,
            )

            # Render the prompt with product data
            prompt_text = ""
            prompt_template_id = None
            prompt_version = None
            if template_data:
                prompt_text = render_prompt(template_data, product_data)
                prompt_template_id = template_data["template_key"]
                prompt_version = template_data["version"]
                await increment_usage_count(
                    session,
                    template_id=UUID(template_data["id"]),
                    workspace_id=ws,
                )
            else:
                # Fallback: use the asset_type as a simple prompt
                prompt_text = f"Generate {asset_type} for {product_data.get('product_name', 'product')}"

            # Create a generation run.
            # The creative gateway routes on OPERATION type ("generate",
            # "background_replace", ...), which is a different axis from the
            # brief's ASSET type ("hero_image", "detail_scene", "banner").
            # Passing the asset type straight through raised
            # ImageGenError("Unknown operation type: hero_image") and failed
            # every generation run. All brief asset types are plain image
            # generation; the asset type stays recorded in
            # parameters.asset_spec below.
            run = await create_generation_run(
                session,
                workspace_id=ws,
                product_id=brief.product_id,
                brief_id=brief_id,
                operation="generate",
                model=model,
                prompt_template_id=prompt_template_id,
                prompt_version=prompt_version,
                parameters={
                    "asset_spec": asset_spec,
                    "product_data": product_data,
                },
                trace_id=trace_id,
            )
            run.prompt_text = prompt_text
            await session.flush()

            created_runs.append(_run_to_dict(run))

            # Execute immediately if requested
            if execute_immediately:
                # Parse width/height from asset_spec or template defaults
                width = 1024
                height = 1024
                aspect_ratio = asset_spec.get("aspect_ratio")
                if aspect_ratio:
                    if aspect_ratio == "1:1":
                        width, height = 2048, 2048
                    elif aspect_ratio == "3:4":
                        width, height = 1536, 2048
                    elif aspect_ratio == "4:3":
                        width, height = 2048, 1536

                # Get reference image from product if available
                reference_image = None
                if product_data.get("main_image_url"):
                    reference_image = product_data["main_image_url"]

                try:
                    updated_run = await execute_generation(
                        session,
                        run_id=run.id,
                        workspace_id=ws,
                        prompt=prompt_text,
                        model=model,
                        width=width,
                        height=height,
                        reference_image=reference_image,
                        trace_id=trace_id,
                    )
                    created_runs[-1] = _run_to_dict(updated_run)

                    if updated_run.output_asset_ids:
                        for asset_id_str in updated_run.output_asset_ids:
                            asset_data = await get_asset(
                                session,
                                asset_id=UUID(asset_id_str),
                                workspace_id=ws,
                            )
                            if asset_data:
                                created_assets.append(asset_data)
                    if updated_run.actual_cost:
                        total_cost += updated_run.actual_cost

                except CreativeServiceError as exc:
                    # Log but continue with other assets
                    logger.warning(
                        "[creative] batch: run %s failed: %s",
                        run.id,
                        exc,
                    )

    await session.flush()

    return {
        "brief_id": str(brief_id),
        "total_runs": len(created_runs),
        "total_assets": len(created_assets),
        "total_cost_cny": float(total_cost),
        "runs": created_runs,
        "assets": created_assets,
    }


async def _find_template_for_asset_type(
    session: AsyncSession,
    *,
    asset_type: str,
    category: str | None = None,
    workspace_id: UUID,
) -> dict[str, Any] | None:
    """Find an active prompt template matching the asset_type and optional category.

    Priority:
    1. Exact match on asset_type + category
    2. Match on asset_type only (general category)
    3. None
    """
    # Try exact match first
    stmt = select(CreativePromptTemplate).where(
        CreativePromptTemplate.asset_type == asset_type,
        CreativePromptTemplate.workspace_id == workspace_id,
        CreativePromptTemplate.status == "ACTIVE",
    )
    if category:
        stmt = stmt.where(CreativePromptTemplate.category == category)
    stmt = stmt.order_by(CreativePromptTemplate.usage_count.desc()).limit(1)
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template:
        return _prompt_template_to_dict(template)

    # Fallback: match on asset_type only
    stmt = select(CreativePromptTemplate).where(
        CreativePromptTemplate.asset_type == asset_type,
        CreativePromptTemplate.workspace_id == workspace_id,
        CreativePromptTemplate.status == "ACTIVE",
        CreativePromptTemplate.category == "general",
    )
    stmt = stmt.order_by(CreativePromptTemplate.usage_count.desc()).limit(1)
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template:
        return _prompt_template_to_dict(template)

    return None


# ===================================================================
# WooCommerce Integration (C4)
# ===================================================================


async def push_asset_to_woocommerce(
    session: AsyncSession,
    *,
    asset_id: UUID,
    workspace_id: UUID | None = None,
    as_featured_image: bool = True,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Push an approved creative asset to WooCommerce as a product image.

    Only APPROVED assets can be pushed. The image is uploaded to the
    WordPress media library via the WooCommerce REST API, and optionally
    set as the product's featured image or added to the gallery.

    P0-6: Prevents duplicate pushes by checking wc_pushed_at/wc_media_id.
    Also enforces publish gate: asset must be APPROVED + QC_PASSED.

    Requires WooCommerce REST API credentials in the product's meta.
    """
    ws = workspace_id or DEFAULT_WORKSPACE

    # Get the asset
    asset_data = await get_asset(session, asset_id=asset_id, workspace_id=ws)
    if not asset_data:
        raise CreativeServiceError(f"Asset not found: {asset_id}")

    # P0-6: Check if asset was already pushed to WooCommerce
    if asset_data.get("wc_pushed_at") or asset_data.get("wc_media_id"):
        return {
            "asset_id": str(asset_id),
            "wc_media_id": asset_data.get("wc_media_id"),
            "wc_media_url": asset_data.get("preview_url"),
            "as_featured_image": as_featured_image,
            "product_id": str(asset_data.get("product_id")),
            "already_pushed": True,
            "message": "Asset was already pushed to WooCommerce",
        }

    # P0-6: Publish gate - asset must be APPROVED
    if asset_data["status"] != "APPROVED":
        raise CreativeServiceError(
            f"Asset must be APPROVED before pushing to WooCommerce; current status: {asset_data['status']}"
        )

    # P0-6: Publish gate - asset must have passed QC
    quality_result = asset_data.get("quality_result", {})
    if quality_result and not quality_result.get("passed", False):
        raise CreativeServiceError(
            "Asset must pass QC before pushing to WooCommerce; "
            f"current QC status: {quality_result.get('passed', 'not_checked')}"
        )

    # Get the product
    product_id = asset_data.get("product_id")
    if not product_id:
        raise CreativeServiceError("Asset has no product_id; cannot push to WooCommerce")

    from app.models.product import Product

    stmt = select(Product).where(
        Product.id == UUID(product_id),
        Product.workspace_id == ws,
    )
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise CreativeServiceError(f"Product not found: {product_id}")

    # Check for WooCommerce credentials in product meta
    meta = product.meta or {}
    wc_base_url = meta.get("wc_base_url")
    wc_consumer_key = meta.get("wc_consumer_key")
    wc_consumer_secret = meta.get("wc_consumer_secret")
    wc_product_id = meta.get("wc_product_id")

    if not all([wc_base_url, wc_consumer_key, wc_consumer_secret, wc_product_id]):
        raise CreativeServiceError(
            "Product missing WooCommerce credentials (wc_base_url, wc_consumer_key, "
            "wc_consumer_secret, wc_product_id) in meta"
        )

    # Read the image file
    image_path = asset_data.get("storage_key")
    if not image_path:
        raise CreativeServiceError("Asset has no storage_key; cannot push image")

    from pathlib import Path

    image_file = Path(image_path)
    if not image_file.exists():
        raise CreativeServiceError(f"Image file not found: {image_path}")

    # Upload image to WooCommerce media library
    wc_media_id, wc_media_url = await _upload_image_to_woocommerce(
        base_url=wc_base_url,
        consumer_key=wc_consumer_key,
        consumer_secret=wc_consumer_secret,
        image_path=image_path,
        alt_text=f"{product.name} - {asset_data.get('asset_type', 'creative asset')}",
    )

    if not wc_media_id:
        raise CreativeServiceError("Failed to upload image to WooCommerce")

    # Update the product's images on WooCommerce
    await _update_wc_product_images(
        base_url=wc_base_url,
        consumer_key=wc_consumer_key,
        consumer_secret=wc_consumer_secret,
        wc_product_id=int(wc_product_id),
        media_id=wc_media_id,
        media_url=wc_media_url,
        as_featured_image=as_featured_image,
    )

    # P0-6: Update the asset with WC push tracking
    from datetime import datetime, UTC

    await update_asset(
        session,
        asset_id=asset_id,
        workspace_id=ws,
        preview_url=wc_media_url,
        wc_pushed_at=datetime.now(UTC),
        wc_media_id=str(wc_media_id),
    )

    # Audit event
    from app.services import event_service

    await event_service.create_event(
        session,
        workspace_id=ws,
        event_type="creative.asset_pushed_to_wc",
        entity_type="creative_asset",
        entity_id=str(asset_id),
        payload={
            "wc_media_id": wc_media_id,
            "wc_media_url": wc_media_url,
            "as_featured_image": as_featured_image,
        },
        trace_id=trace_id,
        commit=False,
    )

    await session.flush()

    return {
        "asset_id": str(asset_id),
        "wc_media_id": wc_media_id,
        "wc_media_url": wc_media_url,
        "as_featured_image": as_featured_image,
        "product_id": str(product_id),
        "already_pushed": False,
    }


async def _upload_image_to_woocommerce(
    *,
    base_url: str,
    consumer_key: str,
    consumer_secret: str,
    image_path: str,
    alt_text: str = "",
) -> tuple[int | None, str | None]:
    """Upload an image to WooCommerce media library.

    Uses the WordPress REST API v2 media endpoint.
    Returns (media_id, media_url) or (None, None) on failure.
    """
    import httpx

    endpoint = f"{base_url.rstrip('/')}/wp-json/wp/v2/media"

    try:
        with open(image_path, "rb") as f:
            file_content = f.read()

        filename = os.path.basename(image_path)
        content_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                endpoint,
                auth=(consumer_key, consumer_secret),
                files={"file": (filename, file_content, content_type)},
                data={
                    "alt": alt_text,
                    "source_url": f"{base_url.rstrip('/')}/wp-content/uploads/{filename}",
                },
            )

        if response.status_code == 201:
            data = response.json()
            return data.get("id"), data.get("source_url")
        else:
            logger.warning(
                "[creative] WC media upload failed: status=%d body=%s",
                response.status_code,
                response.text[:500],
            )
            return None, None

    except Exception as exc:
        logger.exception("[creative] WC media upload error: %s", exc)
        return None, None


async def _update_wc_product_images(
    *,
    base_url: str,
    consumer_key: str,
    consumer_secret: str,
    wc_product_id: int,
    media_id: int,
    media_url: str,
    as_featured_image: bool = True,
) -> bool:
    """Update a WooCommerce product's images with the new media.

    If as_featured_image=True, set the new image as featured image (ID 0).
    Otherwise, add it to the gallery.
    """
    import httpx

    endpoint = f"{base_url.rstrip('/')}/wc/v3/products/{wc_product_id}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First, get the current product images
            get_response = await client.get(
                endpoint,
                auth=(consumer_key, consumer_secret),
            )

            if get_response.status_code != 200:
                logger.warning(
                    "[creative] WC get product failed: status=%d",
                    get_response.status_code,
                )
                return False

            product_data = get_response.json()
            existing_images = product_data.get("images", [])

            # Build the new images list
            new_image_entry = {
                "id": media_id,
                "src": media_url,
                "alt": f"Product image {media_id}",
                "name": f"Image {media_id}",
            }

            if as_featured_image:
                # Put the new image first (as featured image)
                existing_images = [new_image_entry] + existing_images
            else:
                # Add to the end of the gallery
                existing_images = existing_images + [new_image_entry]

            # Update the product
            put_response = await client.put(
                endpoint,
                auth=(consumer_key, consumer_secret),
                json={"images": existing_images},
            )

            if put_response.status_code == 200:
                return True
            else:
                logger.warning(
                    "[creative] WC update product images failed: status=%d body=%s",
                    put_response.status_code,
                    put_response.text[:500],
                )
                return False

    except Exception as exc:
        logger.exception("[creative] WC update product images error: %s", exc)
        return False


# ===================================================================
# Creative Knowledge Learning (C7)
# ===================================================================


async def create_knowledge_entry(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    entry_type: str,
    title: str,
    content: str,
    product_id: UUID | None = None,
    asset_id: UUID | None = None,
    brief_id: UUID | None = None,
    category: str | None = None,
    asset_type: str | None = None,
    tags: list[str] | None = None,
    source: str = "manual",
    confidence: float = 0.0,
    success_count: int = 0,
    failure_count: int = 0,
    created_by: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Create a creative knowledge entry.

    Args:
        session: database session
        workspace_id: workspace identifier
        entry_type: type of knowledge (success_pattern, failure_pattern, etc.)
        title: short title for the entry
        content: detailed content describing the pattern
        product_id: optional product reference
        asset_id: optional asset reference
        brief_id: optional brief reference
        category: optional product category
        asset_type: optional asset type
        tags: optional tags for categorization
        source: source of the knowledge (manual, ai_extracted, feedback)
        confidence: confidence score (0-1)
        success_count: number of successful occurrences
        failure_count: number of failure occurrences
        created_by: creator identifier
        trace_id: optional trace identifier

    Returns:
        Dict with the created entry data.
    """
    from app.models.creative import CREATIVE_KNOWLEDGE_TYPES, CreativeKnowledgeEntry
    from decimal import Decimal

    if entry_type not in CREATIVE_KNOWLEDGE_TYPES:
        raise CreativeServiceError(f"Invalid entry_type: {entry_type}")

    entry = CreativeKnowledgeEntry(
        id=uuid4(),
        workspace_id=workspace_id,
        product_id=product_id,
        asset_id=asset_id,
        brief_id=brief_id,
        category=category,
        asset_type=asset_type,
        entry_type=entry_type,
        title=title,
        content=content,
        tags=tags or [],
        source=source,
        confidence=Decimal(str(confidence)),
        success_count=success_count,
        failure_count=failure_count,
        created_by=created_by,
        trace_id=trace_id,
    )
    session.add(entry)
    await session.flush()

    return _knowledge_entry_to_dict(entry)


async def list_knowledge_entries(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    entry_type: str | None = None,
    category: str | None = None,
    asset_type: str | None = None,
    product_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List creative knowledge entries with optional filters.

    Args:
        session: database session
        workspace_id: workspace identifier
        entry_type: optional filter by entry type
        category: optional filter by product category
        asset_type: optional filter by asset type
        product_id: optional filter by product
        limit: max entries to return
        offset: pagination offset

    Returns:
        Dict with entries and pagination info.
    """
    from app.models.creative import CreativeKnowledgeEntry

    stmt = select(CreativeKnowledgeEntry).where(
        CreativeKnowledgeEntry.workspace_id == workspace_id
    )

    if entry_type:
        stmt = stmt.where(CreativeKnowledgeEntry.entry_type == entry_type)
    if category:
        stmt = stmt.where(CreativeKnowledgeEntry.category == category)
    if asset_type:
        stmt = stmt.where(CreativeKnowledgeEntry.asset_type == asset_type)
    if product_id:
        stmt = stmt.where(CreativeKnowledgeEntry.product_id == product_id)

    stmt = stmt.order_by(CreativeKnowledgeEntry.created_at.desc())
    stmt = stmt.limit(limit).offset(offset)

    result = await session.execute(stmt)
    entries = result.scalars().all()

    return {
        "entries": [_knowledge_entry_to_dict(e) for e in entries],
        "total": len(entries),
        "limit": limit,
        "offset": offset,
    }


async def learn_from_asset_review(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    asset_id: UUID,
    review_result: str,
    review_reasons: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any] | None:
    """Extract knowledge from an asset review and create knowledge entries.

    Analyzes the review result and reasons to extract patterns that can
    improve future creative generation.

    Args:
        session: database session
        workspace_id: workspace identifier
        asset_id: asset identifier
        review_result: 'approved' or 'rejected'
        review_reasons: detailed reasons from the review
        trace_id: optional trace identifier

    Returns:
        Dict with the created knowledge entries, or None if no patterns found.
    """
    from app.models.creative import CreativeStudioAsset, CreativeReview

    # Get the asset
    asset_stmt = select(CreativeStudioAsset).where(
        CreativeStudioAsset.id == asset_id,
        CreativeStudioAsset.workspace_id == workspace_id,
    )
    asset_result = await session.execute(asset_stmt)
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise CreativeServiceError(f"Asset not found: {asset_id}")

    entries_created: list[dict[str, Any]] = []

    if review_result == "approved" and asset.status == "APPROVED":
        # Extract success pattern
        success_content = f"Asset {asset_id} was approved."
        if review_reasons:
            success_content += f" Reasons: {json.dumps(review_reasons)}"

        entry_data = await create_knowledge_entry(
            session,
            workspace_id=workspace_id,
            entry_type="success_pattern",
            title=f"Successful {asset.asset_type} for {asset.product_id or 'unknown product'}",
            content=success_content,
            product_id=asset.product_id,
            asset_id=asset.id,
            brief_id=asset.brief_id,
            category=None,  # Could be populated from product
            asset_type=asset.asset_type,
            tags=["success", asset.asset_type, review_result],
            source="review_extracted",
            confidence=0.8,
            success_count=1,
            created_by="learning_engine",
            trace_id=trace_id,
        )
        entries_created.append(entry_data)

    elif review_result == "rejected" or asset.status == "REJECTED":
        # Extract failure pattern
        failure_content = f"Asset {asset_id} was rejected."
        if review_reasons:
            failure_content += f" Reasons: {json.dumps(review_reasons)}"

        entry_data = await create_knowledge_entry(
            session,
            workspace_id=workspace_id,
            entry_type="failure_pattern",
            title=f"Failed {asset.asset_type} for {asset.product_id or 'unknown product'}",
            content=failure_content,
            product_id=asset.product_id,
            asset_id=asset.id,
            brief_id=asset.brief_id,
            category=None,
            asset_type=asset.asset_type,
            tags=["failure", asset.asset_type, review_result],
            source="review_extracted",
            confidence=0.8,
            failure_count=1,
            created_by="learning_engine",
            trace_id=trace_id,
        )
        entries_created.append(entry_data)

    if entries_created:
        return {
            "asset_id": str(asset_id),
            "entries_created": len(entries_created),
            "entries": entries_created,
        }

    return None


async def generate_learning_summary(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    category: str | None = None,
    asset_type: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """Generate a learning summary from recent creative knowledge.

    Aggregates knowledge entries to provide insights for the Creative Agent.

    Args:
        session: database session
        workspace_id: workspace identifier
        category: optional filter by product category
        asset_type: optional filter by asset type
        days: number of days to look back

    Returns:
        Dict with aggregated learning insights.
    """
    from app.models.creative import CreativeKnowledgeEntry
    from datetime import timedelta

    since = datetime.now(UTC) - timedelta(days=days)

    stmt = select(CreativeKnowledgeEntry).where(
        CreativeKnowledgeEntry.workspace_id == workspace_id,
        CreativeKnowledgeEntry.created_at >= since,
    )

    if category:
        stmt = stmt.where(CreativeKnowledgeEntry.category == category)
    if asset_type:
        stmt = stmt.where(CreativeKnowledgeEntry.asset_type == asset_type)

    result = await session.execute(stmt)
    entries = result.scalars().all()

    # Aggregate by entry type
    by_type: dict[str, list[dict[str, Any]]] = {}
    total_success = 0
    total_failure = 0

    for entry in entries:
        entry_dict = _knowledge_entry_to_dict(entry)
        if entry.entry_type not in by_type:
            by_type[entry.entry_type] = []
        by_type[entry.entry_type].append(entry_dict)
        total_success += entry.success_count
        total_failure += entry.failure_count

    return {
        "period_days": days,
        "total_entries": len(entries),
        "by_type": {
            k: {
                "count": len(v),
                "entries": v,
            }
            for k, v in by_type.items()
        },
        "total_success_count": total_success,
        "total_failure_count": total_failure,
        "success_ratio": total_success / (total_success + total_failure) if (total_success + total_failure) > 0 else 0,
    }


def _knowledge_entry_to_dict(entry) -> dict[str, Any]:
    """Convert a CreativeKnowledgeEntry to a dict."""
    return {
        "id": str(entry.id),
        "product_id": str(entry.product_id) if entry.product_id else None,
        "asset_id": str(entry.asset_id) if entry.asset_id else None,
        "brief_id": str(entry.brief_id) if entry.brief_id else None,
        "category": entry.category,
        "asset_type": entry.asset_type,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "content": entry.content,
        "tags": entry.tags or [],
        "source": entry.source,
        "confidence": float(entry.confidence) if entry.confidence else 0.0,
        "success_count": entry.success_count,
        "failure_count": entry.failure_count,
        "created_by": entry.created_by,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


# ===================================================================
# Creative Calibration (C8)
# ===================================================================

CALIBRATION_MODEL_VERSION = "creative-calibration-v1"
MIN_CALIBRATION_SAMPLES = 3


async def run_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    days: int = 30,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Run creative calibration: aggregate patterns from knowledge entries.

    Deterministically analyzes creative knowledge entries to discover:
    - High-performing prompt patterns
    - Common failure patterns
    - Recommended style adjustments
    - Template improvement suggestions

    The calibration run stays 'proposed' until human approval.

    Args:
        session: database session
        workspace_id: workspace identifier
        days: number of days to look back
        trace_id: optional trace identifier

    Returns:
        Dict with the calibration run data.
    """
    from app.models.creative import (
        CreativeCalibrationRun,
        CreativeKnowledgeEntry,
    )
    from app.services import event_service
    from datetime import timedelta

    since = datetime.now(UTC) - timedelta(days=days)

    # Load all knowledge entries from the period
    stmt = select(CreativeKnowledgeEntry).where(
        CreativeKnowledgeEntry.workspace_id == workspace_id,
        CreativeKnowledgeEntry.created_at >= since,
    )
    result = await session.execute(stmt)
    entries = list(result.scalars().all())

    sample_size = len(entries)
    if sample_size < MIN_CALIBRATION_SAMPLES:
        raise CreativeServiceError(
            f"Not enough knowledge entries for calibration "
            f"(need >= {MIN_CALIBRATION_SAMPLES}, got {sample_size})"
        )

    # Discover patterns
    successful_patterns, failure_patterns, metrics = _discover_patterns(entries)

    # Create calibration run
    run = CreativeCalibrationRun(
        id=uuid4(),
        workspace_id=workspace_id,
        status="proposed",
        model_version=CALIBRATION_MODEL_VERSION,
        input_snapshot={
            "model_version": CALIBRATION_MODEL_VERSION,
            "sample_size": sample_size,
            "period_days": days,
            "knowledge_entry_count": sample_size,
        },
        successful_patterns=successful_patterns,
        failure_patterns=failure_patterns,
        metrics=metrics,
        sample_size=sample_size,
        rationale=(
            "Deterministic pattern discovery from creative knowledge entries. "
            "Proposal only - creative rules are never modified automatically."
        ),
        trace_id=trace_id,
    )
    session.add(run)
    await session.flush()

    # Record event
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="creative.calibration_run_proposed",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={
            "run_id": str(run.id),
            "sample_size": sample_size,
            "success_count": metrics.get("success_count", 0),
            "failure_count": metrics.get("failure_count", 0),
        },
        trace_id=trace_id,
        commit=False,
    )

    return _calibration_run_to_dict(run)


def _discover_patterns(entries) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Discover success and failure patterns from knowledge entries.

    Args:
        entries: list of CreativeKnowledgeEntry objects

    Returns:
        Tuple of (successful_patterns, failure_patterns, metrics).
    """
    successful_patterns: dict[str, Any] = {
        "top_prompts": [],
        "top_styles": [],
        "top_asset_types": [],
        "high_confidence_entries": [],
    }

    failure_patterns: dict[str, Any] = {
        "common_issues": [],
        "low_confidence_entries": [],
        "repeated_failures": [],
    }

    metrics: dict[str, Any] = {
        "total_entries": len(entries),
        "success_count": 0,
        "failure_count": 0,
        "by_entry_type": {},
    }

    # Aggregate by entry type
    by_type: dict[str, list] = {}
    for entry in entries:
        if entry.entry_type not in by_type:
            by_type[entry.entry_type] = []
        by_type[entry.entry_type].append(entry)
        metrics["by_entry_type"][entry.entry_type] = len(by_type[entry.entry_type])

    # Analyze success patterns
    success_entries = [e for e in entries if e.entry_type == "success_pattern"]
    metrics["success_count"] = len(success_entries)

    if success_entries:
        # Top prompts by confidence
        sorted_by_confidence = sorted(success_entries, key=lambda e: e.confidence, reverse=True)
        for entry in sorted_by_confidence[:5]:
            successful_patterns["top_prompts"].append({
                "title": entry.title,
                "content": entry.content[:200],
                "confidence": float(entry.confidence),
                "tags": entry.tags or [],
            })

        # Top asset types
        asset_type_counts: dict[str, int] = {}
        for entry in success_entries:
            if entry.asset_type:
                asset_type_counts[entry.asset_type] = asset_type_counts.get(entry.asset_type, 0) + 1
        successful_patterns["top_asset_types"] = [
            {"asset_type": k, "count": v}
            for k, v in sorted(asset_type_counts.items(), key=lambda x: x[1], reverse=True)
        ]

        # High confidence entries
        high_conf = [e for e in success_entries if e.confidence >= 0.8]
        successful_patterns["high_confidence_entries"] = len(high_conf)

    # Analyze failure patterns
    failure_entries = [e for e in entries if e.entry_type == "failure_pattern"]
    metrics["failure_count"] = len(failure_entries)

    if failure_entries:
        # Common issues from failure content
        issue_keywords = ["blur", "low quality", "poor", "failed", "rejected", "inappropriate", "mismatch"]
        for entry in failure_entries:
            content_lower = entry.content.lower()
            for keyword in issue_keywords:
                if keyword in content_lower:
                    failure_patterns["common_issues"].append({
                        "issue": keyword,
                        "title": entry.title,
                        "asset_type": entry.asset_type,
                    })
                    break

        # Low confidence entries
        low_conf = [e for e in failure_entries if e.confidence < 0.5]
        failure_patterns["low_confidence_entries"] = len(low_conf)

        # Repeated failures (same asset_type failing multiple times)
        failure_by_type: dict[str, int] = {}
        for entry in failure_entries:
            if entry.asset_type:
                failure_by_type[entry.asset_type] = failure_by_type.get(entry.asset_type, 0) + 1
        failure_patterns["repeated_failures"] = [
            {"asset_type": k, "failure_count": v}
            for k, v in sorted(failure_by_type.items(), key=lambda x: x[1], reverse=True)
        ]

    # Calculate success ratio
    if metrics["success_count"] + metrics["failure_count"] > 0:
        metrics["success_ratio"] = round(
            metrics["success_count"] / (metrics["success_count"] + metrics["failure_count"]), 4
        )
    else:
        metrics["success_ratio"] = 0.0

    return successful_patterns, failure_patterns, metrics


async def approve_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Approve a creative calibration proposal (human-only).

    Args:
        session: database session
        workspace_id: workspace identifier
        run_id: calibration run identifier
        actor: approver identifier
        note: optional approval note
        trace_id: optional trace identifier

    Returns:
        Dict with the updated run data.
    """
    from app.models.creative import CreativeCalibrationRun
    from app.services import event_service

    stmt = select(CreativeCalibrationRun).where(
        CreativeCalibrationRun.workspace_id == workspace_id,
        CreativeCalibrationRun.id == run_id,
    )
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()

    if run is None:
        raise CreativeServiceError("Calibration run not found")
    if run.status != "proposed":
        raise CreativeServiceError("Calibration run is not proposed")

    now = datetime.now(UTC)
    run.status = "approved"
    run.approved_by = actor
    run.approved_at = now
    run.updated_at = now
    if note:
        run.rationale = (run.rationale or "") + f" | approved note: {note}"

    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="creative.calibration_run_approved",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={"run_id": str(run.id), "approved_by": actor, "note": note},
        trace_id=trace_id,
        commit=False,
    )

    return _calibration_run_to_dict(run)


async def reject_calibration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    run_id: UUID,
    actor: str,
    note: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Reject a creative calibration proposal (human-only).

    Args:
        session: database session
        workspace_id: workspace identifier
        run_id: calibration run identifier
        actor: rejecter identifier
        note: optional rejection note
        trace_id: optional trace identifier

    Returns:
        Dict with the updated run data.
    """
    from app.models.creative import CreativeCalibrationRun
    from app.services import event_service

    stmt = select(CreativeCalibrationRun).where(
        CreativeCalibrationRun.workspace_id == workspace_id,
        CreativeCalibrationRun.id == run_id,
    )
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()

    if run is None:
        raise CreativeServiceError("Calibration run not found")
    if run.status != "proposed":
        raise CreativeServiceError("Calibration run is not proposed")

    now = datetime.now(UTC)
    run.status = "rejected"
    run.approved_by = actor
    run.approved_at = now
    run.updated_at = now
    if note:
        run.rationale = (run.rationale or "") + f" | rejected note: {note}"

    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="creative.calibration_run_rejected",
        entity_type="workspace",
        entity_id=str(workspace_id),
        payload={"run_id": str(run.id), "rejected_by": actor, "note": note},
        trace_id=trace_id,
        commit=False,
    )

    return _calibration_run_to_dict(run)


async def list_calibration_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List creative calibration runs, newest first.

    Args:
        session: database session
        workspace_id: workspace identifier
        status: optional filter by status
        limit: max runs to return

    Returns:
        List of calibration run dicts.
    """
    from app.models.creative import CreativeCalibrationRun

    stmt = select(CreativeCalibrationRun).where(
        CreativeCalibrationRun.workspace_id == workspace_id
    )
    if status:
        stmt = stmt.where(CreativeCalibrationRun.status == status)
    stmt = stmt.order_by(CreativeCalibrationRun.created_at.desc()).limit(limit)

    result = await session.execute(stmt)
    runs = list(result.scalars().all())

    return [_calibration_run_to_dict(r) for r in runs]


def _calibration_run_to_dict(run) -> dict[str, Any]:
    """Convert a CreativeCalibrationRun to a dict."""
    return {
        "id": str(run.id),
        "status": run.status,
        "model_version": run.model_version,
        "input_snapshot": run.input_snapshot or {},
        "successful_patterns": run.successful_patterns or {},
        "failure_patterns": run.failure_patterns or {},
        "metrics": run.metrics or {},
        "sample_size": run.sample_size,
        "rationale": run.rationale,
        "approved_by": run.approved_by,
        "approved_at": run.approved_at.isoformat() if run.approved_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "trace_id": run.trace_id,
    }


# ===================================================================
# Creative Cost Tracking (C9)
# ===================================================================


async def create_cost_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    model: str,
    provider: str,
    asset_type: str,
    estimated_cost: Decimal,
    actual_cost: Decimal | None = None,
    generation_run_id: UUID | None = None,
    asset_id: UUID | None = None,
    brief_id: UUID | None = None,
    product_id: UUID | None = None,
    cost_category: str = "generation",
    image_count: int = 1,
    currency: str = "CNY",
    context: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Create a creative cost event.

    Args:
        session: database session
        workspace_id: workspace identifier
        model: model used for generation
        provider: provider name
        asset_type: type of asset (hero_image, detail_image, etc.)
        estimated_cost: estimated cost before generation
        actual_cost: actual cost after generation
        generation_run_id: optional generation run reference
        asset_id: optional asset reference
        brief_id: optional brief reference
        product_id: optional product reference
        cost_category: category of cost (generation, qc, calibration, etc.)
        image_count: number of images generated
        currency: currency code
        context: additional context data
        trace_id: optional trace identifier

    Returns:
        Dict with the created cost event data.
    """
    from app.models.creative import CreativeCostEvent

    event = CreativeCostEvent(
        id=uuid4(),
        workspace_id=workspace_id,
        generation_run_id=generation_run_id,
        asset_id=asset_id,
        brief_id=brief_id,
        product_id=product_id,
        model=model,
        provider=provider,
        asset_type=asset_type,
        cost_category=cost_category,
        estimated_cost=estimated_cost,
        actual_cost=actual_cost,
        currency=currency,
        image_count=image_count,
        context=context or {},
        trace_id=trace_id,
    )
    session.add(event)
    await session.flush()

    return _cost_event_to_dict(event)


async def get_cost_summary(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    year: int | None = None,
    month: int | None = None,
    asset_type: str | None = None,
    model: str | None = None,
    product_id: UUID | None = None,
    brief_id: UUID | None = None,
) -> dict[str, Any]:
    """Get a comprehensive cost summary with breakdowns.

    Args:
        session: database session
        workspace_id: workspace identifier
        year: optional year filter
        month: optional month filter
        asset_type: optional filter by asset type
        model: optional filter by model
        product_id: optional filter by product
        brief_id: optional filter by brief

    Returns:
        Dict with cost summary and breakdowns.
    """
    from app.models.creative import CreativeCostEvent
    from datetime import datetime as dt

    now = dt.now(UTC)
    y = year or now.year
    m = month or now.month

    # Calculate date range
    if m == 12:
        start = dt(y, 12, 1, tzinfo=UTC)
        end = dt(y + 1, 1, 1, tzinfo=UTC)
    else:
        start = dt(y, m, 1, tzinfo=UTC)
        end = dt(y, m + 1, 1, tzinfo=UTC)

    stmt = select(CreativeCostEvent).where(
        CreativeCostEvent.workspace_id == workspace_id,
        CreativeCostEvent.created_at >= start,
        CreativeCostEvent.created_at < end,
    )

    if asset_type:
        stmt = stmt.where(CreativeCostEvent.asset_type == asset_type)
    if model:
        stmt = stmt.where(CreativeCostEvent.model == model)
    if product_id:
        stmt = stmt.where(CreativeCostEvent.product_id == product_id)
    if brief_id:
        stmt = stmt.where(CreativeCostEvent.brief_id == brief_id)

    result = await session.execute(stmt)
    events = list(result.scalars().all())

    # Calculate totals
    total_estimated = sum(
        (e.estimated_cost for e in events if e.estimated_cost), Decimal("0")
    )
    total_actual = sum(
        (e.actual_cost for e in events if e.actual_cost), Decimal("0")
    )
    total_images = sum((e.image_count for e in events), 0)

    # Breakdown by model
    by_model: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.model not in by_model:
            by_model[event.model] = {
                "model": event.model,
                "provider": event.provider,
                "total_cost": Decimal("0"),
                "estimated_cost": Decimal("0"),
                "image_count": 0,
                "event_count": 0,
            }
        by_model[event.model]["total_cost"] += (event.actual_cost or event.estimated_cost)
        by_model[event.model]["estimated_cost"] += event.estimated_cost
        by_model[event.model]["image_count"] += event.image_count
        by_model[event.model]["event_count"] += 1

    # Breakdown by asset type
    by_asset_type: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.asset_type not in by_asset_type:
            by_asset_type[event.asset_type] = {
                "asset_type": event.asset_type,
                "total_cost": Decimal("0"),
                "image_count": 0,
                "event_count": 0,
            }
        by_asset_type[event.asset_type]["total_cost"] += (event.actual_cost or event.estimated_cost)
        by_asset_type[event.asset_type]["image_count"] += event.image_count
        by_asset_type[event.asset_type]["event_count"] += 1

    return {
        "period": f"{y}-{m:02d}",
        "total_estimated_cost": float(total_estimated),
        "total_actual_cost": float(total_actual),
        "total_images": total_images,
        "event_count": len(events),
        "avg_cost_per_image": float(total_actual / total_images) if total_images > 0 else 0,
        "by_model": [
            {**v, "total_cost": float(v["total_cost"]), "estimated_cost": float(v["estimated_cost"])}
            for v in by_model.values()
        ],
        "by_asset_type": [
            {**v, "total_cost": float(v["total_cost"])}
            for v in by_asset_type.values()
        ],
    }


async def get_cost_by_product(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    days: int = 30,
) -> dict[str, Any]:
    """Get cost breakdown for a specific product.

    Args:
        session: database session
        workspace_id: workspace identifier
        product_id: product identifier
        days: number of days to look back

    Returns:
        Dict with product cost breakdown.
    """
    from app.models.creative import CreativeCostEvent
    from datetime import timedelta

    since = datetime.now(UTC) - timedelta(days=days)

    stmt = select(CreativeCostEvent).where(
        CreativeCostEvent.workspace_id == workspace_id,
        CreativeCostEvent.product_id == product_id,
        CreativeCostEvent.created_at >= since,
    )
    result = await session.execute(stmt)
    events = list(result.scalars().all())

    total_cost = sum(
        (e.actual_cost or e.estimated_cost for e in events), Decimal("0")
    )
    total_images = sum((e.image_count for e in events), 0)

    # By asset type
    by_asset_type: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.asset_type not in by_asset_type:
            by_asset_type[event.asset_type] = {
                "asset_type": event.asset_type,
                "total_cost": Decimal("0"),
                "image_count": 0,
            }
        by_asset_type[event.asset_type]["total_cost"] += (event.actual_cost or event.estimated_cost)
        by_asset_type[event.asset_type]["image_count"] += event.image_count

    return {
        "product_id": str(product_id),
        "period_days": days,
        "total_cost": float(total_cost),
        "total_images": total_images,
        "avg_cost_per_image": float(total_cost / total_images) if total_images > 0 else 0,
        "by_asset_type": [
            {**v, "total_cost": float(v["total_cost"])}
            for v in by_asset_type.values()
        ],
    }


async def get_cost_by_brief(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    brief_id: UUID,
) -> dict[str, Any]:
    """Get cost breakdown for a specific brief.

    Args:
        session: database session
        workspace_id: workspace identifier
        brief_id: brief identifier

    Returns:
        Dict with brief cost breakdown.
    """
    from app.models.creative import CreativeCostEvent

    stmt = select(CreativeCostEvent).where(
        CreativeCostEvent.workspace_id == workspace_id,
        CreativeCostEvent.brief_id == brief_id,
    )
    result = await session.execute(stmt)
    events = list(result.scalars().all())

    total_cost = sum(
        (e.actual_cost or e.estimated_cost for e in events), Decimal("0")
    )
    total_images = sum((e.image_count for e in events), 0)

    # By model
    by_model: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.model not in by_model:
            by_model[event.model] = {
                "model": event.model,
                "total_cost": Decimal("0"),
                "image_count": 0,
            }
        by_model[event.model]["total_cost"] += (event.actual_cost or event.estimated_cost)
        by_model[event.model]["image_count"] += event.image_count

    return {
        "brief_id": str(brief_id),
        "total_cost": float(total_cost),
        "total_images": total_images,
        "event_count": len(events),
        "by_model": [
            {**v, "total_cost": float(v["total_cost"])}
            for v in by_model.values()
        ],
    }


async def check_budget_with_forecast(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    requested_cost: Decimal,
    budget: Decimal | None = None,
) -> dict[str, Any]:
    """Check budget with cost forecasting.

    Projects future costs based on historical spending patterns.

    Args:
        session: database session
        workspace_id: workspace identifier
        requested_cost: requested cost for the new generation
        budget: optional custom budget (defaults to DEFAULT_MONTHLY_BUDGET_CNY)

    Returns:
        Dict with budget check result including forecast.
    """
    from app.models.creative import CreativeCostEvent
    from datetime import datetime as dt

    budget = budget or DEFAULT_MONTHLY_BUDGET_CNY
    now = dt.now(UTC)

    # Current month spending
    start = dt(now.year, now.month, 1, tzinfo=UTC)
    stmt = select(CreativeCostEvent.actual_cost).where(
        CreativeCostEvent.workspace_id == workspace_id,
        CreativeCostEvent.created_at >= start,
        CreativeCostEvent.actual_cost.isnot(None),
    )
    result = await session.execute(stmt)
    costs = result.scalars().all()
    current_spend = sum(costs, Decimal("0"))

    # Previous 3 months average
    prev_costs: list[Decimal] = []
    for i in range(1, 4):
        prev_month = now.month - i
        prev_year = now.year
        if prev_month < 1:
            prev_month = 12 + prev_month
            prev_year -= 1
        prev_start = dt(prev_year, prev_month, 1, tzinfo=UTC)
        prev_end = dt(
            prev_year + 1 if prev_month == 12 else prev_year,
            1 if prev_month == 12 else prev_month + 1,
            1,
            tzinfo=UTC,
        )
        prev_stmt = select(CreativeCostEvent.actual_cost).where(
            CreativeCostEvent.workspace_id == workspace_id,
            CreativeCostEvent.created_at >= prev_start,
            CreativeCostEvent.created_at < prev_end,
            CreativeCostEvent.actual_cost.isnot(None),
        )
        prev_result = await session.execute(prev_stmt)
        prev_month_costs = sum(prev_result.scalars().all(), Decimal("0"))
        prev_costs.append(prev_month_costs)

    avg_monthly_spend = sum(prev_costs, Decimal("0")) / len(prev_costs) if prev_costs else Decimal("0")

    # Daily rate
    days_in_month = 30
    day_of_month = now.day
    daily_rate = current_spend / day_of_month if day_of_month > 0 else Decimal("0")
    remaining_days = days_in_month - day_of_month
    projected_month_end = current_spend + (daily_rate * remaining_days)

    return {
        "allowed": current_spend + requested_cost <= budget,
        "reason": "within budget" if current_spend + requested_cost <= budget else "budget exceeded",
        "current_spend": float(current_spend),
        "requested_cost": float(requested_cost),
        "budget": float(budget),
        "remaining_budget": float(budget - current_spend),
        "projected_month_end": float(projected_month_end),
        "avg_monthly_spend": float(avg_monthly_spend),
        "daily_rate": float(daily_rate),
        "days_remaining": remaining_days,
    }


async def list_cost_events(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int = 50,
    offset: int = 0,
    asset_type: str | None = None,
    model: str | None = None,
    cost_category: str | None = None,
) -> list[dict[str, Any]]:
    """List recent cost events.

    Args:
        session: database session
        workspace_id: workspace identifier
        limit: max events to return
        offset: pagination offset
        asset_type: optional filter by asset type
        model: optional filter by model
        cost_category: optional filter by cost category

    Returns:
        List of cost event dicts.
    """
    from app.models.creative import CreativeCostEvent

    stmt = select(CreativeCostEvent).where(
        CreativeCostEvent.workspace_id == workspace_id
    )
    if asset_type:
        stmt = stmt.where(CreativeCostEvent.asset_type == asset_type)
    if model:
        stmt = stmt.where(CreativeCostEvent.model == model)
    if cost_category:
        stmt = stmt.where(CreativeCostEvent.cost_category == cost_category)
    stmt = stmt.order_by(CreativeCostEvent.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(stmt)
    events = list(result.scalars().all())

    return [_cost_event_to_dict(e) for e in events]


def _cost_event_to_dict(event) -> dict[str, Any]:
    """Convert a CreativeCostEvent to a dict."""
    return {
        "id": str(event.id),
        "generation_run_id": str(event.generation_run_id) if event.generation_run_id else None,
        "asset_id": str(event.asset_id) if event.asset_id else None,
        "brief_id": str(event.brief_id) if event.brief_id else None,
        "product_id": str(event.product_id) if event.product_id else None,
        "model": event.model,
        "provider": event.provider,
        "asset_type": event.asset_type,
        "cost_category": event.cost_category,
        "estimated_cost": float(event.estimated_cost) if event.estimated_cost else 0.0,
        "actual_cost": float(event.actual_cost) if event.actual_cost else None,
        "currency": event.currency,
        "image_count": event.image_count,
        "context": event.context or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "trace_id": event.trace_id,
    }


# ===================================================================
# Creative Approval Queue (C10)
# ===================================================================


async def create_approval_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_type: str,
    title: str,
    description: str | None = None,
    context: dict[str, Any] | None = None,
    risk_level: str = "medium",
    estimated_cost: Decimal | None = None,
    asset_count: int = 1,
    requested_by: str = "system",
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Create a creative approval request.

    Approval requests are created for high-risk operations that require
    human approval before execution.

    Args:
        session: database session
        workspace_id: workspace identifier
        request_type: type of request (high_cost_generation, batch_generation, etc.)
        title: short title for the request
        description: detailed description
        context: additional context data
        risk_level: risk level (low, medium, high)
        estimated_cost: estimated cost
        asset_count: number of assets involved
        requested_by: who requested the approval
        trace_id: optional trace identifier

    Returns:
        Dict with the created approval request data.
    """
    from app.models.creative import CreativeApprovalRequest

    request = CreativeApprovalRequest(
        id=uuid4(),
        workspace_id=workspace_id,
        request_type=request_type,
        status="pending",
        risk_level=risk_level,
        title=title,
        description=description,
        context=context or {},
        estimated_cost=estimated_cost,
        asset_count=asset_count,
        requested_by=requested_by,
        trace_id=trace_id,
    )
    session.add(request)
    await session.flush()

    return _approval_request_to_dict(request)


async def approve_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_id: UUID,
    actor: str,
    comment: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Approve a creative approval request.

    Args:
        session: database session
        workspace_id: workspace identifier
        request_id: approval request identifier
        actor: approver identifier
        comment: optional approval comment
        trace_id: optional trace identifier

    Returns:
        Dict with the updated request data.
    """
    from app.models.creative import CreativeApprovalRequest
    from app.services import event_service

    stmt = select(CreativeApprovalRequest).where(
        CreativeApprovalRequest.workspace_id == workspace_id,
        CreativeApprovalRequest.id == request_id,
    )
    result = await session.execute(stmt)
    request = result.scalar_one_or_none()

    if request is None:
        raise CreativeServiceError("Approval request not found")
    if request.status != "pending":
        raise CreativeServiceError(f"Approval request is not pending (status: {request.status})")

    now = datetime.now(UTC)
    request.status = "approved"
    request.approved_by = actor
    request.approved_at = now
    request.approval_comment = comment
    request.updated_at = now

    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="creative.approval_request_approved",
        entity_type="creative_approval_request",
        entity_id=str(request_id),
        payload={
            "request_id": str(request_id),
            "approved_by": actor,
            "comment": comment,
        },
        trace_id=trace_id,
        commit=False,
    )

    return _approval_request_to_dict(request)


async def reject_request(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_id: UUID,
    actor: str,
    comment: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Reject a creative approval request.

    Args:
        session: database session
        workspace_id: workspace identifier
        request_id: approval request identifier
        actor: rejecter identifier
        comment: optional rejection comment
        trace_id: optional trace identifier

    Returns:
        Dict with the updated request data.
    """
    from app.models.creative import CreativeApprovalRequest
    from app.services import event_service

    stmt = select(CreativeApprovalRequest).where(
        CreativeApprovalRequest.workspace_id == workspace_id,
        CreativeApprovalRequest.id == request_id,
    )
    result = await session.execute(stmt)
    request = result.scalar_one_or_none()

    if request is None:
        raise CreativeServiceError("Approval request not found")
    if request.status != "pending":
        raise CreativeServiceError(f"Approval request is not pending (status: {request.status})")

    now = datetime.now(UTC)
    request.status = "rejected"
    request.approved_by = actor
    request.approved_at = now
    request.approval_comment = comment
    request.updated_at = now

    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="creative.approval_request_rejected",
        entity_type="creative_approval_request",
        entity_id=str(request_id),
        payload={
            "request_id": str(request_id),
            "rejected_by": actor,
            "comment": comment,
        },
        trace_id=trace_id,
        commit=False,
    )

    return _approval_request_to_dict(request)


async def mark_executed(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    request_id: UUID,
    execution_result: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Mark an approved request as executed.

    Args:
        session: database session
        workspace_id: workspace identifier
        request_id: approval request identifier
        execution_result: execution result data
        trace_id: optional trace identifier

    Returns:
        Dict with the updated request data.
    """
    from app.models.creative import CreativeApprovalRequest
    from app.services import event_service

    stmt = select(CreativeApprovalRequest).where(
        CreativeApprovalRequest.workspace_id == workspace_id,
        CreativeApprovalRequest.id == request_id,
    )
    result = await session.execute(stmt)
    request = result.scalar_one_or_none()

    if request is None:
        raise CreativeServiceError("Approval request not found")
    if request.status != "approved":
        raise CreativeServiceError(f"Approval request is not approved (status: {request.status})")

    now = datetime.now(UTC)
    request.status = "executed"
    request.executed_at = now
    request.execution_result = execution_result or {}
    request.updated_at = now

    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="creative.approval_request_executed",
        entity_type="creative_approval_request",
        entity_id=str(request_id),
        payload={
            "request_id": str(request_id),
            "execution_result": execution_result or {},
        },
        trace_id=trace_id,
        commit=False,
    )

    return _approval_request_to_dict(request)


async def list_approval_requests(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    request_type: str | None = None,
    risk_level: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List creative approval requests with optional filters.

    Args:
        session: database session
        workspace_id: workspace identifier
        status: optional filter by status
        request_type: optional filter by request type
        risk_level: optional filter by risk level
        limit: max requests to return
        offset: pagination offset

    Returns:
        List of approval request dicts.
    """
    from app.models.creative import CreativeApprovalRequest

    stmt = select(CreativeApprovalRequest).where(
        CreativeApprovalRequest.workspace_id == workspace_id
    )
    if status:
        stmt = stmt.where(CreativeApprovalRequest.status == status)
    if request_type:
        stmt = stmt.where(CreativeApprovalRequest.request_type == request_type)
    if risk_level:
        stmt = stmt.where(CreativeApprovalRequest.risk_level == risk_level)
    stmt = stmt.order_by(CreativeApprovalRequest.requested_at.desc()).limit(limit).offset(offset)

    result = await session.execute(stmt)
    requests = list(result.scalars().all())

    return [_approval_request_to_dict(r) for r in requests]


async def get_approval_queue_stats(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    """Get approval queue statistics.

    Args:
        session: database session
        workspace_id: workspace identifier

    Returns:
        Dict with queue statistics.
    """
    from app.models.creative import CreativeApprovalRequest
    from sqlalchemy import func

    # Pending count
    pending_stmt = select(func.count(CreativeApprovalRequest.id)).where(
        CreativeApprovalRequest.workspace_id == workspace_id,
        CreativeApprovalRequest.status == "pending",
    )
    pending_count = (await session.execute(pending_stmt)).scalar() or 0

    # Approved count
    approved_stmt = select(func.count(CreativeApprovalRequest.id)).where(
        CreativeApprovalRequest.workspace_id == workspace_id,
        CreativeApprovalRequest.status == "approved",
    )
    approved_count = (await session.execute(approved_stmt)).scalar() or 0

    # Rejected count
    rejected_stmt = select(func.count(CreativeApprovalRequest.id)).where(
        CreativeApprovalRequest.workspace_id == workspace_id,
        CreativeApprovalRequest.status == "rejected",
    )
    rejected_count = (await session.execute(rejected_stmt)).scalar() or 0

    # Executed count
    executed_stmt = select(func.count(CreativeApprovalRequest.id)).where(
        CreativeApprovalRequest.workspace_id == workspace_id,
        CreativeApprovalRequest.status == "executed",
    )
    executed_count = (await session.execute(executed_stmt)).scalar() or 0

    # High risk pending count
    high_risk_stmt = select(func.count(CreativeApprovalRequest.id)).where(
        CreativeApprovalRequest.workspace_id == workspace_id,
        CreativeApprovalRequest.status == "pending",
        CreativeApprovalRequest.risk_level == "high",
    )
    high_risk_count = (await session.execute(high_risk_stmt)).scalar() or 0

    return {
        "pending": pending_count,
        "approved": approved_count,
        "rejected": rejected_count,
        "executed": executed_count,
        "high_risk_pending": high_risk_count,
        "total": pending_count + approved_count + rejected_count + executed_count,
    }


def _approval_request_to_dict(request) -> dict[str, Any]:
    """Convert a CreativeApprovalRequest to a dict."""
    return {
        "id": str(request.id),
        "request_type": request.request_type,
        "status": request.status,
        "risk_level": request.risk_level,
        "title": request.title,
        "description": request.description,
        "context": request.context or {},
        "estimated_cost": float(request.estimated_cost) if request.estimated_cost else None,
        "asset_count": request.asset_count,
        "requested_by": request.requested_by,
        "requested_at": request.requested_at.isoformat() if request.requested_at else None,
        "approved_by": request.approved_by,
        "approved_at": request.approved_at.isoformat() if request.approved_at else None,
        "approval_comment": request.approval_comment,
        "executed_at": request.executed_at.isoformat() if request.executed_at else None,
        "execution_result": request.execution_result or {},
        "created_at": request.created_at.isoformat() if request.created_at else None,
        "updated_at": request.updated_at.isoformat() if request.updated_at else None,
        "trace_id": request.trace_id,
    }


# ===================================================================
# Creative Analytics & Reporting (C11)
# ===================================================================


async def get_dashboard_metrics(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    days: int = 30,
) -> dict[str, Any]:
    """Get comprehensive dashboard metrics for the Creative Studio.

    Args:
        session: database session
        workspace_id: workspace identifier
        days: number of days to look back

    Returns:
        Dict with dashboard metrics.
    """
    from app.models.creative import (
        CreativeApprovalRequest,
        CreativeBrief,
        CreativeCostEvent,
        CreativeGenerationRun,
        CreativeKnowledgeEntry,
        CreativePromptTemplate,
        CreativeReview,
        CreativeStudioAsset,
    )
    from datetime import timedelta

    since = datetime.now(UTC) - timedelta(days=days)

    # Total assets
    asset_stmt = select(CreativeStudioAsset).where(
        CreativeStudioAsset.workspace_id == workspace_id
    )
    asset_result = await session.execute(asset_stmt)
    assets = list(asset_result.scalars().all())
    total_assets = len(assets)

    # Assets by status
    assets_by_status: dict[str, int] = {}
    for asset in assets:
        assets_by_status[asset.status] = assets_by_status.get(asset.status, 0) + 1

    # Total generation runs
    run_stmt = select(CreativeGenerationRun).where(
        CreativeGenerationRun.workspace_id == workspace_id
    )
    run_result = await session.execute(run_stmt)
    runs = list(run_result.scalars().all())
    total_runs = len(runs)

    # Runs by status
    runs_by_status: dict[str, int] = {}
    for run in runs:
        runs_by_status[run.status] = runs_by_status.get(run.status, 0) + 1

    # Success rate
    success_count = runs_by_status.get("SUCCEEDED", 0)
    total_completed = success_count + runs_by_status.get("FAILED", 0)
    success_rate = success_count / total_completed if total_completed > 0 else 0

    # Total cost
    total_cost = sum(
        (r.actual_cost or r.estimated_cost for r in runs if r.actual_cost or r.estimated_cost),
        Decimal("0"),
    )

    # Total cost from cost events
    cost_stmt = select(CreativeCostEvent.actual_cost).where(
        CreativeCostEvent.workspace_id == workspace_id,
        CreativeCostEvent.actual_cost.isnot(None),
    )
    cost_result = await session.execute(cost_stmt)
    cost_events = cost_result.scalars().all()
    cost_event_total = sum((c for c in cost_events if c), Decimal("0"))

    # Total templates
    template_stmt = select(CreativePromptTemplate).where(
        CreativePromptTemplate.workspace_id == workspace_id
    )
    template_result = await session.execute(template_stmt)
    templates = list(template_result.scalars().all())
    total_templates = len(templates)

    # Templates by status
    templates_by_status: dict[str, int] = {}
    for template in templates:
        templates_by_status[template.status] = templates_by_status.get(template.status, 0) + 1

    # Total knowledge entries
    knowledge_stmt = select(CreativeKnowledgeEntry).where(
        CreativeKnowledgeEntry.workspace_id == workspace_id
    )
    knowledge_result = await session.execute(knowledge_stmt)
    knowledge_entries = list(knowledge_result.scalars().all())
    total_knowledge = len(knowledge_entries)

    # Knowledge by type
    knowledge_by_type: dict[str, int] = {}
    for entry in knowledge_entries:
        knowledge_by_type[entry.entry_type] = knowledge_by_type.get(entry.entry_type, 0) + 1

    # Approval queue stats
    approval_stmt = select(CreativeApprovalRequest).where(
        CreativeApprovalRequest.workspace_id == workspace_id,
        CreativeApprovalRequest.status == "pending",
    )
    approval_result = await session.execute(approval_stmt)
    pending_approvals = len(list(approval_result.scalars().all()))

    # Briefs by status
    brief_stmt = select(CreativeBrief).where(
        CreativeBrief.workspace_id == workspace_id
    )
    brief_result = await session.execute(brief_stmt)
    briefs = list(brief_result.scalars().all())
    briefs_by_status: dict[str, int] = {}
    for brief in briefs:
        briefs_by_status[brief.status] = briefs_by_status.get(brief.status, 0) + 1

    return {
        "period_days": days,
        "assets": {
            "total": total_assets,
            "by_status": assets_by_status,
        },
        "generation": {
            "total_runs": total_runs,
            "by_status": runs_by_status,
            "success_rate": round(success_rate, 4),
            "success_count": success_count,
            "failed_count": runs_by_status.get("FAILED", 0),
        },
        "cost": {
            "total_cny": float(total_cost),
            "from_cost_events": float(cost_event_total),
        },
        "templates": {
            "total": total_templates,
            "by_status": templates_by_status,
        },
        "knowledge": {
            "total_entries": total_knowledge,
            "by_type": knowledge_by_type,
        },
        "approvals": {
            "pending": pending_approvals,
        },
        "briefs": {
            "total": len(briefs),
            "by_status": briefs_by_status,
        },
    }


async def get_performance_metrics(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    days: int = 30,
) -> dict[str, Any]:
    """Get performance metrics for the Creative Studio.

    Args:
        session: database session
        workspace_id: workspace identifier
        days: number of days to look back

    Returns:
        Dict with performance metrics.
    """
    from app.models.creative import (
        CreativeGenerationRun,
        CreativeReview,
    )
    from datetime import timedelta

    since = datetime.now(UTC) - timedelta(days=days)

    # Generation runs in period
    run_stmt = select(CreativeGenerationRun).where(
        CreativeGenerationRun.workspace_id == workspace_id,
        CreativeGenerationRun.created_at >= since,
        CreativeGenerationRun.status == "SUCCEEDED",
    )
    run_result = await session.execute(run_stmt)
    runs = list(run_result.scalars().all())

    if not runs:
        return {
            "period_days": days,
            "avg_generation_time_s": 0,
            "p95_generation_time_s": 0,
            "avg_cost_per_asset": 0,
            "total_assets_generated": 0,
        }

    # Generation times
    generation_times = []
    for run in runs:
        if run.started_at and run.completed_at:
            delta = (run.completed_at - run.started_at).total_seconds()
            generation_times.append(delta)

    avg_time = sum(generation_times) / len(generation_times) if generation_times else 0
    p95_time = sorted(generation_times)[int(len(generation_times) * 0.95)] if generation_times else 0

    # Total assets generated
    total_assets = sum((r.generated_count for r in runs), 0)

    # Average cost per asset
    total_cost = sum(
        (r.actual_cost or r.estimated_cost for r in runs if r.actual_cost or r.estimated_cost),
        Decimal("0"),
    )
    avg_cost = float(total_cost / total_assets) if total_assets > 0 else 0

    # Review metrics
    review_stmt = select(CreativeReview).where(
        CreativeReview.workspace_id == workspace_id,
        CreativeReview.created_at >= since,
    )
    review_result = await session.execute(review_stmt)
    reviews = list(review_result.scalars().all())

    approved_count = sum(1 for r in reviews if r.result == "approved")
    rejected_count = sum(1 for r in reviews if r.result == "rejected")
    total_reviews = len(reviews)
    approval_rate = approved_count / total_reviews if total_reviews > 0 else 0

    return {
        "period_days": days,
        "avg_generation_time_s": round(avg_time, 2),
        "p95_generation_time_s": round(p95_time, 2),
        "avg_cost_per_asset": round(avg_cost, 4),
        "total_assets_generated": total_assets,
        "reviews": {
            "total": total_reviews,
            "approved": approved_count,
            "rejected": rejected_count,
            "approval_rate": round(approval_rate, 4),
        },
    }


async def get_template_effectiveness(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Get template effectiveness metrics.

    Args:
        session: database session
        workspace_id: workspace identifier
        days: number of days to look back

    Returns:
        List of template effectiveness metrics.
    """
    from app.models.creative import CreativePromptTemplate, CreativeGenerationRun
    from datetime import timedelta

    since = datetime.now(UTC) - timedelta(days=days)

    # Get all templates
    template_stmt = select(CreativePromptTemplate).where(
        CreativePromptTemplate.workspace_id == workspace_id
    )
    template_result = await session.execute(template_stmt)
    templates = list(template_result.scalars().all())

    results = []
    for template in templates:
        # Get generation runs using this template
        run_stmt = select(CreativeGenerationRun).where(
            CreativeGenerationRun.workspace_id == workspace_id,
            CreativeGenerationRun.prompt_template_id == template.id,
            CreativeGenerationRun.created_at >= since,
        )
        run_result = await session.execute(run_stmt)
        runs = list(run_result.scalars().all())

        total_runs = len(runs)
        success_count = sum(1 for r in runs if r.status == "SUCCEEDED")
        fail_count = sum(1 for r in runs if r.status == "FAILED")
        success_rate = success_count / total_runs if total_runs > 0 else 0

        total_cost = sum(
            (r.actual_cost or r.estimated_cost for r in runs if r.actual_cost or r.estimated_cost),
            Decimal("0"),
        )
        avg_cost = float(total_cost / success_count) if success_count > 0 else 0

        # Calculate quality score from reviews
        quality_scores = []
        for run in runs:
            if run.status == "SUCCEEDED" and run.generated_count > 0:
                # We'd need to join with assets and reviews for actual quality scores
                # For now, use the run's quality score if available
                pass

        results.append({
            "template_id": str(template.id),
            "template_key": template.template_key,
            "name": template.name,
            "version": template.version,
            "status": template.status,
            "total_runs": total_runs,
            "success_count": success_count,
            "fail_count": fail_count,
            "success_rate": round(success_rate, 4),
            "total_cost": float(total_cost),
            "avg_cost_per_asset": round(avg_cost, 4),
            "quality_score": float(template.quality_score) if template.quality_score else None,
            "usage_count": template.usage_count,
        })

    # Sort by success rate and usage
    results.sort(key=lambda x: (x["success_rate"], x["usage_count"]), reverse=True)

    return results


async def get_knowledge_growth(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    days: int = 30,
) -> dict[str, Any]:
    """Get knowledge base growth metrics.

    Args:
        session: database session
        workspace_id: workspace identifier
        days: number of days to look back

    Returns:
        Dict with knowledge growth metrics.
    """
    from app.models.creative import CreativeKnowledgeEntry
    from datetime import timedelta

    since = datetime.now(UTC) - timedelta(days=days)
    prev_since = datetime.now(UTC) - timedelta(days=days * 2)

    # Total entries
    total_stmt = select(CreativeKnowledgeEntry).where(
        CreativeKnowledgeEntry.workspace_id == workspace_id
    )
    total_result = await session.execute(total_stmt)
    total_entries = len(list(total_result.scalars().all()))

    # New entries in period
    new_stmt = select(CreativeKnowledgeEntry).where(
        CreativeKnowledgeEntry.workspace_id == workspace_id,
        CreativeKnowledgeEntry.created_at >= since,
    )
    new_result = await session.execute(new_stmt)
    new_entries = len(list(new_result.scalars().all()))

    # Previous period entries
    prev_stmt = select(CreativeKnowledgeEntry).where(
        CreativeKnowledgeEntry.workspace_id == workspace_id,
        CreativeKnowledgeEntry.created_at >= prev_since,
        CreativeKnowledgeEntry.created_at < since,
    )
    prev_result = await session.execute(prev_stmt)
    prev_entries = len(list(prev_result.scalars().all()))

    # Growth rate
    growth_rate = (new_entries - prev_entries) / prev_entries if prev_entries > 0 else 0

    # By type in period
    new_entries_stmt = select(CreativeKnowledgeEntry).where(
        CreativeKnowledgeEntry.workspace_id == workspace_id,
        CreativeKnowledgeEntry.created_at >= since,
    )
    new_entries_result = await session.execute(new_entries_stmt)
    new_entries_list = list(new_entries_result.scalars().all())

    by_type: dict[str, int] = {}
    for entry in new_entries_list:
        by_type[entry.entry_type] = by_type.get(entry.entry_type, 0) + 1

    return {
        "period_days": days,
        "total_entries": total_entries,
        "new_entries": new_entries,
        "previous_period_entries": prev_entries,
        "growth_rate": round(growth_rate, 4),
        "new_by_type": by_type,
    }


# ===================================================================
# Creative Automation & Scheduling (C12)
# ===================================================================


async def create_automation_workflow(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    name: str,
    description: str | None = None,
    workflow_type: str = "custom",
    trigger_type: str = "manual",
    trigger_config: dict[str, Any] | None = None,
    steps: list[dict[str, Any]] | None = None,
    parameters: dict[str, Any] | None = None,
    enabled: bool = True,
    created_by: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Create an automation workflow for the Creative Studio.

    Uses the dedicated CreativeAutomationWorkflow model (C11).

    Args:
        session: database session
        workspace_id: workspace identifier
        name: workflow name
        description: optional description
        workflow_type: workflow type (batch_generation, ai_qc_pipeline, etc.)
        trigger_type: trigger type (manual, schedule, event)
        trigger_config: trigger configuration
        steps: list of workflow steps
        parameters: workflow parameters
        enabled: whether the workflow is active
        created_by: creator identifier
        trace_id: optional trace identifier

    Returns:
        Dict with the created workflow data.
    """
    from app.models.creative import CreativeAutomationWorkflow

    workflow = CreativeAutomationWorkflow(
        workspace_id=workspace_id,
        name=name,
        description=description,
        workflow_type=workflow_type,
        trigger_type=trigger_type,
        trigger_config=trigger_config or {},
        status="active" if enabled else "inactive",
        steps=steps or [],
        parameters=parameters or {},
        created_by=created_by or "system",
        trace_id=trace_id,
    )
    session.add(workflow)
    await session.flush()

    return _workflow_to_dict(workflow)


def _workflow_to_dict(workflow: "CreativeAutomationWorkflow") -> dict[str, Any]:
    """Convert a CreativeAutomationWorkflow ORM object to a dict."""
    return {
        "id": str(workflow.id),
        "workspace_id": str(workflow.workspace_id),
        "name": workflow.name,
        "description": workflow.description,
        "workflow_type": workflow.workflow_type,
        "trigger_type": workflow.trigger_type,
        "trigger_config": workflow.trigger_config or {},
        "status": workflow.status,
        "enabled": workflow.status == "active",
        "steps": workflow.steps or [],
        "parameters": workflow.parameters or {},
        "last_run_at": workflow.last_run_at.isoformat() if workflow.last_run_at else None,
        "last_run_status": workflow.last_run_status,
        "total_runs": workflow.total_runs,
        "success_count": workflow.success_count,
        "failure_count": workflow.failure_count,
        "created_by": workflow.created_by,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
        "trace_id": workflow.trace_id,
    }


async def trigger_workflow(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    workflow_id: str,
    context: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Trigger an automation workflow.

    Uses the dedicated CreativeAutomationWorkflow model (C11).

    Args:
        session: database session
        workspace_id: workspace identifier
        workflow_id: workflow identifier
        context: optional context for the workflow execution
        trace_id: optional trace identifier

    Returns:
        Dict with the execution result.
    """
    import logging

    logger = logging.getLogger(__name__)
    from app.models.creative import CreativeAutomationWorkflow

    # Load workflow
    stmt = select(CreativeAutomationWorkflow).where(
        CreativeAutomationWorkflow.workspace_id == workspace_id,
        CreativeAutomationWorkflow.id == UUID(workflow_id),
    )
    result = await session.execute(stmt)
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise CreativeServiceError(f"Workflow not found: {workflow_id}")

    if workflow.status != "active":
        raise CreativeServiceError(f"Workflow is inactive: {workflow_id}")

    steps = workflow.steps or []
    if not steps:
        raise CreativeServiceError(f"Workflow has no steps: {workflow_id}")

    # Execute steps
    execution_result = {
        "workflow_id": workflow_id,
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "context": context or {},
        "steps_executed": [],
        "errors": [],
    }

    for i, step in enumerate(steps):
        step_result = {
            "step_index": i,
            "step_type": step.get("type"),
            "status": "pending",
            "started_at": datetime.now(UTC).isoformat(),
        }

        try:
            step_type = step.get("type")
            step_config = step.get("config", {})

            if step_type == "generate_brief_assets":
                brief_id = step_config.get("brief_id")
                if brief_id:
                    await generate_brief_assets(
                        session,
                        brief_id=UUID(brief_id),
                        workspace_id=workspace_id,
                        execute_immediately=True,
                        trace_id=trace_id,
                    )
                step_result["status"] = "completed"

            elif step_type == "run_qc":
                step_result["status"] = "completed"

            elif step_type == "run_calibration":
                cal_result = await run_calibration(
                    session,
                    workspace_id=workspace_id,
                    days=step_config.get("days", 30),
                    trace_id=trace_id,
                )
                step_result["status"] = "completed"
                step_result["result"] = cal_result

            elif step_type == "push_to_woocommerce":
                step_result["status"] = "pending_approval"

            elif step_type == "notify":
                step_result["status"] = "completed"

            else:
                step_result["status"] = "skipped"
                step_result["error"] = f"Unknown step type: {step_type}"

        except Exception as exc:
            step_result["status"] = "failed"
            step_result["error"] = str(exc)
            logger.error(f"Workflow step {i} failed: {exc}")

        step_result["completed_at"] = datetime.now(UTC).isoformat()
        execution_result["steps_executed"].append(step_result)

    # Update execution result
    execution_result["status"] = "completed"
    execution_result["completed_at"] = datetime.now(UTC).isoformat()

    # Update workflow
    workflow.last_run_at = datetime.now(UTC)
    workflow.last_run_status = execution_result["status"]
    workflow.total_runs = workflow.total_runs + 1
    if execution_result["status"] == "completed":
        workflow.success_count = workflow.success_count + 1
    else:
        workflow.failure_count = workflow.failure_count + 1
    await session.flush()

    return execution_result


async def list_automation_workflows(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    enabled: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List automation workflows.

    Uses the dedicated CreativeAutomationWorkflow model (C11).

    Args:
        session: database session
        workspace_id: workspace identifier
        enabled: optional filter by enabled status
        limit: max workflows to return
        offset: pagination offset

    Returns:
        List of workflow dicts.
    """
    from app.models.creative import CreativeAutomationWorkflow

    stmt = select(CreativeAutomationWorkflow).where(
        CreativeAutomationWorkflow.workspace_id == workspace_id,
    )

    if enabled is not None:
        stmt = stmt.where(
            CreativeAutomationWorkflow.status == ("active" if enabled else "inactive")
        )

    stmt = stmt.order_by(CreativeAutomationWorkflow.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    workflows = list(result.scalars().all())

    return [_workflow_to_dict(w) for w in workflows]


async def update_automation_workflow(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    workflow_id: str,
    updates: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Update an automation workflow.

    Uses the dedicated CreativeAutomationWorkflow model (C11).

    Args:
        session: database session
        workspace_id: workspace_id
        workflow_id: workflow identifier
        updates: fields to update
        trace_id: optional trace identifier

    Returns:
        Dict with the updated workflow data.
    """
    from app.models.creative import CreativeAutomationWorkflow

    stmt = select(CreativeAutomationWorkflow).where(
        CreativeAutomationWorkflow.workspace_id == workspace_id,
        CreativeAutomationWorkflow.id == UUID(workflow_id),
    )
    result = await session.execute(stmt)
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise CreativeServiceError(f"Workflow not found: {workflow_id}")

    # Apply updates
    if "name" in updates:
        workflow.name = updates["name"]
    if "description" in updates:
        workflow.description = updates["description"]
    if "workflow_type" in updates:
        workflow.workflow_type = updates["workflow_type"]
    if "trigger_type" in updates:
        workflow.trigger_type = updates["trigger_type"]
    if "trigger_config" in updates:
        workflow.trigger_config = updates["trigger_config"]
    if "steps" in updates:
        workflow.steps = updates["steps"]
    if "parameters" in updates:
        workflow.parameters = updates["parameters"]
    if "enabled" in updates:
        workflow.status = "active" if updates["enabled"] else "inactive"
    if "status" in updates:
        workflow.status = updates["status"]

    workflow.updated_at = datetime.now(UTC)
    await session.flush()

    return _workflow_to_dict(workflow)


async def run_scheduled_workflow_check(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Check for and run scheduled workflows.

    Uses the dedicated CreativeAutomationWorkflow model (C11).

    This function should be called by a scheduler (e.g., cron job) to check
    for workflows that are due to run.

    Args:
        session: database session
        workspace_id: workspace identifier
        trace_id: optional trace identifier

    Returns:
        Dict with the check result.
    """
    import logging

    logger = logging.getLogger(__name__)
    from app.models.creative import CreativeAutomationWorkflow

    # Get all active scheduled workflows
    stmt = select(CreativeAutomationWorkflow).where(
        CreativeAutomationWorkflow.workspace_id == workspace_id,
        CreativeAutomationWorkflow.status == "active",
        CreativeAutomationWorkflow.trigger_type == "schedule",
    )
    result = await session.execute(stmt)
    workflows = list(result.scalars().all())

    workflows_to_run = []
    now = datetime.now(UTC)

    for workflow in workflows:
        # Check if the workflow is due to run
        schedule_config = workflow.trigger_config or {}
        interval_days = schedule_config.get("interval_days", 7)

        if workflow.last_run_at:
            last_run = workflow.last_run_at
            if (now - last_run).days < interval_days:
                continue  # Not due yet

        workflows_to_run.append(workflow)

    # Run each workflow
    results = []
    for workflow in workflows_to_run:
        try:
            result = await trigger_workflow(
                session,
                workspace_id=workspace_id,
                workflow_id=str(workflow.id),
                trace_id=trace_id,
            )
            results.append({
                "workflow_id": str(workflow.id),
                "status": "triggered",
                "result": result,
            })
        except Exception as exc:
            logger.error(f"Failed to trigger workflow {workflow.id}: {exc}")
            results.append({
                "workflow_id": str(workflow.id),
                "status": "failed",
                "error": str(exc),
            })

    return {
        "checked_at": now.isoformat(),
        "workflows_checked": len(workflows),
        "workflows_triggered": len(workflows_to_run),
        "results": results,
    }


async def run_cost_monitoring(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    budget_threshold: Decimal | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Run cost monitoring and create approval requests if budget exceeded.

    Args:
        session: database session
        workspace_id: workspace identifier
        budget_threshold: optional custom budget threshold
        trace_id: optional trace identifier

    Returns:
        Dict with the monitoring result.
    """
    from app.models.creative import CreativeApprovalRequest

    budget = budget_threshold or DEFAULT_MONTHLY_BUDGET_CNY
    current_spend = await get_monthly_cost(session, workspace_id=workspace_id)

    if current_spend > budget:
        # Create approval request for budget exceeded
        request = CreativeApprovalRequest(
            id=uuid4(),
            workspace_id=workspace_id,
            request_type="budget_exceeded",
            status="pending",
            risk_level="high",
            title=f"Monthly budget exceeded: {current_spend} > {budget}",
            description=f"Current monthly spend ({current_spend} CNY) has exceeded the budget ({budget} CNY). Please review and adjust.",
            context={
                "current_spend": float(current_spend),
                "budget": float(budget),
                "excess": float(current_spend - budget),
            },
            estimated_cost=current_spend,
            asset_count=0,
            requested_by="system",
            trace_id=trace_id,
        )
        session.add(request)
        await session.flush()

        return {
            "status": "budget_exceeded",
            "current_spend": float(current_spend),
            "budget": float(budget),
            "excess": float(current_spend - budget),
            "approval_request_id": str(request.id),
        }

    return {
        "status": "within_budget",
        "current_spend": float(current_spend),
        "budget": float(budget),
        "remaining": float(budget - current_spend),
    }
