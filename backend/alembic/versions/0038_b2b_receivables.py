"""B2B invoices, receipts, and immutable receivable ledger.

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "b2b_invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(32), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("customer_account_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("shipping_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("amount_written_off", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("balance_due", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "items_snapshot",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("subtotal >= 0", name="ck_b2b_invoice_subtotal"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_b2b_invoice_discount"),
        sa.CheckConstraint("shipping_amount >= 0", name="ck_b2b_invoice_shipping"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_b2b_invoice_tax"),
        sa.CheckConstraint("total > 0", name="ck_b2b_invoice_total"),
        sa.CheckConstraint("amount_paid >= 0", name="ck_b2b_invoice_paid"),
        sa.CheckConstraint(
            "amount_written_off >= 0",
            name="ck_b2b_invoice_write_off",
        ),
        sa.CheckConstraint("balance_due >= 0", name="ck_b2b_invoice_balance"),
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
            ["order_id"],
            ["b2b_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "invoice_number",
            name="uq_b2b_invoices_workspace_number",
        ),
    )
    op.create_index("ix_b2b_invoices_workspace_id", "b2b_invoices", ["workspace_id"])
    op.create_index("ix_b2b_invoices_order_id", "b2b_invoices", ["order_id"])
    op.create_index("ix_b2b_invoices_agent_id", "b2b_invoices", ["agent_id"])
    op.create_index(
        "ix_b2b_invoices_customer_account_id",
        "b2b_invoices",
        ["customer_account_id"],
    )
    op.create_index("ix_b2b_invoices_status", "b2b_invoices", ["status"])
    op.create_index("ix_b2b_invoices_due_date", "b2b_invoices", ["due_date"])
    op.create_index(
        "ix_b2b_invoices_workspace_status",
        "b2b_invoices",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_b2b_invoices_workspace_due",
        "b2b_invoices",
        ["workspace_id", "due_date"],
    )
    op.create_index(
        "ix_b2b_invoices_workspace_agent",
        "b2b_invoices",
        ["workspace_id", "agent_id"],
    )

    op.create_table(
        "b2b_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_number", sa.String(32), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("customer_account_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="unapplied"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("unapplied_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "payment_method",
            sa.String(32),
            nullable=False,
            server_default="bank_transfer",
        ),
        sa.Column("bank_reference", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
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
        sa.CheckConstraint("amount > 0", name="ck_b2b_receipt_amount"),
        sa.CheckConstraint(
            "unapplied_amount >= 0 AND unapplied_amount <= amount",
            name="ck_b2b_receipt_unapplied",
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
            "receipt_number",
            name="uq_b2b_receipts_workspace_number",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_b2b_receipts_workspace_idempotency",
        ),
    )
    op.create_index("ix_b2b_receipts_workspace_id", "b2b_receipts", ["workspace_id"])
    op.create_index("ix_b2b_receipts_agent_id", "b2b_receipts", ["agent_id"])
    op.create_index(
        "ix_b2b_receipts_customer_account_id",
        "b2b_receipts",
        ["customer_account_id"],
    )
    op.create_index("ix_b2b_receipts_status", "b2b_receipts", ["status"])
    op.create_index(
        "ix_b2b_receipts_workspace_status",
        "b2b_receipts",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_b2b_receipts_workspace_agent",
        "b2b_receipts",
        ["workspace_id", "agent_id"],
    )
    op.create_index(
        "ix_b2b_receipts_workspace_received",
        "b2b_receipts",
        ["workspace_id", "received_at"],
    )

    op.create_table(
        "b2b_receivable_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=True),
        sa.Column("entry_type", sa.String(24), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_key", sa.String(192), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("amount <> 0", name="ck_b2b_receivable_entry_nonzero"),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["b2b_agents.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["b2b_invoices.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["b2b_receipts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "entry_key",
            name="uq_b2b_receivable_entries_workspace_key",
        ),
    )
    op.create_index(
        "ix_b2b_receivable_entries_workspace_id",
        "b2b_receivable_entries",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_receivable_entries_agent_id",
        "b2b_receivable_entries",
        ["agent_id"],
    )
    op.create_index(
        "ix_b2b_receivable_entries_invoice_id",
        "b2b_receivable_entries",
        ["invoice_id"],
    )
    op.create_index(
        "ix_b2b_receivable_entries_receipt_id",
        "b2b_receivable_entries",
        ["receipt_id"],
    )
    op.create_index(
        "ix_b2b_receivable_entries_entry_type",
        "b2b_receivable_entries",
        ["entry_type"],
    )
    op.create_index(
        "ix_b2b_receivable_entries_workspace_type",
        "b2b_receivable_entries",
        ["workspace_id", "entry_type"],
    )
    op.create_index(
        "ix_b2b_receivable_entries_workspace_agent",
        "b2b_receivable_entries",
        ["workspace_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_b2b_receivable_entries_workspace_agent",
        table_name="b2b_receivable_entries",
    )
    op.drop_index(
        "ix_b2b_receivable_entries_workspace_type",
        table_name="b2b_receivable_entries",
    )
    op.drop_index(
        "ix_b2b_receivable_entries_entry_type",
        table_name="b2b_receivable_entries",
    )
    op.drop_index(
        "ix_b2b_receivable_entries_receipt_id",
        table_name="b2b_receivable_entries",
    )
    op.drop_index(
        "ix_b2b_receivable_entries_invoice_id",
        table_name="b2b_receivable_entries",
    )
    op.drop_index(
        "ix_b2b_receivable_entries_agent_id",
        table_name="b2b_receivable_entries",
    )
    op.drop_index(
        "ix_b2b_receivable_entries_workspace_id",
        table_name="b2b_receivable_entries",
    )
    op.drop_table("b2b_receivable_entries")

    op.drop_index(
        "ix_b2b_receipts_workspace_received",
        table_name="b2b_receipts",
    )
    op.drop_index("ix_b2b_receipts_workspace_agent", table_name="b2b_receipts")
    op.drop_index("ix_b2b_receipts_workspace_status", table_name="b2b_receipts")
    op.drop_index("ix_b2b_receipts_status", table_name="b2b_receipts")
    op.drop_index(
        "ix_b2b_receipts_customer_account_id",
        table_name="b2b_receipts",
    )
    op.drop_index("ix_b2b_receipts_agent_id", table_name="b2b_receipts")
    op.drop_index("ix_b2b_receipts_workspace_id", table_name="b2b_receipts")
    op.drop_table("b2b_receipts")

    op.drop_index("ix_b2b_invoices_workspace_agent", table_name="b2b_invoices")
    op.drop_index("ix_b2b_invoices_workspace_due", table_name="b2b_invoices")
    op.drop_index("ix_b2b_invoices_workspace_status", table_name="b2b_invoices")
    op.drop_index("ix_b2b_invoices_due_date", table_name="b2b_invoices")
    op.drop_index("ix_b2b_invoices_status", table_name="b2b_invoices")
    op.drop_index(
        "ix_b2b_invoices_customer_account_id",
        table_name="b2b_invoices",
    )
    op.drop_index("ix_b2b_invoices_agent_id", table_name="b2b_invoices")
    op.drop_index("ix_b2b_invoices_order_id", table_name="b2b_invoices")
    op.drop_index("ix_b2b_invoices_workspace_id", table_name="b2b_invoices")
    op.drop_table("b2b_invoices")
