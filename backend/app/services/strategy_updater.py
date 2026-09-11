"""策略更新器 — A/B测试结论自动更新营销策略，形成数据驱动闭环。

流程：
1. A/B测试达到统计显著性 → 自动生成结论
2. 结论经审批（高风险）或自动执行（低风险）
3. 更新营销策略配置（写入 strategy_versions 表，可回滚）
4. 结果通知到飞书

策略类型：
- pricing: 定价策略（价格区间/折扣规则）
- listing: 上架策略（标题模板/关键词策略/图片风格）
- marketing: 营销策略（受众定向/出价策略/素材风格）
- inventory: 库存策略（安全库存/补货周期/采购批量）
- content: 内容策略（文案风格/SEO策略/内容频率）
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StrategyVersion
from app.services import agent_suggestion_service

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# 策略风险等级（决定是否需要人审）
STRATEGY_RISK = {
    "pricing": "high",        # 改价必须人审
    "inventory": "medium",     # 库存策略需人审
    "marketing": "medium",     # 营销策略建议人审
    "listing": "low",          # 上架优化可自动执行
    "content": "low",          # 内容优化可自动执行
}


# --------------------------------------------------------------------------- #
# A/B 测试结论评估
# --------------------------------------------------------------------------- #

def evaluate_ab_test_result(
    *,
    variant_a_metrics: dict[str, float],
    variant_b_metrics: dict[str, float],
    sample_size_a: int,
    sample_size_b: int,
    primary_metric: str = "conversion_rate",
    confidence_threshold: float = 0.95,
    min_sample_size: int = 50,
) -> dict[str, Any]:
    """评估 A/B 测试结果，判断是否达到统计显著性。

    使用简化的 Z 检验（实际生产应使用更严谨的统计方法）。

    Returns:
        {
            "significant": bool,
            "winner": "A" | "B" | "none",
            "confidence": float,
            "relative_lift": float,
            "recommendation": str,
            "details": {...}
        }
    """
    import math

    # 样本量检查
    if sample_size_a < min_sample_size or sample_size_b < min_sample_size:
        return {
            "significant": False,
            "winner": "none",
            "confidence": 0.0,
            "relative_lift": 0.0,
            "recommendation": f"样本量不足（A:{sample_size_a}, B:{sample_size_b}），需要至少 {min_sample_size}",
            "details": {"sample_size_a": sample_size_a, "sample_size_b": sample_size_b},
        }

    rate_a = variant_a_metrics.get(primary_metric, 0)
    rate_b = variant_b_metrics.get(primary_metric, 0)

    if rate_a == 0 and rate_b == 0:
        return {
            "significant": False,
            "winner": "none",
            "confidence": 0.0,
            "relative_lift": 0.0,
            "recommendation": "两组转化率均为0，无法评估",
            "details": {},
        }

    # Z 检验（双侧）：置信度 = 1 - p_value
    pooled_se = math.sqrt(
        (rate_a * (1 - rate_a) / sample_size_a) +
        (rate_b * (1 - rate_b) / sample_size_b)
    )
    if pooled_se == 0:
        z_score = 0
    else:
        z_score = (rate_b - rate_a) / pooled_se

    # 标准正态 CDF。由评测集 mm-003/004/006 暴露：旧的 z/3 简化公式
    # 低估置信度（z=2.589 时真实 0.990 被算成 0.863 而误报"不显著"）。
    cdf_z = 0.5 * (1 + math.erf(abs(z_score) / math.sqrt(2)))
    confidence = max(0.0, min(0.999, 2 * cdf_z - 1))

    relative_lift = ((rate_b - rate_a) / rate_a) if rate_a > 0 else 0.0
    significant = confidence >= confidence_threshold

    if significant and rate_b > rate_a:
        winner = "B"
        recommendation = f"B变体显著优于A（提升{relative_lift:.1%}），建议全量推广B变体策略"
    elif significant and rate_a > rate_b:
        winner = "A"
        recommendation = f"A变体显著优于B（B变体降低{abs(relative_lift):.1%}），建议保持A变体策略"
    else:
        winner = "none"
        recommendation = "无显著差异，建议继续实验或选择当前表现较好的变体"

    return {
        "significant": significant,
        "winner": winner,
        "confidence": round(confidence, 4),
        "relative_lift": round(relative_lift, 4),
        "z_score": round(z_score, 4),
        "recommendation": recommendation,
        "details": {
            "rate_a": rate_a,
            "rate_b": rate_b,
            "sample_size_a": sample_size_a,
            "sample_size_b": sample_size_b,
            "primary_metric": primary_metric,
        },
    }


# --------------------------------------------------------------------------- #
# 策略自动更新
# --------------------------------------------------------------------------- #

async def update_strategy_from_ab_test(
    session: AsyncSession,
    *,
    experiment_id: str,
    experiment_name: str,
    strategy_type: str,
    evaluation: dict[str, Any],
    winning_variant_config: dict[str, Any] | None = None,
    auto_apply: bool = False,
) -> dict[str, Any]:
    """根据 A/B 测试结论更新营销策略。

    高风险策略（pricing/inventory）必须人审；
    低风险策略（listing/content）可自动执行。

    Args:
        auto_apply: 是否自动应用（仅低风险策略有效）
    """
    risk_level = STRATEGY_RISK.get(strategy_type, "medium")

    logger.info(
        "A/B测试策略更新: experiment=%s type=%s risk=%s winner=%s",
        experiment_id, strategy_type, risk_level, evaluation.get("winner"),
    )

    # 如果没有显著结论，不更新策略
    if not evaluation.get("significant") or evaluation.get("winner") == "none":
        return {
            "applied": False,
            "reason": "无显著结论，暂不更新策略",
            "evaluation": evaluation,
        }

    # 构建策略更新建议
    winner = evaluation["winner"]
    title = f"A/B测试结论: {experiment_name} - {winner}变体胜出"
    description = (
        f"实验「{experiment_name}」达到统计显著性（置信度{evaluation['confidence']:.1%}）。\n\n"
        f"{evaluation['recommendation']}\n\n"
        f"相对提升: {evaluation['relative_lift']:.1%}\n"
        f"策略类型: {strategy_type}\n"
        f"风险等级: {risk_level}"
    )

    execution_params = {
        "experiment_id": experiment_id,
        "strategy_type": strategy_type,
        "winner": winner,
        "winning_config": winning_variant_config or {},
        "evaluation": evaluation,
    }

    # 创建建议（进入审批队列）
    suggestion = await agent_suggestion_service.create_suggestion(
        session,
        agent_id="marketing_manager",
        suggestion_type="marketing_optimization",
        title=title,
        description=description,
        execution_params=execution_params,
        execution_action=f"update_{strategy_type}_strategy",
        expected_impact=f"预计{evaluation['relative_lift']:.1%}的指标提升",
        priority="high" if evaluation.get("relative_lift", 0) > 0.1 else "medium",
        risk_level=risk_level,
    )

    # 低风险且 auto_apply 时自动审批执行
    if auto_apply and risk_level == "low":
        await agent_suggestion_service.approve_suggestion(
            session,
            suggestion.id,
            approved_by="ab_test_auto",
            comment="A/B测试自动应用（低风险策略）",
            auto_execute=True,
        )
        # 持久化策略版本（A/B 结论 → 策略更新 → 可回滚闭环）
        await record_strategy_change(
            session,
            strategy_type=strategy_type,
            old_config={},
            new_config=winning_variant_config or {},
            reason=f"A/B测试自动应用: {experiment_name} - {winner}胜出（置信度{evaluation['confidence']:.1%}）",
            changed_by="ab_test_auto",
            experiment_id=experiment_id,
            suggestion_id=suggestion.id,
        )
        applied = True
    else:
        applied = False

    await session.commit()

    return {
        "applied": applied,
        "suggestion_id": suggestion.id,
        "risk_level": risk_level,
        "requires_approval": risk_level in ("high", "medium"),
        "evaluation": evaluation,
    }


# --------------------------------------------------------------------------- #
# 策略版本管理（简化版，实际应写入 strategy_versions 表）
# --------------------------------------------------------------------------- #

async def record_strategy_change(
    session: AsyncSession,
    *,
    strategy_type: str,
    old_config: dict[str, Any],
    new_config: dict[str, Any],
    reason: str,
    changed_by: str,
    experiment_id: str | None = None,
    suggestion_id: int | None = None,
    change_type: str = "update",
) -> dict[str, Any]:
    """记录策略变更并持久化到 strategy_versions 表（可审计、可回滚）。

    版本号按策略类型自增：同类型已有版本的最大值 + 1。
    """
    # 计算下一个版本号（同类型内自增）
    result = await session.execute(
        select(StrategyVersion.version)
        .where(
            StrategyVersion.workspace_id == DEFAULT_WORKSPACE_ID,
            StrategyVersion.strategy_type == strategy_type,
        )
        .order_by(StrategyVersion.version.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    next_version = (row or 0) + 1

    version = StrategyVersion(
        workspace_id=DEFAULT_WORKSPACE_ID,
        strategy_type=strategy_type,
        version=next_version,
        old_config=old_config or {},
        new_config=new_config or {},
        reason=reason,
        changed_by=changed_by,
        experiment_id=experiment_id,
        suggestion_id=suggestion_id,
        change_type=change_type,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)

    logger.info(
        "策略变更已持久化: type=%s v%d by=%s reason=%s",
        strategy_type, version.version, changed_by, reason,
    )

    return {
        "strategy_type": strategy_type,
        "version": version.version,
        "version_id": version.id,
        "old_config": old_config,
        "new_config": new_config,
        "reason": reason,
        "changed_by": changed_by,
        "experiment_id": experiment_id,
        "change_type": change_type,
        "changed_at": version.created_at.isoformat(),
    }


async def rollback_strategy(
    session: AsyncSession,
    *,
    strategy_type: str,
    version_id: str,
    reason: str,
) -> dict[str, Any]:
    """回滚策略到指定版本：从 strategy_versions 表恢复配置。

    - 读取目标版本的 new_config 作为恢复后的当前配置；
    - 写入一条 change_type=rollback 的版本记录，保证回滚本身可审计；
    - 恢复的配置由调用方写入实际策略存储（strategy_config 表/配置服务）。
    """
    try:
        vid = int(version_id)
    except (TypeError, ValueError):
        return {
            "rolled_back": False,
            "error": f"无效版本ID: {version_id}",
            "strategy_type": strategy_type,
        }

    target = await session.get(StrategyVersion, vid)
    if target is None or target.strategy_type != strategy_type:
        return {
            "rolled_back": False,
            "error": f"未找到策略版本: type={strategy_type} id={version_id}",
            "strategy_type": strategy_type,
        }

    restored_config = target.new_config

    # 写入回滚记录（change_type=rollback，new_config 为恢复后的配置）
    record = await record_strategy_change(
        session,
        strategy_type=strategy_type,
        old_config={},
        new_config=restored_config,
        reason=f"回滚至版本 v{target.version}（{target.reason[:120]}）：{reason}",
        changed_by="rollback",
        experiment_id=target.experiment_id,
        change_type="rollback",
    )

    logger.warning(
        "策略已回滚: type=%s 目标 v%s -> 新记录 v%s, reason=%s",
        strategy_type, target.version, record["version"], reason,
    )

    return {
        "rolled_back": True,
        "strategy_type": strategy_type,
        "version_id": version_id,
        "restored_config": restored_config,
        "restored_version": target.version,
        "rollback_record_version": record["version"],
        "reason": reason,
        "rolled_back_at": datetime.now(UTC).isoformat(),
    }
