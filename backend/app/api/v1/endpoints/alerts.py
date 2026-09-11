"""
经营预警系统 API 端点
支持预警创建、查看、列表、状态更新、规则配置、自动检查
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.alert_system_service import (
    check_margin_decline,
    check_refund_rate,
    check_stockout_risk,
    create_alert,
    get_alert,
    get_alert_system_status,
    list_alerts,
    load_alert_rules,
    run_all_checks,
    save_alert_rules,
    update_alert_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ============================================
# 请求/响应模型
# ============================================

class CreateAlertRequest(BaseModel):
    """创建预警请求"""
    alert_type: str = Field(..., description="预警类型")
    severity: str = Field(..., description="严重程度")
    title: str = Field(..., description="预警标题")
    description: str = Field("", description="预警描述")
    metric_data: dict[str, Any] | None = Field(None, description="相关指标数据")
    recommended_action: str = Field("", description="建议行动")


class UpdateStatusRequest(BaseModel):
    """更新状态请求"""
    status: str = Field(..., description="新状态")
    updated_by: str = Field("system", description="更新者")
    notes: str = Field("", description="备注")


class RunChecksRequest(BaseModel):
    """运行检查请求"""
    business_data: dict[str, Any] = Field(..., description="经营数据")


class CheckMarginRequest(BaseModel):
    """检查毛利下滑请求"""
    current_margin: float = Field(..., description="当前毛利率（%）")
    previous_margin: float = Field(..., description="上期毛利率（%）")


class CheckRefundRequest(BaseModel):
    """检查退款率请求"""
    current_refund_rate: float = Field(..., description="当前退款率（%）")
    previous_refund_rate: float = Field(0, description="上期退款率（%）")
    total_orders: int = Field(0, description="总订单数")
    refunded_orders: int = Field(0, description="退款订单数")


class CheckStockoutRequest(BaseModel):
    """检查断货风险请求"""
    product_name: str = Field(..., description="产品名称")
    sku: str = Field(..., description="产品 SKU")
    current_stock: int = Field(..., description="当前库存")
    daily_sales_rate: float = Field(..., description="日均销量")


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取经营预警系统状态",
)
async def get_status() -> dict[str, Any]:
    """获取经营预警系统状态、支持的预警类型、启用的规则"""
    return get_alert_system_status()


@router.get(
    "/rules",
    summary="获取预警规则配置",
)
async def get_rules() -> dict[str, Any]:
    """获取所有预警规则配置，包括阈值、严重程度、检查频率"""
    rules = load_alert_rules()
    return {
        "success": True,
        "rules": rules,
        "total_rules": len(rules),
        "enabled_rules": sum(1 for r in rules.values() if r.get("enabled", True)),
    }


@router.put(
    "/rules",
    summary="更新预警规则配置",
)
async def update_rules(
    rules: dict[str, Any],
) -> dict[str, Any]:
    """
    更新预警规则配置

    可调整各预警类型的阈值、严重程度、启用状态、检查频率。
    """
    try:
        save_alert_rules(rules)
        return {
            "success": True,
            "message": "预警规则配置已更新",
            "total_rules": len(rules),
        }
    except Exception as e:
        logger.exception("Update alert rules failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update alert rules failed: {e!s}",
        )


@router.post(
    "",
    summary="创建预警",
)
async def create_alert_endpoint(
    request: CreateAlertRequest,
) -> dict[str, Any]:
    """
    手动创建预警

    支持 10 种预警类型：毛利下滑、退款率过高、断货风险、订单异常、
    收入下滑、ROAS 下滑、库存积压、物流延迟、客户投诉、支付失败。
    """
    try:
        alert = create_alert(
            alert_type=request.alert_type,
            severity=request.severity,
            title=request.title,
            description=request.description,
            metric_data=request.metric_data,
            recommended_action=request.recommended_action,
            source="manual",
        )
        return {
            "success": True,
            "alert": alert,
            "message": "预警创建成功",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Create alert failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Create alert failed: {e!s}",
        )


@router.get(
    "",
    summary="获取预警列表",
)
async def list_alerts_endpoint(
    alert_status: str | None = None,
    severity: str | None = None,
    alert_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    获取预警列表

    支持按状态、严重程度、预警类型筛选。
    返回预警列表和汇总统计。
    """
    try:
        result = list_alerts(
            status=alert_status,
            severity=severity,
            alert_type=alert_type,
            limit=limit,
        )
        return result
    except Exception as e:
        logger.exception("List alerts failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"List alerts failed: {e!s}",
        )


@router.get(
    "/{alert_id}",
    summary="获取预警详情",
)
async def get_alert_endpoint(
    alert_id: str,
) -> dict[str, Any]:
    """获取指定预警的完整详情，包括指标数据、建议行动、历史记录"""
    try:
        alert = get_alert(alert_id)
        return {
            "success": True,
            "alert": alert,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Get alert failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get alert failed: {e!s}",
        )


@router.put(
    "/{alert_id}/status",
    summary="更新预警状态",
)
async def update_status_endpoint(
    alert_id: str,
    request: UpdateStatusRequest,
) -> dict[str, Any]:
    """
    更新预警状态

    支持的状态：new（新建）、acknowledged（已确认）、investigating（调查中）、
    resolved（已解决）、dismissed（已忽略）。
    状态变更会记录历史。
    """
    try:
        alert = update_alert_status(
            alert_id=alert_id,
            new_status=request.status,
            updated_by=request.updated_by,
            notes=request.notes,
        )
        return {
            "success": True,
            "alert": alert,
            "message": f"预警状态已更新为 {request.status}",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Update alert status failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update alert status failed: {e!s}",
        )


@router.post(
    "/check/margin",
    summary="检查毛利下滑预警",
)
async def check_margin_endpoint(
    request: CheckMarginRequest,
) -> dict[str, Any]:
    """
    检查毛利下滑预警

    基于当前和上期毛利率，自动判断是否触发预警。
    触发条件：毛利率低于 30% 或环比下降超过 5%。
    """
    try:
        alert = check_margin_decline(
            current_margin=request.current_margin,
            previous_margin=request.previous_margin,
        )
        if alert:
            return {
                "success": True,
                "alert_triggered": True,
                "alert": alert,
                "message": "毛利下滑预警已触发",
            }
        else:
            return {
                "success": True,
                "alert_triggered": False,
                "message": "毛利率正常，未触发预警",
            }
    except Exception as e:
        logger.exception("Check margin decline failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Check margin decline failed: {e!s}",
        )


@router.post(
    "/check/refund-rate",
    summary="检查退款率预警",
)
async def check_refund_endpoint(
    request: CheckRefundRequest,
) -> dict[str, Any]:
    """
    检查退款率预警

    基于当前退款率，自动判断是否触发预警。
    触发条件：退款率超过 3%（严重）或 2%（警告）。
    """
    try:
        alert = check_refund_rate(
            current_refund_rate=request.current_refund_rate,
            previous_refund_rate=request.previous_refund_rate,
            total_orders=request.total_orders,
            refunded_orders=request.refunded_orders,
        )
        if alert:
            return {
                "success": True,
                "alert_triggered": True,
                "alert": alert,
                "message": "退款率预警已触发",
            }
        else:
            return {
                "success": True,
                "alert_triggered": False,
                "message": "退款率正常，未触发预警",
            }
    except Exception as e:
        logger.exception("Check refund rate failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Check refund rate failed: {e!s}",
        )


@router.post(
    "/check/stockout",
    summary="检查断货风险预警",
)
async def check_stockout_endpoint(
    request: CheckStockoutRequest,
) -> dict[str, Any]:
    """
    检查断货风险预警

    基于当前库存和日均销量，自动判断是否触发预警。
    触发条件：库存低于 14 天销量（警告）或 7 天销量（严重）。
    """
    try:
        alert = check_stockout_risk(
            product_name=request.product_name,
            sku=request.sku,
            current_stock=request.current_stock,
            daily_sales_rate=request.daily_sales_rate,
        )
        if alert:
            return {
                "success": True,
                "alert_triggered": True,
                "alert": alert,
                "message": "断货风险预警已触发",
            }
        else:
            return {
                "success": True,
                "alert_triggered": False,
                "message": "库存充足，未触发预警",
            }
    except Exception as e:
        logger.exception("Check stockout risk failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Check stockout risk failed: {e!s}",
        )


@router.post(
    "/check/all",
    summary="运行所有预警检查",
)
async def run_all_checks_endpoint(
    request: RunChecksRequest,
) -> dict[str, Any]:
    """
    运行所有预警检查

    基于经营数据，自动运行毛利下滑、退款率、断货风险等所有预警检查。
    返回所有触发的预警列表和汇总统计。
    """
    try:
        result = run_all_checks(request.business_data)
        return {
            "success": True,
            "result": result,
            "message": f"检查完成，触发 {result['total_alerts_triggered']} 个预警",
        }
    except Exception as e:
        logger.exception("Run all checks failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Run all checks failed: {e!s}",
        )
