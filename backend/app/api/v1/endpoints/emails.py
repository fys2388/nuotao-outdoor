"""
邮件通知 API 端点
支持手动触发邮件发送、查看邮件记录
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.email_service import (
    EMAIL_STORAGE_DIR,
    get_email_service,
    render_order_confirmation_email,
    render_shipping_confirmation_email,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["emails"])


# ============================================
# 请求/响应模型
# ============================================

class SendTestEmailRequest(BaseModel):
    """发送测试邮件请求"""
    to_email: str = Field(..., description="收件人邮箱")
    email_type: str = Field("order_confirmation", description="邮件类型：order_confirmation / shipping_confirmation")
    order_id: int | None = Field(None, description="订单 ID（用于获取真实订单数据）")


class EmailRecord(BaseModel):
    """邮件记录"""
    email_id: str
    to: str
    subject: str
    from_email: str
    sent_at: str
    mode: str
    success: bool
    metadata: dict[str, Any] = {}


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取邮件服务状态",
)
async def get_email_service_status() -> dict[str, Any]:
    """获取邮件服务配置状态"""
    email_service = get_email_service()
    return {
        "mode": "mock" if email_service.use_mock else "smtp",
        "smtp_configured": not email_service.use_mock,
        "from_email": email_service.from_email,
        "from_name": email_service.from_name,
        "storage_dir": str(EMAIL_STORAGE_DIR),
        "message": "Email service is running in MOCK mode. Configure SMTP settings to send real emails." if email_service.use_mock else "Email service is running in SMTP mode.",
    }


@router.post(
    "/send-test",
    summary="发送测试邮件",
)
async def send_test_email(request: SendTestEmailRequest) -> dict[str, Any]:
    """
    发送测试邮件

    使用模拟订单数据发送测试邮件，验证邮件模板和发送功能。
    """
    email_service = get_email_service()

    # 模拟订单数据
    mock_order = {
        "id": request.order_id or 9999,
        "number": str(request.order_id or 9999),
        "status": "processing",
        "currency": "USD",
        "total": "89.98",
        "date_created": "2026-09-02T00:00:00",
        "billing": {"email": request.to_email, "country": "US"},
        "line_items": [
            {
                "id": 1,
                "name": "Inflatable Camping Sleeping Pad",
                "quantity": 2,
                "price": "44.99",
                "total": "89.98",
            },
        ],
    }

    if request.email_type == "order_confirmation":
        subject, html_content, text_content = render_order_confirmation_email(mock_order)
    elif request.email_type == "shipping_confirmation":
        tracking_info = {
            "carrier": "Standard Shipping",
            "tracking_number": "TRK123456789",
            "tracking_url": "https://tracking.example.com/TRK123456789",
            "estimated_delivery": "7-14 business days",
        }
        subject, html_content, text_content = render_shipping_confirmation_email(mock_order, tracking_info)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid email_type: {request.email_type}. Must be 'order_confirmation' or 'shipping_confirmation'.",
        )

    result = await email_service.send_email(
        to_email=request.to_email,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
        metadata={"test": True, "email_type": request.email_type},
    )

    return result


@router.get(
    "/records",
    summary="获取邮件发送记录",
)
async def list_email_records(limit: int = 20) -> dict[str, Any]:
    """
    获取邮件发送记录

    从本地存储目录读取已发送的邮件记录（模拟模式下）。
    """
    records = []
    if EMAIL_STORAGE_DIR.exists():
        files = sorted(EMAIL_STORAGE_DIR.glob("*.json"), reverse=True)
        for file_path in files[:limit]:
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                    records.append({
                        "email_id": data.get("email_id", file_path.stem),
                        "to": data.get("to", ""),
                        "subject": data.get("subject", ""),
                        "from_email": data.get("from", ""),
                        "sent_at": data.get("sent_at", ""),
                        "mode": "mock",
                        "success": True,
                        "metadata": data.get("metadata", {}),
                        "file": str(file_path),
                    })
            except Exception as e:
                logger.warning("Failed to read email record %s: %s", file_path, str(e))

    return {
        "records": records,
        "total": len(records),
        "storage_dir": str(EMAIL_STORAGE_DIR),
    }


@router.get(
    "/records/{email_id}",
    summary="获取单封邮件详情",
)
async def get_email_record(email_id: str) -> dict[str, Any]:
    """获取单封邮件的完整内容"""
    file_path = EMAIL_STORAGE_DIR / f"{email_id}.json"
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Email record not found: {email_id}",
        )

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    return data
