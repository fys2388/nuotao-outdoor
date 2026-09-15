"""Add brand, legal-entity, and attribution dimensions for consolidation.

Revision ID: 0046
Revises: 0045
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(8), nullable=False, server_default="US"),
        sa.Column(
            "functional_currency",
            sa.String(8),
            nullable=False,
            server_default="USD",
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
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
        sa.CheckConstraint(
            "status IN ('active','inactive')",
            name="ck_legal_entities_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "code",
            name="uq_legal_entities_workspace_code",
        ),
    )
    op.create_index(
        "ix_legal_entities_workspace_id",
        "legal_entities",
        ["workspace_id"],
    )
    op.create_index(
        "ix_legal_entities_workspace_status",
        "legal_entities",
        ["workspace_id", "status"],
    )

    op.create_table(
        "brands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("default_legal_entity_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_brands_status"),
        sa.ForeignKeyConstraint(
            ["default_legal_entity_id"],
            ["legal_entities.id"],
            name="fk_brands_default_legal_entity_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "code", name="uq_brands_workspace_code"),
    )
    op.create_index("ix_brands_workspace_id", "brands", ["workspace_id"])
    op.create_index(
        "ix_brands_default_legal_entity_id",
        "brands",
        ["default_legal_entity_id"],
    )
    op.create_index(
        "ix_brands_workspace_status",
        "brands",
        ["workspace_id", "status"],
    )

    op.add_column("products", sa.Column("brand_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_products_brand_id",
        "products",
        "brands",
        ["brand_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_products_brand_id", "products", ["brand_id"])

    op.create_table(
        "commerce_attributions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(24), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("legal_entity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "assignment_source",
            sa.String(24),
            nullable=False,
            server_default="manual",
        ),
        sa.Column(
            "is_intercompany",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("counterparty_legal_entity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "elimination_status",
            sa.String(16),
            nullable=False,
            server_default="not_applicable",
        ),
        sa.Column(
            "elimination_amount",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("assigned_by", sa.String(128), nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
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
            "entity_type IN ('b2c_order','b2b_order','b2b_invoice')",
            name="ck_commerce_attributions_entity_type",
        ),
        sa.CheckConstraint(
            "assignment_source IN ('auto','manual','invoice_copy','migration')",
            name="ck_commerce_attributions_source",
        ),
        sa.CheckConstraint(
            "elimination_status IN "
            "('not_applicable','pending','approved','rejected')",
            name="ck_commerce_attributions_elimination_status",
        ),
        sa.CheckConstraint(
            "elimination_amount >= 0",
            name="ck_commerce_attributions_elimination_amount",
        ),
        sa.CheckConstraint(
            "NOT is_intercompany OR counterparty_legal_entity_id IS NOT NULL",
            name="ck_commerce_attributions_intercompany_counterparty",
        ),
        sa.CheckConstraint(
            "counterparty_legal_entity_id IS NULL "
            "OR counterparty_legal_entity_id <> legal_entity_id",
            name="ck_commerce_attributions_counterparty_distinct",
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["brands.id"],
            name="fk_commerce_attributions_brand_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["legal_entity_id"],
            ["legal_entities.id"],
            name="fk_commerce_attributions_legal_entity_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["counterparty_legal_entity_id"],
            ["legal_entities.id"],
            name="fk_commerce_attributions_counterparty_legal_entity_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "entity_type",
            "entity_id",
            name="uq_commerce_attributions_workspace_entity",
        ),
    )
    op.create_index(
        "ix_commerce_attributions_workspace_id",
        "commerce_attributions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_commerce_attributions_entity_id",
        "commerce_attributions",
        ["entity_id"],
    )
    op.create_index(
        "ix_commerce_attributions_brand_id",
        "commerce_attributions",
        ["brand_id"],
    )
    op.create_index(
        "ix_commerce_attributions_legal_entity_id",
        "commerce_attributions",
        ["legal_entity_id"],
    )
    op.create_index(
        "ix_commerce_attributions_counterparty_legal_entity_id",
        "commerce_attributions",
        ["counterparty_legal_entity_id"],
    )
    op.create_index(
        "ix_commerce_attributions_workspace_dimensions",
        "commerce_attributions",
        ["workspace_id", "brand_id", "legal_entity_id"],
    )
    op.create_index(
        "ix_commerce_attributions_workspace_entity",
        "commerce_attributions",
        ["workspace_id", "entity_type", "entity_id"],
    )
    op.create_index(
        "ix_commerce_attributions_workspace_elimination",
        "commerce_attributions",
        ["workspace_id", "elimination_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_commerce_attributions_workspace_elimination",
        table_name="commerce_attributions",
    )
    op.drop_index(
        "ix_commerce_attributions_workspace_entity",
        table_name="commerce_attributions",
    )
    op.drop_index(
        "ix_commerce_attributions_workspace_dimensions",
        table_name="commerce_attributions",
    )
    op.drop_index(
        "ix_commerce_attributions_counterparty_legal_entity_id",
        table_name="commerce_attributions",
    )
    op.drop_index(
        "ix_commerce_attributions_legal_entity_id",
        table_name="commerce_attributions",
    )
    op.drop_index(
        "ix_commerce_attributions_brand_id",
        table_name="commerce_attributions",
    )
    op.drop_index(
        "ix_commerce_attributions_entity_id",
        table_name="commerce_attributions",
    )
    op.drop_index(
        "ix_commerce_attributions_workspace_id",
        table_name="commerce_attributions",
    )
    op.drop_table("commerce_attributions")

    op.drop_index("ix_products_brand_id", table_name="products")
    op.drop_constraint("fk_products_brand_id", "products", type_="foreignkey")
    op.drop_column("products", "brand_id")

    op.drop_index("ix_brands_workspace_status", table_name="brands")
    op.drop_index("ix_brands_default_legal_entity_id", table_name="brands")
    op.drop_index("ix_brands_workspace_id", table_name="brands")
    op.drop_table("brands")

    op.drop_index("ix_legal_entities_workspace_status", table_name="legal_entities")
    op.drop_index("ix_legal_entities_workspace_id", table_name="legal_entities")
    op.drop_table("legal_entities")
