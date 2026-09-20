"""Hand off a V3.0 evaluation to the testing loop and approval queue.

After a product is scored it should not sit at a funnel stage with no next
action. This module turns a *test_candidate* result into a (idempotent) proposed
market-test experiment plus a human-approval suggestion, and a *hero* result
into a Hero nomination suggestion. Every suggestion is created with
``auto_approve=False`` — the AI proposes, a human approves (AGENTS.md §3.1/3.3).

Idempotency is deliberate: re-running an evaluation must never stack duplicate
suggestions/experiments (the system already suffered from repeated noise), so
existing open records for the same product/action are reused, not recreated.
Open-state checks are done in Python to stay portable across SQLite tests and
PostgreSQL.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_suggestion import AgentSuggestion
from app.models.product_intelligence import ProductExperiment
from app.services import agent_suggestion_service

logger = logging.getLogger(__name__)

ACTION_MARKET_TEST = "nuotao_start_market_test"
ACTION_HERO_NOMINATION = "nuotao_hero_nomination"

_OPEN_SUGGESTION_STATES = ("pending_approval", "approved", "executing")
_OPEN_EXPERIMENT_STATES = ("proposed", "approved", "running")


async def _has_open_suggestion(
    session: AsyncSession, workspace_id: UUID, product_id: UUID, action: str
) -> bool:
    rows = (
        (
            await session.execute(
                select(AgentSuggestion).where(
                    AgentSuggestion.workspace_id == workspace_id,
                    AgentSuggestion.execution_action == action,
                    AgentSuggestion.status.in_(_OPEN_SUGGESTION_STATES),
                )
            )
        )
        .scalars()
        .all()
    )
    target = str(product_id)
    return any(str(row.execution_params.get("product_id")) == target for row in rows)


async def _open_experiment(
    session: AsyncSession, workspace_id: UUID, product_id: UUID
) -> ProductExperiment | None:
    return (
        (
            await session.execute(
                select(ProductExperiment)
                .where(
                    ProductExperiment.workspace_id == workspace_id,
                    ProductExperiment.product_id == product_id,
                    ProductExperiment.status.in_(_OPEN_EXPERIMENT_STATES),
                )
                .order_by(ProductExperiment.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def propose_selection_handoff(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    product_name: str,
    nuotao_total: float,
    grade: str | None,
    funnel_stage: str,
    vetoed: bool,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Create the next-action experiment/suggestion(s) for an evaluated product.

    Returns a summary of what was created vs. reused. Rejected products produce
    no suggestions (avoid noise).
    """
    created_suggestions: list[int] = []
    actions: list[str] = []
    experiment_id: str | None = None

    if vetoed or grade == "reject" or funnel_stage == "rejected":
        return {
            "suggestion_ids": created_suggestions,
            "experiment_id": None,
            "actions": actions,
            "note": "rejected: no handoff created",
        }

    # 8 -> 3: a product that cleared vetoes and reached test_candidate gets a
    # proposed market-test experiment and a human-gated "start test" suggestion.
    if funnel_stage == "test_candidate":
        experiment = await _open_experiment(session, workspace_id, product_id)
        if experiment is None:
            experiment = ProductExperiment(
                workspace_id=workspace_id,
                product_id=product_id,
                experiment_type="nuotao_market_test",
                status="proposed",
                hypothesis=(
                    f"Nuotao {nuotao_total:.1f}（{grade}）通过一票否决，"
                    "假设小批量测试可达成测试 KPI（转化/ROAS/退货率）。"
                ),
                prediction={
                    "nuotao_total": nuotao_total,
                    "grade": grade,
                    "funnel_stage": funnel_stage,
                    "model": "nuotao-score-v3.0",
                },
                version="v1",
                source_trace_id=trace_id,
            )
            session.add(experiment)
            await session.flush()
            actions.append("experiment_created")
        else:
            actions.append("experiment_reused")
        experiment_id = str(experiment.id)

        if not await _has_open_suggestion(
            session, workspace_id, product_id, ACTION_MARKET_TEST
        ):
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="product_analyst",
                suggestion_type="product_optimization",
                title=f"启动小批量测试：{product_name}",
                description=(
                    f"V3.0 评估 Nuotao {nuotao_total:.1f}、等级 {grade}、"
                    f"漏斗阶段 {funnel_stage}，无一票否决，建议进入 8→3 小批量测试。"
                ),
                execution_action=ACTION_MARKET_TEST,
                execution_params={
                    "product_id": str(product_id),
                    "nuotao_total": nuotao_total,
                    "grade": grade,
                    "funnel_stage": funnel_stage,
                    "experiment_id": experiment_id,
                },
                expected_impact="以最小采购量验证真实转化、ROAS 与退货率，决定是否进入 Hero/Core。",
                priority="high" if grade in ("hero", "core") else "medium",
                risk_level="medium",
                auto_approve=False,
                commit=False,
                workspace_id=workspace_id,
                source="auto",
            )
            created_suggestions.append(suggestion.id)
            actions.append("market_test_suggestion_created")

    # Hero nomination: Nuotao >= 85 and no hard veto -> human nomination gate.
    if grade == "hero" and not vetoed:
        if not await _has_open_suggestion(
            session, workspace_id, product_id, ACTION_HERO_NOMINATION
        ):
            suggestion = await agent_suggestion_service.create_suggestion(
                session,
                agent_id="product_analyst",
                suggestion_type="product_optimization",
                title=f"提名 Hero 产品：{product_name}",
                description=(
                    f"Nuotao {nuotao_total:.1f} ≥ 85 且无一票否决，"
                    "提名进入 Hero 候选，需人工终审确认品类战略与差异化。"
                ),
                execution_action=ACTION_HERO_NOMINATION,
                execution_params={
                    "product_id": str(product_id),
                    "nuotao_total": nuotao_total,
                    "grade": grade,
                },
                expected_impact="确立为品牌 Hero 款，优先资源投入与前台展示。",
                priority="high",
                risk_level="high",
                auto_approve=False,
                commit=False,
                workspace_id=workspace_id,
                source="auto",
            )
            created_suggestions.append(suggestion.id)
            actions.append("hero_nomination_created")

    return {
        "suggestion_ids": created_suggestions,
        "experiment_id": experiment_id,
        "actions": actions,
    }
