"""0082_b2b_showcase_flags

为公开 B2B 展示目录增加产品级控制：
- b2b_showcase_enabled: 仅显式开启的产品才会出现在公开无价格目录（默认 false）。
- b2b_public_slug: 公开 URL 使用的稳定 slug，避免暴露内部 SKU。

Spec: reports/b2b/CHATGPT_M1_M2_SPEC.md (M1.3)

Revision ID: 0082
Revises: 0081
Create Date: 2026-11-11

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "b2b_showcase_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Only explicitly approved products appear in the public B2B catalogue",
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "b2b_public_slug",
            sa.String(160),
            nullable=True,
            comment="Stable public URL slug for the no-price B2B showcase (never the internal SKU)",
        ),
    )
    # 部分唯一索引：仅对已开启展示且填写了 slug 的行保证 slug 唯一。
    op.create_index(
        "ux_products_b2b_public_slug",
        "products",
        ["b2b_public_slug"],
        unique=True,
        postgresql_where=sa.text("b2b_public_slug IS NOT NULL"),
    )
    op.create_index(
        "ix_products_b2b_showcase_enabled",
        "products",
        ["b2b_showcase_enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_products_b2b_showcase_enabled", table_name="products")
    op.drop_index("ux_products_b2b_public_slug", table_name="products")
    op.drop_column("products", "b2b_public_slug")
    op.drop_column("products", "b2b_showcase_enabled")