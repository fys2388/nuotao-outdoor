"""brain core schema: workspace, event_log, products, rules, agent runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    """Create the M1 data foundation tables and seed baseline data."""

    # --- workspaces -------------------------------------------------------
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("market", sa.String(length=16), nullable=False, server_default="US"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- event_log --------------------------------------------------------
    op.create_table(
        "event_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_event_log_type", "event_log", ["event_type"])
    op.execute(sa.text("CREATE INDEX ix_event_log_workspace_created ON event_log (workspace_id, created_at DESC)"))
    op.create_index("ix_event_log_entity", "event_log", ["entity_type", "entity_id"])

    # --- suppliers --------------------------------------------------------
    op.create_table(
        "suppliers",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False, server_default="1688"),
        sa.Column("shop_url", sa.String(length=512), nullable=True),
        sa.Column("rating", sa.String(length=8), nullable=False, server_default="C"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("contact", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "code", name="uq_suppliers_workspace_code"),
    )
    op.create_index("ix_suppliers_workspace_id", "suppliers", ["workspace_id"])

    # --- products ---------------------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("attributes", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("meta", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "sku", name="uq_products_workspace_sku"),
    )
    op.create_index("ix_products_workspace_id", "products", ["workspace_id"])
    op.create_index("ix_products_status", "products", ["status"])

    # --- product_cost -----------------------------------------------------
    op.create_table(
        "product_cost",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("product_id", UUID(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("purchase_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("domestic_shipping", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("first_leg_shipping", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("last_leg_shipping", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("payment_fee", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("marketing_amortization", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("after_sales_loss", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notes", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_product_cost_workspace_id", "product_cost", ["workspace_id"])
    op.create_index("ix_product_cost_product_id", "product_cost", ["product_id"])

    # --- rules ------------------------------------------------------------
    op.create_table(
        "rules",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("rule_type", sa.String(length=16), nullable=False, server_default="hard"),
        sa.Column("version", sa.String(length=16), nullable=False, server_default="v1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("when_conditions", JSONB(), nullable=False),
        sa.Column("then_result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("params", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("approval_level", sa.String(length=8), nullable=False, server_default="L0"),
        sa.Column("owner", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "rule_id", "version", name="uq_rules_workspace_rule_version"),
    )
    op.create_index("ix_rules_workspace_id", "rules", ["workspace_id"])
    op.create_index("ix_rules_category", "rules", ["category"])

    # --- rule_execution_logs ----------------------------------------------
    op.create_table(
        "rule_execution_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("rule_version", sa.String(length=16), nullable=False),
        sa.Column("context", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rule_execution_rule_id", "rule_execution_logs", ["rule_id"])
    op.execute(sa.text("CREATE INDEX ix_rule_execution_created ON rule_execution_logs (workspace_id, created_at DESC)"))

    # --- ai_agent_runs ----------------------------------------------------
    op.create_table(
        "ai_agent_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("agent", sa.String(length=64), nullable=False),
        sa.Column("trigger", sa.String(length=128), nullable=True),
        sa.Column("input", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("plan", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tool_calls", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("output", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("approval", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_agent_runs_agent", "ai_agent_runs", ["agent"])
    op.execute(sa.text("CREATE INDEX ix_ai_agent_runs_created ON ai_agent_runs (workspace_id, created_at DESC)"))

    # --- seed data --------------------------------------------------------
    op.bulk_insert(
        sa.table(
            "workspaces",
            sa.column("id", sa.String()),
            sa.column("name", sa.String()),
            sa.column("code", sa.String()),
            sa.column("market", sa.String()),
            sa.column("currency", sa.String()),
            sa.column("status", sa.String()),
        ),
        [
            {
                "id": DEFAULT_WORKSPACE_ID,
                "name": "Default Workspace",
                "code": "default",
                "market": "US",
                "currency": "USD",
                "status": "active",
            }
        ],
    )

    # Demo rules (editable via API; parameters follow docs/operating_rules.md v1).
    # JSON columns are rendered as explicit ::jsonb literals so offline
    # (``--sql``) migration mode works in addition to online mode.
    def _jsonb_literal(value: dict) -> str:
        """Render a dict as a quoted PostgreSQL jsonb literal."""
        import json

        dumped = json.dumps(value, ensure_ascii=False)
        return "'" + dumped.replace("'", "''") + "'::jsonb"

    demo_rules = [
        {
            "id": "10000000-0000-0000-0000-000000000001",
            "workspace_id": DEFAULT_WORKSPACE_ID,
            "rule_id": "PROD-SEL-005",
            "name": "Logistics constraint: shipping <= 40% of price",
            "category": "PROD-SEL",
            "rule_type": "hard",
            "version": "v1",
            "status": "active",
            "when_conditions": {"field": "cost.shipping_ratio", "op": "lte", "value": 0.4},
            "then_result": {
                "passed_message": "shipping ratio within limit",
                "failed_message": "shipping ratio exceeds 40%",
            },
            "params": {},
            "approval_level": "L0",
        },
        {
            "id": "10000000-0000-0000-0000-000000000002",
            "workspace_id": DEFAULT_WORKSPACE_ID,
            "rule_id": "PROD-SCORE-001",
            "name": "Profit potential scoring (margin >= 45% scores 10)",
            "category": "PROD-SCORE",
            "rule_type": "soft",
            "version": "v1",
            "status": "active",
            "when_conditions": {"field": "cost.target_margin", "op": "gte", "value": 0.45},
            "then_result": {"score": 10, "weight": 3},
            "params": {"pass_score": 10, "fail_score": 4, "weight": 3},
            "approval_level": "L0",
        },
    ]

    for rule in demo_rules:
        op.execute(
            sa.text(
                "INSERT INTO rules ("
                "id, workspace_id, rule_id, name, category, rule_type, version, status, "
                "when_conditions, then_result, params, approval_level"
                ") VALUES ("
                f"'{rule['id']}', '{rule['workspace_id']}', '{rule['rule_id']}', "
                f"'{rule['name'].replace(chr(39), chr(39)*2)}', '{rule['category']}', "
                f"'{rule['rule_type']}', '{rule['version']}', '{rule['status']}', "
                f"{_jsonb_literal(rule['when_conditions'])}, {_jsonb_literal(rule['then_result'])}, "
                f"{_jsonb_literal(rule['params'])}, '{rule['approval_level']}'"
                ")"
            )
        )


def downgrade() -> None:
    """Drop the M1 data foundation tables (reverse order of creation)."""
    op.execute(sa.text("DROP INDEX IF EXISTS ix_ai_agent_runs_created"))
    op.drop_table("ai_agent_runs")
    op.execute(sa.text("DROP INDEX IF EXISTS ix_rule_execution_created"))
    op.drop_table("rule_execution_logs")
    op.drop_table("rules")
    op.drop_table("product_cost")
    op.drop_table("products")
    op.drop_table("suppliers")
    op.execute(sa.text("DROP INDEX IF EXISTS ix_event_log_workspace_created"))
    op.drop_table("event_log")
    op.drop_table("workspaces")
