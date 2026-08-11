"""order domain: orders, order_items and order rule seeds

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def _jsonb_literal(value: dict) -> str:
    """Render a dict as a quoted PostgreSQL jsonb literal (offline-safe)."""
    import json

    dumped = json.dumps(value, ensure_ascii=False)
    return "'" + dumped.replace("'", "''") + "'::jsonb"


def upgrade() -> None:
    """Create the order domain tables and seed order-domain example rules."""

    op.create_table(
        "orders",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("external_order_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="received"),
        sa.Column("payment_status", sa.String(length=24), nullable=True),
        sa.Column("fulfillment_status", sa.String(length=24), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("country", sa.String(length=8), nullable=True),
        sa.Column("payment_method", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="woocommerce"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("shipping_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("payment_fee", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("refunded_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("advertising_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("profit_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("rule_results", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "external_order_id", name="uq_orders_workspace_external"),
    )
    op.create_index("ix_orders_workspace_id", "orders", ["workspace_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_received_at", "orders", [sa.text("received_at DESC")])

    op.create_table(
        "order_items",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("order_id", UUID(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_item_id", sa.String(length=64), nullable=True),
        sa.Column("product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_order_items_workspace_id", "order_items", ["workspace_id"])
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    # Example order-domain rules (editable via API; parameters are v1 defaults
    # following docs/operating_rules.md).
    demo_rules = [
        {
            "id": "10000000-0000-0000-0000-000000000003",
            "rule_id": "PRICE-001",
            "name": "Order discount ratio must not exceed 30%",
            "category": "PRICE",
            "rule_type": "hard",
            "version": "v1",
            "status": "active",
            "when_conditions": {"field": "price.discount_ratio", "op": "lte", "value": 0.3},
            "then_result": {
                "passed_message": "discount ratio within limit",
                "failed_message": "discount ratio exceeds 30%",
            },
            "params": {},
            "approval_level": "L0",
        },
        {
            "id": "10000000-0000-0000-0000-000000000004",
            "rule_id": "PROFIT-002",
            "name": "Contribution margin rate must be >= 20%",
            "category": "PROFIT",
            "rule_type": "hard",
            "version": "v1",
            "status": "active",
            "when_conditions": {"field": "profit.contribution_margin_rate", "op": "gte", "value": 0.2},
            "then_result": {
                "passed_message": "margin rate acceptable",
                "failed_message": "margin rate below 20%",
            },
            "params": {},
            "approval_level": "L0",
        },
        {
            "id": "10000000-0000-0000-0000-000000000005",
            "rule_id": "FULFILLMENT-001",
            "name": "Payment status must be payable to fulfill",
            "category": "FULFILLMENT",
            "rule_type": "hard",
            "version": "v1",
            "status": "active",
            "when_conditions": {
                "field": "fulfillment.payment_status",
                "op": "in",
                "value": ["processing", "completed"],
            },
            "then_result": {
                "passed_message": "payment status payable",
                "failed_message": "payment status not payable",
            },
            "params": {},
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
                f"'{rule['id']}', '{DEFAULT_WORKSPACE_ID}', '{rule['rule_id']}', "
                f"'{rule['name'].replace(chr(39), chr(39) * 2)}', '{rule['category']}', "
                f"'{rule['rule_type']}', '{rule['version']}', '{rule['status']}', "
                f"{_jsonb_literal(rule['when_conditions'])}, "
                f"{_jsonb_literal(rule['then_result'])}, "
                f"{_jsonb_literal(rule['params'])}, '{rule['approval_level']}'"
                ")"
            )
        )


def downgrade() -> None:
    """Drop the order domain tables."""
    op.drop_table("order_items")
    op.drop_table("orders")
