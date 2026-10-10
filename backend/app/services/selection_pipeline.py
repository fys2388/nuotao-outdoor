"""Selection pipeline service — LangGraph workflow orchestration.

Orchestrates the LangGraph selection workflow, persists results to
the database, and integrates with the existing Product Analyst Agent
and approval workflow.

Key responsibilities:
- Trigger the LangGraph selection workflow
- Persist workflow state to product_analysis_runs (audit)
- Create ProductDecision proposals (pending approval)
- Create ai_agent_runs for full-chain auditability
- Integrate with the approval queue (Human-in-the-loop)

Design principles (AGENTS.md):
- Agent is a "proposer": creates pending decisions, never auto-approves.
- Full-chain auditable: every run is recorded in ai_agent_runs.
- Human-in-the-loop: decisions require approval before execution.
- Graceful degradation: LLM failures fall back to deterministic scoring.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.selection_workflows import build_selection_graph, make_initial_state
from app.models.agent import AiAgentRun
from app.models.product_intelligence import (
    ProductAnalysisRun,
    ProductDecision,
)
from app.schemas.selection_workflow import (
    SelectionWorkflowRunOut,
    SelectionWorkflowState,
)
from app.services import event_service
from app.services.category_config_service import load_category_config, load_excluded_categories
from app.services.selection_scorecard import load_operational_weights

logger = logging.getLogger(__name__)

AGENT_NAME = "selection-workflow"
TRIGGER = "api:selection-workflow:run"


# ── Workflow execution ──────────────────────────────────────────────
async def run_selection_workflow(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    product_name: str | None = None,
    category: str | None = None,
    target_market: str = "US",
    dry_run: bool = False,
    trace_id: str | None = None,
) -> SelectionWorkflowState:
    """Execute the LangGraph selection workflow and persist results.

    Args:
        session: DB session for persistence.
        workspace_id: Workspace scope.
        product_id: Product to evaluate.
        product_name: Optional product name for market data collection.
        category: Product category for market data + veto rules.
        target_market: Target market code (US/EU/etc).
        dry_run: If true, validate the chain without writing to DB.
        trace_id: Optional trace ID for correlation.

    Returns:
        The final SelectionWorkflowState.

    Raises:
        ProductAnalystError: when the workflow cannot produce a result.
    """
    trace_id = trace_id or f"selection-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    start_time = datetime.now(UTC)

    # Build initial state
    state = make_initial_state(
        workspace_id=str(workspace_id),
        product_id=str(product_id),
        product_name=product_name,
        category=category,
        target_market=target_market,
        trace_id=trace_id,
    )

    # Load category configuration from strategy_versions (for Brand Fit,
    # compliance requirements, banned subcategories, etc.)
    if category:
        try:
            cat_config = await load_category_config(session, category=category, workspace_id=workspace_id)
            state.category_config = cat_config
            logger.info("Loaded category config for %s: %s", category, cat_config.get("name", "?"))
        except Exception as exc:
            logger.warning("Failed to load category config for %s: %s", category, exc)

        # Load category-specific operational weights
        try:
            from decimal import Decimal
            weights_dec = await load_operational_weights(
                session, workspace_id=str(workspace_id), category=category
            )
            # Convert Decimal to float for Pydantic serialization
            state.operational_weights = {k: float(v) for k, v in weights_dec.items()}
            logger.info("Loaded operational weights for %s: %s", category, state.operational_weights)
        except Exception as exc:
            logger.warning("Failed to load operational weights for %s: %s", category, exc)

    # Build and execute the LangGraph
    graph = build_selection_graph()
    try:
        result_dict = await graph.ainvoke(state)
        # Convert dict back to SelectionWorkflowState
        result_state = SelectionWorkflowState(**result_dict)
    except Exception as exc:
        logger.exception("Selection workflow failed for product %s", product_id)
        result_state = state
        result_state.error = str(exc)
        result_state.status = "failed"
        if not dry_run:
            await _persist_failure(
                session,
                workspace_id=workspace_id,
                product_id=product_id,
                trace_id=trace_id,
                error=str(exc),
                state=state,
            )
        return result_state

    latency_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

    # Persist results (unless dry_run)
    if not dry_run:
        await _persist_run(
            session,
            workspace_id=workspace_id,
            product_id=product_id,
            trace_id=trace_id,
            state=result_state,
            latency_ms=latency_ms,
        )

    return result_state


# ── Persistence ─────────────────────────────────────────────────────
async def _persist_run(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    trace_id: str,
    state: SelectionWorkflowState,
    latency_ms: int,
) -> None:
    """Persist a successful workflow run to the database.

    Creates:
    - product_analysis_runs (audit trail)
    - ai_agent_runs (agent audit)
    - product_decisions (pending approval)
    - event_log entries
    """
    decision = state.recommended_decision or "hold"

    # ── ProductAnalysisRun (audit) ──
    analysis_run = ProductAnalysisRun(
        workspace_id=workspace_id,
        product_id=product_id,
        provider="langgraph",
        model="selection-workflow-v1",
        prompt_version="v3",
        input_snapshot={
            "product_id": str(product_id),
            "product_name": state.product_name,
            "category": state.category,
            "target_market": state.target_market,
        },
        output={
            "current_stage": state.current_stage,
            "recommended_decision": decision,
            "nuotao_score_total": (
                float(state.nuotao_score_total)
                if state.nuotao_score_total
                else None
            ),
            "nuotao_grade": state.nuotao_grade,
            "veto_passed": state.veto_passed,
            "confidence": (
                str(state.confidence) if state.confidence else None
            ),
            "reasons": state.reasons,
            "risks": state.risks,
            "veto_results": [r.model_dump() for r in state.veto_results],
            "market_data": (
                state.market_data.model_dump() if state.market_data else None
            ),
        },
        token_usage={},
        estimated_cost=Decimal("0"),
        latency_ms=latency_ms,
        status="completed",
        trace_id=trace_id,
    )
    session.add(analysis_run)

    # ── ProductDecision (pending approval) ──
    decision_row = ProductDecision(
        workspace_id=workspace_id,
        product_id=product_id,
        decision=decision,
        score=Decimal(str(state.nuotao_score_total))
        if state.nuotao_score_total
        else None,
        confidence=state.confidence,
        reasons=state.reasons,
        risks=state.risks,
        recommended_price=None,  # Pricing is set separately
        max_cac=None,
        test_quantity=50 if decision == "test" else None,
        test_days=30 if decision == "test" else None,
        approval_status="pending",
        trace_id=trace_id,
    )
    session.add(decision_row)

    # ── AiAgentRun (agent audit) ──
    agent_run = AiAgentRun(
        workspace_id=workspace_id,
        agent=AGENT_NAME,
        trigger=TRIGGER,
        input={
            "product_id": str(product_id),
            "product_name": state.product_name,
            "category": state.category,
            "target_market": state.target_market,
        },
        plan={
            "steps": [
                "market_data_collection",
                "initial_screening",
                "v3_scoring",
                "veto_check",
                "decision",
            ]
        },
        tool_calls=[
            {
                "tool": "market_data_collector",
                "sources": state.market_data.data_sources
                if state.market_data
                else [],
            }
        ],
        output={
            "decision": decision,
            "nuotao_score": float(state.nuotao_score_total)
            if state.nuotao_score_total
            else None,
            "nuotao_grade": state.nuotao_grade,
            "veto_passed": state.veto_passed,
            "confidence": str(state.confidence) if state.confidence else None,
        },
        approval={
            "required": True,
            "status": "pending",
            "target": "product_decisions",
        },
        cost=Decimal("0"),
        status="completed",
        trace_id=trace_id,
        completed_at=datetime.now(UTC),
    )
    session.add(agent_run)

    # ── Event log ──
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.selection_workflow.completed",
        entity_type="product",
        entity_id=str(product_id),
        payload={
            "decision": decision,
            "nuotao_score": float(state.nuotao_score_total)
            if state.nuotao_score_total
            else None,
            "veto_passed": state.veto_passed,
            "current_stage": state.current_stage,
        },
        trace_id=trace_id,
    )

    logger.info(
        "Selection workflow persisted: product=%s decision=%s score=%s trace=%s",
        product_id,
        decision,
        state.nuotao_score_total,
        trace_id,
    )


async def _persist_failure(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    trace_id: str,
    error: str,
    state: SelectionWorkflowState,
) -> None:
    """Persist a failed workflow run for audit."""
    analysis_run = ProductAnalysisRun(
        workspace_id=workspace_id,
        product_id=product_id,
        provider="langgraph",
        model="selection-workflow-v1",
        prompt_version="v3",
        input_snapshot={
            "product_id": str(product_id),
            "product_name": state.product_name,
            "category": state.category,
        },
        output={"error": error},
        token_usage={},
        estimated_cost=Decimal("0"),
        latency_ms=0,
        status="failed",
        trace_id=trace_id,
    )
    session.add(analysis_run)

    agent_run = AiAgentRun(
        workspace_id=workspace_id,
        agent=AGENT_NAME,
        trigger=TRIGGER,
        input={"product_id": str(product_id)},
        plan={"steps": []},
        tool_calls=[],
        output={"error": error},
        approval={"required": False, "status": "not_required"},
        cost=Decimal("0"),
        status="failed",
        trace_id=trace_id,
        completed_at=datetime.now(UTC),
    )
    session.add(agent_run)

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="agent.selection_workflow.failed",
        entity_type="product",
        entity_id=str(product_id),
        payload={"error": error[:500]},
        trace_id=trace_id,
    )


# ── Query helpers ───────────────────────────────────────────────────
async def get_latest_workflow_run(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
) -> SelectionWorkflowRunOut | None:
    """Get the most recent selection workflow run for a product."""
    run = (
        (
            await session.execute(
                select(ProductAnalysisRun)
                .where(
                    ProductAnalysisRun.workspace_id == workspace_id,
                    ProductAnalysisRun.product_id == product_id,
                    ProductAnalysisRun.provider == "langgraph",
                )
                .order_by(ProductAnalysisRun.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if run is None:
        return None

    output = run.output or {}
    return SelectionWorkflowRunOut(
        run_id=str(run.id),
        product_id=str(run.product_id),
        workspace_id=str(run.workspace_id),
        status="completed" if run.status == "completed" else "failed",
        current_stage=output.get("current_stage", "recalled"),
        recommended_decision=output.get("recommended_decision"),
        nuotao_score_total=output.get("nuotao_score_total"),
        nuotao_grade=output.get("nuotao_grade"),
        veto_passed=output.get("veto_passed"),
        confidence=Decimal(str(output["confidence"]))
        if output.get("confidence")
        else None,
        reasons=output.get("reasons", []),
        risks=output.get("risks", []),
        trace_id=run.trace_id,
        error=output.get("error") if run.status == "failed" else None,
        created_at=run.created_at.isoformat() if run.created_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
    )


# ── Status ──────────────────────────────────────────────────────────
def get_selection_workflow_status() -> dict[str, Any]:
    """Get the selection workflow system status."""
    return {
        "status": "running",
        "workflow_type": "langgraph_selection",
        "graph_nodes": [
            "market_data",
            "initial_screening",
            "v3_scoring",
            "veto_check",
            "decision",
        ],
        "funnel_stages": [
            "recalled",
            "screened",
            "deep_candidate",
            "test_candidate",
            "testing",
            "hero",
            "rejected",
        ],
        "veto_rules": ["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9", "V10", "V11", "V12"],
        "scoring": {
            "operational": "V2.0 (11 dimensions)",
            "nuotao": "V3.0 (6 dimensions, 0-100)",
        },
        "workflow": "market_data -> screening -> scoring -> veto -> decision -> approval",
        "note": "LangGraph selection workflow is ready. Decisions require human approval.",
    }
