"""选品→上架桥接服务。

负责将选品工作流批准的产品送入 PipelineOrchestrator，自动推进
「文案生成 → 图片生成 → 定价计算 → 人工审核 → WooCommerce上架」全流程。

设计原则（AGENTS.md）：
- Agent 是「提议者」不是「执行者」：只创建待审决策，不自动上架
- 全链路可审计：每次运行记录到 ai_agent_runs
- 优雅降级：PipelineOrchestrator 服务不存在时返回明确错误
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_intelligence import ProductDecision

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


# --------------------------------------------------------------------------- #
# 批量触发 Pipeline
# --------------------------------------------------------------------------- #

async def trigger_listing_pipeline(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    product_ids: list[UUID] | None = None,
    decision_id: UUID | None = None,
    category: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """触发已批准产品的 PipelineOrchestrator。

    Args:
        session: DB session.
        workspace_id: Workspace scope.
        product_ids: Optional list of product IDs to process.
        decision_id: Optional specific decision to process.
        category: Optional category filter.
        dry_run: If true, only report what would be processed.

    Returns:
        Summary dict with counts and pipeline run IDs.
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    trace_id = f"listing-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    # Query approved products
    query = select(Product).where(
        Product.workspace_id == ws,
        Product.deleted_at.is_(None),
    )

    if product_ids:
        query = query.where(Product.id.in_(product_ids))
    if category:
        query = query.where(Product.category == category)

    # Only process products that have approved decisions
    query = query.join(
        ProductDecision,
        ProductDecision.product_id == Product.id,
    ).where(
        ProductDecision.workspace_id == ws,
        ProductDecision.approval_status == "approved",
        ProductDecision.decision.in_(["test", "hold"]),
    )

    if decision_id:
        query = query.where(ProductDecision.id == decision_id)

    results = (await session.execute(query)).scalars().all()

    if not results:
        return {
            "status": "completed",
            "trace_id": trace_id,
            "total_found": 0,
            "triggered": 0,
            "failed": 0,
            "pipeline_runs": [],
        }

    if dry_run:
        return {
            "status": "dry_run",
            "trace_id": trace_id,
            "total_found": len(results),
            "triggered": 0,
            "products": [
                {"product_id": str(p.id), "sku": p.sku, "name": p.name, "category": p.category}
                for p in results
            ],
        }

    # Trigger pipeline for each product
    pipeline_runs = []
    triggered = 0
    failed = 0

    for product in results:
        try:
            run = await _trigger_single_pipeline(
                session,
                product=product,
                workspace_id=ws,
                trace_id=trace_id,
            )
            pipeline_runs.append(run)
            triggered += 1
            logger.info(
                "Pipeline triggered for %s (%s): %s",
                product.sku,
                product.name,
                run.get("run_id", "?"),
            )
        except Exception as exc:
            failed += 1
            pipeline_runs.append({
                "product_id": str(product.id),
                "sku": product.sku,
                "name": product.name,
                "error": str(exc),
                "status": "failed",
            })
            logger.warning("Failed to trigger pipeline for %s: %s", product.sku, exc)

    summary = {
        "status": "completed",
        "trace_id": trace_id,
        "total_found": len(results),
        "triggered": triggered,
        "failed": failed,
        "pipeline_runs": pipeline_runs,
    }

    logger.info(
        "Pipeline triggering complete: %d found, %d triggered, %d failed",
        len(results),
        triggered,
        failed,
    )

    return summary


# --------------------------------------------------------------------------- #
# 单产品 Pipeline 触发
# --------------------------------------------------------------------------- #

async def _trigger_single_pipeline(
    session: AsyncSession,
    *,
    product: Product,
    workspace_id: UUID,
    trace_id: str,
) -> dict[str, Any]:
    """Trigger the PipelineOrchestrator for a single product.

    Returns:
        Dict with run_id and status.
    """
    # Try to use the PipelineOrchestrator
    try:
        from app.services.pipeline_orchestrator import (
            create_pipeline_run,
            start_pipeline,
        )

        # Create pipeline run
        run = create_pipeline_run(
            product_name=product.name,
            source_url=product.source_url,
            source_id=str(product.id),
            auto_list=True,
        )

        # Start pipeline (this runs in background)
        await start_pipeline(run["run_id"])

        # Update product to mark it as in pipeline
        await session.execute(
            update(Product)
            .where(Product.id == product.id)
            .values(
                meta={
                    **product.meta,
                    "pipeline_run_id": run["run_id"],
                    "pipeline_triggered_at": datetime.now(UTC).isoformat(),
                    "pipeline_trace_id": trace_id,
                }
            )
        )

        return {
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "run_id": run["run_id"],
            "status": "started",
        }

    except ImportError as exc:
        # PipelineOrchestrator not available
        logger.warning("PipelineOrchestrator not available: %s", exc)
        return {
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "error": "PipelineOrchestrator service not available",
            "status": "degraded",
        }
    except Exception as exc:
        logger.exception("Failed to trigger pipeline for %s: %s", product.sku, exc)
        return {
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "error": str(exc),
            "status": "failed",
        }


# --------------------------------------------------------------------------- #
# 辅助查询
# --------------------------------------------------------------------------- #

async def get_pending_products(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Get products that are ready for listing pipeline.

    Products must have:
    - approval_status='approved' decision
    - decision_type='test' or 'hold'
    - funnel_stage='test_candidate' or higher
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID

    query = (
        select(
            Product.id,
            Product.sku,
            Product.name,
            Product.category,
            Product.funnel_stage,
            ProductDecision.id.label("decision_id"),
            ProductDecision.decision,
            ProductDecision.confidence,
        )
        .join(ProductDecision, ProductDecision.product_id == Product.id)
        .where(
            Product.workspace_id == ws,
            Product.deleted_at.is_(None),
            ProductDecision.workspace_id == ws,
            ProductDecision.approval_status == "approved",
            ProductDecision.decision.in_(["test", "hold"]),
        )
        .order_by(ProductDecision.created_at.desc())
    )

    results = (await session.execute(query)).all()

    return [
        {
            "product_id": str(row.id),
            "sku": row.sku,
            "name": row.name,
            "category": row.category,
            "funnel_stage": row.funnel_stage,
            "decision_id": str(row.decision_id),
            "decision": row.decision,
            "confidence": str(row.confidence) if row.confidence else None,
        }
        for row in results
    ]


async def get_pipeline_status(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Get pipeline status for all products.

    Returns:
        Dict with counts by pipeline stage.
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID

    # Count products by funnel stage
    query = (
        select(Product.funnel_stage, Product.candidate_status, Product.status)
        .where(
            Product.workspace_id == ws,
            Product.deleted_at.is_(None),
        )
    )
    results = (await session.execute(query)).all()

    by_funnel = {}
    by_candidate = {}
    by_status = {}

    for row in results:
        funnel = row.funnel_stage or "none"
        candidate = row.candidate_status or "none"
        status = row.status or "draft"
        by_funnel[funnel] = by_funnel.get(funnel, 0) + 1
        by_candidate[candidate] = by_candidate.get(candidate, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "total": sum(by_funnel.values()),
        "by_funnel_stage": by_funnel,
        "by_candidate_status": by_candidate,
        "by_product_status": by_status,
    }
