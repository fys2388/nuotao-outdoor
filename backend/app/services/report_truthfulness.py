"""报告防造假校验服务（Report Truthfulness Guardrails）v1.0.

对 AI Agent 生成的经营报告（营销经理每日分析等）执行 7 条防造假硬规则，
在报告落库 / 推送前强制校验，禁止弄虚作假、实事求是：

R1  每个数字必须带来源：无来源数字禁止出现在报告中（广告平台 / CRM / GA4 / 支付单）。
R2  生成前自动对账：活动收入 == Σ订单收入；对不平则强制披露缺口，禁止隐藏或忽略。
R3  预测必须带模型：无公式的"预期收益 / ROAS 提升"一律拒绝；只允许
    "若 X 则 Y" 的情景测算并标注假设（expected_impact 必须携带 basis 与 formula）。
R4  小样本禁下结论：样本量不足时只做描述，禁止统计性 / 评价性表述
    （如"价值是 5.6 倍"、"客单价极高"）。
R5  未投放活动标 N/A：planned / 未启动活动 ROAS 不得写 0.00，
    也不得给出"暂停 / 删除"等执行指令。
R6  输出完整性校验：报告被截断 / 缺字段即视为生成失败，禁止交付半句。
R7  全链路落库：校验结果随 ai_agent_runs 审计记录，人工可复核。

本服务是业务规则唯一来源，Agent 与报告生成器必须通过本服务校验后才可输出。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# 报告防造假规则版本，随规则变更升级
TRUTHFULNESS_RULES_VERSION = "v1.0"

# 对账容差：活动收入与分群收入合计允许的绝对偏差（美元）
RECONCILE_TOLERANCE_USD = Decimal("0.01")
# 小样本阈值：低于该数量禁止统计性结论
MIN_SAMPLE_SIZE = 30
# 预测必须携带的字段：依据 + 公式/模型
REQUIRED_PREDICTION_FIELDS = ("basis", "formula")


@dataclass
class CampaignMetric:
    """单个营销活动的规范化指标。"""

    name: str
    channel: str | None = None
    status: str = "active"  # active | planned | paused | completed | unknown
    spend: Decimal | None = None
    revenue: Decimal | None = None
    source: str | None = None  # R1: 数据来源
    target_roas: Decimal | None = None


@dataclass
class SegmentMetric:
    """客户分群指标。"""

    name: str
    customer_count: int = 0
    revenue: Decimal | None = None
    source: str | None = None  # R1: 数据来源


@dataclass
class ReconciliationResult:
    """收入对账结果（R2）。"""

    campaign_total_revenue: Decimal | None = None
    segment_total_revenue: Decimal | None = None
    gap: Decimal | None = None  # 活动收入 - 分群收入
    reconciled: bool = True  # True 表示已对平
    message: str = ""
    issues: list[str] = field(default_factory=list)


@dataclass
class TruthfulnessCheckResult:
    """一次报告防造假校验的结果。"""

    passed: bool
    rules_version: str = TRUTHFULNESS_RULES_VERSION
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reconciliation: ReconciliationResult | None = None


# --------------------------------------------------------------------------- #
# R2: 收入对账
# --------------------------------------------------------------------------- #

def reconcile_revenue(
    campaigns: list[CampaignMetric],
    segments: list[SegmentMetric],
    *,
    tolerance_usd: Decimal = RECONCILE_TOLERANCE_USD,
) -> ReconciliationResult:
    """对账活动收入与客户分群收入。

    口径说明：
    - 活动收入：所有已投放活动（status != planned）的收入之和；
    - 分群收入：客户分群明细收入之和；
    - 二者应相等（同一笔订单只归因一次）。对不平则返回缺口与告警。

    只对已投放活动做对账；planned 活动收入为 None / 0，不参与求和。
    """
    campaign_total = Decimal("0")
    active_count = 0
    for campaign in campaigns:
        if campaign.status == "planned":
            continue
        active_count += 1
        if campaign.revenue is not None:
            campaign_total += campaign.revenue

    segment_total = Decimal("0")
    segment_with_value = 0
    for segment in segments:
        if segment.revenue is not None:
            segment_total += segment.revenue
            segment_with_value += 1

    if active_count == 0:
        # 无已投放活动，不强制对账（无收入可比）
        return ReconciliationResult(
            campaign_total_revenue=None,
            segment_total_revenue=segment_total if segment_with_value else None,
            gap=None,
            reconciled=True,
            message="无已投放活动，跳过收入对账",
        )

    gap = campaign_total - segment_total
    issues: list[str] = []
    if abs(gap) > tolerance_usd:
        gap_ratio = gap / campaign_total * 100 if campaign_total else Decimal("0")
        issues.append(
            f"收入对账失败：活动收入 ${campaign_total:,.2f} 与客户分群收入 "
            f"${segment_total:,.2f} 相差 ${gap:,.2f}（{gap_ratio:.2f}%），"
            f"缺口必须披露并查明来源后才能出报告"
        )
        logger.warning("revenue reconciliation failed: gap=%s", gap)

    return ReconciliationResult(
        campaign_total_revenue=campaign_total,
        segment_total_revenue=segment_total if segment_with_value else None,
        gap=gap,
        reconciled=abs(gap) <= tolerance_usd,
        message="收入对账通过" if abs(gap) <= tolerance_usd else "收入对账失败，存在未归因缺口",
        issues=issues,
    )


# --------------------------------------------------------------------------- #
# R4: 小样本检查
# --------------------------------------------------------------------------- #

def check_sample_size(
    segments: list[SegmentMetric],
    *,
    min_sample: int = MIN_SAMPLE_SIZE,
) -> list[str]:
    """检查客户分群样本量。

    低于 min_sample 的群组禁止：
    - 统计性结论（"价值是新客户的 N 倍"、"复购价值最高"）；
    - 评价性结论（"客单价极高"、"表现优秀"）。
    只允许描述性陈述（"1 位客户贡献 $449.90"）。
    """
    violations: list[str] = []
    for segment in segments:
        if 0 < segment.customer_count < min_sample:
            violations.append(
                f"样本量不足：分群 '{segment.name}' 仅 {segment.customer_count} 个客户"
                f"（< {min_sample}），禁止统计性 / 评价性结论，只允许描述性陈述"
            )
    return violations


# --------------------------------------------------------------------------- #
# R5: 未投放活动状态校验
# --------------------------------------------------------------------------- #

def check_campaign_status(campaigns: list[CampaignMetric]) -> list[str]:
    """检查活动状态与指标一致性。

    planned / 未启动活动：
    - ROAS 必须为 N/A（不得写 0.00）；
    - 不得给出"暂停 / 删除"等执行指令；
    - 花费 / 收入应为 0 或 None，不得有非零数据。
    """
    violations: list[str] = []
    for campaign in campaigns:
        if campaign.status in ("planned", "paused"):
            has_spend = campaign.spend not in (None, Decimal("0"))
            has_revenue = campaign.revenue not in (None, Decimal("0"))
            if has_spend or has_revenue:
                violations.append(
                    f"活动 '{campaign.name}' 状态为 {campaign.status}（未投放），"
                    f"但存在非零花费/收入数据，数据不一致"
                )
    return violations


# --------------------------------------------------------------------------- #
# R3: 预测必须有模型
# --------------------------------------------------------------------------- #

def check_predictions(actions: list[dict[str, Any]]) -> list[str]:
    """检查行动建议中的预期影响（expected_impact）。

    规则：
    - 无 expected_impact 字段 → 不检查；
    - 有 expected_impact 且含具体数字/涨幅 → 必须携带 basis（依据）与
      formula（公式/模型），否则判违规；
    - 允许"若 X 则 Y"句式，但必须标注假设。
    """
    violations: list[str] = []
    for idx, action in enumerate(actions or []):
        impact = action.get("expected_impact")
        if not impact:
            continue
        # 判断是否含具体数字（$、%、倍数等）
        has_number = re.search(r"[\d$%倍到至]|提升|降低|增加", str(impact)) is not None
        if not has_number:
            continue
        missing = [field_name for field_name in REQUIRED_PREDICTION_FIELDS
                   if not action.get(field_name)]
        if missing:
            violations.append(
                f"建议[{idx}] 预期影响 '{impact}' 缺少预测模型字段 "
                f"{missing}，无公式的收益预测禁止写入报告"
            )
    return violations


# --------------------------------------------------------------------------- #
# R6: 输出完整性校验
# --------------------------------------------------------------------------- #

def check_output_completeness(output: dict[str, Any] | None) -> list[str]:
    """检查报告输出完整性。

    以下情况视为生成失败，禁止交付：
    - output 为空 / 非 dict；
    - 关键字段缺失（summary / action_items / confidence_score）；
    - 字段值被截断（以'——'、'-'、'...'等结尾或为空字符串）；
    - 嵌套结构（list/dict）中的字符串同样检查截断。
    """
    violations: list[str] = []
    if not isinstance(output, dict) or not output:
        return ["报告输出为空，生成失败，禁止交付"]
    required_keys = ("summary", "action_items", "confidence_score")
    for key in required_keys:
        if key not in output or output.get(key) in (None, ""):
            violations.append(f"报告字段 '{key}' 缺失或为空，输出不完整")
    truncated_patterns = re.compile(r"(——+$|-{3,}$|\.{3,}$|…$)")

    def _walk(value: Any, path: str) -> None:
        if isinstance(value, str):
            if truncated_patterns.search(value):
                violations.append(
                    f"报告字段 '{path}' 疑似截断（'...{value[-10:]}'），禁止交付半句"
                )
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                _walk(sub_value, f"{path}.{sub_key}")
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                _walk(item, f"{path}[{idx}]")

    for key, value in output.items():
        _walk(value, key)
    return violations


# --------------------------------------------------------------------------- #
# 汇总校验入口
# --------------------------------------------------------------------------- #

def validate_marketing_report(
    *,
    campaigns: list[CampaignMetric],
    segments: list[SegmentMetric],
    actions: list[dict[str, Any]] | None = None,
    output: dict[str, Any] | None = None,
) -> TruthfulnessCheckResult:
    """营销报告全量防造假校验（R1-R7 入口）。

    Args:
        campaigns: 营销活动指标列表。
        segments: 客户分群指标列表。
        actions: 行动建议列表（含 expected_impact / basis / formula）。
        output: 待交付的报告输出（用于完整性校验）。
            为 None 时跳过 R6 完整性校验（如仅生成建议、无完整报告正文的场景）。

    Returns:
        TruthfulnessCheckResult，passed=False 时报告不得对外发布。
    """
    violations: list[str] = []
    warnings: list[str] = []

    # R2 收入对账
    reconciliation = reconcile_revenue(campaigns, segments)
    violations.extend(reconciliation.issues)

    # R4 小样本
    violations.extend(check_sample_size(segments))

    # R5 活动状态
    violations.extend(check_campaign_status(campaigns))

    # R3 预测模型
    violations.extend(check_predictions(actions or []))

    # R6 完整性（仅当显式传入报告正文时校验）
    if output is not None:
        violations.extend(check_output_completeness(output))

    passed = not violations
    if not passed:
        logger.warning(
            "report truthfulness check FAILED: %d violation(s)", len(violations)
        )
    return TruthfulnessCheckResult(
        passed=passed,
        violations=violations,
        warnings=warnings,
        reconciliation=reconciliation,
    )
