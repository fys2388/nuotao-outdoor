"""
AI 客服服务
支持常见问题自动回答、转人工工单、对话历史记录
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 默认工作空间 ID
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

# 常见问题知识库（FAQ）
FAQ_KNOWLEDGE_BASE = [
    {
        "id": "shipping_time",
        "category": "配送",
        "question": "How long does shipping take?",
        "keywords": ["shipping", "delivery", "time", "how long", "arrive", "ship"],
        "answer": (
            "We offer the following shipping options:\n"
            "- Standard Shipping: 7-14 business days\n"
            "- Express Shipping: 3-7 business days\n"
            "- Free shipping on orders over $99 (standard shipping)\n\n"
            "Shipping times may vary during peak seasons and holidays. "
            "You will receive a tracking number via email once your order ships."
        ),
    },
    {
        "id": "return_policy",
        "category": "退换货",
        "question": "What is your return policy?",
        "keywords": ["return", "refund", "exchange", "policy", "send back"],
        "answer": (
            "We offer a 30-day return policy:\n"
            "- Items must be unused and in original packaging\n"
            "- Return shipping is free for defective items\n"
            "- Refunds are processed within 5-7 business days after we receive the item\n"
            "- Sale items are final sale and cannot be returned\n\n"
            "To initiate a return, please contact our customer service with your order number."
        ),
    },
    {
        "id": "payment_methods",
        "category": "支付",
        "question": "What payment methods do you accept?",
        "keywords": ["payment", "pay", "credit card", "paypal", "method"],
        "answer": (
            "We accept the following payment methods:\n"
            "- Credit/Debit Cards: Visa, Mastercard, American Express\n"
            "- Apple Pay and Google Pay\n"
            "- PayPal (coming soon)\n\n"
            "All transactions are secured with SSL encryption. We do not store your credit card information."
        ),
    },
    {
        "id": "order_tracking",
        "category": "订单",
        "question": "How can I track my order?",
        "keywords": ["track", "tracking", "order status", "where is my order"],
        "answer": (
            "You can track your order in two ways:\n"
            "1. Check the tracking link in your shipping confirmation email\n"
            "2. Log into your account and go to 'My Orders' to view tracking information\n\n"
            "If you haven't received a tracking number within 3 business days, please contact our customer service."
        ),
    },
    {
        "id": "product_quality",
        "category": "产品",
        "question": "What is the quality of your products?",
        "keywords": ["quality", "material", "durable", "warranty", "guarantee"],
        "answer": (
            "All our products are carefully selected and tested:\n"
            "- Premium materials from trusted suppliers\n"
            "- Quality control at every stage of production\n"
            "- 1-year warranty on all products against manufacturing defects\n"
            "- 30-day money-back guarantee if you're not satisfied\n\n"
            "We stand behind the quality of our outdoor gear and are confident you'll love your purchase."
        ),
    },
    {
        "id": "size_guide",
        "category": "产品",
        "question": "How do I choose the right size?",
        "keywords": ["size", "fit", "measurement", "small", "large", "medium"],
        "answer": (
            "For clothing and footwear:\n"
            "- Check the size chart on each product page\n"
            "- Measure yourself and compare to our sizing guide\n"
            "- If you're between sizes, we recommend sizing up for outdoor apparel\n\n"
            "For tents and gear:\n"
            "- Check the dimensions and capacity in the product description\n"
            "- Consider how many people will use it and what gear you'll bring\n\n"
            "If you're unsure, feel free to contact us with your measurements and we'll help you choose."
        ),
    },
    {
        "id": "contact_customer_service",
        "category": "客服",
        "question": "How can I contact customer service?",
        "keywords": ["contact", "customer service", "support", "help", "email", "phone"],
        "answer": (
            "You can reach our customer service team through:\n"
            "- Email: support@nuotaooutdoor.com (response within 24 hours)\n"
            "- Live Chat: Available on our website during business hours\n"
            "- Business Hours: Monday-Friday, 9:00 AM - 6:00 PM (PST)\n\n"
            "For urgent issues, please use the live chat feature for the fastest response."
        ),
    },
    {
        "id": "shipping_cost",
        "category": "配送",
        "question": "How much does shipping cost?",
        "keywords": ["shipping cost", "delivery fee", "postage", "freight"],
        "answer": (
            "Shipping costs are calculated at checkout based on:\n"
            "- Your location\n"
            "- The weight and size of your order\n"
            "- The shipping method you choose\n\n"
            "Free standard shipping on orders over $99!\n"
            "Express shipping options are available for an additional fee."
        ),
    },
]


def _find_matching_faq(question: str, threshold: float = 0.3) -> dict[str, Any] | None:
    """
    基于关键词匹配查找相关 FAQ

    Args:
        question: 用户问题
        threshold: 匹配阈值（0-1）

    Returns:
        匹配的 FAQ 条目，或 None
    """
    question_lower = question.lower()
    best_match = None
    best_score = 0

    for faq in FAQ_KNOWLEDGE_BASE:
        # 计算关键词匹配分数
        matched_keywords = sum(
            1 for keyword in faq["keywords"] if keyword.lower() in question_lower
        )
        score = matched_keywords / len(faq["keywords"]) if faq["keywords"] else 0

        # 如果问题中包含 FAQ 问题的关键词，加分
        if any(word in question_lower for word in faq["question"].lower().split()):
            score += 0.2

        if score > best_score:
            best_score = score
            best_match = faq

    if best_score >= threshold:
        return best_match
    return None


async def generate_ai_response(
    question: str,
    conversation_history: list[dict[str, str]] | None = None,
    customer_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    使用 DeepSeek API 生成 AI 客服回答

    Args:
        question: 用户问题
        conversation_history: 对话历史
        customer_context: 客户上下文（订单信息等）

    Returns:
        包含回答和元数据的字典
    """
    import requests

    settings = get_settings()
    api_key = settings.deepseek_api_key

    if not api_key:
        return {
            "answer": "I'm sorry, but our AI assistant is currently unavailable. Please try again later or contact our customer service team at support@nuotaooutdoor.com.",
            "source": "fallback",
            "confidence": 0.0,
        }

    # 构建系统提示词
    system_prompt = (
        "You are a friendly and knowledgeable customer service representative for Nuotao Outdoor, "
        "an outdoor gear DTC brand targeting European and American customers.\n\n"
        "Guidelines:\n"
        "1. Be helpful, polite, and professional\n"
        "2. Answer questions accurately and concisely\n"
        "3. If you don't know the answer, be honest and suggest contacting human support\n"
        "4. Do not make up policies or promises\n"
        "5. Keep responses focused on the customer's question\n"
        "6. Use English unless the customer writes in another language\n\n"
        "Brand information:\n"
        "- Website: nuotaooutdoor.com\n"
        "- Support email: support@nuotaooutdoor.com\n"
        "- Business hours: Monday-Friday, 9:00 AM - 6:00 PM PST\n"
        "- Free shipping on orders over $99\n"
        "- 30-day return policy\n"
        "- 1-year warranty on all products"
    )

    # 构建用户提示词
    user_parts = [f"Customer question: {question}"]

    if customer_context:
        user_parts.append(f"\nCustomer context: {json.dumps(customer_context, indent=2)}")

    if conversation_history:
        history_text = "\n".join(
            [f"{msg['role'].capitalize()}: {msg['content']}" for msg in conversation_history[-5:]]
        )
        user_parts.append(f"\nRecent conversation:\n{history_text}")

    user_prompt = "\n".join(user_parts)

    # 调用 DeepSeek API
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 1000,
        }

        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        answer = data["choices"][0]["message"]["content"]
        token_usage = data.get("usage", {})

        return {
            "answer": answer,
            "source": "ai",
            "confidence": 0.8,
            "token_usage": token_usage,
        }

    except Exception as e:
        logger.error("AI response generation failed: %s", str(e))
        return {
            "answer": "I'm sorry, but I'm having trouble processing your request right now. Please try again in a moment, or contact our customer service team at support@nuotaooutdoor.com for immediate assistance.",
            "source": "error_fallback",
            "confidence": 0.0,
            "error": str(e),
        }


async def handle_customer_message(
    session: AsyncSession,
    message: str,
    conversation_id: str | None = None,
    customer_id: str | None = None,
    customer_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    处理客户消息（主入口）

    Args:
        session: 数据库会话
        message: 客户消息
        conversation_id: 对话 ID
        customer_id: 客户 ID
        customer_context: 客户上下文

    Returns:
        包含回答和元数据的字典
    """
    start_time = time.time()

    # 1. 先尝试 FAQ 匹配
    faq_match = _find_matching_faq(message)

    # 2. 如果 FAQ 匹配置信度高，直接使用 FAQ 回答
    if faq_match and faq_match.get("id"):
        # 对于常见问题，使用 FAQ 答案 + AI 润色
        faq_answer = faq_match["answer"]
        logger.info("FAQ matched: id=%s, question=%s", faq_match["id"], message[:50])

        result = {
            "answer": faq_answer,
            "source": "faq",
            "faq_id": faq_match["id"],
            "faq_category": faq_match["category"],
            "confidence": 0.9,
            "suggest_human_transfer": False,
        }
    else:
        # 3. 对于非 FAQ 问题，使用 AI 生成回答
        ai_result = await generate_ai_response(
            question=message,
            customer_context=customer_context,
        )
        result = ai_result
        result["suggest_human_transfer"] = ai_result.get("confidence", 0) < 0.5

    # 4. 计算响应时间
    result["response_time_ms"] = int((time.time() - start_time) * 1000)
    result["timestamp"] = datetime.utcnow().isoformat()

    # 5. 记录对话（简化版，实际应存入数据库）
    logger.info(
        "Customer message handled: message=%s, source=%s, response_time=%dms",
        message[:50],
        result.get("source"),
        result.get("response_time_ms", 0),
    )

    return result


async def create_human_ticket(
    session: AsyncSession,
    customer_id: str,
    subject: str,
    description: str,
    priority: str = "normal",
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """
    创建转人工工单

    Args:
        session: 数据库会话
        customer_id: 客户 ID
        subject: 工单主题
        description: 工单描述
        priority: 优先级（low/normal/high/urgent）
        conversation_id: 相关对话 ID

    Returns:
        工单信息
    """
    ticket_id = f"TKT-{int(time.time())}-{customer_id[:4].upper()}"

    ticket = {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "subject": subject,
        "description": description,
        "priority": priority,
        "status": "open",
        "conversation_id": conversation_id,
        "created_at": datetime.utcnow().isoformat(),
        "assigned_to": None,
    }

    logger.info(
        "Human ticket created: ticket_id=%s, customer_id=%s, priority=%s, subject=%s",
        ticket_id,
        customer_id,
        priority,
        subject[:50],
    )

    return {
        "success": True,
        "ticket": ticket,
        "message": (
            f"Your support ticket ({ticket_id}) has been created. "
            f"Our customer service team will review it and respond within 24 hours. "
            f"You will receive an email confirmation shortly."
        ),
    }


def get_faq_categories() -> list[str]:
    """获取 FAQ 分类列表"""
    return list(set(faq["category"] for faq in FAQ_KNOWLEDGE_BASE))


def get_faq_by_category(category: str) -> list[dict[str, Any]]:
    """按分类获取 FAQ"""
    return [faq for faq in FAQ_KNOWLEDGE_BASE if faq["category"].lower() == category.lower()]
