"""V3.0 small-batch test loop: 8 -> 3 -> 1-2 (human-gated, auditable).

Flow:
  test_candidate --(human starts test)--> testing
  testing --(KPI result recorded)--> passed/failed experiment
  passed + grade hero --> (idempotent) Hero nomination suggestion --> human
  final approval (promote_to_hero) --> funnel_stage 'hero'
  failed --> (idempotent) drop suggestion for a human; never auto-deleted.

Thresholds are NOT hard-coded here: the human passes an explicit ``success``
verdict after reading the measured KPIs (AGENTS.md §1.2.5 / §3.1). Every state
change is persisted on the experiment row / suggestion, giving an audit trail.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_intelligence import (
    ProductExperiment,
    ProductNuotaoScore,
)
from app.services import agent_suggestion_service
from app.services.nuotao_handoff import (
    ACTION_HERO_NOMINATION,
    _has_open_suggestion,
    propose_selection_handoff,
)

logger = logging.getLogger(__name__)

ACTION_DROP_AFTER_TEST = "nuotao_drop_after_test"
_OPEN_EXPERIMENT_STATES = ("proposed", "approved", "running", "passed")


async def _latest_experiment(
    session: AsyncSession, workspace_id: UUID, product_id: UUID
) -> ProductExperiment | None:
    return (
        (
            await session.execute(
                select(ProductExperiment)
                .where(
                    ProductExperiment.workspace_id == workspace_id,
                    ProductExperiment.product_id == product_id,
                )
                .order_by(ProductExperiment.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def _latest_grade(
    session: AsyncSession, product_id: UUID
) -> tuple[float | None, str | None]:
    row = (
        (
            await session.execute(
                select(ProductNuotaoScore)
                .where(ProductNuotaoScore.product_id == product_id)
                .order_by(ProductNuotaoScore.scored_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return None, None
    return float(row.total), row.grade


async def _require_active_product(session: AsyncSession, product_id: UUID) -> Product:
    product = await session.get(Product, product_id)
    if product is None or product.deleted_at is not None:
        raise ValueError(f"product not found: {product_id}")
    return product


async def start_market_test(
    session: AsyncSession,
    product_id: UUID,
    *,
    actor: str,
    workspace_id: UUID | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Human gate 1: approve and start the small-batch test (8 -> 3)."""
    product = await _require_active_product(session, product_id)
    workspace_id = workspace_id or product.workspace_id
    if product.funnel_stage not in ("test_candidate", "testing"):
        raise ValueError(
            f"only a test_candidate can start a market test (current: {product.funnel_stage})"
        )
    experiment = await _latest_experiment(session, workspace_id, product_id)
    if experiment is None:
        raise ValueError("no proposed experiment; run V3 evaluation first")

    if plan:
        experiment.experiment = plan
    if experiment.status != "running":
        experiment.status = "running"
        experiment.started_by = actor
    product.funnel_stage = "testing"
    await session.flush()
    return {
        "product_id": str(product_id),
        "funnel_stage": "testing",
        "experiment_id": str(experiment.id),
        "experiment_status": experiment.status,
    }


async def record_test_result(
    session: AsyncSession,
    product_id: UUID,
    *,
    actor: str,
    actual: dict[str, Any],
    success: bool | None,
    note: str | None = None,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Record measured KPIs; on pass nominate Hero (grade hero), on fail propose drop."""
    product = await _require_active_product(session, product_id)
    workspace_id = workspace_id or product.workspace_id
    experiment = await _latest_experiment(session, workspace_id, product_id)
    if experiment is None:
        raise ValueError("no experiment found for product")

    experiment.actual_result = actual or {}
    history = list(experiment.result_history or [])
    history.append(
        {
            "actor": actor,
            "actual": actual or {},
            "success": success,
            "note": note,
            "at": datetime.now(UTC).isoformat(),
        }
    )
    experiment.result_history = history
    if success is True:
        experiment.status = "passed"
    elif success is False:
        experiment.status = "failed"
    else:
        experiment.status = "completed"

    actions: list[str] = []
    total, grade = await _latest_grade(session, product_id)
    if success is True and grade == "hero":
        handoff = await propose_selection_handoff(
            session,
            workspace_id=workspace_id,
            product_id=product_id,
            product_name=product.name,
            nuotao_total=total or 0.0,
            grade=grade,
            funnel_stage="testing",
            vetoed=False,
        )
        if handoff["suggestion_ids"]:
            actions.append("hero_nomination_created")

    if success is False and not await _has_open_suggestion(
        session, workspace_id, product_id, ACTION_DROP_AFTER_TEST
    ):
        suggestion = await agent_suggestion_service.create_suggestion(
            session,
            agent_id="product_analyst",
            suggestion_type="product_optimization",
            title=f"测试未达标，建议淘汰/回炉：{product.name}",
            description=(
                "小批量测试 KPI 未达标，建议人工复核后淘汰或回炉优化。"
                f"实测：{actual or {}}。备注：{note or '无'}"
            ),
            execution_action=ACTION_DROP_AFTER_TEST,
            execution_params={"product_id": str(product_id), "actual": actual or {}},
            priority="medium",
            risk_level="medium",
            auto_approve=False,
            commit=False,
            workspace_id=workspace_id,
            source="auto",
        )
        actions.append("drop_suggestion_created")
        logger.info("test-fail drop suggestion %s for %s", suggestion.id, product_id)

    await session.flush()
    return {
        "product_id": str(product_id),
        "experiment_id": str(experiment.id),
        "experiment_status": experiment.status,
        "funnel_stage": product.funnel_stage,
        "actions": actions,
    }


async def promote_to_hero(
    session: AsyncSession,
    product_id: UUID,
    *,
    actor: str,
    comment: str | None = None,
    force: bool = False,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Human gate 2 (final): approve a passed test as a Hero product (3 -> 1-2)."""
    product = await _require_active_product(session, product_id)
    workspace_id = workspace_id or product.workspace_id
    experiment = await _latest_experiment(session, workspace_id, product_id)
    if not force and (experiment is None or experiment.status != "passed"):
        raise ValueError(
            "promotion requires a passed market test; pass force=True to override"
        )

    product.funnel_stage = "hero"
    if experiment is not None:
        experiment.approved_by = actor
        experiment.approved_at = datetime.now(UTC)
        experiment.status = "completed"
        if comment:
            experiment.calibration = {**(experiment.calibration or {}), "hero_comment": comment}
    await session.flush()
    return {"product_id": str(product_id), "funnel_stage": "hero", "forced": force}
