"""Convert B2B Agent analysis output into human-reviewed advisory suggestions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_runtime import AgentRegistry, AgentTask
from app.models.agent_suggestion import AgentSuggestion
from app.services import agent_suggestion_service

MAX_SUGGESTIONS_PER_RUN = 20
OPEN_SUGGESTION_STATUSES = ("pending_approval", "approved", "executing")

ACTION_LABELS = {
    "assign_and_qualify": "分配负责人并完成资质确认",
    "prepare_quote": "准备报价草稿",
    "renew_quote": "重新确认报价有效期",
    "follow_up": "跟进客户决策",
    "send_reminder": "发送应收回款提醒",
    "sales_escalation": "升级销售负责人介入",
    "credit_hold_review": "复核信用额度并评估冻结",
    "collections_review": "进入重点催收复核",
    "proceed_to_quote": "复核报价并进入正式报价流程",
    "negotiate_or_escalate": "价格谈判或升级审批",
    "do_not_quote": "暂停报价并补齐阻断项",
}


def _priority(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _dedupe_key(analysis_type: str, entity_id: str, action: str) -> str:
    return f"{analysis_type}:{entity_id}:{action}"


async def _existing_dedupe_keys(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str,
) -> set[str]:
    rows = (
        (
            await session.execute(
                select(AgentSuggestion).where(
                    AgentSuggestion.workspace_id == workspace_id,
                    AgentSuggestion.agent_id == agent_id,
                    AgentSuggestion.status.in_(OPEN_SUGGESTION_STATUSES),
                )
            )
        )
        .scalars()
        .all()
    )
    return {
        str((row.execution_params or {}).get("dedupe_key"))
        for row in rows
        if (row.execution_params or {}).get("dedupe_key")
    }


def _parameters(
    *,
    task: AgentTask,
    dedupe_key: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "advisory_only": True,
        "business_scope": "B2B",
        "b2b_agent_task_id": str(task.id),
        "dedupe_key": dedupe_key,
        "evidence": evidence,
    }


async def _sales_suggestions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    task: AgentTask,
    output: dict[str, Any],
    existing: set[str],
    limit: int,
) -> list[AgentSuggestion]:
    suggestions: list[AgentSuggestion] = []
    for item in output.get("opportunities", []):
        if len(suggestions) >= limit:
            break
        action = str(item.get("recommended_action") or "monitor")
        if action == "monitor":
            continue
        entity_id = str(item.get("rfq_id"))
        dedupe_key = _dedupe_key("b2b_sales_pipeline", entity_id, action)
        if dedupe_key in existing:
            continue
        action_label = ACTION_LABELS.get(action, action)
        suggestion = await agent_suggestion_service.create_suggestion(
            session,
            workspace_id=workspace_id,
            agent_id="b2b_sales_agent",
            suggestion_type="b2b_sales_follow_up",
            title=f"RFQ {item.get('rfq_number')}：{action_label}",
            description=(
                f"{item.get('reason')}。目标金额 "
                f"{item.get('currency')} {item.get('target_value')}，"
                f"优先级评分 {item.get('priority_score')}。"
            ),
            expected_impact=f"降低询盘停滞风险，目标金额 {item.get('target_value')}",
            priority=_priority(int(item.get("priority_score") or 0)),
            risk_level="high" if "SLA_AT_RISK" in item.get("risk_flags", []) else "medium",
            execution_action="manual_review",
            execution_params=_parameters(
                task=task,
                dedupe_key=dedupe_key,
                evidence={
                    "analysis_type": "b2b_sales_pipeline",
                    "as_of": output.get("as_of"),
                    "record": item,
                },
            ),
            source="b2b_agent",
            auto_approve=False,
            commit=False,
        )
        suggestions.append(suggestion)
        existing.add(dedupe_key)
    return suggestions


async def _quote_suggestion(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    task: AgentTask,
    output: dict[str, Any],
    existing: set[str],
) -> list[AgentSuggestion]:
    action = str(output.get("recommended_action") or "do_not_quote")
    entity_id = str(output.get("rfq_id"))
    dedupe_key = _dedupe_key("b2b_quote_recommendation", entity_id, action)
    if dedupe_key in existing:
        return []
    blockers = [str(item) for item in output.get("blockers", [])]
    summary = output.get("summary") or {}
    description_parts = [
        (
            f"RFQ {output.get('rfq_number')} 的报价建议为："
            f"{ACTION_LABELS.get(action, action)}。"
        ),
        (
            f"已发布价收入 {summary.get('published_revenue')} "
            f"{summary.get('currency')}，预计毛利 "
            f"{summary.get('overall_margin_percent')}%。"
        ),
    ]
    if blockers:
        description_parts.append("阻断项：" + "；".join(blockers))
    suggestion = await agent_suggestion_service.create_suggestion(
        session,
        workspace_id=workspace_id,
        agent_id="b2b_quotation_agent",
        suggestion_type="b2b_quote_recommendation",
        title=f"RFQ {output.get('rfq_number')}：{ACTION_LABELS.get(action, action)}",
        description=" ".join(description_parts),
        expected_impact=(
            f"目标价差额 {summary.get('target_gap')}，"
            f"建议有效期至 {summary.get('suggested_valid_until')}"
        ),
        priority="high" if blockers or action != "proceed_to_quote" else "medium",
        risk_level="high",
        execution_action="manual_review",
        execution_params=_parameters(
            task=task,
            dedupe_key=dedupe_key,
            evidence={
                "analysis_type": "b2b_quote_recommendation",
                "rfq_id": output.get("rfq_id"),
                "rfq_number": output.get("rfq_number"),
                "customer": output.get("customer"),
                "summary": summary,
                "lines": output.get("lines", []),
                "blockers": blockers,
                "confidence": output.get("confidence"),
            },
        ),
        source="b2b_agent",
        auto_approve=False,
        commit=False,
    )
    existing.add(dedupe_key)
    return [suggestion]


async def _collection_suggestions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    task: AgentTask,
    output: dict[str, Any],
    existing: set[str],
    limit: int,
) -> list[AgentSuggestion]:
    suggestions: list[AgentSuggestion] = []
    for item in output.get("priorities", []):
        if len(suggestions) >= limit:
            break
        action = str(item.get("recommended_action") or "monitor")
        if action == "monitor":
            continue
        entity_id = str(item.get("invoice_id"))
        dedupe_key = _dedupe_key("b2b_collections", entity_id, action)
        if dedupe_key in existing:
            continue
        risk_flags = [str(flag) for flag in item.get("risk_flags", [])]
        action_label = ACTION_LABELS.get(action, action)
        suggestion = await agent_suggestion_service.create_suggestion(
            session,
            workspace_id=workspace_id,
            agent_id="b2b_collection_agent",
            suggestion_type="b2b_collection_action",
            title=f"发票 {item.get('invoice_number')}：{action_label}",
            description=(
                f"客户 {item.get('company_name') or item.get('agent_id')} "
                f"应收余额 {item.get('currency')} {item.get('balance_due')}，"
                f"账龄 {item.get('age_days')} 天（{item.get('aging_bucket')}）。"
            ),
            expected_impact=f"降低逾期应收风险，回收目标 {item.get('balance_due')}",
            priority=_priority(int(item.get("priority_score") or 0)),
            risk_level=(
                "high"
                if action in {"credit_hold_review", "collections_review"}
                or "CREDIT_LIMIT_EXCEEDED" in risk_flags
                else "medium"
            ),
            execution_action="manual_review",
            execution_params=_parameters(
                task=task,
                dedupe_key=dedupe_key,
                evidence={
                    "analysis_type": "b2b_collections",
                    "as_of": output.get("as_of"),
                    "record": item,
                },
            ),
            source="b2b_agent",
            auto_approve=False,
            commit=False,
        )
        suggestions.append(suggestion)
        existing.add(dedupe_key)
    return suggestions


async def create_advisory_suggestions(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent: AgentRegistry,
    task: AgentTask,
    output: dict[str, Any],
) -> tuple[list[AgentSuggestion], int]:
    """Create deduplicated, human-only advisory suggestions for one B2B run."""
    existing = await _existing_dedupe_keys(
        session,
        workspace_id=workspace_id,
        agent_id=agent.agent_id,
    )
    analysis_type = output.get("analysis_type")
    if analysis_type == "b2b_sales_pipeline":
        actionable_count = sum(
            1
            for item in output.get("opportunities", [])
            if item.get("recommended_action") not in (None, "monitor")
        )
        suggestions = await _sales_suggestions(
            session,
            workspace_id=workspace_id,
            task=task,
            output=output,
            existing=existing,
            limit=MAX_SUGGESTIONS_PER_RUN,
        )
    elif analysis_type == "b2b_quote_recommendation":
        actionable_count = 1
        suggestions = await _quote_suggestion(
            session,
            workspace_id=workspace_id,
            task=task,
            output=output,
            existing=existing,
        )
    elif analysis_type == "b2b_collections":
        actionable_count = sum(
            1
            for item in output.get("priorities", [])
            if item.get("recommended_action") not in (None, "monitor")
        )
        suggestions = await _collection_suggestions(
            session,
            workspace_id=workspace_id,
            task=task,
            output=output,
            existing=existing,
            limit=MAX_SUGGESTIONS_PER_RUN,
        )
    else:
        return [], 0

    return suggestions, max(0, actionable_count - MAX_SUGGESTIONS_PER_RUN)
