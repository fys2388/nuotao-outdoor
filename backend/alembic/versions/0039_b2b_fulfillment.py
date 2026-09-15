"""B2B order fulfillment linkage to WMS inventory and TMS shipments.

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shipment_records",
        sa.Column("b2b_order_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_shipment_records_b2b_order_id",
        "shipment_records",
        "b2b_orders",
        ["b2b_order_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_shipment_records_b2b_order_id",
        "shipment_records",
        ["b2b_order_id"],
    )

    op.create_table(
        "b2b_order_fulfillments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("fulfillment_number", sa.String(32), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="reserved"),
        sa.Column("warehouse_location", sa.String(32), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=True),
        sa.Column("reservation_key", sa.String(128), nullable=True),
        sa.Column("shipment_key", sa.String(128), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=True),
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
            "warehouse_location IN ('cn', 'us', 'eu')",
            name="ck_b2b_fulfillment_warehouse",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["b2b_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shipment_id"],
            ["shipment_records.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "fulfillment_number",
            name="uq_b2b_fulfillments_workspace_number",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "order_id",
            name="uq_b2b_fulfillments_workspace_order",
        ),
    )
    op.create_index(
        "ix_b2b_order_fulfillments_workspace_id",
        "b2b_order_fulfillments",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_order_fulfillments_order_id",
        "b2b_order_fulfillments",
        ["order_id"],
    )
    op.create_index(
        "ix_b2b_order_fulfillments_status",
        "b2b_order_fulfillments",
        ["status"],
    )
    op.create_index(
        "ix_b2b_order_fulfillments_shipment_id",
        "b2b_order_fulfillments",
        ["shipment_id"],
    )
    op.create_index(
        "ix_b2b_fulfillments_workspace_status",
        "b2b_order_fulfillments",
        ["workspace_id", "status"],
    )

    op.create_table(
        "b2b_order_fulfillment_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("fulfillment_id", sa.Uuid(), nullable=False),
        sa.Column("order_item_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False),
        sa.Column("shipped_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("released_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_b2b_fulfillment_item_quantity",
        ),
        sa.CheckConstraint(
            "reserved_quantity >= 0 AND shipped_quantity >= 0 "
            "AND released_quantity >= 0",
            name="ck_b2b_fulfillment_item_nonnegative",
        ),
        sa.CheckConstraint(
            "shipped_quantity + released_quantity <= quantity",
            name="ck_b2b_fulfillment_item_balance",
        ),
        sa.ForeignKeyConstraint(
            ["fulfillment_id"],
            ["b2b_order_fulfillments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_snapshot_id"],
            ["inventory_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"],
            ["b2b_order_items.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fulfillment_id",
            "order_item_id",
            name="uq_b2b_fulfillment_items_order_line",
        ),
    )
    op.create_index(
        "ix_b2b_order_fulfillment_items_workspace_id",
        "b2b_order_fulfillment_items",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_order_fulfillment_items_fulfillment_id",
        "b2b_order_fulfillment_items",
        ["fulfillment_id"],
    )
    op.create_index(
        "ix_b2b_order_fulfillment_items_product_id",
        "b2b_order_fulfillment_items",
        ["product_id"],
    )
    op.create_index(
        "ix_b2b_order_fulfillment_items_inventory_snapshot_id",
        "b2b_order_fulfillment_items",
        ["inventory_snapshot_id"],
    )
    op.create_index(
        "ix_b2b_fulfillment_items_workspace_product",
        "b2b_order_fulfillment_items",
        ["workspace_id", "product_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_b2b_fulfillment_items_workspace_product",
        table_name="b2b_order_fulfillment_items",
    )
    op.drop_index(
        "ix_b2b_order_fulfillment_items_inventory_snapshot_id",
        table_name="b2b_order_fulfillment_items",
    )
    op.drop_index(
        "ix_b2b_order_fulfillment_items_product_id",
        table_name="b2b_order_fulfillment_items",
    )
    op.drop_index(
        "ix_b2b_order_fulfillment_items_fulfillment_id",
        table_name="b2b_order_fulfillment_items",
    )
    op.drop_index(
        "ix_b2b_order_fulfillment_items_workspace_id",
        table_name="b2b_order_fulfillment_items",
    )
    op.drop_table("b2b_order_fulfillment_items")

    op.drop_index(
        "ix_b2b_fulfillments_workspace_status",
        table_name="b2b_order_fulfillments",
    )
    op.drop_index(
        "ix_b2b_order_fulfillments_shipment_id",
        table_name="b2b_order_fulfillments",
    )
    op.drop_index(
        "ix_b2b_order_fulfillments_status",
        table_name="b2b_order_fulfillments",
    )
    op.drop_index(
        "ix_b2b_order_fulfillments_order_id",
        table_name="b2b_order_fulfillments",
    )
    op.drop_index(
        "ix_b2b_order_fulfillments_workspace_id",
        table_name="b2b_order_fulfillments",
    )
    op.drop_table("b2b_order_fulfillments")

    op.drop_index(
        "ix_shipment_records_b2b_order_id",
        table_name="shipment_records",
    )
    op.drop_constraint(
        "fk_shipment_records_b2b_order_id",
        "shipment_records",
        type_="foreignkey",
    )
    op.drop_column("shipment_records", "b2b_order_id")
