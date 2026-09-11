"""
飞书通知 API 端点
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.feishu_notification_service import (
    get_notification_status,
    send_alert_notification,
    send_feishu_text_message,
    send_order_notification,
    send_weekly_report_notification,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])


class TextMessageRequest(BaseModel):
    content: str = Field(..., description="消息内容")
    webhook_url: str | None = Field(None, description="飞书 Webhook URL（可选）")


class AlertNotificationRequest(BaseModel):
    alert_type: str = Field(..., description="预警类型")
    severity: str = Field(..., description="严重程度（critical/warning/info）")
    title: str = Field(..., description="预警标题")
    description: str = Field("", description="预警描述")
    metric_data: dict[str, Any] | None = Field(None, description="指标数据")
    recommended_action: str = Field("", description="建议行动")
    webhook_url: str | None = Field(None, description="飞书 Webhook URL（可选）")


class OrderNotificationRequest(BaseModel):
    order_type: str = Field(..., description="订单类型（order_new/order_shipped/order_refunded）")
    order_id: str = Field(..., description="订单 ID")
    customer_name: str = Field(..., description="客户名称")
    total_amount: float = Field(..., description="订单金额")
    currency: str = Field("USD", description="货币")
    items_count: int = Field(0, description="商品数量")
    webhook_url: str | None = Field(None, description="飞书 Webhook URL（可选）")


class WeeklyReportNotificationRequest(BaseModel):
    report_title: str = Field(..., description="周报标题")
    total_revenue: float = Field(..., description="总收入")
    total_orders: int = Field(..., description="总订单数")
    gross_margin: float = Field(..., description="毛利率")
    alerts_count: int = Field(0, description="预警数量")
    report_url: str = Field("", description="周报链接")
    webhook_url: str | None = Field(None, description="飞书 Webhook URL（可选）")


@router.get("/status")
async def status() -> dict[str, Any]:
    return get_notification_status()


@router.post("/send-text")
async def send_text(request: TextMessageRequest) -> dict[str, Any]:
    """发送飞书文本消息"""
    try:
        result = send_feishu_text_message(request.content, request.webhook_url)
        return result
    except Exception as e:
        logger.exception("Send text message failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Send text message failed: {e!s}")


@router.post("/send-alert")
async def send_alert(request: AlertNotificationRequest) -> dict[str, Any]:
    """发送经营预警通知到飞书"""
    try:
        result = send_alert_notification(
            alert_type=request.alert_type,
            severity=request.severity,
            title=request.title,
            description=request.description,
            metric_data=request.metric_data,
            recommended_action=request.recommended_action,
            webhook_url=request.webhook_url,
        )
        return result
    except Exception as e:
        logger.exception("Send alert notification failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Send alert notification failed: {e!s}")


@router.post("/send-order")
async def send_order(request: OrderNotificationRequest) -> dict[str, Any]:
    """发送订单通知到飞书"""
    try:
        result = send_order_notification(
            order_type=request.order_type,
            order_id=request.order_id,
            customer_name=request.customer_name,
            total_amount=request.total_amount,
            currency=request.currency,
            items_count=request.items_count,
            webhook_url=request.webhook_url,
        )
        return result
    except Exception as e:
        logger.exception("Send order notification failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Send order notification failed: {e!s}")


@router.post("/send-weekly-report")
async def send_weekly_report(request: WeeklyReportNotificationRequest) -> dict[str, Any]:
    """发送周报通知到飞书"""
    try:
        result = send_weekly_report_notification(
            report_title=request.report_title,
            total_revenue=request.total_revenue,
            total_orders=request.total_orders,
            gross_margin=request.gross_margin,
            alerts_count=request.alerts_count,
            report_url=request.report_url,
            webhook_url=request.webhook_url,
        )
        return result
    except Exception as e:
        logger.exception("Send weekly report notification failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Send weekly report notification failed: {e!s}")
