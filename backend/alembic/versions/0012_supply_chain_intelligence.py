"""M4.1: supply chain intelligence - suppliers, purchase orders, inventory, logistics, knowledge

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the M4.1 supply chain intelligence tables."""

    # --- supplier_profiles ------------------------------------------------------
    op.create_table(
        "supplier_profiles",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "supplier_id", UUID(), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("location", sa.String(128), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("minimum_order_qty", sa.Integer(), nullable=True),
        sa.Column("quality_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("on_time_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("defect_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("certifications", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_supplier_profiles_workspace_risk", "supplier_profiles", ["workspace_id", "risk_level"]
    )
    op.create_index("ix_supplier_profiles_supplier_id", "supplier_profiles", ["supplier_id"])
    op.execute(
        sa.text(
            "ALTER TABLE supplier_profiles ADD CONSTRAINT "
            "uq_supplier_profiles_workspace_supplier UNIQUE (workspace_id, supplier_id)"
        )
    )

    # --- purchase_orders --------------------------------------------------------
    op.create_table(
        "purchase_orders",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("po_number", sa.String(64), nullable=False),
        sa.Column(
            "supplier_id", UUID(), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("shipping_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("expected_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_purchase_orders_workspace_status", "purchase_orders", ["workspace_id", "status"]
    )
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])
    op.execute(
        sa.text(
            "ALTER TABLE purchase_orders ADD CONSTRAINT "
            "uq_purchase_orders_workspace_po UNIQUE (workspace_id, po_number)"
        )
    )

    # --- purchase_order_items ---------------------------------------------------
    op.create_table(
        "purchase_order_items",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "purchase_order_id",
            UUID(),
            sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_purchase_order_items_po_id", "purchase_order_items", ["purchase_order_id"])
    op.create_index("ix_purchase_order_items_product_id", "purchase_order_items", ["product_id"])

    # --- inventory_snapshots ------------------------------------------------------
    op.create_table(
        "inventory_snapshots",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("location", sa.String(32), nullable=False, server_default="cn-main"),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("in_transit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_inventory_workspace_location", "inventory_snapshots", ["workspace_id", "location"]
    )
    op.create_index("ix_inventory_snapshots_product_id", "inventory_snapshots", ["product_id"])
    op.execute(
        sa.text(
            "ALTER TABLE inventory_snapshots ADD CONSTRAINT "
            "uq_inventory_workspace_product_location UNIQUE (workspace_id, product_id, location)"
        )
    )

    # --- shipment_records ----------------------------------------------------------
    op.create_table(
        "shipment_records",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "purchase_order_id",
            UUID(),
            sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("carrier", sa.String(64), nullable=False),
        sa.Column("origin", sa.String(128), nullable=True),
        sa.Column("destination", sa.String(128), nullable=True),
        sa.Column("tracking_number", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="created"),
        sa.Column("ship_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_time_days", sa.Integer(), nullable=True),
        sa.Column("delay_reason", sa.String(500), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_shipments_workspace_status", "shipment_records", ["workspace_id", "status"])
    op.create_index(
        "ix_shipments_workspace_carrier", "shipment_records", ["workspace_id", "carrier"]
    )
    op.create_index("ix_shipments_purchase_order_id", "shipment_records", ["purchase_order_id"])

    # --- logistics_events ------------------------------------------------------------
    op.create_table(
        "logistics_events",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "shipment_id",
            UUID(),
            sa.ForeignKey("shipment_records.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("location", sa.String(128), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_logistics_events_workspace_shipment",
        "logistics_events",
        ["workspace_id", "shipment_id"],
    )
    op.create_index("ix_logistics_events_shipment_id", "logistics_events", ["shipment_id"])

    # --- supply_chain_knowledge_entries -----------------------------------------------
    op.create_table(
        "supply_chain_knowledge_entries",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "supplier_id", UUID(), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("entry_type", sa.String(32), nullable=False, server_default="supplier_pattern"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.String(4000), nullable=False),
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_supply_chain_knowledge_workspace_cat",
        "supply_chain_knowledge_entries",
        ["workspace_id", "category"],
    )
    op.create_index(
        "ix_supply_chain_knowledge_workspace_supplier",
        "supply_chain_knowledge_entries",
        ["workspace_id", "supplier_id"],
    )
    op.create_index(
        "ix_sc_knowledge_supplier_id", "supply_chain_knowledge_entries", ["supplier_id"]
    )
    op.create_index("ix_sc_knowledge_product_id", "supply_chain_knowledge_entries", ["product_id"])
    op.create_index("ix_sc_knowledge_entry_type", "supply_chain_knowledge_entries", ["entry_type"])


def downgrade() -> None:
    """Drop the M4.1 supply chain tables (not for production)."""
    op.drop_table("supply_chain_knowledge_entries")
    op.drop_table("logistics_events")
    op.drop_table("shipment_records")
    op.drop_table("inventory_snapshots")
    op.drop_table("purchase_order_items")
    op.drop_table("purchase_orders")
    op.drop_table("supplier_profiles")
