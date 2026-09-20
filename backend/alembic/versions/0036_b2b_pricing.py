"""B2B price books, versions, tier pricing, and order price snapshots.

Revision ID: 0036
Revises: 0035
Create Date: 2026-09-13
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def _insert_legacy_price_backfill() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT workspace_id, product_id, tier, agent_id, wholesale_price, "
            "moq, currency, is_active FROM b2b_product_prices "
            "ORDER BY workspace_id, product_id, tier NULLS FIRST, agent_id NULLS FIRST"
        )
    ).mappings().all()
    if not rows:
        return

    books: dict[object, object] = {}
    versions: dict[object, object] = {}
    for row in rows:
        workspace_id = row["workspace_id"]
        if workspace_id not in books:
            book_id = uuid4()
            version_id = uuid4()
            bind.execute(
                sa.text(
                    "INSERT INTO b2b_price_books "
                    "(id, workspace_id, code, name, currency, status, is_default, "
                    "created_by, created_at, updated_at) "
                    "VALUES (:id, :workspace_id, :code, :name, :currency, 'active', "
                    "TRUE, 'migration-0036', now(), now())"
                ),
                {
                    "id": book_id,
                    "workspace_id": workspace_id,
                    "code": "DEFAULT",
                    "name": "默认 B2B 价格簿",
                    "currency": "USD",
                },
            )
            bind.execute(
                sa.text(
                    "INSERT INTO b2b_price_versions "
                    "(id, workspace_id, price_book_id, version_number, status, "
                    "effective_from, approved_by, approved_at, created_by, "
                    "created_at, updated_at) "
                    "VALUES (:id, :workspace_id, :book_id, 1, 'active', "
                    ":effective_from, 'migration-0036', now(), "
                    "'migration-0036', now(), now())"
                ),
                {
                    "id": version_id,
                    "workspace_id": workspace_id,
                    "book_id": book_id,
                    "effective_from": date(1970, 1, 1),
                },
            )
            books[workspace_id] = book_id
            versions[workspace_id] = version_id

        bind.execute(
            sa.text(
                "INSERT INTO b2b_price_tiers "
                "(id, workspace_id, price_version_id, product_id, tier, agent_id, "
                "min_quantity, max_quantity, unit_price, currency, is_active, "
                "created_at, updated_at) "
                "VALUES (:id, :workspace_id, :version_id, :product_id, :tier, "
                ":agent_id, :min_quantity, NULL, :unit_price, :currency, "
                ":is_active, now(), now())"
            ),
            {
                "id": uuid4(),
                "workspace_id": workspace_id,
                "version_id": versions[workspace_id],
                "product_id": row["product_id"],
                "tier": row["tier"],
                "agent_id": row["agent_id"],
                "min_quantity": max(int(row["moq"] or 1), 1),
                "unit_price": row["wholesale_price"],
                "currency": row["currency"] or "USD",
                "is_active": bool(row["is_active"]),
            },
        )


def upgrade() -> None:
    op.create_table(
        "b2b_price_books",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "code",
            name="uq_b2b_price_books_workspace_code",
        ),
    )
    op.create_index(
        "ix_b2b_price_books_workspace_id",
        "b2b_price_books",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_price_books_workspace_status",
        "b2b_price_books",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_b2b_price_books_workspace_default",
        "b2b_price_books",
        ["workspace_id", "is_default"],
    )
    op.create_index(
        "uq_b2b_price_books_workspace_default_active",
        "b2b_price_books",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE AND status = 'active'"),
        sqlite_where=sa.text("is_default = 1 AND status = 'active'"),
    )

    op.create_table(
        "b2b_price_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("price_book_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("submitted_by", sa.String(128), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
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
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_b2b_price_version_effective_period",
        ),
        sa.ForeignKeyConstraint(
            ["price_book_id"],
            ["b2b_price_books.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "price_book_id",
            "version_number",
            name="uq_b2b_price_versions_book_version",
        ),
    )
    op.create_index(
        "ix_b2b_price_versions_workspace_id",
        "b2b_price_versions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_price_versions_price_book_id",
        "b2b_price_versions",
        ["price_book_id"],
    )
    op.create_index(
        "ix_b2b_price_versions_status",
        "b2b_price_versions",
        ["status"],
    )
    op.create_index(
        "ix_b2b_price_versions_book_status",
        "b2b_price_versions",
        ["workspace_id", "price_book_id", "status"],
    )
    op.create_index(
        "ix_b2b_price_versions_effective",
        "b2b_price_versions",
        ["workspace_id", "effective_from", "effective_to"],
    )
    op.create_index(
        "uq_b2b_price_versions_one_active",
        "b2b_price_versions",
        ["workspace_id", "price_book_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "b2b_price_tiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("price_version_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("tier", sa.String(16), nullable=True),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("min_quantity", sa.Integer(), nullable=False),
        sa.Column("max_quantity", sa.Integer(), nullable=True),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
            "(tier IS NOT NULL AND agent_id IS NULL) "
            "OR (tier IS NULL AND agent_id IS NOT NULL)",
            name="ck_b2b_price_tier_exactly_one_scope",
        ),
        sa.CheckConstraint(
            "min_quantity >= 1",
            name="ck_b2b_price_tier_min_quantity",
        ),
        sa.CheckConstraint(
            "max_quantity IS NULL OR max_quantity > min_quantity",
            name="ck_b2b_price_tier_quantity_range",
        ),
        sa.CheckConstraint(
            "unit_price > 0",
            name="ck_b2b_price_tier_unit_price",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["b2b_agents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["price_version_id"],
            ["b2b_price_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_b2b_price_tiers_workspace_id",
        "b2b_price_tiers",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_price_tiers_price_version_id",
        "b2b_price_tiers",
        ["price_version_id"],
    )
    op.create_index(
        "ix_b2b_price_tiers_product_id",
        "b2b_price_tiers",
        ["product_id"],
    )
    op.create_index(
        "ix_b2b_price_tiers_agent_id",
        "b2b_price_tiers",
        ["agent_id"],
    )
    op.create_index(
        "ix_b2b_price_tiers_version_product_tier",
        "b2b_price_tiers",
        ["workspace_id", "price_version_id", "product_id", "tier"],
    )
    op.create_index(
        "ix_b2b_price_tiers_version_product_agent",
        "b2b_price_tiers",
        ["workspace_id", "price_version_id", "product_id", "agent_id"],
    )

    op.add_column(
        "b2b_order_items",
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
    )
    op.add_column(
        "b2b_order_items",
        sa.Column("price_book_version_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "b2b_order_items",
        sa.Column("price_tier_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "b2b_order_items",
        sa.Column("price_source", sa.String(16), nullable=False, server_default="TIER"),
    )
    op.create_foreign_key(
        "fk_b2b_order_items_price_version",
        "b2b_order_items",
        "b2b_price_versions",
        ["price_book_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_b2b_order_items_price_tier",
        "b2b_order_items",
        "b2b_price_tiers",
        ["price_tier_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_b2b_order_items_price_book_version_id",
        "b2b_order_items",
        ["price_book_version_id"],
    )
    op.create_index(
        "ix_b2b_order_items_price_tier_id",
        "b2b_order_items",
        ["price_tier_id"],
    )
    op.create_check_constraint(
        "ck_b2b_order_item_price_source",
        "b2b_order_items",
        "price_source IN ('TIER', 'AGENT', 'QUOTE')",
    )

    _insert_legacy_price_backfill()


def downgrade() -> None:
    op.drop_constraint(
        "ck_b2b_order_item_price_source",
        "b2b_order_items",
        type_="check",
    )
    op.drop_index(
        "ix_b2b_order_items_price_tier_id",
        table_name="b2b_order_items",
    )
    op.drop_index(
        "ix_b2b_order_items_price_book_version_id",
        table_name="b2b_order_items",
    )
    op.drop_constraint(
        "fk_b2b_order_items_price_tier",
        "b2b_order_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_b2b_order_items_price_version",
        "b2b_order_items",
        type_="foreignkey",
    )
    op.drop_column("b2b_order_items", "price_source")
    op.drop_column("b2b_order_items", "price_tier_id")
    op.drop_column("b2b_order_items", "price_book_version_id")
    op.drop_column("b2b_order_items", "currency")

    op.drop_index("ix_b2b_price_tiers_version_product_agent", table_name="b2b_price_tiers")
    op.drop_index("ix_b2b_price_tiers_version_product_tier", table_name="b2b_price_tiers")
    op.drop_index("ix_b2b_price_tiers_agent_id", table_name="b2b_price_tiers")
    op.drop_index("ix_b2b_price_tiers_product_id", table_name="b2b_price_tiers")
    op.drop_index("ix_b2b_price_tiers_price_version_id", table_name="b2b_price_tiers")
    op.drop_index("ix_b2b_price_tiers_workspace_id", table_name="b2b_price_tiers")
    op.drop_table("b2b_price_tiers")

    op.drop_index("uq_b2b_price_versions_one_active", table_name="b2b_price_versions")
    op.drop_index("ix_b2b_price_versions_effective", table_name="b2b_price_versions")
    op.drop_index("ix_b2b_price_versions_book_status", table_name="b2b_price_versions")
    op.drop_index("ix_b2b_price_versions_status", table_name="b2b_price_versions")
    op.drop_index("ix_b2b_price_versions_price_book_id", table_name="b2b_price_versions")
    op.drop_index("ix_b2b_price_versions_workspace_id", table_name="b2b_price_versions")
    op.drop_table("b2b_price_versions")

    op.drop_index(
        "uq_b2b_price_books_workspace_default_active",
        table_name="b2b_price_books",
    )
    op.drop_index("ix_b2b_price_books_workspace_default", table_name="b2b_price_books")
    op.drop_index("ix_b2b_price_books_workspace_status", table_name="b2b_price_books")
    op.drop_index("ix_b2b_price_books_workspace_id", table_name="b2b_price_books")
    op.drop_table("b2b_price_books")
