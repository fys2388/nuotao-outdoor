"""
阿里牛顿（Newton Cloud）AI Agent API 端点
提供自然语言找品、批量询盘、任务管理、额度查询等能力
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
from app.services.newton_cost_monitor import (
    check_alerts,
    generate_monitor_report,
    get_daily_usage,
    get_remote_credits,
    get_weekly_usage,
    log_api_call,
)
from app.services.auto_inquiry_service import (
    get_inquiry_history,
    get_inquiry_stats,
    trigger_auto_inquiry,
)
from app.services.newton_sourcing_storage import (
    get_newton_candidate_stats,
    import_products_to_candidates,
    list_newton_candidates,
    load_sourcing_result_by_id,
    load_sourcing_results,
    save_sourcing_result,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/newton", tags=["newton-agent"])
DbSession = Annotated[AsyncSession, Depends(get_db)]


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
        log_api_call("batch_inquiry", success=result.get("success", False))
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Batch inquiry failed: %s", str(e))
        log_api_call("batch_inquiry", success=False, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 成本监控端点
# ============================================

@router.get("/cost/daily", summary="获取每日用量统计")
async def get_daily_cost_usage(
    date: str = Query(None, description="日期（YYYY-MM-DD），默认为今天"),
) -> StandardResponse:
    """获取指定日期的API用量统计（调用次数、积分消耗、token使用）"""
    try:
        result = get_daily_usage(date)
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Get daily usage failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost/weekly", summary="获取7天用量趋势")
async def get_weekly_cost_usage() -> StandardResponse:
    """获取最近7天的API用量趋势和统计"""
    try:
        result = get_weekly_usage()
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Get weekly usage failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost/alerts", summary="检查额度告警")
async def get_cost_alerts() -> StandardResponse:
    """检查API额度使用告警（80%/90%阈值、失败率异常）"""
    try:
        result = check_alerts()
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Check alerts failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost/credits", summary="查询远程积分详情")
async def get_remote_cost_credits() -> StandardResponse:
    """从牛顿API查询远程积分余额和历史消耗记录"""
    try:
        result = get_remote_credits()
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "查询积分失败"))
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Get remote credits failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost/report", summary="生成完整监控报告")
async def get_cost_monitor_report() -> StandardResponse:
    """生成完整的成本监控报告（每日用量、7天趋势、告警、远程积分）"""
    try:
        result = generate_monitor_report()
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Generate monitor report failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 自动询盘端点
# ============================================

@router.get("/auto-inquiry/history", summary="查询自动询盘历史")
async def get_auto_inquiry_history(
    purchase_order_id: str = Query(None, description="采购单ID（可选）"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> StandardResponse:
    """查询自动询盘历史记录，支持按采购单ID筛选"""
    try:
        result = get_inquiry_history(purchase_order_id=purchase_order_id, limit=limit)
        return StandardResponse(success=True, data={"records": result, "total": len(result)})
    except Exception as e:
        logger.error("Get inquiry history failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auto-inquiry/stats", summary="查询自动询盘统计")
async def get_auto_inquiry_stats() -> StandardResponse:
    """查询自动询盘统计信息（总数、成功率、按策略分布）"""
    try:
        result = get_inquiry_stats()
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Get inquiry stats failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


class TriggerInquiryRequest(BaseModel):
    """手动触发询盘请求"""
    purchase_order: dict[str, Any] = Field(..., description="采购单数据")
    strategy: str = Field("standard", description="询盘策略：spot/custom/standard")
    auto: bool = Field(True, description="是否自动执行（False=仅生成草稿）")


@router.post("/auto-inquiry/trigger", summary="手动触发自动询盘")
async def trigger_auto_inquiry_endpoint(request: TriggerInquiryRequest) -> StandardResponse:
    """手动触发自动询盘（用于测试或补触发）"""
    try:
        result = trigger_auto_inquiry(
            purchase_order=request.purchase_order,
            strategy=request.strategy,
            auto=request.auto,
        )
        if not result.get("success") and result.get("error"):
            # 部分情况（如无商品映射）也算成功返回，但带错误信息
            pass
        log_api_call("auto_inquiry_trigger", success=result.get("success", False))
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Trigger auto inquiry failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 选品结果入库端点
# ============================================

@router.get("/sourcing/results", summary="查询历史选品结果列表")
async def get_sourcing_results_list(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> StandardResponse:
    """查询牛顿AI历史选品结果列表（JSON文件存储）"""
    try:
        results = load_sourcing_results(limit=limit)
        return StandardResponse(success=True, data={"results": results, "total": len(results)})
    except Exception as e:
        logger.error("Get sourcing results failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sourcing/results/{sourcing_id}", summary="查询选品结果详情")
async def get_sourcing_result_detail(sourcing_id: str) -> StandardResponse:
    """根据选品ID查询详细结果（含商品列表和AI总结）"""
    try:
        result = load_sourcing_result_by_id(sourcing_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"选品结果 {sourcing_id} 不存在")
        return StandardResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get sourcing result detail failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


class ImportSourcingRequest(BaseModel):
    """导入选品结果到候选库请求"""
    products: list[dict[str, Any]] = Field(..., description="商品列表")
    sourcing_id: str = Field("", description="选品批次ID")
    source_query: str = Field("", description="来源查询词")


@router.post("/sourcing/import", summary="导入选品结果到候选库")
async def import_sourcing_to_candidates(
    request: ImportSourcingRequest,
    db: DbSession,
) -> StandardResponse:
    """将牛顿找品商品批量导入系统选品候选库"""
    try:
        result = await import_products_to_candidates(
            session=db,
            products=request.products,
            sourcing_id=request.sourcing_id,
            source_query=request.source_query,
        )
        log_api_call("sourcing_import", success=result.get("imported", 0) > 0)
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Import sourcing to candidates failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sourcing/candidates", summary="查询牛顿来源的选品候选")
async def get_newton_sourcing_candidates(
    db: DbSession,
    status: str = Query("candidate", description="候选状态：candidate/approved/testing/winner/rejected"),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
) -> StandardResponse:
    """查询牛顿AI来源的选品候选列表"""
    try:
        result = await list_newton_candidates(
            session=db,
            status=status,
            limit=limit,
            offset=offset,
        )
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Get newton candidates failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sourcing/stats", summary="查询选品候选统计")
async def get_sourcing_candidate_stats(db: DbSession) -> StandardResponse:
    """查询牛顿选品候选统计（按状态分布）"""
    try:
        result = await get_newton_candidate_stats(session=db)
        return StandardResponse(success=True, data=result)
    except Exception as e:
        logger.error("Get sourcing stats failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
