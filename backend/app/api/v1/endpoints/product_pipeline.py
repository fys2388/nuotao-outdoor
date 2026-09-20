"""
产品端到端工作流 API 端点（P2-2）

Routes:
- GET  /api/v1/product-pipeline/status          — 工作流服务状态
- POST /api/v1/product-pipeline/run             — 运行完整工作流
- POST /api/v1/product-pipeline/confirm-list    — 人工确认后上架
- GET  /api/v1/product-pipeline/steps           — 获取工作流步骤定义
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import Product
from app.services import product_import_job_service
from app.services.product_pipeline_service import (
    FUNNEL_REJECTED,
    PIPELINE_STEPS,
    confirm_and_list,
    get_pipeline_status,
    import_and_analyze_from_1688,
    import_from_1688,
    run_pipeline,
    upsert_local_listed_product,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/product-pipeline", tags=["product_pipeline"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================
# Request / Response models
# ============================================


class ProductInfoRequest(BaseModel):
    """商品信息请求"""
    name: str = Field(..., description="商品名称", min_length=1)
    category: str = Field("", description="商品类目")
    price: str = Field("", description="商品价格")
    description: str = Field("", description="商品描述")
    core_selling_points: list[str] = Field(default_factory=list, description="核心卖点")
    target_audience: str = Field("", description="目标人群")
    usage_scenarios: list[str] = Field(default_factory=list, description="使用场景")
    product_features: list[str] = Field(default_factory=list, description="产品功能")
    materials: list[str] = Field(default_factory=list, description="材质")
    dimensions: str = Field("", description="尺寸")
    weight: str = Field("", description="重量")
    source_url: str = Field("", description="1688商品链接")
    source_id: str = Field("", description="1688商品ID")


class RunPipelineRequest(BaseModel):
    """运行工作流请求"""
    product_info: ProductInfoRequest
    auto_list: bool = Field(False, description="是否自动上架（默认False，需要人工确认）")
    include_images: bool = Field(False, description="是否包含图片生成")


class ConfirmListRequest(BaseModel):
    """确认上架请求"""
    pipeline_result: dict[str, Any] = Field(..., description="工作流结果")
    status: str = Field("publish", description="上架状态（publish/draft/pending）")


class ImportFrom1688Request(BaseModel):
    """从1688导入商品请求"""
    url_or_id: str = Field(..., description="1688商品URL或商品ID", min_length=1)
    auto_run_pipeline: bool = Field(False, description="是否自动运行完整工作流")
    auto_list: bool = Field(False, description="是否自动上架WooCommerce（仅在auto_run_pipeline=True时生效）")


class ImportAndAnalyzeFrom1688Request(BaseModel):
    """从1688导入并执行 AI 产品分析请求"""
    url_or_id: str = Field(..., description="1688商品URL或商品ID", min_length=1)
    temperature: float = Field(0.3, ge=0, le=1, description="LLM温度")
    max_tokens: int = Field(2000, ge=500, le=8000, description="最大token数")


# ============================================
# API endpoints
# ============================================


@router.get("/status", summary="获取工作流服务状态")
async def get_status() -> dict[str, Any]:
    """返回工作流服务状态、步骤定义和配置"""
    return get_pipeline_status()


@router.get("/steps", summary="获取工作流步骤定义")
async def get_steps() -> dict[str, Any]:
    """返回工作流6个步骤的详细定义"""
    return {
        "success": True,
        "data": {
            "steps": PIPELINE_STEPS,
            "total_steps": len(PIPELINE_STEPS),
        },
        "error": None,
    }


@router.post("/run", summary="运行完整产品工作流")
async def run_product_pipeline(
    request: RunPipelineRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    运行完整的产品端到端工作流：
    1. 商品信息输入
    2. AI产品分析（10字段识别 + 17字段报告）
    3. 主图生产（3套方向 + 短文案 + 10个变体）
    4. 生图Prompt生成
    5. 上架数据生成
    6. V3.0选品闸门（Nuotao Score + V1-V12 一票否决 + 漏斗阶段）
    7. 上架WooCommerce（可选，需要人工确认；被闸门否决则阻断）
    """
    try:
        product_info = request.product_info.model_dump()
        result = await run_pipeline(
            product_info,
            auto_list=request.auto_list,
            include_images=request.include_images,
            session=db,
        )
        # 闸门会落库候选产品与 V3.0 评分，get_db 不自动提交，必须显式 commit，
        # 否则评分历史与漏斗阶段全部丢失。
        await db.commit()
        return result
    except Exception as e:
        await db.rollback()
        logger.error("Run pipeline error: %s", str(e))
        return {
            "success": False,
            "data": None,
            "error": str(e),
        }


@router.post("/confirm-list", summary="人工确认后执行上架")
async def confirm_product_listing(
    request: ConfirmListRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    人工确认工作流结果后，执行上架到WooCommerce

    Args:
        pipeline_result: 工作流结果（包含listing_data）
        status: 上架状态（publish/draft/pending）
    """
    try:
        listing_data = (
            (request.pipeline_result or {}).get("data", {}).get("steps", {})
            .get("listing_data", {}).get("data", {})
        )
        # 服务端权威校验：被 V3.0 否决的产品即使前端点了确认也不能上架。
        # 以前端回传的 pipeline_result 为准不可靠（可被篡改/过期），因此按
        # SKU 查数据库里的漏斗阶段。此端点原本不要求鉴权，故不引入用户依赖，
        # 直接用默认工作空间（当前版本为单工作空间部署）。
        sku = str(listing_data.get("sku") or "").strip()
        # 低分但无红线否决时，人工确认即视为知情放行，提示语透传给前端留痕。
        gate_override_notice: str | None = None
        if sku:
            row = (
                await db.execute(
                    select(Product.funnel_stage, Product.reject_reasons).where(
                        Product.workspace_id == DEFAULT_WORKSPACE_ID,
                        Product.sku == sku,
                        Product.deleted_at.is_(None),
                    )
                )
            ).first()
            if row is not None and row.funnel_stage == FUNNEL_REJECTED:
                hard_reasons = [
                    item.get("detail") or item.get("rule_id")
                    for item in (row.reject_reasons or [])
                    if isinstance(item, dict)
                ]
                # reject_reasons 只记录确定性一票否决（nuotao_selection_service 仅把
                # veto.failed 写入）。funnel_stage=rejected 但原因为空，代表 Nuotao Score
                # 低分（grade=reject<65）而无红线证据——pipeline 闸门三态中属 needs_review。
                # 按 AGENTS.md「AI 只建议、关键动作人审」，低分不应被系统强制阻断，人工
                # 点击确认即知情放行；只有侵权/合规等硬否决才无论 draft/publish 一律拦截。
                if hard_reasons:
                    detail = "；".join(str(item) for item in hard_reasons if item) or "触发一票否决"
                    logger.warning("confirm-list hard-veto rejected for sku=%s: %s", sku, detail)
                    return {
                        "success": False,
                        "data": {"sku": sku, "funnel_stage": row.funnel_stage},
                        "error": f"V3.0 一票否决，禁止上架：{detail}",
                    }
                gate_override_notice = (
                    "该商品 Nuotao Score 低于 65（AI 评级 Reject，无一票否决红线），"
                    "已由人工确认放行；建议先在候选池补全成本/供应商数据后重评。"
                )
                logger.info(
                    "confirm-list low-score human override for sku=%s (no hard veto)", sku
                )

        result = confirm_and_list(
            request.pipeline_result,
            status=request.status,
        )
        if gate_override_notice and result.get("success"):
            result["gate_override_warning"] = gate_override_notice

        # WC 推送成功后，同步落库到本地商品主数据（修复"只推 WC、本地为空"断层）
        if result.get("success") and listing_data:
            try:
                data_section = (request.pipeline_result or {}).get("data", {})
                product_info = data_section.get("product_info") or {}
                source_url = (
                    product_info.get("source_url")
                    or product_info.get("url")
                    or product_info.get("source_1688_url")
                    or ""
                )
                local = await upsert_local_listed_product(
                    db,
                    listing_data,
                    result,
                    DEFAULT_WORKSPACE_ID,
                    source="pipeline",
                    source_url=source_url,
                )
                result["local_product_id"] = local.get("product_id")
                result["local_created"] = local.get("created")
            except Exception as upsert_err:
                # 本地落库失败不回滚 WC，但必须显式告警，避免静默数据断层
                logger.error("Local product upsert failed for sku=%s: %s", sku, upsert_err)
                result["local_upsert_error"] = str(upsert_err)

        return {
            "success": result.get("success", False),
            "data": result,
            "error": None if result.get("success") else result.get("error"),
        }
    except Exception as e:
        logger.error("Confirm list error: %s", str(e))
        return {
            "success": False,
            "data": None,
            "error": str(e),
        }


@router.post("/import-from-1688", summary="从1688商品URL/ID一键导入")
async def import_product_from_1688(
    request: ImportFrom1688Request,
    db: DbSession,
) -> dict[str, Any]:
    """
    从1688商品URL或ID一键导入商品信息到产品工作流

    流程：
    1. 解析URL提取商品ID
    2. 调用1688 API获取商品详情
    3. 转换为产品工作流输入格式（名称/价格/描述/图片/属性等）
    4. 可选：自动运行完整工作流（AI分析→主图→Prompt→上架数据→V3.0闸门）
    5. 可选：自动上架WooCommerce

    Args:
        url_or_id: 1688商品URL或商品ID
        auto_run_pipeline: 是否自动运行完整工作流
        auto_list: 是否自动上架（仅在auto_run_pipeline=True时生效）

    Returns:
        导入结果，包含商品信息和可选的工作流结果
    """
    try:
        # import_from_1688 现在是协程（内部把阻塞抓取放到线程池），必须 await；
        # 传入 db 让自动流转同样经过 V3.0 选品闸门。
        result = await import_from_1688(
            url_or_id=request.url_or_id,
            auto_run_pipeline=request.auto_run_pipeline,
            auto_list=request.auto_list,
            session=db,
        )
        if result.get("success"):
            # 闸门落库的候选产品与评分记录需要显式提交，get_db 不自动 commit
            await db.commit()
        else:
            await db.rollback()
        return result
    except Exception as e:
        await db.rollback()
        logger.error("Import from 1688 error: %s", str(e))
        return {
            "success": False,
            "data": None,
            "error": str(e),
        }


@router.post(
    "/import-and-analyze-1688",
    summary="从1688导入并立即完成 AI 产品分析",
    dependencies=[Depends(get_current_user)],
)
async def import_and_analyze_product_from_1688(
    request: ImportAndAnalyzeFrom1688Request,
) -> dict[str, Any]:
    """
    导入单个 1688 商品并立即生成 10 字段 AI 识别和 17 字段产品报告。

    管理端批量导入由前端逐条调用本接口，保证单条失败隔离和进度反馈。
    """
    try:
        return await import_and_analyze_from_1688(
            url_or_id=request.url_or_id,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as e:
        logger.error("Import and analyze from 1688 error: %s", str(e))
        return {
            "success": False,
            "data": None,
            "error": str(e),
        }


@router.post(
    "/import-and-analyze-1688/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交1688导入与AI分析后台任务",
    dependencies=[Depends(get_current_user)],
)
async def create_import_and_analyze_job(
    request: ImportAndAnalyzeFrom1688Request,
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    """立即返回任务 ID，前端通过状态接口轮询结果，避免网关长连接超时。"""
    try:
        job = await product_import_job_service.create_job(
            redis,
            url_or_id=request.url_or_id,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return {
            "success": True,
            "data": {
                "job_id": job["job_id"],
                "status": job["status"],
            },
            "error": None,
        }
    except Exception as e:
        logger.error("Create 1688 import job failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="无法创建后台导入任务，请检查 Redis 服务",
        ) from e


@router.get(
    "/import-and-analyze-1688/jobs/{job_id}",
    summary="查询1688导入与AI分析后台任务",
    dependencies=[Depends(get_current_user)],
)
async def get_import_and_analyze_job(
    job_id: str,
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    """查询后台任务状态和最终商品分析结果。"""
    try:
        job = await product_import_job_service.get_job(redis, job_id)
    except Exception as e:
        logger.error("Get 1688 import job failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="无法读取后台导入任务状态",
        ) from e
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="导入任务不存在或已过期",
        )
    return {"success": True, "data": job, "error": None}
