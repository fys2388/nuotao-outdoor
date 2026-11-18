"""b2b_leads PII 加密列（APR-M440-PII-001 设计/Staging 验证阶段）。

Owner 决策：本轮仅允许设计、代码、测试与 Staging 验证；生产 PII schema
迁移未获批准（APR-M440-PII-001 NOT APPROVED FOR PRODUCTION EXECUTION）。
本迁移只会在 Staging 库执行（``nuotao_staging``）；生产不应用。

Revision: 0087
Create Date: 2026-11-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

_TABLE = "b2b_leads"


def _has_table() -> bool:
    bind = op.get_bind()
    return _TABLE in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table():
        return
    op.add_column(_TABLE, sa.Column("email_hash", sa.String(64), nullable=True))
    op.add_column(_TABLE, sa.Column("email_encrypted", sa.Text(), nullable=True))
    op.add_column(_TABLE, sa.Column("contact_name_encrypted", sa.Text(), nullable=True))
    op.add_column(_TABLE, sa.Column("pii_key_version", sa.String(16), nullable=True))
    op.create_index(
        "ux_b2b_leads_email_hash",
        _TABLE,
        ["email_hash"],
        unique=True,
        postgresql_where=sa.text("email_hash IS NOT NULL"),
    )


def downgrade() -> None:
    if not _has_table():
        return
    op.drop_index("ux_b2b_leads_email_hash", table_name=_TABLE)
    op.drop_column(_TABLE, "pii_key_version")
    op.drop_column(_TABLE, "contact_name_encrypted")
    op.drop_column(_TABLE, "email_encrypted")
    op.drop_column(_TABLE, "email_hash")
