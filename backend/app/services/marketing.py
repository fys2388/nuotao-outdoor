"""Marketing intelligence service (M3.1): data capture, derived metrics, lifecycle.

Pure data + proposal layer - no marketing action is ever executed
automatically. Every create/update/delete/state change emits an event so the
audit trail stays complete.
"""

import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import (
    Campaign,
    CreativeAsset,
    CustomerFeedback,
    MarketingExperiment,
)
from app.models.product import Product
from app.schemas.marketing import (
    CampaignCreate,
    CampaignUpdate,
    CreativeCreate,
    CreativeUpdate,
    ExperimentCompleteRequest,
    ExperimentCreate,
    ExperimentStartRequest,
    FeedbackCreate,
    FeedbackUpdate,
)
from app.services import event_service

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
D4 = Decimal("0.0001")
D6 = Decimal("0.000001")


class MarketingError(Exception):
    """Raised when a marketing operation cannot complete."""


def _q(value: Decimal, quantum: Decimal = D4) -> Decimal:
    return value.quantize(quantum, ROUND_HALF_UP)


def calculate_roi(revenue: Decimal, spend: Decimal) -> Decimal | None:
    """Return-on-investment: (revenue - spend) / spend; None when spend = 0."""
    if spend <= ZERO:
        return None
    return _q((revenue - spend) / spend)


def derive_metrics(
    *,
    spend: Decimal,
    impressions: int,
    clicks: int,
    revenue: Decimal,
    ctr: Decimal | None = None,
    cpc: Decimal | None = None,
    roas: Decimal | None = None,
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Compute derived metrics; provided values take precedence."""
    if ctr is None and impressions > 0:
        ctr = _q(Decimal(clicks) / Decimal(impressions), D6)
    if cpc is None and clicks > 0:
        cpc = _q(spend / Decimal(clicks))
    if roas is None and spend > ZERO:
        roas = _q(revenue / spend)
    return ctr, cpc, roas


async def _ensure_product(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID | None
) -> None:
    """Validate that a referenced product belongs to the workspace."""
    if product_id is None:
        return
    exists = (
        await session.execute(
            select(Product.id).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        raise MarketingError("product not found")


# --------------------------------------------------------------------------- #
# Campaigns
# --------------------------------------------------------------------------- #


async def create_campaign(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: CampaignCreate,
    trace_id: str | None = None,
) -> Campaign:
    """Create a campaign; derived metrics are computed when omitted."""
    await _ensure_product(session, workspace_id=workspace_id, product_id=data.product_id)
    ctr, cpc, roas = derive_metrics(
        spend=data.spend,
        impressions=data.impressions,
        clicks=data.clicks,
        revenue=data.revenue,
        ctr=data.ctr,
        cpc=data.cpc,
        roas=data.roas,
    )
    campaign = Campaign(
        workspace_id=workspace_id,
        platform=data.platform,
        campaign_id=data.campaign_id,
        name=data.name,
        product_id=data.product_id,
        status=data.status,
        currency=data.currency,
        budget=data.budget,
        spend=data.spend,
        impressions=data.impressions,
        clicks=data.clicks,
        ctr=ctr,
        cpc=cpc,
        conversion=data.conversion,
        revenue=data.revenue,
        roas=roas,
        started_at=data.started_at,
        ended_at=data.ended_at,
        trace_id=trace_id,
    )
    session.add(campaign)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise MarketingError(
            f"campaign '{data.platform}/{data.campaign_id}' already exists"
        ) from exc
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="campaign.created",
        entity_type="campaign",
        entity_id=str(campaign.id),
        payload={
            "platform": data.platform,
            "campaign_id": data.campaign_id,
            "product_id": str(data.product_id) if data.product_id else None,
            "roas": str(roas) if roas is not None else None,
            "roi": str(calculate_roi(data.revenue, data.spend)) if data.spend > ZERO else None,
        },
        trace_id=trace_id,
    )
    logger.info("campaign %s/%s created trace=%s", data.platform, data.campaign_id, trace_id)
    return campaign


async def _load_campaign(
    session: AsyncSession, *, workspace_id: UUID, campaign_id: UUID
) -> Campaign | None:
    return (
        await session.execute(
            select(Campaign).where(
                Campaign.workspace_id == workspace_id,
                Campaign.id == campaign_id,
            )
        )
    ).scalar_one_or_none()


async def update_campaign(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    campaign_id: UUID,
    data: CampaignUpdate,
    trace_id: str | None = None,
) -> Campaign:
    """Partially update a campaign and recompute derived metrics."""
    campaign = await _load_campaign(session, workspace_id=workspace_id, campaign_id=campaign_id)
    if campaign is None:
        raise MarketingError("campaign not found")

    updates = data.model_dump(exclude_unset=True)
    provided_ctr = updates.pop("ctr", None)
    provided_cpc = updates.pop("cpc", None)
    provided_roas = updates.pop("roas", None)
    for key, value in updates.items():
        setattr(campaign, key, value)
    ctr, cpc, roas = derive_metrics(
        spend=campaign.spend,
        impressions=campaign.impressions,
        clicks=campaign.clicks,
        revenue=campaign.revenue,
        ctr=provided_ctr,
        cpc=provided_cpc,
        roas=provided_roas,
    )
    campaign.ctr = ctr
    campaign.cpc = cpc
    campaign.roas = roas
    campaign.updated_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="campaign.updated",
        entity_type="campaign",
        entity_id=str(campaign.id),
        payload={"roas": str(roas) if roas is not None else None},
        trace_id=trace_id,
    )
    return campaign


async def list_campaigns(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    platform: str | None = None,
    product_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Campaign]:
    """List campaigns with optional filters, newest first."""
    stmt = select(Campaign).where(Campaign.workspace_id == workspace_id)
    if platform:
        stmt = stmt.where(Campaign.platform == platform)
    if product_id is not None:
        stmt = stmt.where(Campaign.product_id == product_id)
    if status:
        stmt = stmt.where(Campaign.status == status)
    stmt = stmt.order_by(Campaign.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def delete_campaign(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    campaign_id: UUID,
    trace_id: str | None = None,
) -> None:
    """Hard-delete a campaign (audited via event before removal)."""
    campaign = await _load_campaign(session, workspace_id=workspace_id, campaign_id=campaign_id)
    if campaign is None:
        raise MarketingError("campaign not found")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="campaign.deleted",
        entity_type="campaign",
        entity_id=str(campaign.id),
        payload={"platform": campaign.platform, "campaign_id": campaign.campaign_id},
        trace_id=trace_id,
    )
    await session.delete(campaign)
    await session.flush()


# --------------------------------------------------------------------------- #
# Creative assets
# --------------------------------------------------------------------------- #


async def create_creative(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: CreativeCreate,
    trace_id: str | None = None,
) -> CreativeAsset:
    await _ensure_product(session, workspace_id=workspace_id, product_id=data.product_id)
    creative = CreativeAsset(
        workspace_id=workspace_id,
        product_id=data.product_id,
        platform=data.platform,
        asset_type=data.asset_type,
        reference=data.reference,
        hook=data.hook,
        angle=data.angle,
        copy=data.copy,
        performance_snapshot=data.performance_snapshot,
        status=data.status,
        trace_id=trace_id,
    )
    session.add(creative)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="creative.created",
        entity_type="creative_asset",
        entity_id=str(creative.id),
        payload={
            "product_id": str(data.product_id) if data.product_id else None,
            "asset_type": data.asset_type,
            "platform": data.platform,
        },
        trace_id=trace_id,
    )
    return creative


async def _load_creative(
    session: AsyncSession, *, workspace_id: UUID, creative_id: UUID
) -> CreativeAsset | None:
    return (
        await session.execute(
            select(CreativeAsset).where(
                CreativeAsset.workspace_id == workspace_id,
                CreativeAsset.id == creative_id,
            )
        )
    ).scalar_one_or_none()


async def update_creative(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    creative_id: UUID,
    data: CreativeUpdate,
    trace_id: str | None = None,
) -> CreativeAsset:
    creative = await _load_creative(session, workspace_id=workspace_id, creative_id=creative_id)
    if creative is None:
        raise MarketingError("creative not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(creative, key, value)
    creative.updated_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="creative.updated",
        entity_type="creative_asset",
        entity_id=str(creative.id),
        payload={"status": creative.status},
        trace_id=trace_id,
    )
    return creative


async def list_creatives(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID | None = None,
    platform: str | None = None,
    limit: int = 50,
) -> list[CreativeAsset]:
    stmt = select(CreativeAsset).where(CreativeAsset.workspace_id == workspace_id)
    if product_id is not None:
        stmt = stmt.where(CreativeAsset.product_id == product_id)
    if platform:
        stmt = stmt.where(CreativeAsset.platform == platform)
    stmt = stmt.order_by(CreativeAsset.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def delete_creative(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    creative_id: UUID,
    trace_id: str | None = None,
) -> None:
    creative = await _load_creative(session, workspace_id=workspace_id, creative_id=creative_id)
    if creative is None:
        raise MarketingError("creative not found")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="creative.deleted",
        entity_type="creative_asset",
        entity_id=str(creative.id),
        payload={"asset_type": creative.asset_type},
        trace_id=trace_id,
    )
    await session.delete(creative)
    await session.flush()


# --------------------------------------------------------------------------- #
# Customer feedback
# --------------------------------------------------------------------------- #


async def create_feedback(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: FeedbackCreate,
    trace_id: str | None = None,
) -> CustomerFeedback:
    await _ensure_product(session, workspace_id=workspace_id, product_id=data.product_id)
    feedback = CustomerFeedback(
        workspace_id=workspace_id,
        product_id=data.product_id,
        source=data.source,
        content=data.content,
        sentiment=data.sentiment,
        issue_type=data.issue_type,
        rating=data.rating,
        metadata_json=data.metadata,
        trace_id=trace_id,
    )
    session.add(feedback)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="feedback.created",
        entity_type="customer_feedback",
        entity_id=str(feedback.id),
        payload={
            "product_id": str(data.product_id) if data.product_id else None,
            "sentiment": data.sentiment,
            "source": data.source,
        },
        trace_id=trace_id,
    )
    return feedback


async def _load_feedback(
    session: AsyncSession, *, workspace_id: UUID, feedback_id: UUID
) -> CustomerFeedback | None:
    return (
        await session.execute(
            select(CustomerFeedback).where(
                CustomerFeedback.workspace_id == workspace_id,
                CustomerFeedback.id == feedback_id,
            )
        )
    ).scalar_one_or_none()


async def update_feedback(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    feedback_id: UUID,
    data: FeedbackUpdate,
    trace_id: str | None = None,
) -> CustomerFeedback:
    """Update classification fields; the original content stays immutable."""
    feedback = await _load_feedback(session, workspace_id=workspace_id, feedback_id=feedback_id)
    if feedback is None:
        raise MarketingError("feedback not found")
    updates = data.model_dump(exclude_unset=True)
    if "metadata" in updates:
        feedback.metadata_json = updates.pop("metadata")
    for key, value in updates.items():
        setattr(feedback, key, value)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="feedback.updated",
        entity_type="customer_feedback",
        entity_id=str(feedback.id),
        payload={"sentiment": feedback.sentiment},
        trace_id=trace_id,
    )
    return feedback


async def list_feedback(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID | None = None,
    source: str | None = None,
    sentiment: str | None = None,
    limit: int = 50,
) -> list[CustomerFeedback]:
    stmt = select(CustomerFeedback).where(CustomerFeedback.workspace_id == workspace_id)
    if product_id is not None:
        stmt = stmt.where(CustomerFeedback.product_id == product_id)
    if source:
        stmt = stmt.where(CustomerFeedback.source == source)
    if sentiment:
        stmt = stmt.where(CustomerFeedback.sentiment == sentiment)
    stmt = stmt.order_by(CustomerFeedback.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def delete_feedback(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    feedback_id: UUID,
    trace_id: str | None = None,
) -> None:
    feedback = await _load_feedback(session, workspace_id=workspace_id, feedback_id=feedback_id)
    if feedback is None:
        raise MarketingError("feedback not found")
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="feedback.deleted",
        entity_type="customer_feedback",
        entity_id=str(feedback.id),
        payload={"sentiment": feedback.sentiment},
        trace_id=trace_id,
    )
    await session.delete(feedback)
    await session.flush()


# --------------------------------------------------------------------------- #
# Marketing experiments (lifecycle: proposed -> active -> completed)
# --------------------------------------------------------------------------- #


async def propose_experiment(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: ExperimentCreate,
    trace_id: str | None = None,
) -> MarketingExperiment:
    """Propose an A/B test; no traffic is ever allocated automatically."""
    await _ensure_product(session, workspace_id=workspace_id, product_id=data.product_id)
    experiment = MarketingExperiment(
        workspace_id=workspace_id,
        product_id=data.product_id,
        name=data.name,
        hypothesis=data.hypothesis,
        status="proposed",
        variant_a=data.variant_a,
        variant_b=data.variant_b,
        trace_id=trace_id,
    )
    session.add(experiment)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="marketing_experiment.proposed",
        entity_type="marketing_experiment",
        entity_id=str(experiment.id),
        payload={
            "product_id": str(data.product_id) if data.product_id else None,
            "name": data.name,
            "status": "proposed",
        },
        trace_id=trace_id,
    )
    return experiment


async def _load_experiment(
    session: AsyncSession, *, workspace_id: UUID, experiment_id: UUID
) -> MarketingExperiment | None:
    return (
        await session.execute(
            select(MarketingExperiment).where(
                MarketingExperiment.workspace_id == workspace_id,
                MarketingExperiment.id == experiment_id,
            )
        )
    ).scalar_one_or_none()


async def start_experiment(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    experiment_id: UUID,
    data: ExperimentStartRequest,
    trace_id: str | None = None,
) -> MarketingExperiment:
    """Activate a proposed experiment (proposed -> active)."""
    experiment = await _load_experiment(
        session, workspace_id=workspace_id, experiment_id=experiment_id
    )
    if experiment is None:
        raise MarketingError("experiment not found")
    if experiment.status != "proposed":
        raise MarketingError("experiment is not proposed")
    if data.variant_a:
        experiment.variant_a = data.variant_a
    if data.variant_b:
        experiment.variant_b = data.variant_b
    experiment.status = "active"
    experiment.updated_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="marketing_experiment.started",
        entity_type="marketing_experiment",
        entity_id=str(experiment.id),
        payload={"status": "active"},
        trace_id=trace_id,
    )
    return experiment


def _ab_calibration(variant_a: dict, variant_b: dict) -> dict:
    """Deterministic A/B deltas (B - A) for shared numeric metrics."""
    deltas: dict[str, str] = {}
    for key, value_b in variant_b.items():
        value_a = variant_a.get(key)
        if value_a is None:
            continue
        try:
            delta = Decimal(str(value_b)) - Decimal(str(value_a))
        except (TypeError, ValueError):
            continue
        deltas[key] = f"{_q(delta).normalize():f}"
    return {"deltas": deltas, "keys": sorted(deltas)}


async def complete_experiment(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    experiment_id: UUID,
    data: ExperimentCompleteRequest,
    trace_id: str | None = None,
) -> MarketingExperiment:
    """Complete an active experiment and compute A/B calibration."""
    experiment = await _load_experiment(
        session, workspace_id=workspace_id, experiment_id=experiment_id
    )
    if experiment is None:
        raise MarketingError("experiment not found")
    if experiment.status != "active":
        raise MarketingError("experiment is not active")
    experiment.result = {
        "variant_a": data.variant_a_result,
        "variant_b": data.variant_b_result,
        "winner": data.winner,
        "notes": data.notes,
        "completed_at": (
            data.completed_at.isoformat() if data.completed_at else datetime.now(UTC).isoformat()
        ),
    }
    experiment.calibration = _ab_calibration(data.variant_a_result, data.variant_b_result)
    experiment.status = "completed"
    experiment.updated_at = datetime.now(UTC)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="marketing_experiment.completed",
        entity_type="marketing_experiment",
        entity_id=str(experiment.id),
        payload={
            "winner": data.winner,
            "calibration": experiment.calibration,
        },
        trace_id=trace_id,
    )
    return experiment


async def list_experiments(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[MarketingExperiment]:
    stmt = select(MarketingExperiment).where(MarketingExperiment.workspace_id == workspace_id)
    if product_id is not None:
        stmt = stmt.where(MarketingExperiment.product_id == product_id)
    if status:
        stmt = stmt.where(MarketingExperiment.status == status)
    stmt = stmt.order_by(MarketingExperiment.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
