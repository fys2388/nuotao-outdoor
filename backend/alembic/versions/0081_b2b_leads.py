"""0081_b2b_leads

创建 B2B 公开网站线索表 b2b_leads。
公开「Request a Quote」询盘创建线索，绝不直接创建 b2b_agents 账号。
合格线索由内部运营显式转换为正式 B2B 合作伙伴申请（converted_application_id）。

Spec: reports/b2b/CHATGPT_M1_M2_SPEC.md (M1.1)

Revision ID: 0081
Revises: 0080
Create Date: 2026-11-11

"""
from alembic import context
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def _create() -> None:
    op.create_table(
        "b2b_leads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("reference_number", sa.String(32), nullable=False),
        # 必填询盘字段
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("contact_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("country", sa.String(64), nullable=False),
        sa.Column("business_type", sa.String(32), nullable=False),
        sa.Column("products_of_interest", postgresql.JSONB(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("privacy_consent", sa.Boolean(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        # 可选询盘字段
        sa.Column("company_website", sa.String(255), nullable=True),
        sa.Column("whatsapp", sa.String(64), nullable=True),
        sa.Column("wechat", sa.String(64), nullable=True),
        sa.Column("estimated_order_quantity", sa.String(64), nullable=True),
        sa.Column("annual_purchase_range", sa.String(64), nullable=True),
        sa.Column("destination_market", sa.String(120), nullable=True),
        # 来源与生命周期（服务端控制）
        sa.Column("source", sa.String(32), nullable=False, server_default="b2b_public_website"),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        # 内部管理字段（绝不通过公开路由暴露）
        sa.Column("assigned_to", sa.String(128), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("follow_ups", postgresql.JSONB(), nullable=True),
        # 转正式申请
        sa.Column("converted_application_id", sa.Uuid(), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        # 时间戳
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["converted_application_id"], ["b2b_agents.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "status IN ('new','reviewing','qualified','contacted','closed')",
            name="ck_b2b_leads_status",
        ),
        sa.CheckConstraint(
            "source IN ('b2b_public_website','manual')",
            name="ck_b2b_leads_source",
        ),
        sa.UniqueConstraint("reference_number", name="uq_b2b_leads_reference_number"),
        sa.Index("ix_b2b_leads_workspace_id", "workspace_id"),
        sa.Index("ix_b2b_leads_status_created", "status", "created_at"),
        sa.Index("ix_b2b_leads_email", "email"),
        sa.Index("ix_b2b_leads_country", "country"),
        sa.Index("ix_b2b_leads_converted_application_id", "converted_application_id"),
    )


def upgrade() -> None:
    # Offline (dry-run) mode only compiles SQL and never executes, so emit the
    # full DDL (CREATE TABLE IF NOT EXISTS) without inspecting live schema.
    if context.is_offline_mode():
        op.create_table(
            "b2b_leads",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("workspace_id", sa.Uuid(), nullable=False),
            sa.Column("reference_number", sa.String(32), nullable=False),
            sa.Column("company_name", sa.String(200), nullable=False),
            sa.Column("contact_name", sa.String(100), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("country", sa.String(64), nullable=False),
            sa.Column("business_type", sa.String(32), nullable=False),
            sa.Column("products_of_interest", postgresql.JSONB(), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("privacy_consent", sa.Boolean(), nullable=False),
            sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("company_website", sa.String(255), nullable=True),
            sa.Column("whatsapp", sa.String(64), nullable=True),
            sa.Column("wechat", sa.String(64), nullable=True),
            sa.Column("estimated_order_quantity", sa.String(64), nullable=True),
            sa.Column("annual_purchase_range", sa.String(64), nullable=True),
            sa.Column("destination_market", sa.String(120), nullable=True),
            sa.Column("source", sa.String(32), nullable=False, server_default="b2b_public_website"),
            sa.Column("status", sa.String(16), nullable=False, server_default="new"),
            sa.Column("assigned_to", sa.String(128), nullable=True),
            sa.Column("internal_notes", sa.Text(), nullable=True),
            sa.Column("follow_ups", postgresql.JSONB(), nullable=True),
            sa.Column("converted_application_id", sa.Uuid(), nullable=True),
            sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ["converted_application_id"], ["b2b_agents.id"], ondelete="SET NULL"
            ),
            sa.CheckConstraint(
                "status IN ('new','reviewing','qualified','contacted','closed')",
                name="ck_b2b_leads_status",
            ),
            sa.CheckConstraint(
                "source IN ('b2b_public_website','manual')",
                name="ck_b2b_leads_source",
            ),
            sa.UniqueConstraint("reference_number", name="uq_b2b_leads_reference_number"),
            sa.Index("ix_b2b_leads_workspace_id", "workspace_id"),
            sa.Index("ix_b2b_leads_status_created", "status", "created_at"),
            sa.Index("ix_b2b_leads_email", "email"),
            sa.Index("ix_b2b_leads_country", "country"),
            sa.Index("ix_b2b_leads_converted_application_id", "converted_application_id"),
            if_not_exists=True,
        )
        return

    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "b2b_leads" in insp.get_table_names():
        # The table (and its columns / indexes) already exists - e.g. a
        # previously hand-built schema. Skipping the whole create avoids the
        # DuplicateTableError on ix_b2b_leads_converted_application_id, which
        # if_not_exists=True does NOT cover (it only guards the CREATE TABLE,
        # not the CREATE INDEX statements Alembic emits for in-table Indexes).
        return
    _create()


def downgrade() -> None:
    op.drop_table("b2b_leads")
