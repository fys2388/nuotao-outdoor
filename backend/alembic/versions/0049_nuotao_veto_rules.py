"""V3.0: register V1-V12 proactive veto rules in the Rule Registry.

The rules table is the auditable control plane; the deterministic evaluation
lives in app/services/nuotao_veto.py. These rows make the veto catalogue
visible/manageable in the Rules UI and align with docs/nuotao_product_score_v3.0
section 3. Inserts are idempotent (ON CONFLICT DO NOTHING). SQL is built with
inline, escaped literals (same proven pattern as migration 0002 demo rules) to
avoid any Alembic op.execute parameter-binding differences.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

# (rule_id, name, group, check_type, when_conditions, extra params)
RULES: list[tuple[str, str, str, str, dict, dict]] = [
    ("V1", "知识产权侵权风险（商标/外观/专利）", "compliance", "ai",
     {"engine": "ai", "field": "ip_risk"}, {"stage": "screening"}),
    ("V2", "目标市场法规/强制认证缺失", "compliance", "ai",
     {"engine": "ai", "field": "regulatory"}, {"stage": "screening"}),
    ("V3", "产品安全设计缺陷", "compliance", "ai",
     {"engine": "ai", "field": "safety"}, {"stage": "screening"}),
    ("V4", "目标市场禁售/平台违禁品类", "compliance", "deterministic",
     {"field": "category", "op": "in_banned_list"}, {"stage": "screening"}),
    ("V5", "破坏品牌品类聚焦", "brand", "ai",
     {"engine": "ai", "field": "brand_focus"}, {"stage": "brand"}),
    ("V6", "低价杂货感（参考售价低于 impulse 阈值）", "brand", "deterministic",
     {"field": "reference_price_usd", "op": "lt", "value": 5}, {"stage": "brand"}),
    ("V7", "与现有 Hero 产品同质化", "brand", "deterministic",
     {"field": "category", "op": "overlaps_hero"}, {"stage": "brand"}),
    ("V8", "Brand Fit 维度分低于 5", "brand", "deterministic",
     {"field": "brand_fit", "op": "lt", "value": 5}, {"stage": "brand"}),
    ("V9", "国际运费占售价比高于 40%", "commercial", "deterministic",
     {"field": "shipping_ratio", "op": "gt", "value": 0.4}, {"stage": "commercial"}),
    ("V10", "全成本利润率低于 20%", "commercial", "deterministic",
     {"field": "margin_rate", "op": "lt", "value": 0.2}, {"stage": "commercial"}),
    ("V11", "无 C 级以上合格供应商", "commercial", "deterministic",
     {"field": "supplier_rating", "op": "below", "value": "C"}, {"stage": "commercial"}),
    ("V12", "预估退货率高于 15%", "commercial", "hybrid",
     {"field": "return_rate", "op": "gt", "value": 0.15}, {"stage": "commercial"}),
]


def _quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _jsonb(value: dict) -> str:
    return _quote(json.dumps(value, ensure_ascii=False)) + "::jsonb"


def upgrade() -> None:
    for index, (rule_id, name, group, check_type, when, extra) in enumerate(RULES, start=1):
        rule_id_sql = f"00000000-0049-0000-0000-{index:012d}"
        then_result = {
            "action": "reject",
            "failed_message": f"{rule_id} {name}，一票否决",
        }
        params = {"group": group, "check_type": check_type, **extra}
        statement = f"""
            INSERT INTO rules (
                id, workspace_id, rule_id, name, category, rule_type, version, status,
                when_conditions, then_result, params, approval_level
            ) VALUES (
                {_quote(rule_id_sql)}, {_quote(WORKSPACE_ID)}, {_quote(rule_id)},
                {_quote(name)}, 'PROD-VETO', 'hard', 'v1', 'active',
                {_jsonb(when)}, {_jsonb(then_result)}, {_jsonb(params)}, 'L0'
            )
            ON CONFLICT ON CONSTRAINT uq_rules_workspace_rule_version DO NOTHING
        """
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM rules
            WHERE category = 'PROD-VETO'
              AND rule_id IN ('V1','V2','V3','V4','V5','V6',
                              'V7','V8','V9','V10','V11','V12')
            """
        )
    )
