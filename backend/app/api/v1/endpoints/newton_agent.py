"""
阿里牛顿（Newton Cloud）AI Agent API 端点
提供自然语言找品、批量询盘、任务管理、额度查询等能力
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.newton_agent_service import (
    batch_inquiry,
    create_agent_task,
    fetch_task_result,
    get_task_status,
    is_configured,
    list_models,
    list_tasks,
    newton_agent_search,
    query_points,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/newton", tags=["newton-agent"])


# ============================================
# 请求/响应模型
# ============================================

class CreateTaskRequest(BaseModel):
    """创建Agent任务请求"""
    message: str = Field(..., description="自然语言任务描述", min_length=1)
    auto: bool = Field(True, description="是否让Agent自主补全默认值")
    model: str | None = Field(None, description="指定Agent模型（如qwen3.6-plus）")


class SearchRequest(BaseModel):
    """自然语言找品请求"""
    query: str = Field(..., description="找品需求描述，如'户外露营灯，10-30元'", min_length=1)
    min_price: float | None = Field(None, description="最低价格（元）", gt=0)
    max_price: float | None = Field(None, description="最高价格（元）", gt=0)
    min_order_qty: int | None = Field(None, description="最小起订量", gt=0)
    category: str | None = Field(None, description="品类限定")
    auto: bool = Field(True, description="Agent自主补全参数")


class BatchInquiryRequest(BaseModel):
    """批量询盘请求"""
    product_ids: list[str] = Field(..., description="1688商品ID列表", min_length=1)
    inquiry_message: str = Field(
        "请问这款产品的批发价、起订量、交货周期是多少？",
        description="询盘内容",
    )


class StandardResponse(BaseModel):
    """标准响应包装"""
    success: bool
    data: Any | None = None
    error: str | None = None


# ============================================
# 端点实现
# ============================================

@router.get("/status", summary="检查牛顿Agent配置状态")
async def get_config_status() -> StandardResponse:
    """检查牛顿API是否已配置（appKey+appSecret+accessToken）"""
    configured = is_configured()
    return StandardResponse(
        success=True,
        data={
            "configured": configured,
            "app_key_present": bool(is_configured()),
            "daily_limit": 5000,
            "description": "阿里牛顿云端Agent解决方案" if configured else "未配置API凭证",
        },
    )


@router.get("/models", summary="列出可用Agent模型")
async def get_models() -> StandardResponse:
    """列出牛顿云可用的Agent模型档位"""
    try:
        result = list_models()
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "获取模型列表失败"))
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Get models failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/points", summary="查询积分/额度详情")
async def get_points() -> StandardResponse:
    """查询API积分使用情况和剩余额度"""
    try:
        result = query_points()
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "查询额度失败"))
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Get points failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks", summary="创建Agent任务")
async def create_task(request: CreateTaskRequest) -> StandardResponse:
    """
    创建牛顿Agent长程任务
    返回task_id，用/tasks/{task_id}查询状态
    """
    try:
        result = create_agent_task(
            message=request.message,
            auto=request.auto,
            model=request.model,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "创建任务失败"))
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Create task failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks", summary="查询任务列表")
async def get_task_list(
    page: int = Query(1, description="页码", ge=1),
    page_size: int = Query(20, description="每页数量", ge=1, le=100),
) -> StandardResponse:
    """查询Agent任务列表"""
    try:
        result = list_tasks(page=page, page_size=page_size)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "查询任务列表失败"))
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("List tasks failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", summary="查询任务状态")
async def get_task(task_id: str) -> StandardResponse:
    """
    查询Agent任务执行状态
    状态枚举：INIT/RUNNING/WAIT_SKILL/WAIT_USER/END/KILL
    """
    try:
        result = get_task_status(task_id)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "查询任务状态失败"))
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Get task status failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/result", summary="获取任务结果")
async def get_task_result(task_id: str) -> StandardResponse:
    """获取Agent任务的最终结果（商品列表/对比表/询盘结果等）"""
    try:
        result = fetch_task_result(task_id)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "获取任务结果失败"))
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Get task result failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", summary="自然语言找品")
async def search_products(request: SearchRequest) -> StandardResponse:
    """
    牛顿AI智能找品（高层封装）
    用自然语言描述需求，Agent自动在1688找品、比价、筛选
    """
    try:
        result = newton_agent_search(
            query=request.query,
            min_price=request.min_price,
            max_price=request.max_price,
            min_order_qty=request.min_order_qty,
            category=request.category,
            auto=request.auto,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "找品失败"))
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Newton search failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inquiry", summary="批量询盘")
async def create_batch_inquiry(request: BatchInquiryRequest) -> StandardResponse:
    """
    对多个1688商品发起批量询盘
    询盘内容可自定义，支持价格、起订量、交期等问题
    """
    try:
        result = batch_inquiry(
            product_ids=request.product_ids,
            inquiry_message=request.inquiry_message,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "批量询盘失败"))
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Batch inquiry failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
