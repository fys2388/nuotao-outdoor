"""B2B RFQ, quote, contract, and order linkage.

Revision ID: 0037
Revises: 0036
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "b2b_rfqs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("rfq_number", sa.String(32), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("customer_account_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(24), nullable=False, server_default="manual"),
        sa.Column("requested_currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("destination_country", sa.String(8), nullable=True),
        sa.Column("incoterm", sa.String(16), nullable=True),
        sa.Column("requested_delivery_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("assigned_to", sa.String(128), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["b2b_agents.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_account_id"],
            ["customer_accounts.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "rfq_number",
            name="uq_b2b_rfqs_workspace_number",
        ),
    )
    op.create_index("ix_b2b_rfqs_workspace_id", "b2b_rfqs", ["workspace_id"])
    op.create_index("ix_b2b_rfqs_agent_id", "b2b_rfqs", ["agent_id"])
    op.create_index(
        "ix_b2b_rfqs_customer_account_id",
        "b2b_rfqs",
        ["customer_account_id"],
    )
    op.create_index("ix_b2b_rfqs_status", "b2b_rfqs", ["status"])
    op.create_index(
        "ix_b2b_rfqs_workspace_status",
        "b2b_rfqs",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_b2b_rfqs_workspace_agent",
        "b2b_rfqs",
        ["workspace_id", "agent_id"],
    )

    op.create_table(
        "b2b_rfq_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("rfq_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("sku_snapshot", sa.String(64), nullable=False),
        sa.Column("product_name_snapshot", sa.String(255), nullable=False),
        sa.Column("requested_quantity", sa.Integer(), nullable=False),
        sa.Column("target_unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("specifications", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "requested_quantity > 0",
            name="ck_b2b_rfq_item_quantity",
        ),
        sa.CheckConstraint(
            "target_unit_price IS NULL OR target_unit_price > 0",
            name="ck_b2b_rfq_item_target_price",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rfq_id"],
            ["b2b_rfqs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_b2b_rfq_items_workspace_id", "b2b_rfq_items", ["workspace_id"])
    op.create_index("ix_b2b_rfq_items_rfq_id", "b2b_rfq_items", ["rfq_id"])
    op.create_index("ix_b2b_rfq_items_product_id", "b2b_rfq_items", ["product_id"])

    op.create_table(
        "b2b_quotes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("quote_number", sa.String(32), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rfq_id", sa.Uuid(), nullable=True),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("customer_account_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("base_currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column(
            "exchange_rate_to_base",
            sa.Numeric(18, 8),
            nullable=False,
            server_default="1",
        ),
        sa.Column("price_book_version_id", sa.Uuid(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("incoterm", sa.String(16), nullable=True),
        sa.Column("shipping_terms", sa.Text(), nullable=True),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("shipping_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("version_number >= 1", name="ck_b2b_quote_version"),
        sa.CheckConstraint(
            "exchange_rate_to_base > 0",
            name="ck_b2b_quote_exchange_rate",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["b2b_agents.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_account_id"],
            ["customer_accounts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["price_book_version_id"],
            ["b2b_price_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rfq_id"],
            ["b2b_rfqs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "quote_number",
            "version_number",
            name="uq_b2b_quotes_workspace_number_version",
        ),
    )
    op.create_index("ix_b2b_quotes_workspace_id", "b2b_quotes", ["workspace_id"])
    op.create_index("ix_b2b_quotes_rfq_id", "b2b_quotes", ["rfq_id"])
    op.create_index("ix_b2b_quotes_agent_id", "b2b_quotes", ["agent_id"])
    op.create_index(
        "ix_b2b_quotes_customer_account_id",
        "b2b_quotes",
        ["customer_account_id"],
    )
    op.create_index(
        "ix_b2b_quotes_price_book_version_id",
        "b2b_quotes",
        ["price_book_version_id"],
    )
    op.create_index("ix_b2b_quotes_status", "b2b_quotes", ["status"])
    op.create_index(
        "ix_b2b_quotes_workspace_status",
        "b2b_quotes",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_b2b_quotes_workspace_agent",
        "b2b_quotes",
        ["workspace_id", "agent_id"],
    )

    op.create_table(
        "b2b_quote_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("rfq_item_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("sku_snapshot", sa.String(64), nullable=False),
        sa.Column("product_name_snapshot", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("line_subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_tier_id", sa.Uuid(), nullable=True),
        sa.Column("price_source", sa.String(16), nullable=False, server_default="TIER"),
        sa.Column("cost_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "specifications",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("quantity > 0", name="ck_b2b_quote_item_quantity"),
        sa.CheckConstraint("unit_price > 0", name="ck_b2b_quote_item_unit_price"),
        sa.CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 100",
            name="ck_b2b_quote_item_discount",
        ),
        sa.ForeignKeyConstraint(
            ["price_tier_id"],
            ["b2b_price_tiers.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["b2b_quotes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rfq_item_id"],
            ["b2b_rfq_items.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_b2b_quote_items_workspace_id", "b2b_quote_items", ["workspace_id"])
    op.create_index("ix_b2b_quote_items_quote_id", "b2b_quote_items", ["quote_id"])
    op.create_index("ix_b2b_quote_items_product_id", "b2b_quote_items", ["product_id"])

    op.create_table(
        "b2b_contracts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("contract_number", sa.String(32), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("customer_account_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("document_url", sa.String(1000), nullable=True),
        sa.Column("terms", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("customer_signed_by", sa.String(128), nullable=True),
        sa.Column("customer_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("company_signed_by", sa.String(128), nullable=True),
        sa.Column("company_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_b2b_contract_effective_period",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["b2b_agents.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_account_id"],
            ["customer_accounts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["b2b_quotes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "contract_number",
            name="uq_b2b_contracts_workspace_number",
        ),
    )
    op.create_index("ix_b2b_contracts_workspace_id", "b2b_contracts", ["workspace_id"])
    op.create_index("ix_b2b_contracts_quote_id", "b2b_contracts", ["quote_id"])
    op.create_index("ix_b2b_contracts_agent_id", "b2b_contracts", ["agent_id"])
    op.create_index("ix_b2b_contracts_status", "b2b_contracts", ["status"])
    op.create_index(
        "ix_b2b_contracts_workspace_status",
        "b2b_contracts",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_b2b_contracts_workspace_agent",
        "b2b_contracts",
        ["workspace_id", "agent_id"],
    )

    op.add_column("b2b_orders", sa.Column("quote_id", sa.Uuid(), nullable=True))
    op.add_column("b2b_orders", sa.Column("contract_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_b2b_orders_quote",
        "b2b_orders",
        "b2b_quotes",
        ["quote_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_b2b_orders_workspace_quote",
        "b2b_orders",
        ["workspace_id", "quote_id"],
    )
    op.create_foreign_key(
        "fk_b2b_orders_contract",
        "b2b_orders",
        "b2b_contracts",
        ["contract_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_b2b_orders_quote_id", "b2b_orders", ["quote_id"])
    op.create_index("ix_b2b_orders_contract_id", "b2b_orders", ["contract_id"])

    op.add_column("b2b_order_items", sa.Column("quote_item_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_b2b_order_items_quote_item",
        "b2b_order_items",
        "b2b_quote_items",
        ["quote_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_b2b_order_items_quote_item_id",
        "b2b_order_items",
        ["quote_item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_b2b_order_items_quote_item_id", table_name="b2b_order_items")
    op.drop_constraint(
        "fk_b2b_order_items_quote_item",
        "b2b_order_items",
        type_="foreignkey",
    )
    op.drop_column("b2b_order_items", "quote_item_id")

    op.drop_index("ix_b2b_orders_contract_id", table_name="b2b_orders")
    op.drop_index("ix_b2b_orders_quote_id", table_name="b2b_orders")
    op.drop_constraint(
        "uq_b2b_orders_workspace_quote",
        "b2b_orders",
        type_="unique",
    )
    op.drop_constraint("fk_b2b_orders_contract", "b2b_orders", type_="foreignkey")
    op.drop_constraint("fk_b2b_orders_quote", "b2b_orders", type_="foreignkey")
    op.drop_column("b2b_orders", "contract_id")
    op.drop_column("b2b_orders", "quote_id")

    op.drop_index("ix_b2b_contracts_workspace_agent", table_name="b2b_contracts")
    op.drop_index("ix_b2b_contracts_workspace_status", table_name="b2b_contracts")
    op.drop_index("ix_b2b_contracts_status", table_name="b2b_contracts")
    op.drop_index("ix_b2b_contracts_agent_id", table_name="b2b_contracts")
    op.drop_index("ix_b2b_contracts_quote_id", table_name="b2b_contracts")
    op.drop_index("ix_b2b_contracts_workspace_id", table_name="b2b_contracts")
    op.drop_table("b2b_contracts")

    op.drop_index("ix_b2b_quote_items_product_id", table_name="b2b_quote_items")
    op.drop_index("ix_b2b_quote_items_quote_id", table_name="b2b_quote_items")
    op.drop_index("ix_b2b_quote_items_workspace_id", table_name="b2b_quote_items")
    op.drop_table("b2b_quote_items")

    op.drop_index("ix_b2b_quotes_workspace_agent", table_name="b2b_quotes")
    op.drop_index("ix_b2b_quotes_workspace_status", table_name="b2b_quotes")
    op.drop_index("ix_b2b_quotes_status", table_name="b2b_quotes")
    op.drop_index("ix_b2b_quotes_price_book_version_id", table_name="b2b_quotes")
    op.drop_index("ix_b2b_quotes_customer_account_id", table_name="b2b_quotes")
    op.drop_index("ix_b2b_quotes_agent_id", table_name="b2b_quotes")
    op.drop_index("ix_b2b_quotes_rfq_id", table_name="b2b_quotes")
    op.drop_index("ix_b2b_quotes_workspace_id", table_name="b2b_quotes")
    op.drop_table("b2b_quotes")

    op.drop_index("ix_b2b_rfq_items_product_id", table_name="b2b_rfq_items")
    op.drop_index("ix_b2b_rfq_items_rfq_id", table_name="b2b_rfq_items")
    op.drop_index("ix_b2b_rfq_items_workspace_id", table_name="b2b_rfq_items")
    op.drop_table("b2b_rfq_items")

    op.drop_index("ix_b2b_rfqs_workspace_agent", table_name="b2b_rfqs")
    op.drop_index("ix_b2b_rfqs_workspace_status", table_name="b2b_rfqs")
    op.drop_index("ix_b2b_rfqs_status", table_name="b2b_rfqs")
    op.drop_index("ix_b2b_rfqs_customer_account_id", table_name="b2b_rfqs")
    op.drop_index("ix_b2b_rfqs_agent_id", table_name="b2b_rfqs")
    op.drop_index("ix_b2b_rfqs_workspace_id", table_name="b2b_rfqs")
    op.drop_table("b2b_rfqs")
