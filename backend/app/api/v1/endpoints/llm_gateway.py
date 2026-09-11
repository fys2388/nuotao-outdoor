"""
LLM Gateway API 端点
统一的大语言模型调用网关接口
基于 app.services.llm_gateway 实现
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.llm_gateway import (
    PRICING,
    SUPPORTED_PROVIDERS,
    LLMError,
    LLMRequest,
    complete,
    estimate_cost,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm-gateway", tags=["llm-gateway"])


# ============================================
# 请求/响应模型
# ============================================

class ChatRequest(BaseModel):
    """聊天请求"""
    messages: list[dict[str, str]] = Field(..., description="消息列表，格式：[{role: 'user', content: '...'}]")
    provider: str | None = Field(None, description="指定供应商：openai/deepseek（可选）")
    model: str | None = Field(None, description="指定模型（可选）")
    task_type: str = Field("default", description="任务类型")
    temperature: float = Field(0.2, description="温度（0-1）", ge=0, le=1)
    max_tokens: int | None = Field(None, description="最大 token 数")
    response_format: str | None = Field(None, description="响应格式：json_object（可选）")


class ChatResponse(BaseModel):
    """聊天响应"""
    success: bool
    content: str | None = None
    provider: str | None = None
    model: str | None = None
    tokens: dict[str, int] = {}
    cost: float = 0
    latency_ms: int = 0
    trace_id: str | None = None
    error: str | None = None
    error_kind: str | None = None


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取 LLM 网关状态",
)
async def get_status() -> dict[str, Any]:
    """
    获取 LLM 网关状态

    包括：供应商配置、模型列表、定价信息、支持的供应商
    """
    settings = get_settings()

    providers_status = {}
    for provider in SUPPORTED_PROVIDERS:
        if provider == "openai":
            api_key = settings.openai_api_key
            base_url = settings.openai_base_url
            default_model = settings.openai_default_model
        elif provider == "deepseek":
            api_key = settings.deepseek_api_key
            base_url = settings.deepseek_base_url
            default_model = settings.deepseek_default_model
        else:
            api_key = None
            base_url = None
            default_model = None

        providers_status[provider] = {
            "configured": api_key is not None,
            "base_url": base_url,
            "default_model": default_model,
        }

    # 获取所有配置的模型和定价
    models_pricing = {}
    for key, (input_price, output_price) in PRICING.items():
        provider, model = key.split(":", 1)
        if provider not in models_pricing:
            models_pricing[provider] = []
        models_pricing[provider].append({
            "model": model,
            "input_price_per_1k": float(input_price),
            "output_price_per_1k": float(output_price),
        })

    return {
        "status": "running",
        "primary_provider": settings.llm_provider,
        "providers": providers_status,
        "supported_providers": list(SUPPORTED_PROVIDERS),
        "models": models_pricing,
        "default_max_tokens": settings.llm_max_tokens,
        "default_timeout_seconds": settings.llm_timeout_seconds,
        "fallback_provider": settings.llm_fallback_provider,
    }


@router.get(
    "/models",
    summary="获取可用模型列表",
)
async def list_models() -> dict[str, Any]:
    """获取所有可用模型列表（包含定价信息）"""
    models = []
    for key, (input_price, output_price) in PRICING.items():
        provider, model = key.split(":", 1)
        models.append({
            "provider": provider,
            "model": model,
            "input_price_per_1k": float(input_price),
            "output_price_per_1k": float(output_price),
        })

    return {
        "models": models,
        "total": len(models),
    }


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="统一聊天补全接口",
)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    统一聊天补全接口

    - 自动根据配置路由到主供应商
    - 主供应商失败时自动降级到备用供应商（网络/5xx/限流错误）
    - 支持结构化输出（response_format=json_object）
    - 自动计算成本和延迟
    """
    try:
        llm_request = LLMRequest(
            messages=request.messages,
            provider=request.provider,
            model=request.model,
            task_type=request.task_type,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            response_format=request.response_format,
        )

        response = await complete(llm_request, allow_fallback=True)

        return ChatResponse(
            success=True,
            content=response.content,
            provider=response.provider,
            model=response.model,
            tokens=response.tokens,
            cost=float(response.cost),
            latency_ms=response.latency_ms,
            trace_id=response.trace_id,
        )

    except LLMError as e:
        logger.warning("LLM gateway chat failed: kind=%s, error=%s", e.kind, str(e))
        return ChatResponse(
            success=False,
            error=str(e),
            error_kind=e.kind,
        )
    except Exception as e:
        logger.exception("LLM gateway chat unexpected error: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM gateway error: {e!s}",
        )


@router.post(
    "/chat/simple",
    summary="简单聊天接口（单条消息）",
)
async def simple_chat(
    message: str,
    provider: str | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """
    简单聊天接口

    快速测试用，只需要传入一条消息即可。
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})

    try:
        llm_request = LLMRequest(
            messages=messages,
            provider=provider,
            task_type="simple_chat",
        )
        response = await complete(llm_request, allow_fallback=True)

        return {
            "question": message,
            "answer": response.content,
            "provider": response.provider,
            "model": response.model,
            "success": True,
            "cost": float(response.cost),
            "latency_ms": response.latency_ms,
            "trace_id": response.trace_id,
        }
    except LLMError as e:
        return {
            "question": message,
            "answer": None,
            "success": False,
            "error": str(e),
            "error_kind": e.kind,
        }


@router.post(
    "/cost/estimate",
    summary="估算调用成本",
)
async def estimate_call_cost(
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> dict[str, Any]:
    """
    估算 LLM 调用成本

    根据供应商、模型和 token 数量估算 USD 成本。
    """
    tokens = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }

    try:
        cost = estimate_cost(provider, model, tokens)
        return {
            "provider": provider,
            "model": model,
            "tokens": tokens,
            "estimated_cost_usd": float(cost),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cost estimation failed: {e!s}",
        )
