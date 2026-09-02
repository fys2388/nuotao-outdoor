"""
采购自动化 API 端点
支持采购规则配置、自动生成采购单、异常检测
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.product import Product
from app.services.purchase_automation_service import (
    auto_generate_purchase_order,
    detect_anomalies,
    get_purchase_automation_status,
    load_purchase_rules,
    save_purchase_rules,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/purchase-automation", tags=["purchase-automation"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================
# 请求/响应模型
# ============================================

class PurchaseRulesUpdate(BaseModel):
    """采购规则更新请求"""
    auto_purchase_enabled: bool | None = Field(None, description="是否启用自动采购")
    min_stock_threshold: int | None = Field(None, description="最低库存阈值", gt=0)
    default_purchase_quantity: int | None = Field(None, description="默认采购数量", gt=0)
    max_purchase_amount: float | None = Field(None, description="单次采购最大金额", gt=0)
    cost_variance_threshold: float | None = Field(None, description="成本波动阈值（如 0.20 = 20%）", gt=0, le=1)
    require_approval_above: float | None = Field(None, description="超过此金额需要审批", gt=0)
    supplier_blacklist: list[str] | None = Field(None, description="供应商黑名单")
    auto_approve_low_value: bool | None = Field(None, description="低价值采购单是否自动审批")


class AutoPurchaseRequest(BaseModel):
    """自动采购请求"""
    product_id: str = Field(..., description="产品 ID（UUID）")
    quantity: int | None = Field(None, description="采购数量（不提供则使用默认值）", gt=0)
    unit_cost: float | None = Field(None, description="单位成本（不提供则使用产品成本）", gt=0)
    supplier_id: str | None = Field(None, description="供应商 ID")


class AnomalyDetectionRequest(BaseModel):
    """异常检测请求"""
    product_id: str = Field(..., description="产品 ID（UUID）")
    quantity: int = Field(..., description="采购数量", gt=0)
    unit_cost: float = Field(..., description="单位成本", gt=0)
    supplier_id: str | None = Field(None, description="供应商 ID")


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取采购自动化系统状态",
)
async def get_status() -> dict[str, Any]:
    """获取采购自动化系统状态、规则配置、工作流说明"""
    return get_purchase_automation_status()


@router.get(
    "/rules",
    summary="获取采购规则配置",
)
async def get_rules() -> dict[str, Any]:
    """获取当前采购规则配置"""
    rules = load_purchase_rules()
    return {
        "rules": {k: str(v) if isinstance(v, Decimal) else v for k, v in rules.items()},
    }


@router.put(
    "/rules",
    summary="更新采购规则配置",
)
async def update_rules(
    request: PurchaseRulesUpdate,
) -> dict[str, Any]:
    """
    更新采购规则配置

    支持更新：自动采购开关、库存阈值、默认采购数量、最大金额、成本波动阈值、审批门槛、供应商黑名单等
    """
    try:
        from decimal import Decimal as _Decimal

        rules = load_purchase_rules()
        updates = request.model_dump(exclude_none=True)

        for key, value in updates.items():
            if key in ["max_purchase_amount", "cost_variance_threshold", "require_approval_above"]:
                rules[key] = _Decimal(str(value))
            else:
                rules[key] = value

        save_purchase_rules(rules)

        return {
            "success": True,
            "message": "采购规则已更新",
            "rules": {k: str(v) if isinstance(v, Decimal) else v for k, v in rules.items()},
        }
    except Exception as e:
        logger.exception("Update purchase rules failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update purchase rules failed: {e!s}",
        )


@router.post(
    "/auto-purchase",
    summary="自动生成采购单（带异常检测和人工介入）",
)
async def auto_purchase(
    request: AutoPurchaseRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    自动生成采购单（带异常检测和人工介入）

    工作流程：
    1. 检查自动采购是否启用
    2. 异常检测（成本波动、金额超限、供应商黑名单等）
    3. 如果有阻塞性异常，暂停并要求人工介入
    4. 生成采购单
    5. 低价值采购单自动审批，高价值采购单进入审批队列
    """
    try:
        from decimal import Decimal as _Decimal
        from uuid import UUID as _UUID

        product_id = _UUID(request.product_id)
        unit_cost = _Decimal(str(request.unit_cost)) if request.unit_cost else None

        result = await auto_generate_purchase_order(
            session=db,
            product_id=product_id,
            quantity=request.quantity,
            unit_cost=unit_cost,
            supplier_id=request.supplier_id,
        )

        if result.get("success"):
            await db.commit()
        else:
            await db.rollback()

        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Auto purchase failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auto purchase failed: {e!s}",
        )


@router.post(
    "/detect-anomalies",
    summary="检测采购异常（不生成采购单）",
)
async def detect_anomalies_endpoint(
    request: AnomalyDetectionRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    检测采购异常（不生成采购单）

    检测类型：
    - cost_spike：成本激增
    - supplier_blacklisted：供应商在黑名单
    - quantity_abnormal：数量异常
    - amount_exceeds_limit：金额超限
    - no_supplier：无供应商
    """
    try:
        from decimal import Decimal as _Decimal
        from uuid import UUID as _UUID

        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        product_id = _UUID(request.product_id)

        # 使用 selectinload 预加载 cost 关系，避免异步懒加载问题
        product_query = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.cost))
        )
        product_result = await db.execute(product_query)
        product = product_result.scalar_one_or_none()

        if not product:
            raise ValueError(f"Product not found: {product_id}")

        unit_cost = _Decimal(str(request.unit_cost))
        rules = load_purchase_rules()

        anomalies = detect_anomalies(product, request.quantity, unit_cost, request.supplier_id, rules)

        return {
            "product": {
                "id": str(product.id),
                "name": product.name,
                "sku": product.sku,
            },
            "quantity": request.quantity,
            "unit_cost": float(unit_cost),
            "total_amount": float(unit_cost * _Decimal(str(request.quantity))),
            "anomalies": anomalies,
            "anomaly_count": len(anomalies),
            "blocking_count": sum(1 for a in anomalies if a.get("blocking")),
            "has_blocking_anomalies": any(a.get("blocking") for a in anomalies),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Detect anomalies failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Detect anomalies failed: {e!s}",
        )
