"""
Agent 分析 API 端点
支持 5 个 AI Agent 的分析调用，直接连接 DeepSeek API
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-analysis", tags=["agent-analysis"])


# ============================================
# 请求/响应模型
# ============================================

class AgentAnalysisRequest(BaseModel):
    """Agent 分析请求"""
    agent_type: str = Field(
        ...,
        description="Agent 类型: product, marketing, supply_chain, customer, business",
        example="product",
    )
    context: dict[str, Any] = Field(
        ...,
        description="分析上下文数据（JSON 对象）",
        example={"product": {"name": "Test Product", "price": 99.99}},
    )
    temperature: float = Field(
        0.3,
        description="LLM 温度参数（0-1）",
        ge=0,
        le=1,
    )


class AgentAnalysisResponse(BaseModel):
    """Agent 分析响应"""
    success: bool
    agent_type: str
    agent_name: str
    elapsed_seconds: float
    result: dict[str, Any] | None = None
    error: str | None = None
    token_usage: dict[str, Any] | None = None


# ============================================
# 5 个 Agent 的配置
# ============================================

AGENTS_CONFIG = {
    "product": {
        "name": "产品分析师",
        "name_en": "Product Analyst",
        "system_prompt": (
            "You are the Product Analyst for Nuotao Outdoor, an outdoor gear DTC brand "
            "targeting European and American customers. Analyze the provided product context "
            "and respond with ONLY a JSON object matching the output schema."
        ),
        "user_prompt_template": (
            "Context: {context_json}\n\n"
            "Output schema: {output_schema}\n\n"
            "Focus on: product performance analysis, pricing recommendations, "
            "competitive positioning, inventory optimization, and actionable product insights. "
            "All recommendations must be data-driven and include confidence scores."
        ),
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Brief summary of product analysis"},
                "performance_score": {"type": "number", "description": "Product performance score (0-100)"},
                "pricing_recommendation": {
                    "type": "object",
                    "properties": {
                        "suggested_price": {"type": "number"},
                        "rationale": {"type": "string"},
                        "expected_impact": {"type": "string"},
                    },
                },
                "competitive_position": {"type": "string"},
                "inventory_advice": {"type": "string"},
                "actionable_insights": {"type": "array", "items": {"type": "string"}},
                "confidence_score": {"type": "number", "description": "Confidence score (0-1)"},
            },
            "required": ["summary", "performance_score", "actionable_insights", "confidence_score"],
        },
    },
    "marketing": {
        "name": "营销经理",
        "name_en": "Marketing Manager",
        "system_prompt": (
            "You are the Marketing Manager for Nuotao Outdoor, an outdoor gear DTC brand "
            "targeting European and American customers. Analyze the provided marketing context "
            "and respond with ONLY a JSON object matching the output schema."
        ),
        "user_prompt_template": (
            "Context: {context_json}\n\n"
            "Output schema: {output_schema}\n\n"
            "Focus on: campaign ROI analysis, customer segmentation, pricing strategy, "
            "competitive positioning, and actionable marketing recommendations. "
            "All recommendations must be data-driven and include confidence scores."
        ),
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "campaign_analysis": {"type": "object"},
                "customer_segments": {"type": "array", "items": {"type": "object"}},
                "pricing_suggestions": {"type": "array", "items": {"type": "object"}},
                "marketing_recommendations": {"type": "array", "items": {"type": "string"}},
                "confidence_score": {"type": "number"},
            },
            "required": ["summary", "campaign_analysis", "marketing_recommendations", "confidence_score"],
        },
    },
    "supply_chain": {
        "name": "供应链经理",
        "name_en": "Supply Chain Manager",
        "system_prompt": (
            "You are the Supply Chain Manager for Nuotao Outdoor, an outdoor gear DTC brand "
            "targeting European and American customers. Analyze the provided supply chain context "
            "and respond with ONLY a JSON object matching the output schema."
        ),
        "user_prompt_template": (
            "Context: {context_json}\n\n"
            "Output schema: {output_schema}\n\n"
            "Focus on: supplier performance evaluation, inventory optimization, "
            "cost reduction opportunities, logistics efficiency, risk assessment, "
            "and actionable supply chain recommendations. "
            "All recommendations must be data-driven and include confidence scores."
        ),
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "supplier_performance": {"type": "array", "items": {"type": "object"}},
                "inventory_optimization": {"type": "object"},
                "cost_analysis": {"type": "object"},
                "risk_assessment": {"type": "array", "items": {"type": "object"}},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "confidence_score": {"type": "number"},
            },
            "required": ["summary", "supplier_performance", "recommendations", "confidence_score"],
        },
    },
    "customer": {
        "name": "客户经理",
        "name_en": "Customer Manager",
        "system_prompt": (
            "You are the Customer Manager for Nuotao Outdoor, an outdoor gear DTC brand "
            "targeting European and American customers. Analyze the provided customer context "
            "and respond with ONLY a JSON object matching the output schema."
        ),
        "user_prompt_template": (
            "Context: {context_json}\n\n"
            "Output schema: {output_schema}\n\n"
            "Focus on: customer sentiment analysis, support ticket prioritization, "
            "response draft generation, feedback analysis, churn risk assessment, "
            "and actionable customer experience recommendations. "
            "All recommendations must be data-driven and include confidence scores."
        ),
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "sentiment_analysis": {"type": "object"},
                "ticket_prioritization": {"type": "array", "items": {"type": "object"}},
                "response_draft": {"type": "string"},
                "churn_risk": {"type": "object"},
                "feedback_insights": {"type": "array", "items": {"type": "string"}},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "confidence_score": {"type": "number"},
            },
            "required": ["summary", "sentiment_analysis", "response_draft", "recommendations", "confidence_score"],
        },
    },
    "business": {
        "name": "商业分析师",
        "name_en": "Business Analyst",
        "system_prompt": (
            "You are the Business Analyst for Nuotao Outdoor, an outdoor gear DTC brand "
            "targeting European and American customers. Analyze the provided business context "
            "and respond with ONLY a JSON object matching the output schema."
        ),
        "user_prompt_template": (
            "Context: {context_json}\n\n"
            "Output schema: {output_schema}\n\n"
            "Focus on: financial performance analysis, sales trends, KPI tracking, "
            "market opportunity identification, risk assessment, profitability analysis, "
            "and actionable business recommendations. "
            "All recommendations must be data-driven and include confidence scores."
        ),
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "financial_analysis": {"type": "object"},
                "sales_analysis": {"type": "object"},
                "kpi_dashboard": {"type": "object"},
                "market_opportunities": {"type": "array", "items": {"type": "object"}},
                "risk_assessment": {"type": "array", "items": {"type": "object"}},
                "profitability_analysis": {"type": "object"},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "confidence_score": {"type": "number"},
            },
            "required": ["summary", "financial_analysis", "kpi_dashboard", "recommendations", "confidence_score"],
        },
    },
}


# ============================================
# DeepSeek API 调用
# ============================================

def call_deepseek_api(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """
    调用 DeepSeek API

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        temperature: 温度参数

    Returns:
        API 响应 JSON
    """
    import requests

    settings = get_settings()
    api_key = settings.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY", "")

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DeepSeek API key not configured",
        )

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
        "temperature": temperature,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error("DeepSeek API call failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek API call failed: {e!s}",
        ) from e


def extract_json_content(response: dict[str, Any]) -> dict[str, Any]:
    """从 API 响应中提取并解析 JSON 内容"""
    try:
        content = response["choices"][0]["message"]["content"]
        return json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.error("Failed to parse JSON from DeepSeek response: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse JSON from LLM response: {e!s}",
        ) from e


# ============================================
# API 端点
# ============================================

@router.post(
    "/analyze",
    response_model=AgentAnalysisResponse,
    summary="运行 AI Agent 分析",
)
async def analyze_with_agent(
    request: AgentAnalysisRequest,
) -> AgentAnalysisResponse:
    """
    运行指定的 AI Agent 进行分析

    - **agent_type**: 可选值 product, marketing, supply_chain, customer, business
    - **context**: 分析上下文数据（JSON 对象）
    - **temperature**: LLM 温度参数（0-1），默认 0.3
    """
    start_time = time.time()

    # 验证 Agent 类型
    if request.agent_type not in AGENTS_CONFIG:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported agent type: {request.agent_type}. "
                   f"Supported types: {', '.join(AGENTS_CONFIG.keys())}",
        )

    agent_config = AGENTS_CONFIG[request.agent_type]

    logger.info(
        "Starting agent analysis: agent=%s, context_keys=%s",
        request.agent_type,
        list(request.context.keys()),
    )

    try:
        # 构建用户提示词
        user_prompt = agent_config["user_prompt_template"].format(
            context_json=json.dumps(request.context, indent=2, ensure_ascii=False),
            output_schema=json.dumps(agent_config["output_schema"], indent=2, ensure_ascii=False),
        )

        # 调用 DeepSeek API
        api_response = call_deepseek_api(
            system_prompt=agent_config["system_prompt"],
            user_prompt=user_prompt,
            temperature=request.temperature,
        )

        # 解析结果
        result = extract_json_content(api_response)

        elapsed = time.time() - start_time

        logger.info(
            "Agent analysis completed: agent=%s, elapsed=%.2fs, result_keys=%s",
            request.agent_type,
            elapsed,
            list(result.keys()),
        )

        return AgentAnalysisResponse(
            success=True,
            agent_type=request.agent_type,
            agent_name=agent_config["name"],
            elapsed_seconds=round(elapsed, 2),
            result=result,
            token_usage=api_response.get("usage"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agent analysis failed: %s", str(e))
        elapsed = time.time() - start_time
        return AgentAnalysisResponse(
            success=False,
            agent_type=request.agent_type,
            agent_name=agent_config["name"],
            elapsed_seconds=round(elapsed, 2),
            error=str(e),
        )


@router.get(
    "/agents",
    summary="获取支持的 Agent 列表",
)
async def list_agents() -> dict[str, Any]:
    """获取支持的 AI Agent 列表及其配置"""
    return {
        "agents": [
            {
                "type": agent_type,
                "name": config["name"],
                "name_en": config["name_en"],
                "description": f"{config['name']} AI Agent for Nuotao Outdoor",
            }
            for agent_type, config in AGENTS_CONFIG.items()
        ],
        "total": len(AGENTS_CONFIG),
    }


@router.post(
    "/analyze/batch",
    summary="批量运行多个 Agent 分析",
)
async def batch_analyze(
    requests: list[AgentAnalysisRequest],
) -> dict[str, Any]:
    """
    批量运行多个 Agent 分析

    注意：每个请求会依次调用，总耗时为各请求耗时之和
    """
    results = []
    for req in requests:
        try:
            result = await analyze_with_agent(req)
            results.append(result.model_dump())
        except Exception as e:
            results.append({
                "success": False,
                "agent_type": req.agent_type,
                "agent_name": AGENTS_CONFIG.get(req.agent_type, {}).get("name", "Unknown"),
                "elapsed_seconds": 0,
                "error": str(e),
            })

    return {
        "total": len(requests),
        "success": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "results": results,
    }
