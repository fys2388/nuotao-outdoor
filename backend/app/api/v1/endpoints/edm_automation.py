"""
EDM 营销自动化 API 端点
支持营销活动管理、邮件发送、效果追踪、统计分析
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.edm_automation_service import (
    create_campaign,
    get_campaign_stats,
    get_edm_automation_status,
    list_campaigns,
    send_campaign_email,
    track_email_event,
    update_campaign_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/edm", tags=["edm"])


# ============================================
# 请求/响应模型
# ============================================

class CreateCampaignRequest(BaseModel):
    """创建营销活动请求"""
    campaign_type: str = Field(..., description="活动类型")
    name: str = Field(..., description="活动名称")
    description: str = Field("", description="活动描述")
    subject: str = Field("", description="邮件主题")
    email_content: dict[str, Any] | None = Field(None, description="邮件内容")
    trigger: str = Field("", description="触发条件")
    schedule: dict[str, Any] | None = Field(None, description="调度配置")
    target_audience: str = Field("all", description="目标受众")
    discount_percent: int = Field(0, description="折扣百分比", ge=0, le=50)


class UpdateStatusRequest(BaseModel):
    """更新状态请求"""
    status: str = Field(..., description="新状态")
    updated_by: str = Field("system", description="更新者")


class SendEmailRequest(BaseModel):
    """发送邮件请求"""
    campaign_id: str = Field(..., description="活动 ID")
    recipient_email: str = Field(..., description="收件人邮箱")
    recipient_name: str = Field("Customer", description="收件人名称")
    order_data: dict[str, Any] | None = Field(None, description="订单数据")
    cart_data: dict[str, Any] | None = Field(None, description="购物车数据")


class TrackEventRequest(BaseModel):
    """追踪事件请求"""
    campaign_id: str = Field(..., description="活动 ID")
    send_id: str = Field(..., description="发送 ID")
    event_type: str = Field(..., description="事件类型")
    event_data: dict[str, Any] | None = Field(None, description="事件数据")


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取 EDM 营销自动化系统状态",
)
async def get_status() -> dict[str, Any]:
    """获取 EDM 营销自动化系统状态、支持的活动类型、可用流程"""
    return get_edm_automation_status()


@router.post(
    "/campaigns",
    summary="创建营销活动",
)
async def create_campaign_endpoint(
    request: CreateCampaignRequest,
) -> dict[str, Any]:
    """
    创建营销活动

    支持的活动类型：abandoned_cart（弃购挽回）、post_purchase（购后营销）、
    welcome（欢迎邮件）、newsletter（新闻通讯）、promotional（促销活动）、
    win_back（召回邮件）、review_request（评价请求）。
    """
    try:
        campaign = create_campaign(
            campaign_type=request.campaign_type,
            name=request.name,
            description=request.description,
            subject=request.subject,
            email_content=request.email_content,
            trigger=request.trigger,
            schedule=request.schedule,
            target_audience=request.target_audience,
            discount_percent=request.discount_percent,
        )
        return {
            "success": True,
            "campaign": campaign,
            "message": "营销活动创建成功",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Create campaign failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Create campaign failed: {e!s}",
        )


@router.put(
    "/campaigns/{campaign_id}/status",
    summary="更新营销活动状态",
)
async def update_status_endpoint(
    campaign_id: str,
    request: UpdateStatusRequest,
) -> dict[str, Any]:
    """
    更新营销活动状态

    支持的状态：draft（草稿）、scheduled（已调度）、active（进行中）、
    paused（已暂停）、completed（已完成）、cancelled（已取消）。
    """
    try:
        campaign = update_campaign_status(
            campaign_id=campaign_id,
            new_status=request.status,
            updated_by=request.updated_by,
        )
        return {
            "success": True,
            "campaign": campaign,
            "message": f"营销活动状态已更新为 {request.status}",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Update campaign status failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update campaign status failed: {e!s}",
        )


@router.post(
    "/send",
    summary="发送营销活动邮件",
)
async def send_email_endpoint(
    request: SendEmailRequest,
) -> dict[str, Any]:
    """
    发送营销活动邮件

    向指定收件人发送营销活动邮件，记录发送日志。
    活动必须处于 active 或 scheduled 状态。
    """
    try:
        result = send_campaign_email(
            campaign_id=request.campaign_id,
            recipient_email=request.recipient_email,
            recipient_name=request.recipient_name,
            order_data=request.order_data,
            cart_data=request.cart_data,
        )
        return {
            "success": True,
            "send_result": result,
            "message": "邮件发送成功",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Send campaign email failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Send campaign email failed: {e!s}",
        )


@router.post(
    "/track",
    summary="追踪邮件事件",
)
async def track_event_endpoint(
    request: TrackEventRequest,
) -> dict[str, Any]:
    """
    追踪邮件事件

    支持的事件类型：open（打开）、click（点击）、conversion（转化）、
    unsubscribe（退订）、bounce（退信）、complaint（投诉）、delivery（送达）。

    转化事件可包含 revenue 字段，用于收入归因。
    """
    try:
        event = track_email_event(
            campaign_id=request.campaign_id,
            send_id=request.send_id,
            event_type=request.event_type,
            event_data=request.event_data,
        )
        return {
            "success": True,
            "event": event,
            "message": "事件追踪成功",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Track email event failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Track email event failed: {e!s}",
        )


@router.get(
    "/campaigns/{campaign_id}/stats",
    summary="获取营销活动统计数据",
)
async def get_stats_endpoint(
    campaign_id: str,
) -> dict[str, Any]:
    """
    获取营销活动统计数据

    包含原始统计（发送数、送达数、打开数、点击数、转化数、收入）和
    计算比率（送达率、打开率、点击率、点击打开率、转化率、每邮件收入）。
    还包含行业基准对比和性能评估。
    """
    try:
        stats = get_campaign_stats(campaign_id)
        return {
            "success": True,
            "stats": stats,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Get campaign stats failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get campaign stats failed: {e!s}",
        )


@router.get(
    "/campaigns",
    summary="获取营销活动列表",
)
async def list_campaigns_endpoint(
    campaign_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    获取营销活动列表

    支持按活动类型和状态筛选，返回活动列表和汇总统计。
    """
    try:
        result = list_campaigns(
            campaign_type=campaign_type,
            status=status,
            limit=limit,
        )
        return result
    except Exception as e:
        logger.exception("List campaigns failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"List campaigns failed: {e!s}",
        )
