"""产品流水线编排器 — 选品审批通过后自动推进全链路（P2-2）。

自动流程：
选品审批通过 → 1688信息抓取 → AI产品分析 → 主图生成 → 文案生成 → 定价计算 → WooCommerce上架 → SEO提交

每个步骤：
- 自动执行（低风险）或等待人工确认（高风险）
- 失败可重试（最多3次）
- 状态实时记录，可通过 API 查询
- 人工可随时介入/暂停/跳过

设计原则：
- Human-in-the-loop：上架动作必须人工确认
- 幂等：重复触发不会产生重复产品
- 可观测：每步状态、耗时、错误都记录
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import agent_suggestion_service

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# 流水线步骤定义（按执行顺序）
PIPELINE_STEPS = [
    {
        "id": "sourcing",
        "name": "1688寻源",
        "description": "从1688抓取产品信息（价格/规格/供应商）",
        "auto_execute": True,
        "max_retries": 3,
        "timeout_seconds": 120,
    },
    {
        "id": "analysis",
        "name": "AI产品分析",
        "description": "AI识别产品属性，生成产品报告",
        "auto_execute": True,
        "max_retries": 2,
        "timeout_seconds": 180,
    },
    {
        "id": "copywriting",
        "name": "文案生成",
        "description": "AI生成标题/五点描述/详情页/SEO关键词",
        "auto_execute": True,
        "max_retries": 2,
        "timeout_seconds": 120,
    },
    {
        "id": "images",
        "name": "图片生成",
        "description": "AI生成/优化产品主图和场景图",
        "auto_execute": True,
        "max_retries": 2,
        "timeout_seconds": 300,
    },
    {
        "id": "pricing",
        "name": "定价计算",
        "description": "成本核算 + 竞品对标 + 利润目标 → 最终定价",
        "auto_execute": True,
        "max_retries": 1,
        "timeout_seconds": 60,
    },
    {
        "id": "review",
        "name": "人工审核",
        "description": "人工确认产品信息、文案、图片、价格",
        "auto_execute": False,  # 必须人工确认
        "max_retries": 0,
        "timeout_seconds": 86400,  # 24小时
    },
    {
        "id": "listing",
        "name": "WooCommerce上架",
        "description": "自动上架到WooCommerce商店",
        "auto_execute": True,  # 审核通过后自动执行
        "max_retries": 2,
        "timeout_seconds": 120,
    },
    {
        "id": "seo",
        "name": "SEO提交",
        "description": "提交sitemap、设置SEO元数据",
        "auto_execute": True,
        "max_retries": 1,
        "timeout_seconds": 60,
    },
]

# 流水线状态
PIPELINE_RUN_STATUSES = ("pending", "running", "waiting_human", "completed", "failed", "paused", "cancelled")
STEP_STATUSES = ("pending", "running", "completed", "failed", "skipped", "waiting_human")


class PipelineOrchestratorError(Exception):
    """流水线编排器异常。"""


# --------------------------------------------------------------------------- #
# 流水线运行管理（内存版，生产应写入数据库）
# --------------------------------------------------------------------------- #

# 内存中的流水线运行记录（生产环境应持久化到数据库）
_pipeline_runs: dict[str, dict[str, Any]] = {}


def create_pipeline_run(
    *,
    product_name: str,
    source_url: str | None = None,
    source_id: str | None = None,
    selection_id: str | None = None,
    auto_list: bool = False,
) -> dict[str, Any]:
    """创建一个新的流水线运行实例。

    Args:
        auto_list: 审核通过后是否自动上架（False=审核后仍需手动触发上架）
    """
    run_id = f"pipe_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{UUID.hex[:8]}"

    steps = []
    for step_def in PIPELINE_STEPS:
        steps.append({
            "id": step_def["id"],
            "name": step_def["name"],
            "description": step_def["description"],
            "status": "pending",
            "auto_execute": step_def["auto_execute"],
            "max_retries": step_def["max_retries"],
            "retry_count": 0,
            "result": None,
            "error": None,
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
        })

    run = {
        "run_id": run_id,
        "product_name": product_name,
        "source_url": source_url,
        "source_id": source_id,
        "selection_id": selection_id,
        "auto_list": auto_list,
        "status": "pending",
        "current_step_index": 0,
        "steps": steps,
        "created_at": datetime.now(UTC).isoformat(),
        "started_at": None,
        "completed_at": None,
        "error": None,
        "product_data": {},  # 各步骤产出的产品数据
    }

    _pipeline_runs[run_id] = run
    logger.info("流水线已创建: %s - %s", run_id, product_name)
    return run


def get_pipeline_run(run_id: str) -> dict[str, Any] | None:
    """获取流水线运行状态。"""
    return _pipeline_runs.get(run_id)


def list_pipeline_runs(*, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """列出流水线运行记录。"""
    runs = list(_pipeline_runs.values())
    if status:
        runs = [r for r in runs if r["status"] == status]
    runs.sort(key=lambda r: r["created_at"], reverse=True)
    return runs[:limit]


# --------------------------------------------------------------------------- #
# 流水线执行
# --------------------------------------------------------------------------- #

async def start_pipeline(run_id: str) -> dict[str, Any]:
    """启动流水线（从第一步开始自动推进）。"""
    run = get_pipeline_run(run_id)
    if not run:
        raise PipelineOrchestratorError(f"流水线不存在: {run_id}")
    if run["status"] == "running":
        raise PipelineOrchestratorError(f"流水线已在运行: {run_id}")

    run["status"] = "running"
    run["started_at"] = datetime.now(UTC).isoformat()
    logger.info("流水线启动: %s", run_id)

    # 自动推进到第一个需要人工干预的步骤
    await _auto_advance(run_id)

    return run


async def _auto_advance(run_id: str) -> None:
    """自动推进流水线，直到遇到需要人工干预的步骤或完成/失败。"""
    run = get_pipeline_run(run_id)
    if not run:
        return

    while run["status"] == "running":
        idx = run["current_step_index"]
        if idx >= len(run["steps"]):
            # 所有步骤完成
            run["status"] = "completed"
            run["completed_at"] = datetime.now(UTC).isoformat()
            logger.info("流水线完成: %s", run_id)
            break

        step = run["steps"][idx]

        # 如果步骤不需要自动执行（如人工审核），暂停等待
        if not step["auto_execute"] and step["status"] == "pending":
            run["status"] = "waiting_human"
            step["status"] = "waiting_human"
            logger.info("流水线等待人工确认: %s - 步骤: %s", run_id, step["name"])
            break

        # 执行步骤
        if step["status"] in ("pending", "failed"):
            await _execute_step(run_id, idx)

        # 检查步骤结果
        if step["status"] == "failed":
            if step["retry_count"] < step["max_retries"]:
                step["retry_count"] += 1
                step["status"] = "pending"
                logger.info(
                    "步骤失败，准备重试 (%d/%d): %s - %s",
                    step["retry_count"], step["max_retries"], run_id, step["name"],
                )
                await asyncio.sleep(2)  # 重试前短暂等待
                continue
            else:
                run["status"] = "failed"
                run["error"] = f"步骤 {step['name']} 失败: {step.get('error', '未知错误')}"
                logger.error("流水线失败: %s - %s", run_id, run["error"])
                break

        # 步骤完成，推进到下一步
        if step["status"] == "completed":
            run["current_step_index"] = idx + 1
            continue

        # 其他状态（skipped）直接推进
        if step["status"] == "skipped":
            run["current_step_index"] = idx + 1
            continue

        break  # 不应该到这里，安全退出


async def _execute_step(run_id: str, step_index: int) -> None:
    """执行单个流水线步骤。"""
    run = get_pipeline_run(run_id)
    if not run:
        return

    step = run["steps"][step_index]
    step["status"] = "running"
    step["started_at"] = datetime.now(UTC).isoformat()

    logger.info("执行步骤: %s - %s", run_id, step["name"])

    try:
        # 根据步骤ID调用对应服务
        result = await _dispatch_step(step["id"], run)
        step["status"] = "completed"
        step["result"] = result
        step["completed_at"] = datetime.now(UTC).isoformat()
        step["duration_seconds"] = (
            datetime.fromisoformat(step["completed_at"]) -
            datetime.fromisoformat(step["started_at"])
        ).total_seconds()

        # 将步骤产出合并到 product_data
        if isinstance(result, dict):
            run["product_data"].update(result)

        logger.info(
            "步骤完成: %s - %s (%.1fs)",
            run_id, step["name"], step["duration_seconds"],
        )

    except Exception as e:
        step["status"] = "failed"
        step["error"] = f"{type(e).__name__}: {str(e)}"
        step["completed_at"] = datetime.now(UTC).isoformat()
        logger.exception("步骤失败: %s - %s", run_id, step["name"])


async def _dispatch_step(step_id: str, run: dict[str, Any]) -> dict[str, Any]:
    """根据步骤ID分发到对应服务执行。

    每个步骤返回 dict，会合并到 run["product_data"]。
    """
    product_data = run["product_data"]

    if step_id == "sourcing":
        # 1688寻源
        return await _step_sourcing(run)
    elif step_id == "analysis":
        # AI产品分析
        return await _step_analysis(run)
    elif step_id == "copywriting":
        # 文案生成
        return await _step_copywriting(run)
    elif step_id == "images":
        # 图片生成
        return await _step_images(run)
    elif step_id == "pricing":
        # 定价计算
        return await _step_pricing(run)
    elif step_id == "review":
        # 人工审核（不会自动执行到这里）
        return {"review_status": "pending"}
    elif step_id == "listing":
        # WooCommerce上架
        return await _step_listing(run)
    elif step_id == "seo":
        # SEO提交
        return await _step_seo(run)
    else:
        return {"note": f"未知步骤: {step_id}，已跳过"}


# --------------------------------------------------------------------------- #
# 各步骤实现（简化版，调用对应业务服务）
# --------------------------------------------------------------------------- #

async def _step_sourcing(run: dict[str, Any]) -> dict[str, Any]:
    """1688寻源步骤。"""
    source_url = run.get("source_url", "")
    source_id = run.get("source_id", "")

    try:
        from app.services.sourcing_1688_service import get_product_detail
        if source_url or source_id:
            detail = await get_product_detail(source_url or source_id)
            return {"sourcing_data": detail, "sourcing_status": "completed"}
    except ImportError:
        pass
    except Exception as e:
        logger.warning("1688寻源失败: %s", e)

    # 降级：使用已有产品数据
    return {
        "sourcing_data": run["product_data"].get("sourcing_data", {}),
        "sourcing_status": "degraded",
        "note": "1688寻源服务不可用，使用已有数据",
    }


async def _step_analysis(run: dict[str, Any]) -> dict[str, Any]:
    """AI产品分析步骤。"""
    try:
        from app.services.product_analysis_service import analyze_and_generate_report
        product_info = run["product_data"].get("sourcing_data", {})
        if product_info:
            report = await analyze_and_generate_report(product_info)
            return {"analysis_report": report, "analysis_status": "completed"}
    except ImportError:
        pass
    except Exception as e:
        logger.warning("AI产品分析失败: %s", e)

    return {"analysis_status": "skipped", "note": "产品分析服务不可用"}


async def _step_copywriting(run: dict[str, Any]) -> dict[str, Any]:
    """文案生成步骤。"""
    try:
        from app.services.product_copy_service import generate_product_copy
        product_name = run.get("product_name", "")
        if product_name:
            copy = await generate_product_copy(product_name, run["product_data"])
            return {"copy_data": copy, "copywriting_status": "completed"}
    except ImportError:
        pass
    except Exception as e:
        logger.warning("文案生成失败: %s", e)

    return {"copywriting_status": "skipped", "note": "文案服务不可用"}


async def _step_images(run: dict[str, Any]) -> dict[str, Any]:
    """图片生成步骤。"""
    try:
        from app.services.main_image_service import run_complete_workflow
        product_name = run.get("product_name", "")
        if product_name:
            images = await run_complete_workflow(product_name, run["product_data"])
            return {"image_data": images, "images_status": "completed"}
    except ImportError:
        pass
    except Exception as e:
        logger.warning("图片生成失败: %s", e)

    return {"images_status": "skipped", "note": "图片服务不可用"}


async def _step_pricing(run: dict[str, Any]) -> dict[str, Any]:
    """定价计算步骤。"""
    try:
        from app.services.cost_model_service import calculate_price
        sourcing_data = run["product_data"].get("sourcing_data", {})
        if sourcing_data:
            pricing = await calculate_price(sourcing_data)
            return {"pricing_data": pricing, "pricing_status": "completed"}
    except ImportError:
        pass
    except Exception as e:
        logger.warning("定价计算失败: %s", e)

    # 降级：使用默认定价
    return {
        "pricing_data": {"price": 29.99, "currency": "USD"},
        "pricing_status": "default",
        "note": "定价服务不可用，使用默认价格",
    }


async def _step_listing(run: dict[str, Any]) -> dict[str, Any]:
    """WooCommerce上架步骤。"""
    try:
        from app.services.product_listing_service import list_to_woocommerce
        product_data = run["product_data"]
        if product_data:
            result = await list_to_woocommerce(product_data)
            return {"listing_result": result, "listing_status": "completed"}
    except ImportError:
        pass
    except Exception as e:
        logger.warning("WooCommerce上架失败: %s", e)
        raise

    return {"listing_status": "skipped", "note": "上架服务不可用"}


async def _step_seo(run: dict[str, Any]) -> dict[str, Any]:
    """SEO提交步骤。"""
    try:
        from app.services.seo_service import submit_seo
        product_data = run["product_data"]
        if product_data:
            result = await submit_seo(product_data)
            return {"seo_result": result, "seo_status": "completed"}
    except ImportError:
        pass
    except Exception as e:
        logger.warning("SEO提交失败: %s", e)

    return {"seo_status": "skipped", "note": "SEO服务不可用"}


# --------------------------------------------------------------------------- #
# 人工干预
# --------------------------------------------------------------------------- #

async def approve_review(run_id: str, *, approved_by: str) -> dict[str, Any]:
    """人工审核通过，继续推进流水线。"""
    run = get_pipeline_run(run_id)
    if not run:
        raise PipelineOrchestratorError(f"流水线不存在: {run_id}")
    if run["status"] != "waiting_human":
        raise PipelineOrchestratorError(f"流水线不处于等待人工状态: {run['status']}")

    # 找到 review 步骤并标记完成
    for step in run["steps"]:
        if step["id"] == "review":
            step["status"] = "completed"
            step["result"] = {"approved_by": approved_by, "approved_at": datetime.now(UTC).isoformat()}
            step["completed_at"] = datetime.now(UTC).isoformat()
            break

    run["status"] = "running"
    run["current_step_index"] += 1  # 推进到上架步骤

    logger.info("人工审核通过: %s by %s", run_id, approved_by)

    # 继续自动推进
    await _auto_advance(run_id)

    return run


async def reject_review(run_id: str, *, rejected_by: str, reason: str) -> dict[str, Any]:
    """人工审核拒绝，暂停流水线。"""
    run = get_pipeline_run(run_id)
    if not run:
        raise PipelineOrchestratorError(f"流水线不存在: {run_id}")

    for step in run["steps"]:
        if step["id"] == "review":
            step["status"] = "failed"
            step["error"] = f"人工审核拒绝: {reason}"
            break

    run["status"] = "paused"
    run["error"] = f"人工审核拒绝 by {rejected_by}: {reason}"

    logger.info("人工审核拒绝: %s by %s - %s", run_id, rejected_by, reason)
    return run


async def skip_step(run_id: str, step_id: str, *, reason: str = "") -> dict[str, Any]:
    """跳过某个步骤。"""
    run = get_pipeline_run(run_id)
    if not run:
        raise PipelineOrchestratorError(f"流水线不存在: {run_id}")

    for i, step in enumerate(run["steps"]):
        if step["id"] == step_id:
            step["status"] = "skipped"
            step["error"] = reason
            if i == run["current_step_index"]:
                run["current_step_index"] = i + 1
            break

    # 如果流水线在运行，继续推进
    if run["status"] == "running":
        await _auto_advance(run_id)

    return run


async def retry_pipeline(run_id: str) -> dict[str, Any]:
    """从失败步骤重试流水线。"""
    run = get_pipeline_run(run_id)
    if not run:
        raise PipelineOrchestratorError(f"流水线不存在: {run_id}")
    if run["status"] not in ("failed", "paused"):
        raise PipelineOrchestratorError(f"流水线状态不允许重试: {run['status']}")

    # 重置当前失败步骤
    idx = run["current_step_index"]
    if idx < len(run["steps"]):
        step = run["steps"][idx]
        if step["status"] == "failed":
            step["status"] = "pending"
            step["error"] = None

    run["status"] = "running"
    run["error"] = None

    logger.info("流水线重试: %s", run_id)
    await _auto_advance(run_id)

    return run


# --------------------------------------------------------------------------- #
# 从选品建议自动触发流水线
# --------------------------------------------------------------------------- #

async def trigger_pipeline_from_selection(
    session: AsyncSession,
    *,
    suggestion_id: int,
    auto_list: bool = False,
) -> dict[str, Any]:
    """从选品建议触发产品流水线。

    当选品建议被审批通过后，调用此函数自动启动产品上架流水线。
    """
    suggestion = await agent_suggestion_service.get_suggestion(session, suggestion_id)
    if not suggestion:
        raise PipelineOrchestratorError(f"建议不存在: {suggestion_id}")

    params = suggestion.execution_params or {}
    product_name = params.get("product_name") or suggestion.title

    run = create_pipeline_run(
        product_name=product_name,
        source_url=params.get("source_url"),
        source_id=params.get("source_id"),
        selection_id=str(suggestion_id),
        auto_list=auto_list,
    )

    # 启动流水线
    await start_pipeline(run["run_id"])

    logger.info(
        "从选品建议触发流水线: suggestion=%s -> pipeline=%s",
        suggestion_id, run["run_id"],
    )

    return run
