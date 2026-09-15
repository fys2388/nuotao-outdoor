"""Add cross-channel identity, consent, and data subject request controls.

Revision ID: 0045
Revises: 0044
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customer_accounts",
        sa.Column("merged_into_account_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "customer_accounts",
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_customer_accounts_merged_into",
        "customer_accounts",
        "customer_accounts",
        ["merged_into_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_customer_accounts_merged_into_account_id",
        "customer_accounts",
        ["merged_into_account_id"],
    )

    op.add_column(
        "orders",
        sa.Column("customer_account_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_orders_customer_account_id",
        "orders",
        "customer_accounts",
        ["customer_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_orders_customer_account_id",
        "orders",
        ["customer_account_id"],
    )

    op.add_column(
        "email_subscriptions",
        sa.Column("customer_account_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_email_subscriptions_customer_account_id",
        "email_subscriptions",
        "customer_accounts",
        ["customer_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_email_subscriptions_customer_account_id",
        "email_subscriptions",
        ["customer_account_id"],
    )

    op.create_table(
        "customer_identity_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("customer_account_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("external_system", sa.String(64), nullable=False),
        sa.Column("identity_type", sa.String(32), nullable=False),
        sa.Column("identity_hash", sa.String(128), nullable=False),
        sa.Column(
            "hash_key_version",
            sa.String(32),
            nullable=False,
            server_default="v1",
        ),
        sa.Column("fingerprint", sa.String(32), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(16),
            nullable=False,
            server_default="verified",
        ),
        sa.Column("source", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
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
            "channel IN ("
            "'b2c_store','b2b_portal','email','support','crm','other'"
            ")",
            name="ck_customer_identity_link_channel",
        ),
        sa.CheckConstraint(
            "identity_type IN ("
            "'email','phone','woocommerce_customer_id','company_tax_id','other'"
            ")",
            name="ck_customer_identity_link_type",
        ),
        sa.CheckConstraint(
            "verification_status IN ("
            "'pending','verified','conflict','rejected','revoked','merged'"
            ")",
            name="ck_customer_identity_link_status",
        ),
        sa.ForeignKeyConstraint(
            ["customer_account_id"],
            ["customer_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "customer_account_id",
            "channel",
            "external_system",
            "identity_type",
            "identity_hash",
            name="uq_customer_identity_links_account_identity",
        ),
    )
    for name, columns in (
        ("ix_customer_identity_links_workspace_id", ["workspace_id"]),
        ("ix_customer_identity_links_customer_account_id", ["customer_account_id"]),
        ("ix_customer_identity_links_channel", ["channel"]),
        ("ix_customer_identity_links_external_system", ["external_system"]),
        ("ix_customer_identity_links_identity_type", ["identity_type"]),
        ("ix_customer_identity_links_identity_hash", ["identity_hash"]),
        ("ix_customer_identity_links_verification_status", ["verification_status"]),
        (
            "ix_customer_identity_links_workspace_hash",
            ["workspace_id", "identity_type", "identity_hash"],
        ),
        (
            "ix_customer_identity_links_workspace_account_status",
            ["workspace_id", "customer_account_id", "verification_status"],
        ),
    ):
        op.create_index(name, "customer_identity_links", columns)

    op.create_table(
        "customer_account_merges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_account_id", sa.Uuid(), nullable=False),
        sa.Column("target_account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("match_type", sa.String(32), nullable=False),
        sa.Column("match_hash", sa.String(128), nullable=False),
        sa.Column(
            "evidence_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("completed_by", sa.String(128), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "result_summary",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
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
            "status IN ('pending','approved','rejected','completed','cancelled')",
            name="ck_customer_account_merge_status",
        ),
        sa.CheckConstraint(
            "source_account_id <> target_account_id",
            name="ck_customer_account_merge_distinct_accounts",
        ),
        sa.ForeignKeyConstraint(
            ["source_account_id"],
            ["customer_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_account_id"],
            ["customer_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_customer_account_merges_workspace_id", ["workspace_id"]),
        ("ix_customer_account_merges_source_account_id", ["source_account_id"]),
        ("ix_customer_account_merges_target_account_id", ["target_account_id"]),
        ("ix_customer_account_merges_status", ["status"]),
        ("ix_customer_account_merges_workspace_status", ["workspace_id", "status"]),
        (
            "ix_customer_account_merges_source_status",
            ["workspace_id", "source_account_id", "status"],
        ),
    ):
        op.create_index(name, "customer_account_merges", columns)

    op.create_table(
        "customer_consent_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("customer_account_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("recorded_by", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "evidence_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "purpose IN ("
            "'marketing_email','transactional_email','analytics',"
            "'personalization','ai_processing'"
            ")",
            name="ck_customer_consent_event_purpose",
        ),
        sa.CheckConstraint(
            "channel IN ("
            "'b2c_store','b2b_portal','email','support','crm','other'"
            ")",
            name="ck_customer_consent_event_channel",
        ),
        sa.CheckConstraint(
            "status IN ('granted','withdrawn')",
            name="ck_customer_consent_event_status",
        ),
        sa.ForeignKeyConstraint(
            ["customer_account_id"],
            ["customer_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_customer_consent_events_workspace_idempotency",
        ),
    )
    for name, columns in (
        ("ix_customer_consent_events_workspace_id", ["workspace_id"]),
        ("ix_customer_consent_events_customer_account_id", ["customer_account_id"]),
        ("ix_customer_consent_events_purpose", ["purpose"]),
        ("ix_customer_consent_events_channel", ["channel"]),
        ("ix_customer_consent_events_status", ["status"]),
        ("ix_customer_consent_events_occurred_at", ["occurred_at"]),
        (
            "ix_customer_consent_events_workspace_account_purpose",
            [
                "workspace_id",
                "customer_account_id",
                "purpose",
                "channel",
                "occurred_at",
            ],
        ),
    ):
        op.create_index(name, "customer_consent_events", columns)

    op.create_table(
        "data_subject_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("request_number", sa.String(48), nullable=False),
        sa.Column("customer_account_id", sa.Uuid(), nullable=True),
        sa.Column("request_type", sa.String(16), nullable=False),
        sa.Column(
            "status",
            sa.String(24),
            nullable=False,
            server_default="received",
        ),
        sa.Column("identity_hash", sa.String(128), nullable=True),
        sa.Column("verification_method", sa.String(64), nullable=True),
        sa.Column("verified_by", sa.String(128), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_by", sa.String(128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("request_details", sa.Text(), nullable=True),
        sa.Column(
            "result_summary",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "evidence_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("requested_by", sa.String(128), nullable=False),
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
            "request_type IN ('access','export','delete','correct','restrict')",
            name="ck_data_subject_request_type",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'received','verifying','approved','processing','completed',"
            "'rejected','cancelled'"
            ")",
            name="ck_data_subject_request_status",
        ),
        sa.ForeignKeyConstraint(
            ["customer_account_id"],
            ["customer_accounts.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "request_number",
            name="uq_data_subject_requests_workspace_number",
        ),
    )
    for name, columns in (
        ("ix_data_subject_requests_workspace_id", ["workspace_id"]),
        ("ix_data_subject_requests_customer_account_id", ["customer_account_id"]),
        ("ix_data_subject_requests_request_type", ["request_type"]),
        ("ix_data_subject_requests_status", ["status"]),
        (
            "ix_data_subject_requests_workspace_status_due",
            ["workspace_id", "status", "due_at"],
        ),
    ):
        op.create_index(name, "data_subject_requests", columns)

    op.create_table(
        "data_subject_request_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(48), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "result_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "action_type IN ("
            "'received','verified','approved','rejected','export_generated',"
            "'identity_links_revoked','consent_withdrawn','profile_erased',"
            "'b2b_contact_anonymized','account_anonymized','completed',"
            "'manual_review'"
            ")",
            name="ck_data_subject_request_action_type",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["data_subject_requests.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_data_subject_request_actions_workspace_id", ["workspace_id"]),
        ("ix_data_subject_request_actions_request_id", ["request_id"]),
        ("ix_data_subject_request_actions_action_type", ["action_type"]),
        (
            "ix_data_subject_request_actions_workspace_request",
            ["workspace_id", "request_id", "created_at"],
        ),
    ):
        op.create_index(name, "data_subject_request_actions", columns)


def downgrade() -> None:
    for name in (
        "ix_data_subject_request_actions_workspace_request",
        "ix_data_subject_request_actions_action_type",
        "ix_data_subject_request_actions_request_id",
        "ix_data_subject_request_actions_workspace_id",
    ):
        op.drop_index(name, table_name="data_subject_request_actions")
    op.drop_table("data_subject_request_actions")

    for name in (
        "ix_data_subject_requests_workspace_status_due",
        "ix_data_subject_requests_status",
        "ix_data_subject_requests_request_type",
        "ix_data_subject_requests_customer_account_id",
        "ix_data_subject_requests_workspace_id",
    ):
        op.drop_index(name, table_name="data_subject_requests")
    op.drop_table("data_subject_requests")

    for name in (
        "ix_customer_consent_events_workspace_account_purpose",
        "ix_customer_consent_events_occurred_at",
        "ix_customer_consent_events_status",
        "ix_customer_consent_events_channel",
        "ix_customer_consent_events_purpose",
        "ix_customer_consent_events_customer_account_id",
        "ix_customer_consent_events_workspace_id",
    ):
        op.drop_index(name, table_name="customer_consent_events")
    op.drop_table("customer_consent_events")

    for name in (
        "ix_customer_account_merges_source_status",
        "ix_customer_account_merges_workspace_status",
        "ix_customer_account_merges_status",
        "ix_customer_account_merges_target_account_id",
        "ix_customer_account_merges_source_account_id",
        "ix_customer_account_merges_workspace_id",
    ):
        op.drop_index(name, table_name="customer_account_merges")
    op.drop_table("customer_account_merges")

    for name in (
        "ix_customer_identity_links_workspace_account_status",
        "ix_customer_identity_links_workspace_hash",
        "ix_customer_identity_links_verification_status",
        "ix_customer_identity_links_identity_hash",
        "ix_customer_identity_links_identity_type",
        "ix_customer_identity_links_external_system",
        "ix_customer_identity_links_channel",
        "ix_customer_identity_links_customer_account_id",
        "ix_customer_identity_links_workspace_id",
    ):
        op.drop_index(name, table_name="customer_identity_links")
    op.drop_table("customer_identity_links")

    op.drop_index(
        "ix_email_subscriptions_customer_account_id",
        table_name="email_subscriptions",
    )
    op.drop_constraint(
        "fk_email_subscriptions_customer_account_id",
        "email_subscriptions",
        type_="foreignkey",
    )
    op.drop_column("email_subscriptions", "customer_account_id")

    op.drop_index("ix_orders_customer_account_id", table_name="orders")
    op.drop_constraint(
        "fk_orders_customer_account_id",
        "orders",
        type_="foreignkey",
    )
    op.drop_column("orders", "customer_account_id")

    op.drop_index(
        "ix_customer_accounts_merged_into_account_id",
        table_name="customer_accounts",
    )
    op.drop_constraint(
        "fk_customer_accounts_merged_into",
        "customer_accounts",
        type_="foreignkey",
    )
    op.drop_column("customer_accounts", "merged_at")
    op.drop_column("customer_accounts", "merged_into_account_id")
