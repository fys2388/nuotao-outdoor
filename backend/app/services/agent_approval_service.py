"""Agent 自动审批服务 — 多 Agent 互审机制。

工作流程（替代飞书人工审批）：
1. AI Agent 创建建议 → 不再推送飞书
2. 根据建议类型自动分发给「对应审核 Agent」（生成 Agent ≠ 审核 Agent，形成制衡）
3. 审核 Agent 通过 LLM 判断建议是否合理 → 自动批准/拒绝
4. 低风险建议批准后自动执行；中高风险进入 approved 状态等待执行调度
5. 全流程审计落库（ai_agent_runs + agent_suggestions.approved_by）

配置：
- AGENT_AUTO_APPROVAL_ENABLED=true  （默认开启，关闭则回退到 pending_approval 等待人工）
- AGENT_APPROVAL_LLM_TASK_TYPE=agent_approval  （LLM Gateway 路由任务类型）
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AiAgentRun
from app.models.agent_suggestion import AgentSuggestion
from app.services import event_service, llm_gateway
from app.services.llm_gateway import LLMError, LLMRequest, parse_json_content

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# 开关：Agent 自动审批是否启用
AUTO_APPROVAL_ENABLED = os.getenv("AGENT_AUTO_APPROVAL_ENABLED", "true").lower() == "true"

# 审核 LLM 温度（低温度 = 更保守稳定的审批判断）
APPROVAL_TEMPERATURE = float(os.getenv("AGENT_APPROVAL_TEMPERATURE", "0.2"))

# 审核置信度阈值：低于此值时自动拒绝并标记需人工复核
CONFIDENCE_THRESHOLD = float(os.getenv("AGENT_APPROVAL_CONFIDENCE_THRESHOLD", "0.6"))

# --------------------------------------------------------------------------- #
# 建议类型 → 审核 Agent 映射（生成 Agent ≠ 审核 Agent，形成多 Agent 制衡）
# --------------------------------------------------------------------------- #

# 格式: suggestion_type -> (reviewer_agent_id, reviewer_agent_name)
SUGGESTION_TYPE_REVIEWER_MAP: dict[str, tuple[str, str]] = {
    # 产品类建议 → 商业分析审核（从商业可行性角度审核产品决策）
    "product_optimization": ("business_analyst", "Business Analyst"),
    "pricing_adjustment": ("business_analyst", "Business Analyst"),
    # 营销类建议 → 产品分析审核（从产品定位和品牌一致性角度审核营销）
    "marketing_optimization": ("product_analyst", "Product Analyst"),
    "listing_optimization": ("product_analyst", "Product Analyst"),
    # 库存补货 → 产品分析审核（审核是否真的需要补货，避免积压）
    "inventory_restock": ("product_analyst", "Product Analyst"),
    # 客户运营 → 商业分析审核（从 ROI 和品牌影响角度审核客户运营）
    "customer_operation": ("business_analyst", "Business Analyst"),
    # 供应链 → 商业分析审核（从成本和风险角度审核供应链决策）
    "supply_chain": ("business_analyst", "Business Analyst"),
    # 商业洞察 → 产品分析审核（从产品执行可行性角度审核商业洞察）
    "business_insight": ("product_analyst", "Product Analyst"),
    # 其他 → 商业分析兜底
    "other": ("business_analyst", "Business Analyst"),
}

# 审核 Agent 的职责描述（用于构建审核 prompt）
REVIEWER_ROLE_DESCRIPTIONS: dict[str, str] = {
    "business_analyst": (
        "你是 Nuotao AI OS 的商业分析师（Business Analyst）。"
        "你的职责是从商业可行性、成本收益、风险控制和品牌战略一致性的角度，"
        "审核其他 AI Agent 提出的运营建议。你关注：这个建议是否符合商业逻辑？"
        "成本是否可控？是否有不可接受的风险？是否与 Nuotao 的品牌定位和战略目标一致？"
    ),
    "product_analyst": (
        "你是 Nuotao AI OS 的产品分析师（Product Analyst）。"
        "你的职责是从产品定位、用户价值、选品逻辑和品牌一致性的角度，"
        "审核其他 AI Agent 提出的运营建议。你关注：这个建议是否符合 Nuotao 的产品战略？"
        "是否对用户有真实价值？是否会削弱品牌聚焦？是否与现有产品组合协调？"
    ),
}


def get_reviewer_for_suggestion(suggestion_type: str, source_agent_id: str) -> tuple[str, str]:
    """根据建议类型获取审核 Agent（确保审核 Agent ≠ 生成 Agent）。

    如果映射的审核 Agent 恰好是生成 Agent（异常情况），则降级到 business_analyst。
    """
    reviewer_id, reviewer_name = SUGGESTION_TYPE_REVIEWER_MAP.get(
        suggestion_type, ("business_analyst", "Business Analyst")
    )
    # 制衡原则：审核 Agent 不能是生成 Agent 本身
    if reviewer_id == source_agent_id:
        logger.warning(
            "审核 Agent(%s) 与生成 Agent(%s) 相同，降级到 business_analyst",
            reviewer_id, source_agent_id,
        )
        reviewer_id, reviewer_name = "business_analyst", "Business Analyst"
    return reviewer_id, reviewer_name


# --------------------------------------------------------------------------- #
# 审核 Prompt 构建
# --------------------------------------------------------------------------- #

def _build_approval_prompt(
    *,
    suggestion: AgentSuggestion,
    reviewer_id: str,
    reviewer_name: str,
) -> tuple[str, str]:
    """构建审核 Agent 的 system prompt 和 user prompt。

    Returns:
        (system_prompt, user_prompt)
    """
    role_desc = REVIEWER_ROLE_DESCRIPTIONS.get(reviewer_id, REVIEWER_ROLE_DESCRIPTIONS["business_analyst"])

    system_prompt = (
        f"{role_desc}\n\n"
        "你正在执行「多 Agent 互审」职责：另一个 AI Agent 提出了一条运营建议，"
        "你需要独立判断这条建议是否应该被批准执行。\n\n"
        "审核原则：\n"
        "1. 建议必须有明确的商业逻辑或用户价值支撑\n"
        "2. 成本和风险必须可控，不能有不可接受的负面影响\n"
        "3. 必须符合 Nuotao 的品牌定位（专业户外装备品牌，Value not cheap）\n"
        "4. 不能与现有业务战略冲突\n"
        "5. 数据不足或逻辑不清时，倾向于拒绝而非盲目批准\n\n"
        "输出格式：必须返回严格的 JSON 对象，包含以下字段：\n"
        "{\n"
        '  "decision": "approve" | "reject",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "reason": "审核理由（简明扼要，说明批准或拒绝的核心原因）",\n'
        '  "risk_assessment": "风险评估（低/中/高 + 简要说明）",\n'
        '  "suggested_modification": "如果拒绝，建议如何修改（可选）"\n'
        "}\n"
        "只返回 JSON，不要返回其他任何文字。"
    )

    # 构建建议上下文
    execution_params_str = ""
    if suggestion.execution_params:
        try:
            execution_params_str = json.dumps(suggestion.execution_params, ensure_ascii=False, indent=2)
        except Exception:
            execution_params_str = str(suggestion.execution_params)

    user_prompt = (
        "请审核以下 AI Agent 建议：\n\n"
        f"【建议 ID】{suggestion.id}\n"
        f"【建议类型】{suggestion.suggestion_type}\n"
        f"【建议标题】{suggestion.title}\n"
        f"【生成 Agent】{suggestion.agent_id}\n"
        f"【风险等级】{suggestion.risk_level}\n"
        f"【优先级】{suggestion.priority}\n"
        f"【建议内容】\n{suggestion.description}\n"
        f"【执行参数】\n{execution_params_str or '（无）'}\n"
        f"【预期影响】\n{suggestion.expected_impact or '（未提供）'}\n\n"
        "请独立判断这条建议是否应该被批准执行。严格按照要求的 JSON 格式返回。"
    )

    return system_prompt, user_prompt


# --------------------------------------------------------------------------- #
# 核心：自动审批
# --------------------------------------------------------------------------- #

async def auto_approve_suggestion(
    session: AsyncSession,
    suggestion: AgentSuggestion,
    *,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """对一条建议执行 Agent 自动审批。

    流程：
    1. 根据建议类型确定审核 Agent
    2. 调用 LLM 让审核 Agent 判断建议是否合理
    3. 根据 LLM 输出自动批准或拒绝
    4. 低风险批准后自动触发执行
    5. 全流程审计落库

    Returns:
        审批结果 dict，包含 decision, confidence, reason, reviewer, auto_executed 等
    """
    if not AUTO_APPROVAL_ENABLED:
        logger.info("Agent 自动审批已禁用，建议 %s 保持 pending_approval", suggestion.id)
        return {"decision": "skipped", "reason": "auto_approval_disabled"}

    # 1. 确定审核 Agent
    reviewer_id, reviewer_name = get_reviewer_for_suggestion(
        suggestion.suggestion_type, suggestion.agent_id
    )
    logger.info(
        "建议 %s 自动审批：生成 Agent=%s → 审核 Agent=%s",
        suggestion.id, suggestion.agent_id, reviewer_id,
    )

    # 2. 构建审核 prompt
    system_prompt, user_prompt = _build_approval_prompt(
        suggestion=suggestion,
        reviewer_id=reviewer_id,
        reviewer_name=reviewer_name,
    )

    # 3. 调用 LLM
    request = LLMRequest(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        task_type="agent_approval",
        response_format="json_object",
        temperature=APPROVAL_TEMPERATURE,
    )

    approval_start = datetime.now(UTC)
    try:
        response = await llm_gateway.complete(request, trace_id=trace_id)
    except LLMError as exc:
        error_msg = f"审核 LLM 调用失败: {exc}"
        logger.error("建议 %s 自动审批失败: %s", suggestion.id, error_msg)
        # LLM 失败时保守处理：保持 pending_approval，不自动批准也不拒绝
        await _persist_approval_audit(
            session, suggestion=suggestion, reviewer_id=reviewer_id,
            reviewer_name=reviewer_name, decision="error",
            confidence=0.0, reason=error_msg, risk_assessment="unknown",
            latency_ms=int((datetime.now(UTC) - approval_start).total_seconds() * 1000),
            tokens={}, cost=0, model="unknown", provider="unknown",
            trace_id=trace_id,
        )
        return {"decision": "error", "reason": error_msg, "reviewer": reviewer_id}

    # 4. 解析 LLM 输出
    try:
        parsed = parse_json_content(response.content)
        decision = str(parsed.get("decision", "reject")).lower().strip()
        confidence = float(parsed.get("confidence", 0.0))
        reason = str(parsed.get("reason", ""))[:2000]
        risk_assessment = str(parsed.get("risk_assessment", ""))[:500]
        suggested_modification = str(parsed.get("suggested_modification", ""))[:1000]
    except (LLMError, ValueError, TypeError) as exc:
        error_msg = f"审核输出解析失败: {exc}"
        logger.error("建议 %s 自动审批解析失败: %s", suggestion.id, error_msg)
        await _persist_approval_audit(
            session, suggestion=suggestion, reviewer_id=reviewer_id,
            reviewer_name=reviewer_name, decision="error",
            confidence=0.0, reason=error_msg, risk_assessment="unknown",
            latency_ms=int((datetime.now(UTC) - approval_start).total_seconds() * 1000),
            tokens=response.tokens, cost=float(response.cost), model=response.model,
            provider=response.provider, trace_id=trace_id,
        )
        return {"decision": "error", "reason": error_msg, "reviewer": reviewer_id}

    # 5. 置信度检查：低于阈值时拒绝并标记需人工复核
    if confidence < CONFIDENCE_THRESHOLD:
        decision = "reject"
        reason = f"[低置信度自动拒绝] 审核置信度 {confidence:.2f} 低于阈值 {CONFIDENCE_THRESHOLD:.2f}。原理由：{reason}"
        logger.info("建议 %s 因低置信度(%.2f)自动拒绝", suggestion.id, confidence)

    # 6. 执行审批决策
    auto_executed = False
    if decision == "approve":
        suggestion.status = "approved"
        suggestion.approved_by = f"agent:{reviewer_id}"
        suggestion.approved_at = datetime.now(UTC)
        suggestion.approval_comment = f"[Agent自动审批] {reviewer_name}: {reason}"
        await session.flush()

        logger.info(
            "建议 %s 已由 %s 自动批准 (confidence=%.2f)",
            suggestion.id, reviewer_id, confidence,
        )

        # 低风险建议批准后自动执行
        if suggestion.risk_level == "low":
            try:
                from app.services.execution_router import execute_suggestion
                await execute_suggestion(session, suggestion)
                auto_executed = True
                logger.info("建议 %s 低风险自动执行完成", suggestion.id)
            except Exception as exc:
                logger.error("建议 %s 自动执行失败: %s", suggestion.id, exc)
                # 执行失败不回滚审批状态，保持 approved，execution_router 会标记 failed
    else:
        # reject
        suggestion.status = "rejected"
        suggestion.approved_by = f"agent:{reviewer_id}"
        suggestion.approved_at = datetime.now(UTC)
        rejection_reason = reason
        if suggested_modification:
            rejection_reason = f"{reason} | 修改建议: {suggested_modification}"
        suggestion.approval_comment = f"[Agent自动审批拒绝] {reviewer_name}: {rejection_reason}"
        await session.flush()

        logger.info(
            "建议 %s 已由 %s 自动拒绝 (confidence=%.2f): %s",
            suggestion.id, reviewer_id, confidence, reason[:200],
        )

    await session.commit()

    # 7. 审计落库
    latency_ms = int((datetime.now(UTC) - approval_start).total_seconds() * 1000)
    await _persist_approval_audit(
        session, suggestion=suggestion, reviewer_id=reviewer_id,
        reviewer_name=reviewer_name, decision=decision,
        confidence=confidence, reason=reason, risk_assessment=risk_assessment,
        latency_ms=latency_ms, tokens=response.tokens,
        cost=float(response.cost), model=response.model,
        provider=response.provider, trace_id=trace_id,
    )

    # 8. 事件通知
    await event_service.create_event(
        session,
        workspace_id=suggestion.workspace_id,
        event_type="agent_suggestion.auto_approved" if decision == "approve" else "agent_suggestion.auto_rejected",
        entity_type="agent_suggestion",
        entity_id=str(suggestion.id),
        payload={
            "suggestion_id": suggestion.id,
            "decision": decision,
            "confidence": confidence,
            "reviewer": reviewer_id,
            "source_agent": suggestion.agent_id,
            "auto_executed": auto_executed,
        },
        trace_id=trace_id,
    )

    return {
        "decision": decision,
        "confidence": confidence,
        "reason": reason,
        "risk_assessment": risk_assessment,
        "reviewer": reviewer_id,
        "reviewer_name": reviewer_name,
        "source_agent": suggestion.agent_id,
        "auto_executed": auto_executed,
        "suggestion_id": suggestion.id,
        "latency_ms": latency_ms,
        "model": response.model,
        "cost": float(response.cost),
    }


# --------------------------------------------------------------------------- #
# 审计落库
# --------------------------------------------------------------------------- #

async def _persist_approval_audit(
    session: AsyncSession,
    *,
    suggestion: AgentSuggestion,
    reviewer_id: str,
    reviewer_name: str,
    decision: str,
    confidence: float,
    reason: str,
    risk_assessment: str,
    latency_ms: int,
    tokens: dict[str, int],
    cost: float,
    model: str,
    provider: str,
    trace_id: str | None,
) -> None:
    """将 Agent 自动审批的完整过程落库到 ai_agent_runs，保证可审计。"""
    agent_run = AiAgentRun(
        workspace_id=suggestion.workspace_id,
        agent=reviewer_id,
        trigger="auto_approval:agent_suggestion",
        input={
            "suggestion_id": suggestion.id,
            "suggestion_type": suggestion.suggestion_type,
            "source_agent": suggestion.agent_id,
            "title": suggestion.title,
            "risk_level": suggestion.risk_level,
        },
        plan={"steps": ["build_approval_prompt", "llm_gateway", "parse_output", "apply_decision"]},
        tool_calls=[
            {
                "tool": "llm_gateway.complete",
                "provider": provider,
                "model": model,
                "tokens": tokens,
                "latency_ms": latency_ms,
                "task_type": "agent_approval",
            }
        ],
        output={
            "decision": decision,
            "confidence": confidence,
            "reason": reason,
            "risk_assessment": risk_assessment,
            "reviewer": reviewer_id,
            "reviewer_name": reviewer_name,
            "suggestion_status": suggestion.status,
        },
        approval={"required": False, "status": "not_required", "note": "Agent auto-approval itself"},
        cost=cost,
        status="completed" if decision in ("approve", "reject") else "failed",
        trace_id=trace_id,
        completed_at=datetime.now(UTC),
    )
    session.add(agent_run)
    await session.flush()
