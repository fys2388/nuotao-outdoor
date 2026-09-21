"""审批队列告警 —— 中高风险建议积压或超 SLA 时推送飞书。

背景
----
AGENT_AUTO_APPROVAL_ENABLED 门禁上线后，medium/high risk 建议不再被 LLM 自动
批准，全部退回 pending_approval 等人工确认（见 AGENTS.md 3.1「Agent 是提议者
不是执行者」）。prod 上已有 284 条积压。

问题在于：门禁只保证"不自动执行"，不保证"有人会看"。如果没人去审批页，这些
建议会无限期堆积，人审环节形同虚设——比门禁缺失更隐蔽，因为审计日志看起来
一切正常（没有人批准，也没有人执行）。

本任务负责让队列被看见：
- 按风险等级统计待审数量
- 计算最老一条的等待时长，对照 SLA
- 超 SLA 或出现中高风险积压时推送飞书卡片
- 同一签名按节流窗口限频，避免每轮调度刷屏

SLA 与节流窗口均为环境变量，不写死在业务逻辑里（AGENTS.md 1.2 第 5 条）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import create_redis_client
from app.models.agent_suggestion import AgentSuggestion

logger = logging.getLogger(__name__)

# 各风险等级的审阅 SLA（小时）。超时即推送提醒。
APPROVAL_SLA_HOURS: dict[str, float] = {
    "high": float(os.getenv("APPROVAL_SLA_HIGH_HOURS", "4")),
    "medium": float(os.getenv("APPROVAL_SLA_MEDIUM_HOURS", "24")),
    "low": float(os.getenv("APPROVAL_SLA_LOW_HOURS", "72")),
}

# 同一告警签名的最短推送间隔（秒）。默认 1 小时。
ALERT_THROTTLE_SECONDS = int(os.getenv("APPROVAL_ALERT_THROTTLE_SECONDS", "3600"))

# 卡片上最多展示几条示例
MAX_EXAMPLES = 5

REDIS_KEY = "nuotao:approval_queue_alert:last_signature"
REDIS_TTL = 7 * 24 * 3600


async def _get_last_signature() -> tuple[str, float]:
    """读取上次推送的签名和时间戳（Redis，best-effort）。"""
    try:
        r = create_redis_client()
        try:
            raw = await r.get(REDIS_KEY)
            if not raw:
                return "", 0.0
            data = json.loads(raw)
            return data.get("signature", ""), float(data.get("sent_at", 0))
        finally:
            await r.aclose()
    except Exception:
        logger.exception("读取告警节流状态失败，视为从未推送")
        return "", 0.0


async def _set_last_signature(signature: str) -> None:
    try:
        r = create_redis_client()
        try:
            await r.set(
                REDIS_KEY,
                json.dumps({"signature": signature, "sent_at": time.time()}),
                ex=REDIS_TTL,
            )
        finally:
            await r.aclose()
    except Exception:
        logger.exception("写入告警节流状态失败（不影响本轮推送）")


async def _build_queue_stats(session: AsyncSession, workspace_id: UUID) -> dict[str, Any]:
    """统计待审队列，返回分组数量、最老等待时长和超 SLA 清单。"""
    base = select(AgentSuggestion).where(
        AgentSuggestion.workspace_id == workspace_id,
        AgentSuggestion.status == "pending_approval",
    )

    total = (await session.execute(select(func.count()).select_from(base))).scalar() or 0
    if total == 0:
        return {
            "total": 0,
            "by_risk": {},
            "oldest_hours": 0.0,
            "sla_breaches": [],
            "examples": [],
        }

    rows = (
        await session.execute(base.order_by(AgentSuggestion.created_at.asc()))
    ).scalars().all()

    now = datetime.now(timezone.utc)
    by_risk: dict[str, int] = {}
    for row in rows:
        by_risk[row.risk_level] = by_risk.get(row.risk_level, 0) + 1

    oldest = rows[0]
    created = oldest.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    oldest_hours = round((now - created).total_seconds() / 3600, 1)

    sla_breaches = []
    for row in rows:
        created_at = row.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age_hours = (now - created_at).total_seconds() / 3600
        limit = APPROVAL_SLA_HOURS.get(row.risk_level)
        if limit and age_hours > limit:
            sla_breaches.append({
                "id": row.id,
                "risk_level": row.risk_level,
                "age_hours": round(age_hours, 1),
                "sla_hours": limit,
                "title": row.title,
                "agent_id": row.agent_id,
            })
    sla_breaches.sort(key=lambda x: -x["age_hours"])

    examples = [
        {
            "id": row.id,
            "title": (row.title or "")[:60],
            "risk_level": row.risk_level,
            "age_hours": round(
                (now - (
                    row.created_at.replace(tzinfo=timezone.utc)
                    if row.created_at.tzinfo is None else row.created_at
                )).total_seconds() / 3600, 1
            ),
        }
        for row in rows[:MAX_EXAMPLES]
    ]

    return {
        "total": total,
        "by_risk": by_risk,
        "oldest_hours": oldest_hours,
        "sla_breaches": sla_breaches,
        "examples": examples,
    }


def _build_card(stats: dict[str, Any]) -> dict[str, Any]:
    """构建飞书交互式卡片。"""
    from app.services.feishu_approval_service import RISK_COLORS

    by_risk = stats["by_risk"]
    breaches = stats["sla_breaches"]
    color = "red" if breaches else "orange"

    risk_line = " / ".join(
        f"{lvl} {count}" for lvl, count in sorted(by_risk.items())
    ) or "无"

    breach_lines = []
    for b in breaches[:3]:
        breach_lines.append(
            f"- #{b['id']} **{b['risk_level']}** 已等待 {b['age_hours']}h"
            f"（SLA {b['sla_hours']}h）"
        )
    example_lines = [
        f"- #{e['id']} [{e['risk_level']}] {e['title']}（{e['age_hours']}h）"
        for e in stats["examples"]
    ]

    title = f"🔔 待审建议积压 {stats['total']} 条"
    if breaches:
        title = f"🚨 待审建议超 SLA {len(breaches)} 条（总积压 {stats['total']} 条）"

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**风险分布**：{risk_line}\n"
                    f"**最老一条**：已等待 {stats['oldest_hours']}h"
                ),
            },
        },
    ]
    if breach_lines:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**超 SLA 明细**\n" + "\n".join(breach_lines),
            },
        })
    if example_lines:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**待审示例**\n" + "\n".join(example_lines),
            },
        })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": color,
        },
        "elements": elements,
    }


async def run_approval_queue_alert(session: AsyncSession) -> dict[str, Any]:
    """扫描待审队列并在需要时推送飞书提醒。

    Returns:
        本轮结果摘要（不推送时 notified=False）。
    """
    from app.core.workspace import DEFAULT_WORKSPACE_ID
    from app.services.feishu_approval_service import _is_within_push_hours, _send_card_via_app_api

    stats = await _build_queue_stats(session, DEFAULT_WORKSPACE_ID)

    total = stats["total"]
    medium_high = sum(
        v for k, v in stats["by_risk"].items() if k in ("medium", "high")
    )
    breaches = stats["sla_breaches"]

    # 只有中高风险积压或超 SLA 才值得打断人。纯 low 风险不用提醒。
    should_notify = bool(breaches) or medium_high > 0
    if not should_notify:
        return {
            "notified": False,
            "reason": "no_medium_high_backlog",
            "total": total,
            "by_risk": stats["by_risk"],
        }

    if not _is_within_push_hours():
        logger.info("不在推送时段，跳过审批队列告警（total=%d）", total)
        return {
            "notified": False,
            "reason": "outside_push_hours",
            "total": total,
            "by_risk": stats["by_risk"],
        }

    # 节流签名：风险分布 + 超 SLA 的 id 集合。同一签名在窗口内只推一次。
    signature = "|".join([
        ",".join(f"{k}:{v}" for k, v in sorted(stats["by_risk"].items())),
        ",".join(str(b["id"]) for b in breaches[:10]),
    ])
    last_sig, last_sent = await _get_last_signature()
    elapsed = time.time() - last_sent
    if signature == last_sig and elapsed < ALERT_THROTTLE_SECONDS:
        logger.info(
            "审批队列告警节流中: 签名未变，距上次 %ds < %ds",
            int(elapsed), ALERT_THROTTLE_SECONDS,
        )
        return {
            "notified": False,
            "reason": "throttled",
            "total": total,
            "by_risk": stats["by_risk"],
            "sla_breaches": len(breaches),
        }

    card = _build_card(stats)
    result = await asyncio.to_thread(_send_card_via_app_api, card)

    if result.get("success"):
        await _set_last_signature(signature)
        logger.info(
            "审批队列告警已推送: total=%d medium_high=%d breaches=%d",
            total, medium_high, len(breaches),
        )
    else:
        logger.warning("审批队列告警推送失败: %s", result.get("error"))

    return {
        "notified": bool(result.get("success")),
        "total": total,
        "medium_high": medium_high,
        "sla_breaches": len(breaches),
        "by_risk": stats["by_risk"],
        "channel": result.get("channel"),
        "error": result.get("error"),
    }
