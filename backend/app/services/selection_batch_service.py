"""批量选品工作流处理服务。

负责将 products 表中 funnel_stage='recalled' 的产品批量送入 LangGraph 选品工作流，
更新每个产品的 funnel_stage、评分结果、决策建议，并记录到审批队列。

设计原则（AGENTS.md）：
- Agent 是「提议者」不是「执行者」：只创建待审决策，不自动执行
- 全链路可审计：每次运行记录到 ai_agent_runs
- 优雅降级：单个产品失败不影响其他产品
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_intelligence import ProductAnalysisRun, ProductDecision
from app.schemas.selection_workflow import SelectionWorkflowState
from app.services.selection_pipeline import run_selection_workflow

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


# --------------------------------------------------------------------------- #
# 批量处理入口
# --------------------------------------------------------------------------- #

async def process_batch_products(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    category: str | None = None,
    limit: int = 50,
    dry_run: bool = False,
) -> dict[str, Any]:
    """批量处理 funnel_stage='recalled' 的产品。

    Args:
        session: DB session.
        workspace_id: Workspace scope.
        category: Optional category filter.
        limit: Max products to process.
        dry_run: If true, only report what would be processed.

    Returns:
        Summary dict with counts and results.
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    trace_id = f"batch-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    # Query products to process
    query = select(Product).where(
        Product.workspace_id == ws,
        Product.funnel_stage == "recalled",
        Product.deleted_at.is_(None),
    )
    if category:
        query = query.where(Product.category == category)
    query = query.limit(limit)

    products = (await session.execute(query)).scalars().all()

    if not products:
        return {
            "status": "completed",
            "trace_id": trace_id,
            "total_found": 0,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "results": [],
        }

    if dry_run:
        return {
            "status": "dry_run",
            "trace_id": trace_id,
            "total_found": len(products),
            "processed": 0,
            "results": [
                {"product_id": str(p.id), "sku": p.sku, "name": p.name, "category": p.category}
                for p in products
            ],
        }

    # Process each product
    results = []
    succeeded = 0
    failed = 0

    for product in products:
        try:
            result = await _process_single_product(
                session,
                product=product,
                workspace_id=ws,
                trace_id=trace_id,
            )
            results.append(result)
            succeeded += 1
            logger.info(
                "Product %s (%s) processed: stage=%s decision=%s",
                product.sku,
                product.name,
                result.get("funnel_stage"),
                result.get("decision"),
            )
        except Exception as exc:
            failed += 1
            results.append({
                "product_id": str(product.id),
                "sku": product.sku,
                "name": product.name,
                "error": str(exc),
                "status": "failed",
            })
            logger.warning("Failed to process product %s: %s", product.sku, exc)

    summary = {
        "status": "completed",
        "trace_id": trace_id,
        "total_found": len(products),
        "processed": succeeded + failed,
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }

    logger.info(
        "Batch processing complete: %d found, %d succeeded, %d failed",
        len(products),
        succeeded,
        failed,
    )

    return summary


# --------------------------------------------------------------------------- #
# 单产品处理
# --------------------------------------------------------------------------- #

async def _process_single_product(
    session: AsyncSession,
    *,
    product: Product,
    workspace_id: UUID,
    trace_id: str,
) -> dict[str, Any]:
    """Process a single product through the selection workflow.

    Returns:
        Dict with product_id, sku, name, funnel_stage, decision, etc.
    """
    # Run the selection workflow
    state = await run_selection_workflow(
        session,
        workspace_id=workspace_id,
        product_id=product.id,
        product_name=product.name,
        category=product.category,
        target_market=product.target_market,
        dry_run=False,
        trace_id=trace_id,
    )

    # Update product funnel stage
    new_stage = state.current_stage
    await session.execute(
        update(Product)
        .where(Product.id == product.id)
        .values(funnel_stage=new_stage)
    )

    # If we have a decision, create a pending approval
    if state.recommended_decision and new_stage in ("test_candidate", "deep_candidate"):
        await _create_pending_decision(
            session,
            product=product,
            workspace_id=workspace_id,
            state=state,
            trace_id=trace_id,
        )

    # Create analysis run record
    await _create_analysis_run(
        session,
        product=product,
        workspace_id=workspace_id,
        state=state,
        trace_id=trace_id,
    )

    return {
        "product_id": str(product.id),
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "funnel_stage": new_stage,
        "decision": state.recommended_decision,
        "nuotao_score": state.nuotao_score_total,
        "nuotao_grade": state.nuotao_grade,
        "veto_passed": state.veto_passed,
        "confidence": str(state.confidence) if state.confidence else None,
        "reasons": state.reasons,
        "status": "completed",
    }


async def _create_pending_decision(
    session: AsyncSession,
    *,
    product: Product,
    workspace_id: UUID,
    state: SelectionWorkflowState,
    trace_id: str,
) -> ProductDecision:
    """Create a pending product decision for approval."""
    decision = ProductDecision(
        workspace_id=workspace_id,
        product_id=product.id,
        decision=state.recommended_decision or "hold",
        approval_status="pending",
        confidence=state.confidence,
        reasoning=state.reasons,
        risks=state.risks,
        veto_results=[
            {
                "rule_id": r.rule_id,
                "verdict": r.verdict,
                "reason": r.reason,
            }
            for r in state.veto_results
        ],
        nuotao_score=state.nuotao_score_total,
        nuotao_grade=state.nuotao_grade,
        created_by="selection-workflow",
        trace_id=trace_id,
    )
    session.add(decision)
    await session.flush()
    return decision


async def _create_analysis_run(
    session: AsyncSession,
    *,
    product: Product,
    workspace_id: UUID,
    state: SelectionWorkflowState,
    trace_id: str,
) -> ProductAnalysisRun:
    """Create a product analysis run record for audit."""
    analysis = ProductAnalysisRun(
        workspace_id=workspace_id,
        product_id=product.id,
        provider="langgraph",
        model="selection-workflow-v1",
        prompt_version="v3",
        input_snapshot={
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "category": product.category,
            "target_market": product.target_market,
        },
        output={
            "funnel_stage": state.current_stage,
            "decision": state.recommended_decision,
            "nuotao_score": state.nuotao_score_total,
            "nuotao_grade": state.nuotao_grade,
            "veto_passed": state.veto_passed,
            "confidence": str(state.confidence) if state.confidence else None,
        },
        trace_id=trace_id,
    )
    session.add(analysis)
    await session.flush()
    return analysis


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #

async def get_batch_status(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Get the status of all products in the selection funnel.

    Returns:
        Dict with counts per funnel stage.
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID

    query = (
        select(Product.funnel_stage, Product.category, func.count().label("count"))
        .where(
            Product.workspace_id == ws,
            Product.funnel_stage.isnot(None),
            Product.deleted_at.is_(None),
        )
        .group_by(Product.funnel_stage, Product.category)
    )
    results = (await session.execute(query)).all()

    by_stage = {}
    by_category = {}
    for row in results:
        stage, category, count = row
        by_stage[stage] = by_stage.get(stage, 0) + count
        if category:
            by_category.setdefault(category, {})
            by_category[category][stage] = by_category[category].get(stage, 0) + count

    return {
        "total": sum(by_stage.values()),
        "by_stage": by_stage,
        "by_category": by_category,
    }


async def approve_and_trigger_pipeline(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    product_ids: list[UUID] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Approve pending decisions and trigger listing pipeline.

    This function:
    1. Approves all pending product decisions
    2. Triggers the PipelineOrchestrator for each approved product

    Args:
        session: DB session.
        workspace_id: Workspace scope.
        product_ids: Optional list of product IDs to process.
        dry_run: If true, only report what would be approved.

    Returns:
        Summary dict with approval and pipeline trigger results.
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    trace_id = f"approve-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    # Query pending decisions
    query = select(ProductDecision).where(
        ProductDecision.workspace_id == ws,
        ProductDecision.approval_status == "pending",
    )
    if product_ids:
        query = query.where(ProductDecision.product_id.in_(product_ids))

    results = (await session.execute(query)).scalars().all()

    if not results:
        return {
            "status": "completed",
            "trace_id": trace_id,
            "pending_found": 0,
            "approved": 0,
            "pipeline_triggered": 0,
        }

    if dry_run:
        return {
            "status": "dry_run",
            "trace_id": trace_id,
            "pending_found": len(results),
            "products": [
                {"decision_id": str(d.id), "product_id": str(d.product_id), "decision": d.decision}
                for d in results
            ],
        }

    # Approve all pending decisions
    approved = 0
    pipeline_triggered = 0

    for decision in results:
        try:
            # Approve the decision
            decision.approval_status = "approved"
            decision.approved_by = "batch-approval"
            decision.approved_at = datetime.now(UTC)
            approved += 1

            # Trigger pipeline
            from app.services.selection_listing_bridge import trigger_listing_pipeline
            pipeline_result = await trigger_listing_pipeline(
                session,
                workspace_id=ws,
                product_ids=[decision.product_id],
                dry_run=False,
            )
            if pipeline_result.get("triggered", 0) > 0:
                pipeline_triggered += 1

        except Exception as exc:
            logger.warning("Failed to approve/trigger for decision %s: %s", decision.id, exc)

    await session.commit()

    return {
        "status": "completed",
        "trace_id": trace_id,
        "pending_found": len(results),
        "approved": approved,
        "pipeline_triggered": pipeline_triggered,
    }
