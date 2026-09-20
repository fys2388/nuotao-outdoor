"""B2C + B2B P0 compatibility hardening.

Adds tenant boundaries to B2B tables, introduces unified customer accounts,
separates order idempotency by source, and records explicit business models.

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-13
"""

from __future__ import annotations

import hashlib
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

_COUNTRY_CODES = {
    "australia": "AU",
    "canada": "CA",
    "china": "CN",
    "france": "FR",
    "germany": "DE",
    "hong kong": "HK",
    "italy": "IT",
    "japan": "JP",
    "netherlands": "NL",
    "singapore": "SG",
    "spain": "ES",
    "united kingdom": "GB",
    "united states": "US",
}


def _country_code(value: str | None) -> str | None:
    """Normalize legacy country labels to the storage-width ISO codes."""
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) <= 2 and normalized.isalpha():
        return normalized.upper()
    mapped = _COUNTRY_CODES.get(normalized.casefold())
    if mapped:
        return mapped
    if len(normalized) <= 8:
        return normalized
    return None


def _customer_accounts_table() -> sa.TableClause:
    return sa.table(
        "customer_accounts",
        sa.column("id", sa.Uuid()),
        sa.column("workspace_id", sa.Uuid()),
        sa.column("customer_number", sa.String()),
        sa.column("customer_type", sa.String()),
        sa.column("business_model", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("status", sa.String()),
        sa.column("country", sa.String()),
        sa.column("default_currency", sa.String()),
    )


def _backfill_b2b_customer_accounts() -> None:
    bind = op.get_bind()
    accounts = _customer_accounts_table()
    rows = bind.execute(
        sa.text(
            "SELECT id, workspace_id, agent_number, company_name, country, currency "
            "FROM b2b_agents"
        )
    ).mappings()
    for row in rows:
        account_id = uuid4()
        bind.execute(
            accounts.insert().values(
                id=account_id,
                workspace_id=row["workspace_id"],
                customer_number=f"B2B-{row['agent_number']}",
                customer_type="WHOLESALER",
                business_model="B2B",
                display_name=row["company_name"],
                status="active",
                country=_country_code(row["country"]),
                default_currency=row["currency"] or "USD",
            )
        )
        bind.execute(
            sa.text(
                "UPDATE b2b_agents SET customer_account_id = :account_id "
                "WHERE id = :agent_id"
            ),
            {"account_id": account_id, "agent_id": row["id"]},
        )


def _backfill_b2c_customer_accounts() -> None:
    bind = op.get_bind()
    accounts = _customer_accounts_table()
    rows = bind.execute(
        sa.text(
            "SELECT id, workspace_id, customer_reference_id, country "
            "FROM customer_profiles"
        )
    ).mappings()
    for row in rows:
        reference = row["customer_reference_id"]
        digest = hashlib.sha256(reference.encode("utf-8")).hexdigest()[:24]
        account_id = uuid4()
        bind.execute(
            accounts.insert().values(
                id=account_id,
                workspace_id=row["workspace_id"],
                customer_number=f"B2C-{digest}",
                customer_type="CONSUMER",
                business_model="B2C",
                display_name=None,
                status="active",
                country=_country_code(row["country"]),
                default_currency="USD",
            )
        )
        bind.execute(
            sa.text(
                "UPDATE customer_profiles SET customer_account_id = :account_id "
                "WHERE id = :profile_id"
            ),
            {"account_id": account_id, "profile_id": row["id"]},
        )


def upgrade() -> None:
    op.create_table(
        "customer_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("customer_number", sa.String(64), nullable=False),
        sa.Column("customer_type", sa.String(32), nullable=False),
        sa.Column("business_model", sa.String(8), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("country", sa.String(8), nullable=True),
        sa.Column("default_currency", sa.String(8), nullable=False, server_default="USD"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "customer_number",
            name="uq_customer_accounts_workspace_number",
        ),
    )
    op.create_index(
        "ix_customer_accounts_workspace_id",
        "customer_accounts",
        ["workspace_id"],
    )
    op.create_index(
        "ix_customer_accounts_workspace_type",
        "customer_accounts",
        ["workspace_id", "customer_type"],
    )
    op.create_index(
        "ix_customer_accounts_workspace_business_model",
        "customer_accounts",
        ["workspace_id", "business_model"],
    )

    op.add_column("customer_profiles", sa.Column("customer_account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_customer_profiles_customer_account",
        "customer_profiles",
        "customer_accounts",
        ["customer_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_customer_profiles_customer_account_id",
        "customer_profiles",
        ["customer_account_id"],
    )

    op.add_column("orders", sa.Column("business_model", sa.String(8), nullable=False, server_default="B2C"))
    op.drop_constraint("uq_orders_workspace_external", "orders", type_="unique")
    op.create_unique_constraint(
        "uq_orders_workspace_source_external",
        "orders",
        ["workspace_id", "source", "external_order_id"],
    )

    for table_name in ("b2b_agents", "b2b_product_prices", "b2b_orders", "b2b_order_items"):
        op.add_column(table_name, sa.Column("workspace_id", sa.Uuid(), nullable=True))
        op.create_index(
            f"ix_{table_name}_workspace_id",
            table_name,
            ["workspace_id"],
        )

    op.execute(
        sa.text(
            "UPDATE b2b_agents SET workspace_id = CAST(:workspace_id AS UUID) "
            "WHERE workspace_id IS NULL"
        ).bindparams(workspace_id=DEFAULT_WORKSPACE_ID)
    )
    op.execute(
        sa.text(
            "UPDATE b2b_product_prices SET workspace_id = CAST(:workspace_id AS UUID) "
            "WHERE workspace_id IS NULL"
        ).bindparams(workspace_id=DEFAULT_WORKSPACE_ID)
    )
    op.execute(
        sa.text(
            "UPDATE b2b_orders SET workspace_id = CAST(:workspace_id AS UUID) "
            "WHERE workspace_id IS NULL"
        ).bindparams(workspace_id=DEFAULT_WORKSPACE_ID)
    )
    op.execute(
        sa.text(
            "UPDATE b2b_order_items i SET workspace_id = o.workspace_id "
            "FROM b2b_orders o "
            "WHERE i.order_id = o.id AND i.workspace_id IS NULL"
        )
    )
    for table_name in ("b2b_agents", "b2b_product_prices", "b2b_orders", "b2b_order_items"):
        op.alter_column(table_name, "workspace_id", nullable=False)

    op.add_column("b2b_agents", sa.Column("customer_account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_b2b_agents_customer_account",
        "b2b_agents",
        "customer_accounts",
        ["customer_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_b2b_agents_customer_account_id",
        "b2b_agents",
        ["customer_account_id"],
    )

    op.add_column("b2b_orders", sa.Column("customer_account_id", sa.Uuid(), nullable=True))
    op.add_column(
        "b2b_orders",
        sa.Column("business_model", sa.String(8), nullable=False, server_default="B2B"),
    )
    op.create_foreign_key(
        "fk_b2b_orders_customer_account",
        "b2b_orders",
        "customer_accounts",
        ["customer_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_b2b_orders_customer_account_id",
        "b2b_orders",
        ["customer_account_id"],
    )

    _backfill_b2b_customer_accounts()
    _backfill_b2c_customer_accounts()
    op.execute(
        sa.text(
            "UPDATE b2b_orders o SET customer_account_id = a.customer_account_id "
            "FROM b2b_agents a "
            "WHERE o.agent_id = a.id AND o.customer_account_id IS NULL"
        )
    )

    op.drop_constraint("uq_b2b_agents_agent_number", "b2b_agents", type_="unique")
    op.drop_constraint("uq_b2b_agents_email", "b2b_agents", type_="unique")
    op.create_unique_constraint(
        "uq_b2b_agents_workspace_number",
        "b2b_agents",
        ["workspace_id", "agent_number"],
    )
    op.create_unique_constraint(
        "uq_b2b_agents_workspace_email",
        "b2b_agents",
        ["workspace_id", "email"],
    )
    op.create_index(
        "ix_b2b_agents_workspace_status",
        "b2b_agents",
        ["workspace_id", "status"],
    )

    op.drop_constraint("uq_b2b_price_product_tier", "b2b_product_prices", type_="unique")
    op.drop_constraint("uq_b2b_price_product_agent", "b2b_product_prices", type_="unique")
    op.create_check_constraint(
        "ck_b2b_price_exactly_one_scope",
        "b2b_product_prices",
        "(tier IS NOT NULL AND agent_id IS NULL) "
        "OR (tier IS NULL AND agent_id IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_b2b_price_workspace_product_tier",
        "b2b_product_prices",
        ["workspace_id", "product_id", "tier"],
    )
    op.create_unique_constraint(
        "uq_b2b_price_workspace_product_agent",
        "b2b_product_prices",
        ["workspace_id", "product_id", "agent_id"],
    )

    op.drop_constraint("uq_b2b_orders_order_number", "b2b_orders", type_="unique")
    op.create_unique_constraint(
        "uq_b2b_orders_workspace_number",
        "b2b_orders",
        ["workspace_id", "order_number"],
    )
    op.create_index(
        "ix_b2b_orders_workspace_agent",
        "b2b_orders",
        ["workspace_id", "agent_id"],
    )
    op.create_index(
        "ix_b2b_orders_workspace_status",
        "b2b_orders",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_b2b_orders_workspace_payment_status",
        "b2b_orders",
        ["workspace_id", "payment_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_b2b_orders_workspace_payment_status", table_name="b2b_orders")
    op.drop_index("ix_b2b_orders_workspace_status", table_name="b2b_orders")
    op.drop_index("ix_b2b_orders_workspace_agent", table_name="b2b_orders")
    op.drop_constraint("uq_b2b_orders_workspace_number", "b2b_orders", type_="unique")
    op.create_unique_constraint("uq_b2b_orders_order_number", "b2b_orders", ["order_number"])

    op.drop_constraint("uq_b2b_price_workspace_product_agent", "b2b_product_prices", type_="unique")
    op.drop_constraint("uq_b2b_price_workspace_product_tier", "b2b_product_prices", type_="unique")
    op.drop_constraint(
        "ck_b2b_price_exactly_one_scope",
        "b2b_product_prices",
        type_="check",
    )
    op.create_unique_constraint(
        "uq_b2b_price_product_agent",
        "b2b_product_prices",
        ["product_id", "agent_id"],
    )
    op.create_unique_constraint(
        "uq_b2b_price_product_tier",
        "b2b_product_prices",
        ["product_id", "tier"],
    )

    op.drop_index("ix_b2b_agents_workspace_status", table_name="b2b_agents")
    op.drop_constraint("uq_b2b_agents_workspace_email", "b2b_agents", type_="unique")
    op.drop_constraint("uq_b2b_agents_workspace_number", "b2b_agents", type_="unique")
    op.create_unique_constraint("uq_b2b_agents_email", "b2b_agents", ["email"])
    op.create_unique_constraint("uq_b2b_agents_agent_number", "b2b_agents", ["agent_number"])

    op.drop_index("ix_b2b_orders_customer_account_id", table_name="b2b_orders")
    op.drop_constraint("fk_b2b_orders_customer_account", "b2b_orders", type_="foreignkey")
    op.drop_column("b2b_orders", "business_model")
    op.drop_column("b2b_orders", "customer_account_id")

    op.drop_index("ix_b2b_agents_customer_account_id", table_name="b2b_agents")
    op.drop_constraint("fk_b2b_agents_customer_account", "b2b_agents", type_="foreignkey")
    op.drop_column("b2b_agents", "customer_account_id")

    for table_name in ("b2b_order_items", "b2b_orders", "b2b_product_prices", "b2b_agents"):
        op.drop_index(f"ix_{table_name}_workspace_id", table_name=table_name)
        op.drop_column(table_name, "workspace_id")

    op.drop_constraint("uq_orders_workspace_source_external", "orders", type_="unique")
    op.create_unique_constraint(
        "uq_orders_workspace_external",
        "orders",
        ["workspace_id", "external_order_id"],
    )
    op.drop_column("orders", "business_model")

    op.drop_index(
        "ix_customer_profiles_customer_account_id",
        table_name="customer_profiles",
    )
    op.drop_constraint(
        "fk_customer_profiles_customer_account",
        "customer_profiles",
        type_="foreignkey",
    )
    op.drop_column("customer_profiles", "customer_account_id")

    op.drop_index(
        "ix_customer_accounts_workspace_business_model",
        table_name="customer_accounts",
    )
    op.drop_index(
        "ix_customer_accounts_workspace_type",
        table_name="customer_accounts",
    )
    op.drop_index("ix_customer_accounts_workspace_id", table_name="customer_accounts")
    op.drop_table("customer_accounts")
