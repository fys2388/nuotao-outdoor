"""产品流水线编排器 — 选品审批通过后自动推进全链路（P2-2）。

自动流程：
选品审批通过 → 1688寻源 → AI分析 → 文案生成 → 图片生成 → 定价计算 → 人工审核 → WooCommerce上架 → SEO提交

所有外部服务调用使用动态导入（importlib + getattr），函数不存在时自动降级。
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import agent_suggestion_service

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


def _safe_call(module_path: str, func_name: str, *args, **kwargs) -> tuple[bool, Any]:
    """安全调用外部服务函数。"""
    try:
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name, None)
        if func is None or not callable(func):
            return False, f"函数 {module_path}.{func_name} 不存在"
        result = func(*args, **kwargs)
        return True, result
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)}"


# 流水线步骤定义
PIPELINE_STEPS = [
    {"id": "sourcing", "name": "1688寻源", "auto_execute": True, "max_retries": 3, "timeout_seconds": 120},
    {"id": "analysis", "name": "AI产品分析", "auto_execute": True, "max_retries": 2, "timeout_seconds": 180},
    {"id": "copywriting", "name": "文案生成", "auto_execute": True, "max_retries": 2, "timeout_seconds": 120},
    {"id": "images", "name": "图片生成", "auto_execute": True, "max_retries": 2, "timeout_seconds": 300},
    {"id": "pricing", "name": "定价计算", "auto_execute": True, "max_retries": 1, "timeout_seconds": 60},
    {"id": "review", "name": "人工审核", "auto_execute": False, "max_retries": 0, "timeout_seconds": 86400},
    {"id": "listing", "name": "WooCommerce上架", "auto_execute": True, "max_retries": 2, "timeout_seconds": 120},
    {"id": "seo", "name": "SEO提交", "auto_execute": True, "max_retries": 1, "timeout_seconds": 60},
]

_pipeline_runs: dict[str, dict[str, Any]] = {}


class PipelineOrchestratorError(Exception):
    pass


def create_pipeline_run(*, product_name: str, source_url: str | None = None,
                         source_id: str | None = None, selection_id: str | None = None,
                         auto_list: bool = False) -> dict[str, Any]:
    """创建流水线运行实例。"""
    run_id = f"pipe_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{UUID.hex[:8]}"
    steps = []
    for sd in PIPELINE_STEPS:
        steps.append({**sd, "status": "pending", "retry_count": 0, "result": None,
                      "error": None, "started_at": None, "completed_at": None, "duration_seconds": None})
    run = {
        "run_id": run_id, "product_name": product_name, "source_url": source_url,
        "source_id": source_id, "selection_id": selection_id, "auto_list": auto_list,
        "status": "pending", "current_step_index": 0, "steps": steps,
        "created_at": datetime.now(UTC).isoformat(), "started_at": None,
        "completed_at": None, "error": None, "product_data": {},
    }
    _pipeline_runs[run_id] = run
    logger.info("流水线已创建: %s - %s", run_id, product_name)
    return run


def get_pipeline_run(run_id: str) -> dict[str, Any] | None:
    return _pipeline_runs.get(run_id)


def list_pipeline_runs(*, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    runs = list(_pipeline_runs.values())
    if status:
        runs = [r for r in runs if r["status"] == status]
    runs.sort(key=lambda r: r["created_at"], reverse=True)
    return runs[:limit]


async def start_pipeline(run_id: str) -> dict[str, Any]:
    """启动流水线。"""
    run = get_pipeline_run(run_id)
    if not run:
        raise PipelineOrchestratorError(f"流水线不存在: {run_id}")
    if run["status"] == "running":
        raise PipelineOrchestratorError(f"流水线已在运行: {run_id}")
    run["status"] = "running"
    run["started_at"] = datetime.now(UTC).isoformat()
    logger.info("流水线启动: %s", run_id)
    await _auto_advance(run_id)
    return run


async def _auto_advance(run_id: str) -> None:
    """自动推进流水线。"""
    run = get_pipeline_run(run_id)
    if not run:
        return
    while run["status"] == "running":
        idx = run["current_step_index"]
        if idx >= len(run["steps"]):
            run["status"] = "completed"
            run["completed_at"] = datetime.now(UTC).isoformat()
            logger.info("流水线完成: %s", run_id)
            break
        step = run["steps"][idx]
        if not step["auto_execute"] and step["status"] == "pending":
            run["status"] = "waiting_human"
            step["status"] = "waiting_human"
            logger.info("流水线等待人工确认: %s - %s", run_id, step["name"])
            break
        if step["status"] in ("pending", "failed"):
            await _execute_step(run_id, idx)
        if step["status"] == "failed":
            if step["retry_count"] < step["max_retries"]:
                step["retry_count"] += 1
                step["status"] = "pending"
                await asyncio.sleep(2)
                continue
            run["status"] = "failed"
            run["error"] = f"步骤 {step['name']} 失败: {step.get('error', '未知错误')}"
            logger.error("流水线失败: %s - %s", run_id, run["error"])
            break
        if step["status"] in ("completed", "skipped"):
            run["current_step_index"] = idx + 1
            continue
        break


async def _execute_step(run_id: str, step_index: int) -> None:
    """执行单个步骤。"""
    run = get_pipeline_run(run_id)
    if not run:
        return
    step = run["steps"][step_index]
    step["status"] = "running"
    step["started_at"] = datetime.now(UTC).isoformat()
    logger.info("执行步骤: %s - %s", run_id, step["name"])
    try:
        result = await _dispatch_step(step["id"], run)
        step["status"] = "completed"
        step["result"] = result
        step["completed_at"] = datetime.now(UTC).isoformat()
        step["duration_seconds"] = (
            datetime.fromisoformat(step["completed_at"]) - datetime.fromisoformat(step["started_at"])
        ).total_seconds()
        if isinstance(result, dict):
            run["product_data"].update(result)
        logger.info("步骤完成: %s - %s (%.1fs)", run_id, step["name"], step["duration_seconds"])
    except Exception as e:
        step["status"] = "failed"
        step["error"] = f"{type(e).__name__}: {str(e)}"
        step["completed_at"] = datetime.now(UTC).isoformat()
        logger.exception("步骤失败: %s - %s", run_id, step["name"])


async def _dispatch_step(step_id: str, run: dict[str, Any]) -> dict[str, Any]:
    """分发步骤到对应服务（动态调用，不存在时降级）。"""
    if step_id == "sourcing":
        return await _step_sourcing(run)
    elif step_id == "analysis":
        return await _step_analysis(run)
    elif step_id == "copywriting":
        return await _step_copywriting(run)
    elif step_id == "images":
        return await _step_images(run)
    elif step_id == "pricing":
        return await _step_pricing(run)
    elif step_id == "review":
        return {"review_status": "pending"}
    elif step_id == "listing":
        return await _step_listing(run)
    elif step_id == "seo":
        return await _step_seo(run)
    return {"note": f"未知步骤: {step_id}"}


async def _step_sourcing(run: dict[str, Any]) -> dict[str, Any]:
    ok, result = _safe_call("app.services.sourcing_1688_service", "get_product_detail",
                             run.get("source_url") or run.get("source_id", ""))
    if ok:
        return {"sourcing_data": result, "sourcing_status": "completed"}
    return {"sourcing_data": run["product_data"].get("sourcing_data", {}),
            "sourcing_status": "degraded", "note": "1688寻源服务待接入"}


async def _step_analysis(run: dict[str, Any]) -> dict[str, Any]:
    ok, result = _safe_call("app.services.product_analysis_service", "analyze_and_generate_report",
                             run["product_data"].get("sourcing_data", {}))
    if ok:
        return {"analysis_report": result, "analysis_status": "completed"}
    return {"analysis_status": "skipped", "note": "产品分析服务待接入"}


async def _step_copywriting(run: dict[str, Any]) -> dict[str, Any]:
    ok, result = _safe_call("app.services.product_copy_service", "generate_product_copy",
                             run.get("product_name", ""), run["product_data"])
    if ok:
        return {"copy_data": result, "copywriting_status": "completed"}
    return {"copywriting_status": "skipped", "note": "文案服务待接入"}


async def _step_images(run: dict[str, Any]) -> dict[str, Any]:
    ok, result = _safe_call("app.services.main_image_service", "run_complete_workflow",
                             run.get("product_name", ""), run["product_data"])
    if ok:
        return {"image_data": result, "images_status": "completed"}
    return {"images_status": "skipped", "note": "图片服务待接入"}


async def _step_pricing(run: dict[str, Any]) -> dict[str, Any]:
    ok, result = _safe_call("app.services.cost_model_service", "calculate_order_cost",
                             run["product_data"].get("sourcing_data", {}))
    if ok:
        return {"pricing_data": result, "pricing_status": "completed"}
    return {"pricing_data": {"price": 29.99, "currency": "USD"},
            "pricing_status": "default", "note": "定价服务待接入，使用默认价格"}


async def _step_listing(run: dict[str, Any]) -> dict[str, Any]:
    ok, result = _safe_call("app.services.product_listing_service", "list_to_woocommerce",
                             run["product_data"])
    if ok:
        return {"listing_result": result, "listing_status": "completed"}
    raise PipelineOrchestratorError("WooCommerce上架服务待接入")


async def _step_seo(run: dict[str, Any]) -> dict[str, Any]:
    ok, result = _safe_call("app.services.seo_service", "generate_sitemap")
    if ok:
        return {"seo_result": result, "seo_status": "completed"}
    return {"seo_status": "skipped", "note": "SEO服务待接入"}


async def approve_review(run_id: str, *, approved_by: str) -> dict[str, Any]:
    """人工审核通过。"""
    run = get_pipeline_run(run_id)
    if not run:
        raise PipelineOrchestratorError(f"流水线不存在: {run_id}")
    if run["status"] != "waiting_human":
        raise PipelineOrchestratorError(f"流水线不处于等待人工状态: {run['status']}")
    for step in run["steps"]:
        if step["id"] == "review":
            step["status"] = "completed"
            step["result"] = {"approved_by": approved_by, "approved_at": datetime.now(UTC).isoformat()}
            step["completed_at"] = datetime.now(UTC).isoformat()
            break
    run["status"] = "running"
    run["current_step_index"] += 1
    logger.info("人工审核通过: %s by %s", run_id, approved_by)
    await _auto_advance(run_id)
    return run


async def reject_review(run_id: str, *, rejected_by: str, reason: str) -> dict[str, Any]:
    """人工审核拒绝。"""
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
    if run["status"] == "running":
        await _auto_advance(run_id)
    return run


async def retry_pipeline(run_id: str) -> dict[str, Any]:
    """从失败步骤重试。"""
    run = get_pipeline_run(run_id)
    if not run:
        raise PipelineOrchestratorError(f"流水线不存在: {run_id}")
    if run["status"] not in ("failed", "paused"):
        raise PipelineOrchestratorError(f"流水线状态不允许重试: {run['status']}")
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


async def trigger_pipeline_from_selection(
    session: AsyncSession, *, suggestion_id: int, auto_list: bool = False
) -> dict[str, Any]:
    """从选品建议触发产品流水线。"""
    suggestion = await agent_suggestion_service.get_suggestion(session, suggestion_id)
    if not suggestion:
        raise PipelineOrchestratorError(f"建议不存在: {suggestion_id}")
    params = suggestion.execution_params or {}
    product_name = params.get("product_name") or suggestion.title
    run = create_pipeline_run(
        product_name=product_name, source_url=params.get("source_url"),
        source_id=params.get("source_id"), selection_id=str(suggestion_id), auto_list=auto_list,
    )
    await start_pipeline(run["run_id"])
    logger.info("从选品建议触发流水线: suggestion=%s -> pipeline=%s", suggestion_id, run["run_id"])
    return run
