"""回款台账端点 — 登记应回款 / 实收 / 争议标记 / 列表筛选 / 统计。

对应运营闭环 P0-1：把 COD 回款、清关账单等资金流结构化录入，
让「待收 / 已收 / 争议」金额可查、可审计。
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import settlement_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settlements"])

DbSession = AsyncSession


class RegisterSettlementRequest(BaseModel):
    """登记一笔应回款（COD / 清关 / 杂费 / 退款）。"""

    carrier: str = Field(..., description="渠道：correos / clearance_hungary / stripe ...")
    expected_amount: Decimal = Field(..., gt=0, description="应回款金额")
    settlement_kind: str = Field("cod", description="cod / clearance / fee / refund")
    order_id: str | None = Field(None, description="关联订单 id")
    external_order_id: str | None = Field(None, description="外部单号（对账用）")
    fees: Decimal = Field(Decimal("0"), ge=0, description="扣费")
    currency: str = Field("USD", description="币种")
    due_date: str | None = Field(None, description="应回款日 YYYY-MM-DD")
    note: str | None = Field(None, description="备注/争议说明")


class RecordReceiptRequest(BaseModel):
    """登记实收金额（推进状态机 expected -> partial -> received）。"""

    received_amount: Decimal = Field(..., ge=0, description="实收金额")
    fees: Decimal | None = Field(None, ge=0, description="实际扣费（覆盖登记值）")
    note: str | None = Field(None, description="收款备注")


@router.post("/settlements")
async def register_settlement(
    request: RegisterSettlementRequest,
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    """登记一笔应回款，进入待收台账。"""
    try:
        entry = await settlement_service.register_settlement(
            db,
            workspace_id=settlement_service.DEFAULT_WORKSPACE_ID,
            carrier=request.carrier,
            expected_amount=request.expected_amount,
            settlement_kind=request.settlement_kind,
            order_id=UUID(request.order_id) if request.order_id else None,
            external_order_id=request.external_order_id,
            fees=request.fees,
            currency=request.currency,
            due_date=date.fromisoformat(request.due_date) if request.due_date else None,
            note=request.note,
        )
        return {"success": True, "settlement": entry}
    except settlement_service.SettlementError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/settlements")
async def list_settlements(
    status: str | None = Query(None, description="expected/partial/received/disputed"),
    carrier: str | None = Query(None, description="渠道筛选"),
    settlement_kind: str | None = Query(None, description="cod/clearance/fee/refund"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    """回款台账列表（可筛选、分页）。"""
    try:
        return await settlement_service.list_settlements(
            db,
            workspace_id=settlement_service.DEFAULT_WORKSPACE_ID,
            status=status,
            carrier=carrier,
            settlement_kind=settlement_kind,
            limit=limit,
            offset=offset,
        )
    except settlement_service.SettlementError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/settlements/stats")
async def settlements_stats(
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    """回款统计：按状态/渠道汇总，含待收、已收、争议金额。"""
    return await settlement_service.settlement_stats(
        db, workspace_id=settlement_service.DEFAULT_WORKSPACE_ID
    )


@router.post("/settlements/{settlement_id}/receipt")
async def record_receipt(
    settlement_id: UUID,
    request: RecordReceiptRequest,
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    """登记实收；实收≥应回款自动置为已收，否则部分回款。"""
    try:
        entry = await settlement_service.record_receipt(
            db,
            settlement_id=settlement_id,
            received_amount=request.received_amount,
            fees=request.fees,
            note=request.note,
        )
        return {"success": True, "settlement": entry}
    except settlement_service.SettlementError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/settlements/{settlement_id}/dispute")
async def mark_disputed(
    settlement_id: UUID,
    note: str | None = Query(None, description="争议说明"),
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    """标记争议，保留在待追讨列表。"""
    try:
        entry = await settlement_service.mark_disputed(
            db, settlement_id=settlement_id, note=note
        )
        return {"success": True, "settlement": entry}
    except settlement_service.SettlementError as e:
        raise HTTPException(status_code=400, detail=str(e))
