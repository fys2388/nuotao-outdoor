"""Activity planner service (M6): AI-generated e-commerce campaign plans.

Generates, rewrites, and optimizes structured activity plans through the
LLM gateway. All plans are proposals — they enter an approval queue before
any downstream action (EDM sends, image batches, discount config).

Agent access: Marketing Manager uses this via the whitelist tool
``generate_activity_plan``; agents never mutate plan rows directly.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select

from app.agents.generic_agent import run_generic_agent
from app.models.activity_plan import ACTIVITY_TYPES, PLAN_STATUSES, ActivityPlan

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

AGENT_ID = "activity_planner"
AGENT_NAME = "Activity Planner"
PROMPT_NAME = "ACTIVITY_PLANNER_V1"
TRIGGER = "api:activity_planner:generate"

# Output schema for the LLM (structured plan).
ACTIVITY_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Brief summary of the activity plan"},
        "target_audience": {"type": "string", "description": "Target audience description"},
        "objectives": {
            "type": "object",
            "properties": {
                "target_revenue": {"type": "number"},
                "target_orders": {"type": "integer"},
                "target_roas": {"type": "number"},
                "target_conversion_rate": {"type": "number"},
            },
        },
        "discount_strategy": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["percentage", "fixed", "tiered", "bogo", "free_shipping"]},
                "value": {"type": "number"},
                "tiers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "min_qty": {"type": "integer"},
                            "discount_pct": {"type": "number"},
                        },
                    },
                },
                "min_order_value": {"type": "number"},
            },
        },
        "product_selection": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "product_name": {"type": "string"},
                    "reason": {"type": "string"},
                    "expected_velocity": {"type": "string"},
                },
            },
        },
        "marketing_channels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "budget_allocation_pct": {"type": "number"},
                    "tactics": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "content_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "publish_date": {"type": "string"},
                    "content_type": {"type": "string"},
                    "headline": {"type": "string"},
                    "key_message": {"type": "string"},
                },
            },
        },
        "creative_assets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["banner", "social_post", "email_header", "product_image", "video"]},
                    "spec": {"type": "string"},
                    "prompt": {"type": "string"},
                    "use_case": {"type": "string"},
                },
            },
        },
        "timeline": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phase": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "actions": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "risk_mitigation": {"type": "array", "items": {"type": "string"}},
        "kpi_tracking": {
            "type": "object",
            "properties": {
                "primary_metrics": {"type": "array", "items": {"type": "string"}},
                "tracking_method": {"type": "string"},
                "review_frequency": {"type": "string"},
            },
        },
        "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["summary", "discount_strategy", "timeline", "confidence_score"],
}


class ActivityPlannerError(Exception):
    """Raised when the activity planner service cannot fulfill a request."""


def get_activity_planner_status() -> dict[str, Any]:
    """Return service status and configuration."""
    return {
        "service": "activity_planner",
        "status": "operational",
        "agent_id": AGENT_ID,
        "prompt_name": PROMPT_NAME,
        "activity_types": list(ACTIVITY_TYPES),
        "plan_statuses": list(PLAN_STATUSES),
        "approval_required": True,
    }


async def generate_activity_plan(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    name: str,
    activity_type: str = "other",
    start_date: str | None = None,
    end_date: str | None = None,
    budget_total: float = 0.0,
    budget_currency: str = "USD",
    target_revenue: float | None = None,
    target_orders: int | None = None,
    target_roas: float | None = None,
    product_ids: list[str] | None = None,
    additional_context: dict[str, Any] | None = None,
    created_by: str = "system",
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Generate an activity plan via the LLM gateway and persist it.

    The plan enters ``pending`` approval status; no downstream action is
    taken until a human approves it.
    """
    if activity_type not in ACTIVITY_TYPES:
        raise ActivityPlannerError(f"invalid activity_type: {activity_type}; must be one of {ACTIVITY_TYPES}")

    ws = workspace_id or DEFAULT_WORKSPACE_ID

    # Build context for the LLM
    context: dict[str, Any] = {
        "activity_name": name,
        "activity_type": activity_type,
        "start_date": start_date,
        "end_date": end_date,
        "budget": {"total": budget_total, "currency": budget_currency},
        "targets": {
            "revenue": target_revenue,
            "orders": target_orders,
            "roas": target_roas,
        },
        "product_ids": product_ids or [],
        "brand": "Nuotao Outdoor",
        "market": "US/EU outdoor gear DTC",
    }
    if additional_context:
        context["additional_context"] = additional_context

    # Call the LLM via generic agent framework
    result = await run_generic_agent(
        session,
        workspace_id=ws,
        agent_id=AGENT_ID,
        agent_name=AGENT_NAME,
        trigger=TRIGGER,
        context=context,
        prompt_name=PROMPT_NAME,
        output_schema=ACTIVITY_PLAN_SCHEMA,
        system_instruction=(
            "You are a senior e-commerce marketing planner for an outdoor gear DTC brand. "
            "Generate a complete, data-driven activity plan. Respond ONLY with a valid JSON "
            "object matching the schema. All discount rates must be realistic (5-70%). "
            "All dates must be valid. Include risk mitigation for every plan."
        ),
        temperature=0.4,
        task_type="activity_planning",
        trace_id=trace_id,
    )

    if result.error or not result.output:
        raise ActivityPlannerError(f"plan generation failed: {result.error or 'no output'}")

    plan_json = result.output

    # Parse dates
    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date)

    # Persist the plan
    plan = ActivityPlan(
        id=uuid4(),
        workspace_id=ws,
        name=name,
        activity_type=activity_type,
        start_date=start_dt,
        end_date=end_dt,
        budget_total=Decimal(str(budget_total)),
        budget_currency=budget_currency,
        target_revenue=Decimal(str(target_revenue)) if target_revenue else None,
        target_orders=target_orders,
        target_roas=Decimal(str(target_roas)) if target_roas else None,
        plan_json=plan_json,
        status="draft",
        approval_status="pending",
        created_by=created_by,
        version=1,
        trace_id=trace_id,
    )
    session.add(plan)
    await session.flush()

    # Audit event
    from app.services import event_service
    await event_service.create_event(
        session,
        workspace_id=ws,
        event_type="activity_plan.generated",
        entity_type="activity_plan",
        entity_id=str(plan.id),
        payload={
            "activity_type": activity_type,
            "name": name,
            "confidence_score": plan_json.get("confidence_score"),
        },
        trace_id=trace_id,
    )

    return {
        "id": str(plan.id),
        "name": plan.name,
        "activity_type": plan.activity_type,
        "status": plan.status,
        "approval_status": plan.approval_status,
        "version": plan.version,
        "plan": plan_json,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }


async def rewrite_activity_plan(
    session: AsyncSession,
    *,
    plan_id: UUID,
    feedback: str,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Rewrite an existing plan based on human feedback (creates v2)."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    existing = await _get_plan(session, plan_id=plan_id, workspace_id=ws)
    if not existing:
        raise ActivityPlannerError(f"plan not found: {plan_id}")

    context = {
        "original_plan": existing.plan_json,
        "feedback": feedback,
        "activity_name": existing.name,
        "activity_type": existing.activity_type,
    }

    result = await run_generic_agent(
        session,
        workspace_id=ws,
        agent_id=AGENT_ID,
        agent_name=AGENT_NAME,
        trigger="api:activity_planner:rewrite",
        context=context,
        prompt_name=PROMPT_NAME,
        output_schema=ACTIVITY_PLAN_SCHEMA,
        system_instruction=(
            "You are a senior e-commerce marketing planner. Rewrite the activity plan "
            "based on the provided feedback. Keep the parts that work, fix the parts "
            "that need improvement. Respond ONLY with a valid JSON object matching the schema."
        ),
        temperature=0.4,
        task_type="activity_planning",
        trace_id=trace_id,
    )

    if result.error or not result.output:
        raise ActivityPlannerError(f"rewrite failed: {result.error or 'no output'}")

    # Create new version
    new_plan = ActivityPlan(
        id=uuid4(),
        workspace_id=ws,
        name=existing.name,
        activity_type=existing.activity_type,
        start_date=existing.start_date,
        end_date=existing.end_date,
        budget_total=existing.budget_total,
        budget_currency=existing.budget_currency,
        target_revenue=existing.target_revenue,
        target_orders=existing.target_orders,
        target_roas=existing.target_roas,
        plan_json=result.output,
        status="draft",
        approval_status="pending",
        created_by=existing.created_by,
        parent_plan_id=existing.id,
        version=existing.version + 1,
        trace_id=trace_id,
    )
    session.add(new_plan)
    await session.flush()

    return {
        "id": str(new_plan.id),
        "parent_id": str(existing.id),
        "version": new_plan.version,
        "status": new_plan.status,
        "approval_status": new_plan.approval_status,
        "plan": result.output,
    }


async def optimize_activity_plan(
    session: AsyncSession,
    *,
    plan_id: UUID,
    historical_data: dict[str, Any] | None = None,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Optimize a plan based on historical performance data (creates new version)."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    existing = await _get_plan(session, plan_id=plan_id, workspace_id=ws)
    if not existing:
        raise ActivityPlannerError(f"plan not found: {plan_id}")

    context = {
        "original_plan": existing.plan_json,
        "historical_data": historical_data or {},
        "optimization_goal": "maximize ROAS and conversion rate while staying within budget",
    }

    result = await run_generic_agent(
        session,
        workspace_id=ws,
        agent_id=AGENT_ID,
        agent_name=AGENT_NAME,
        trigger="api:activity_planner:optimize",
        context=context,
        prompt_name=PROMPT_NAME,
        output_schema=ACTIVITY_PLAN_SCHEMA,
        system_instruction=(
            "You are a senior e-commerce marketing analyst. Optimize the activity plan "
            "based on historical performance data. Adjust discount strategy, channel "
            "allocation, and product selection to maximize ROAS. Respond ONLY with JSON."
        ),
        temperature=0.3,
        task_type="activity_planning",
        trace_id=trace_id,
    )

    if result.error or not result.output:
        raise ActivityPlannerError(f"optimization failed: {result.error or 'no output'}")

    new_plan = ActivityPlan(
        id=uuid4(),
        workspace_id=ws,
        name=f"{existing.name} (optimized)",
        activity_type=existing.activity_type,
        start_date=existing.start_date,
        end_date=existing.end_date,
        budget_total=existing.budget_total,
        budget_currency=existing.budget_currency,
        target_revenue=existing.target_revenue,
        target_orders=existing.target_orders,
        target_roas=existing.target_roas,
        plan_json=result.output,
        status="draft",
        approval_status="pending",
        parent_plan_id=existing.id,
        version=existing.version + 1,
        trace_id=trace_id,
    )
    session.add(new_plan)
    await session.flush()

    return {
        "id": str(new_plan.id),
        "parent_id": str(existing.id),
        "version": new_plan.version,
        "plan": result.output,
    }


async def approve_plan(
    session: AsyncSession,
    *,
    plan_id: UUID,
    approved_by: str,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Approve a plan for execution (human-in-the-loop gate)."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    plan = await _get_plan(session, plan_id=plan_id, workspace_id=ws)
    if not plan:
        raise ActivityPlannerError(f"plan not found: {plan_id}")
    plan.approval_status = "approved"
    plan.status = "approved"
    plan.approved_by = approved_by
    plan.approved_at = datetime.now(UTC)
    await session.flush()
    return {"id": str(plan.id), "approval_status": plan.approval_status, "approved_by": plan.approved_by}


async def reject_plan(
    session: AsyncSession,
    *,
    plan_id: UUID,
    reject_reason: str,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Reject a plan."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    plan = await _get_plan(session, plan_id=plan_id, workspace_id=ws)
    if not plan:
        raise ActivityPlannerError(f"plan not found: {plan_id}")
    plan.approval_status = "rejected"
    plan.status = "rejected"
    plan.reject_reason = reject_reason
    await session.flush()
    return {"id": str(plan.id), "approval_status": plan.approval_status, "reject_reason": plan.reject_reason}


async def list_plans(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    status: str | None = None,
    activity_type: str | None = None,
    approval_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List activity plans with filters."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    stmt = select(ActivityPlan).where(ActivityPlan.workspace_id == ws)
    if status:
        stmt = stmt.where(ActivityPlan.status == status)
    if activity_type:
        stmt = stmt.where(ActivityPlan.activity_type == activity_type)
    if approval_status:
        stmt = stmt.where(ActivityPlan.approval_status == approval_status)
    stmt = stmt.order_by(desc(ActivityPlan.created_at)).limit(limit).offset(offset)

    result = await session.execute(stmt)
    plans = result.scalars().all()

    return {
        "plans": [_plan_to_dict(p) for p in plans],
        "total": len(plans),
        "limit": limit,
        "offset": offset,
    }


async def get_plan(
    session: AsyncSession,
    *,
    plan_id: UUID,
    workspace_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Get a single plan by ID."""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    plan = await _get_plan(session, plan_id=plan_id, workspace_id=ws)
    return _plan_to_dict(plan) if plan else None


async def _get_plan(
    session: AsyncSession, *, plan_id: UUID, workspace_id: UUID
) -> ActivityPlan | None:
    stmt = select(ActivityPlan).where(
        ActivityPlan.id == plan_id,
        ActivityPlan.workspace_id == workspace_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _plan_to_dict(plan: ActivityPlan) -> dict[str, Any]:
    return {
        "id": str(plan.id),
        "name": plan.name,
        "activity_type": plan.activity_type,
        "start_date": plan.start_date.isoformat() if plan.start_date else None,
        "end_date": plan.end_date.isoformat() if plan.end_date else None,
        "budget_total": float(plan.budget_total),
        "budget_currency": plan.budget_currency,
        "target_revenue": float(plan.target_revenue) if plan.target_revenue else None,
        "target_orders": plan.target_orders,
        "target_roas": float(plan.target_roas) if plan.target_roas else None,
        "status": plan.status,
        "approval_status": plan.approval_status,
        "version": plan.version,
        "parent_plan_id": str(plan.parent_plan_id) if plan.parent_plan_id else None,
        "created_by": plan.created_by,
        "approved_by": plan.approved_by,
        "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
        "reject_reason": plan.reject_reason,
        "plan": plan.plan_json,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse a date string (YYYY-MM-DD) to a timezone-aware datetime."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str).replace(tzinfo=UTC) if "T" in date_str else datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None
