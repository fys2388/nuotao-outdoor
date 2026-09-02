"""Product Context Builder (M2.2).

Assembles the complete, JSON-safe context that the Product Analyst Agent
receives: product master data, current cost + landed cost model, supplier
candidates, latest score with per-dimension evidence, active rules, and the
experiment history. The agent is READ-only with respect to this data.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductCost
from app.models.product_intelligence import (
    ProductExperiment,
    ProductScore,
    ProductScoreEvidence,
    ProductSource,
    SourcingCandidate,
)
from app.models.rule import Rule
from app.services import knowledge
from app.services.product_intelligence import _landed_cost

logger = logging.getLogger(__name__)


class ProductContextError(Exception):
    """Raised when a product context cannot be built."""


def _json_safe(value: Any) -> Any:
    """Convert Decimals/UUIDs/datetimes to JSON-safe primitives."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


async def _load_rule_gates(session: AsyncSession, *, workspace_id: UUID) -> list[dict[str, Any]]:
    """Load active product-analysis rules (read-only registry snapshot)."""
    rows = (
        (
            await session.execute(
                select(Rule).where(
                    Rule.workspace_id == workspace_id,
                    Rule.status == "active",
                    Rule.category == "PRODUCT",
                )
            )
        )
        .scalars()
        .all()
    )
    rules: dict[str, Rule] = {}
    for row in rows:
        current = rules.get(row.rule_id)
        if current is None or row.version > current.version:
            rules[row.rule_id] = row
    return [
        {
            "rule_id": row.rule_id,
            "name": row.name,
            "version": row.version,
            "category": row.category,
            "rule_type": row.rule_type,
            "params": row.params,
            "conditions": row.when_conditions,
            "then_result": row.then_result,
        }
        for row in sorted(rules.values(), key=lambda item: item.rule_id)
    ]


async def build_product_context(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Build the full AI analysis context for a product.

    Raises:
        ProductContextError: when the product does not exist in the workspace.
    """
    product = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        raise ProductContextError("product not found")

    cost = (
        (
            await session.execute(
                select(ProductCost).where(
                    ProductCost.workspace_id == workspace_id,
                    ProductCost.product_id == product_id,
                )
            )
        )
        .scalars()
        .first()
    )

    candidates = (
        (
            await session.execute(
                select(SourcingCandidate)
                .where(
                    SourcingCandidate.workspace_id == workspace_id,
                    SourcingCandidate.product_id == product_id,
                )
                .order_by(SourcingCandidate.purchase_price)
            )
        )
        .scalars()
        .all()
    )

    # M5.13: newest captured source type (1688/MANUAL/CSV/OTHER) is part of
    # the candidate identity passed to the Product Analyst.
    source_type = (
        (
            await session.execute(
                select(ProductSource.source_type)
                .where(
                    ProductSource.workspace_id == workspace_id,
                    ProductSource.product_id == product_id,
                )
                .order_by(ProductSource.captured_at.desc(), ProductSource.created_at.desc())
            )
        )
        .scalars()
        .first()
    )

    score = (
        (
            await session.execute(
                select(ProductScore)
                .where(
                    ProductScore.workspace_id == workspace_id,
                    ProductScore.product_id == product_id,
                )
                .order_by(ProductScore.scored_at.desc())
            )
        )
        .scalars()
        .first()
    )

    evidence: list[ProductScoreEvidence] = []
    if score is not None:
        evidence = (
            (
                await session.execute(
                    select(ProductScoreEvidence).where(
                        ProductScoreEvidence.workspace_id == workspace_id,
                        ProductScoreEvidence.product_score_id == score.id,
                    )
                )
            )
            .scalars()
            .all()
        )

    experiments = (
        (
            await session.execute(
                select(ProductExperiment)
                .where(
                    ProductExperiment.workspace_id == workspace_id,
                    ProductExperiment.product_id == product_id,
                )
                .order_by(ProductExperiment.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    rules = await _load_rule_gates(session, workspace_id=workspace_id)

    # M5.6 knowledge feedback: prior experiment outcomes (only after human-
    # approved calibration) ground the next analysis round.
    knowledge_entries = await knowledge.list_knowledge_entries(
        session,
        workspace_id=workspace_id,
        product_id=product_id,
        limit=5,
    )

    landed = _landed_cost(cost)
    cost_status = "KNOWN" if landed > Decimal("0") else "UNKNOWN"

    context = {
        "meta": {
            "workspace_id": str(workspace_id),
            "product_id": str(product_id),
            "built_at": datetime.now(UTC).isoformat(),
            "trace_id": trace_id,
            "market": product.target_market,
        },
        "product": {
            "sku": product.sku,
            "name": product.name,
            "description": product.description,
            "category": product.category,
            "brand": product.brand,
            "status": product.status,
            "candidate_status": product.candidate_status,
            "source": product.source,
            "source_type": source_type,
            "source_url": product.source_url,
            "tags": product.tags,
            "attributes": product.attributes,
            "weight_kg": str(product.weight_kg) if product.weight_kg is not None else None,
            "dimensions": product.dimensions,
            "target_market": product.target_market,
        },
        "cost": {
            "currency": cost.currency if cost else "USD",
            "purchase_cost": str(cost.purchase_cost) if cost else "0",
            "domestic_shipping": str(cost.domestic_shipping) if cost else "0",
            "first_leg_shipping": str(cost.first_leg_shipping) if cost else "0",
            "last_leg_shipping": str(cost.last_leg_shipping) if cost else "0",
            "payment_fee": str(cost.payment_fee) if cost else "0",
            "marketing_amortization": str(cost.marketing_amortization) if cost else "0",
            "after_sales_loss": str(cost.after_sales_loss) if cost else "0",
            "total_cost": str(cost.total_cost) if cost else "0",
            "version": cost.version if cost else None,
        },
        "landed_cost": {
            "purchase_cost": str(cost.purchase_cost) if cost else "0",
            "domestic_shipping": str(cost.domestic_shipping) if cost else "0",
            "international_shipping": (str(cost.international_shipping) if cost else "0"),
            "packaging": str(cost.packaging) if cost else "0",
            "tax_estimate": str(cost.tax_estimate) if cost else "0",
            "handling": str(cost.handling) if cost else "0",
            "total_landed_cost": str(landed),
            "cost_status": cost_status,
        },
        "supplier_candidates": [
            {
                "supplier_code": candidate.supplier_code,
                "source_type": candidate.source_type,
                "source_url": candidate.source_url,
                "title": candidate.title,
                "purchase_price": str(candidate.purchase_price),
                "moq": candidate.moq,
                "lead_time_days": candidate.lead_time_days,
                "trend_score": (
                    str(candidate.trend_score) if candidate.trend_score is not None else None
                ),
                "profit_model": candidate.profit_model,
                "status": candidate.status,
            }
            for candidate in candidates
        ],
        "score": (
            {
                "score_id": str(score.id),
                "total": str(score.total),
                "dimensions": {
                    "profit": str(score.profit),
                    "logistics": str(score.logistics),
                    "demand": str(score.demand),
                    "competition": str(score.competition),
                    "differentiation": str(score.differentiation),
                    "compliance": str(score.compliance),
                },
                "model_version": score.model_version,
                "rule_version": score.rule_version,
                "scored_at": score.scored_at.isoformat(),
                "evidence": [
                    {
                        "dimension": row.dimension,
                        "score": str(row.score),
                        "source": row.source,
                        "evidence": row.evidence,
                        "confidence": str(row.confidence),
                    }
                    for row in evidence
                ],
            }
            if score is not None
            else None
        ),
        "rules": rules,
        "knowledge": [
            {
                "knowledge_id": str(entry.id),
                "entry_type": entry.entry_type,
                "category": entry.category,
                "title": entry.title,
                "content": entry.content,
                "tags": entry.tags,
                "source": entry.source,
                "trace_id": entry.trace_id,
            }
            for entry in knowledge_entries
        ],
        "experiments": [
            {
                "experiment_id": str(experiment.id),
                "experiment_type": experiment.experiment_type,
                "status": experiment.status,
                "prediction": experiment.prediction,
                "experiment": experiment.experiment,
                "actual_result": experiment.actual_result,
                "calibration": experiment.calibration,
            }
            for experiment in experiments
        ],
    }
    return _json_safe(context)
