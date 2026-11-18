"""0086_b2b_lead_quotes

M440-04 (M4.4): add the versioned B2B lead quote table (``b2b_lead_quotes``).
A quote is immutable once approved (a new version is created instead of
mutating the approved row) and is internal-only - never exposed via public
routes and never auto-sent to a lead without explicit human approval.

Forward-only, inspector-guarded (idempotent) like 0083/0085; offline mode emits
plain SQL without executing it.

Revision ID: 0086
Revises: 0085
Create Date: 2026-11-17

"""
from alembic import context
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None

_TABLE = "b2b_lead_quotes"


def _create_table() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("b2b_leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quote_number", sa.String(32), nullable=False),
        sa.Column("quote_version", sa.Integer(), nullable=False, default=1),
        sa.Column("currency", sa.String(8), nullable=False, default="USD"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, default=1),
        sa.Column("shipping_cost", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("estimated_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_terms", sa.String(64), nullable=True),
        sa.Column("shipping_terms", sa.String(64), nullable=True),
        sa.Column("approval_status", sa.String(16), nullable=False, default="draft"),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "approval_status IN ('draft','pending','approved','rejected')",
            name="ck_b2b_lead_quotes_approval",
        ),
        sa.Index("ix_b2b_lead_quotes_lead_version", "lead_id", "quote_version"),
    )


def upgrade() -> None:
    if context.is_offline_mode():
        _create_table()
        return
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if _TABLE in [t["name"] for t in insp.get_table_names()]:
        return
    _create_table()


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_table(_TABLE)
        return
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if _TABLE in [t["name"] for t in insp.get_table_names()]:
        op.drop_table(_TABLE)
