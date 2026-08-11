"""product intelligence: sources, cost history, scores, analysis, decisions

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def _jsonb_literal(value: object) -> str:
    """Render a JSON value as a quoted PostgreSQL jsonb literal (offline-safe)."""
    import json

    dumped = json.dumps(value, ensure_ascii=False)
    return "'" + dumped.replace("'", "''") + "'::jsonb"


def upgrade() -> None:
    """Create the M2.1 product intelligence tables and seed product rules."""

    op.add_column(
        "products",
        sa.Column("weight_kg", sa.Numeric(8, 3), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("dimensions", JSONB(), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("target_market", sa.String(16), nullable=False, server_default="US"),
    )

    # --- product_sources ----------------------------------------------------
    op.create_table(
        "product_sources",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_url", sa.String(512), nullable=True),
        sa.Column("supplier_id", UUID(), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supplier_code", sa.String(64), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("raw_data", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_product_sources_workspace_id", "product_sources", ["workspace_id"])
    op.create_index("ix_product_sources_product_id", "product_sources", ["product_id"])
    op.execute(sa.text("CREATE INDEX ix_product_sources_captured ON product_sources (workspace_id, captured_at)"))

    # --- product_cost_snapshots (append-only history) -----------------------
    op.create_table(
        "product_cost_snapshots",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("product_id", UUID(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("purchase_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("domestic_shipping", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("first_leg_shipping", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("last_leg_shipping", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("payment_fee", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("marketing_amortization", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("after_sales_loss", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("weight_kg", sa.Numeric(8, 3), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_product_cost_snapshots_workspace_id", "product_cost_snapshots", ["workspace_id"])
    op.create_index("ix_product_cost_snapshots_product_id", "product_cost_snapshots", ["product_id"])

    # --- product_scores -----------------------------------------------------
    op.create_table(
        "product_scores",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("product_id", UUID(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profit", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("logistics", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("demand", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("competition", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("differentiation", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("compliance", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_product_scores_workspace_id", "product_scores", ["workspace_id"])
    op.create_index("ix_product_scores_product_id", "product_scores", ["product_id"])

    # --- product_analysis_runs ----------------------------------------------
    op.create_table(
        "product_analysis_runs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=True),
        sa.Column("input_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("token_usage", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_product_analysis_runs_workspace_id", "product_analysis_runs", ["workspace_id"])
    op.create_index("ix_product_analysis_runs_product_id", "product_analysis_runs", ["product_id"])

    # --- product_decisions ---------------------------------------------------
    op.create_table(
        "product_decisions",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("product_id", UUID(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("score", sa.Numeric(6, 2), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("reasons", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risks", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("recommended_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("max_cac", sa.Numeric(12, 2), nullable=True),
        sa.Column("test_quantity", sa.Integer(), nullable=True),
        sa.Column("test_days", sa.Integer(), nullable=True),
        sa.Column("approval_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_product_decisions_workspace_id", "product_decisions", ["workspace_id"])
    op.create_index("ix_product_decisions_product_id", "product_decisions", ["product_id"])
    op.create_index("ix_product_decisions_approval", "product_decisions", ["workspace_id", "approval_status"])

    # --- seed rules ----------------------------------------------------------
    # PROFIT-003: hard gate - an UNKNOWN product cost must never produce a
    # high-confidence profitability conclusion (M1.6 requirement).
    # PROD-SEL-004/005: deterministic product intake gates evaluated by the
    # product intelligence chain (M2.1).
    seed_rules = [
        {
            "id": "10000000-0000-0000-0000-000000000006",
            "rule_id": "PROFIT-003",
            "name": "Profit conclusion requires non-unknown product cost",
            "category": "PROFIT",
            "rule_type": "hard",
            "version": "v1",
            "status": "active",
            "when_conditions": {
                "field": "profit.cost_status",
                "op": "in",
                "value": ["KNOWN", "ESTIMATED"],
            },
            "then_result": {
                "passed_message": "product cost is known enough for a profit conclusion",
                "failed_message": "product cost is UNKNOWN; profit conclusion withheld",
            },
        },
        {
            "id": "10000000-0000-0000-0000-000000000007",
            "rule_id": "PROD-GATE-001",
            "name": "Product cost data must be complete and verifiable",
            "category": "PRODUCT",
            "rule_type": "hard",
            "version": "v1",
            "status": "active",
            "when_conditions": {"field": "cost.total_cost", "op": "gt", "value": 0},
            "then_result": {
                "passed_message": "cost data available",
                "failed_message": "cost data missing",
            },
        },
        {
            "id": "10000000-0000-0000-0000-000000000008",
            "rule_id": "PROD-GATE-002",
            "name": "Shipping must stay within 40% of expected price",
            "category": "PRODUCT",
            "rule_type": "hard",
            "version": "v1",
            "status": "active",
            "when_conditions": {
                "field": "logistics.shipping_ratio",
                "op": "lte",
                "value": 0.4,
            },
            "then_result": {
                "passed_message": "shipping ratio within limit",
                "failed_message": "shipping ratio exceeds 40%",
            },
        },
    ]

    for rule in seed_rules:
        op.execute(
            sa.text(
                "INSERT INTO rules ("
                "id, workspace_id, rule_id, name, category, rule_type, version, status, "
                "when_conditions, then_result, params, approval_level"
                ") VALUES ("
                f"'{rule['id']}', '{DEFAULT_WORKSPACE_ID}', '{rule['rule_id']}', "
                f"'{rule['name'].replace(chr(39), chr(39) * 2)}', '{rule['category']}', "
                f"'{rule['rule_type']}', '{rule['version']}', '{rule['status']}', "
                f"{_jsonb_literal(rule['when_conditions'])}, "
                f"{_jsonb_literal(rule['then_result'])}, "
                f"{_jsonb_literal({})}, 'L0'"
                ")"
            )
        )


def downgrade() -> None:
    """Drop the product intelligence tables and revert products columns."""
    op.drop_table("product_decisions")
    op.drop_table("product_analysis_runs")
    op.drop_table("product_scores")
    op.drop_table("product_cost_snapshots")
    op.drop_table("product_sources")
    op.drop_column("products", "target_market")
    op.drop_column("products", "dimensions")
    op.drop_column("products", "weight_kg")
