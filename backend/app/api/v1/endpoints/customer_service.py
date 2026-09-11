"""
AI 客服 API 端点
支持常见问题自动回答、转人工工单、FAQ 查询
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.customer_service import (
    create_human_ticket,
    get_faq_by_category,
    get_faq_categories,
    handle_customer_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customer-service", tags=["customer-service"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================
# 请求/响应模型
# ============================================

class CustomerMessageRequest(BaseModel):
    """客户消息请求"""
    message: str = Field(..., description="客户消息内容", min_length=1, max_length=2000)
    conversation_id: str | None = Field(None, description="对话 ID（用于多轮对话）")
    customer_id: str | None = Field(None, description="客户 ID")
    customer_context: dict[str, Any] | None = Field(None, description="客户上下文（订单信息等）")


class CustomerMessageResponse(BaseModel):
    """客户消息响应"""
    answer: str
    source: str  # faq / ai / fallback / error_fallback
    confidence: float
    response_time_ms: int
    timestamp: str
    suggest_human_transfer: bool = False
    faq_id: str | None = None
    faq_category: str | None = None
    conversation_id: str | None = None


class HumanTicketRequest(BaseModel):
    """转人工工单请求"""
    customer_id: str = Field(..., description="客户 ID")
    subject: str = Field(..., description="工单主题", min_length=1, max_length=200)
    description: str = Field(..., description="工单描述", min_length=1, max_length=5000)
    priority: str = Field("normal", description="优先级：low/normal/high/urgent")
    conversation_id: str | None = Field(None, description="相关对话 ID")


class HumanTicketResponse(BaseModel):
    """转人工工单响应"""
    success: bool
    ticket: dict[str, Any]
    message: str


class FAQItem(BaseModel):
    """FAQ 条目"""
    id: str
    category: str
    question: str
    answer: str
    keywords: list[str]


# ============================================
# API 端点
# ============================================

@router.post(
    "/chat",
    response_model=CustomerMessageResponse,
    summary="发送客户消息，获取 AI 回答",
)
async def chat_with_customer_service(
    request: CustomerMessageRequest,
    db: DbSession,
) -> CustomerMessageResponse:
    """
    发送客户消息，获取 AI 客服回答

    - 优先匹配 FAQ 知识库
    - 未匹配时使用 AI 生成回答
    - 低置信度时建议转人工
    """
    try:
        result = await handle_customer_message(
            session=db,
            message=request.message,
            conversation_id=request.conversation_id,
            customer_id=request.customer_id,
            customer_context=request.customer_context,
        )

        return CustomerMessageResponse(
            answer=result["answer"],
            source=result["source"],
            confidence=result.get("confidence", 0.0),
            response_time_ms=result.get("response_time_ms", 0),
            timestamp=result["timestamp"],
            suggest_human_transfer=result.get("suggest_human_transfer", False),
            faq_id=result.get("faq_id"),
            faq_category=result.get("faq_category"),
            conversation_id=request.conversation_id or "new",
        )

    except Exception as e:
        logger.exception("Customer service chat failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Customer service error: {e!s}",
        )


@router.post(
    "/human-ticket",
    response_model=HumanTicketResponse,
    summary="创建转人工工单",
)
async def create_human_support_ticket(
    request: HumanTicketRequest,
    db: DbSession,
) -> HumanTicketResponse:
    """
    创建转人工工单

    当 AI 客服无法解决问题时，客户可以请求转人工服务。
    工单创建后，客服团队会在 24 小时内响应。
    """
    # 验证优先级
    valid_priorities = ["low", "normal", "high", "urgent"]
    if request.priority not in valid_priorities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid priority. Must be one of: {', '.join(valid_priorities)}",
        )

    try:
        result = await create_human_ticket(
            session=db,
            customer_id=request.customer_id,
            subject=request.subject,
            description=request.description,
            priority=request.priority,
            conversation_id=request.conversation_id,
        )

        return HumanTicketResponse(**result)

    except Exception as e:
        logger.exception("Human ticket creation failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ticket creation failed: {e!s}",
        )


@router.get(
    "/faq/categories",
    summary="获取 FAQ 分类列表",
)
async def list_faq_categories() -> dict[str, Any]:
    """获取所有 FAQ 分类"""
    categories = get_faq_categories()
    return {
        "categories": sorted(categories),
        "total": len(categories),
    }


@router.get(
    "/faq",
    summary="获取 FAQ 列表",
)
async def list_faq(
    category: str | None = None,
) -> dict[str, Any]:
    """
    获取 FAQ 列表

    - 不指定 category 时返回所有 FAQ
    - 指定 category 时返回该分类下的 FAQ
    """
    from app.services.customer_service import FAQ_KNOWLEDGE_BASE

    if category:
        faqs = get_faq_by_category(category)
    else:
        faqs = FAQ_KNOWLEDGE_BASE

    return {
        "faqs": [
            FAQItem(
                id=faq["id"],
                category=faq["category"],
                question=faq["question"],
                answer=faq["answer"],
                keywords=faq["keywords"],
            )
            for faq in faqs
        ],
        "total": len(faqs),
        "category": category,
    }


@router.get(
    "/faq/search",
    summary="搜索 FAQ",
)
async def search_faq(
    q: str,
) -> dict[str, Any]:
    """
    搜索 FAQ

    根据关键词搜索相关的 FAQ 条目
    """
    from app.services.customer_service import _find_matching_faq

    match = _find_matching_faq(q, threshold=0.2)

    if match:
        return {
            "query": q,
            "match": FAQItem(
                id=match["id"],
                category=match["category"],
                question=match["question"],
                answer=match["answer"],
                keywords=match["keywords"],
            ),
            "found": True,
        }
    else:
        return {
            "query": q,
            "match": None,
            "found": False,
            "suggestion": "No matching FAQ found. Try asking our AI assistant or create a human support ticket.",
        }
