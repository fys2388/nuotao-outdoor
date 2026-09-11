"""
AI 产品经理选品建议 API 端点
支持候选清单生成、决策创建、审批流程
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.selection_manager_service import (
    approve_selection_decision,
    create_selection_decision,
    generate_selection_recommendations,
    get_selection_decisions,
    get_selection_manager_status,
    reject_selection_decision,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/selection", tags=["selection"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================
# 请求/响应模型
# ============================================

class SelectionDecisionRequest(BaseModel):
    """选品决策创建请求"""
    product_id: str = Field(..., description="产品 ID（UUID）")
    decision: str = Field(..., description="决策类型：test/hold/reject")
    score: float | None = Field(None, description="产品评分（0-100）", ge=0, le=100)
    confidence: float | None = Field(None, description="置信度（0-1）", ge=0, le=1)
    reasons: list[str] | None = Field(None, description="决策理由")
    risks: list[str] | None = Field(None, description="风险提示")
    recommended_price: float | None = Field(None, description="建议售价", gt=0)
    max_cac: float | None = Field(None, description="最大客户获取成本", gt=0)
    test_quantity: int | None = Field(None, description="测试数量", gt=0)
    test_days: int | None = Field(None, description="测试天数", gt=0)


class ApprovalRequest(BaseModel):
    """审批请求"""
    approved_by: str = Field("admin", description="审批人")
    reject_reason: str | None = Field(None, description="拒绝原因（仅拒绝时使用）")


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取选品管理系统状态",
)
async def get_status() -> dict[str, Any]:
    """获取选品管理系统状态、阈值配置、工作流说明"""
    return get_selection_manager_status()


@router.get(
    "/recommendations",
    summary="生成选品建议候选清单",
)
async def get_recommendations(
    db: DbSession,
    limit: int = 20,
    min_score: float = 50.0,
) -> dict[str, Any]:
    """
    生成选品建议候选清单

    基于产品评分排序，筛选出符合最低分数要求的产品，
    生成分级建议（强烈推荐/推荐/观察/拒绝）。

    Args:
        limit: 返回数量限制（默认 20）
        min_score: 最低分数要求（默认 50）
    """
    try:
        result = await generate_selection_recommendations(
            session=db,
            limit=limit,
            min_score=min_score,
        )
        return result
    except Exception as e:
        logger.exception("Generate selection recommendations failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate selection recommendations failed: {e!s}",
        )


@router.post(
    "/decisions",
    summary="创建选品决策（进入审批队列）",
)
async def create_decision(
    request: SelectionDecisionRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    创建选品决策（进入审批队列）

    决策类型：
    - test：测试（建议小批量试销）
    - hold：观望（持续观察，暂不行动）
    - reject：拒绝（不建议采购）

    创建后状态为 pending，需要人工审批。
    """
    try:
        from uuid import UUID as _UUID

        product_id = _UUID(request.product_id)

        decision = await create_selection_decision(
            session=db,
            product_id=product_id,
            decision=request.decision,
            score=request.score,
            confidence=request.confidence,
            reasons=request.reasons,
            risks=request.risks,
            recommended_price=request.recommended_price,
            max_cac=request.max_cac,
            test_quantity=request.test_quantity,
            test_days=request.test_days,
        )
        await db.commit()

        return {
            "success": True,
            "decision": {
                "id": str(decision.id),
                "product_id": str(decision.product_id),
                "decision": decision.decision,
                "score": float(decision.score) if decision.score else None,
                "approval_status": decision.approval_status,
                "created_at": decision.created_at.isoformat() if decision.created_at else None,
            },
            "message": "Decision created and pending approval",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Create selection decision failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Create selection decision failed: {e!s}",
        )


@router.post(
    "/decisions/{decision_id}/approve",
    summary="审批通过选品决策",
)
async def approve_decision(
    decision_id: str,
    request: ApprovalRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    审批通过选品决策

    如果决策类型是 test，产品候选状态将更新为 testing。
    """
    try:
        from uuid import UUID as _UUID

        decision_uuid = _UUID(decision_id)
        decision = await approve_selection_decision(
            session=db,
            decision_id=decision_uuid,
            approved_by=request.approved_by,
        )
        await db.commit()

        return {
            "success": True,
            "decision": {
                "id": str(decision.id),
                "product_id": str(decision.product_id),
                "decision": decision.decision,
                "approval_status": decision.approval_status,
                "approved_by": decision.approved_by,
                "approved_at": decision.approved_at.isoformat() if decision.approved_at else None,
            },
            "message": "Decision approved successfully",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Approve selection decision failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Approve selection decision failed: {e!s}",
        )


@router.post(
    "/decisions/{decision_id}/reject",
    summary="拒绝选品决策",
)
async def reject_decision(
    decision_id: str,
    request: ApprovalRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    拒绝选品决策

    如果决策类型是 reject，产品候选状态将更新为 rejected。
    """
    try:
        from uuid import UUID as _UUID

        decision_uuid = _UUID(decision_id)
        decision = await reject_selection_decision(
            session=db,
            decision_id=decision_uuid,
            rejected_by=request.approved_by,
            reject_reason=request.reject_reason,
        )
        await db.commit()

        return {
            "success": True,
            "decision": {
                "id": str(decision.id),
                "product_id": str(decision.product_id),
                "decision": decision.decision,
                "approval_status": decision.approval_status,
                "approved_by": decision.approved_by,
                "approved_at": decision.approved_at.isoformat() if decision.approved_at else None,
            },
            "message": "Decision rejected successfully",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Reject selection decision failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reject selection decision failed: {e!s}",
        )


@router.get(
    "/decisions",
    summary="获取选品决策列表",
)
async def list_decisions(
    db: DbSession,
    approval_status: str | None = None,
    decision_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    获取选品决策列表

    支持按审批状态（pending/approved/rejected）和决策类型（test/hold/reject）筛选。
    """
    try:
        result = await get_selection_decisions(
            session=db,
            approval_status=approval_status,
            decision_type=decision_type,
            limit=limit,
            offset=offset,
        )
        return result
    except Exception as e:
        logger.exception("List selection decisions failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"List selection decisions failed: {e!s}",
        )
