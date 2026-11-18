"""
Revision ID: 0068
Revises: 0067
Create Date: 2026-10-02

Add MFA columns to users table:
- mfa_enabled: Boolean
- mfa_secret: String (TOTP secret)
- mfa_backup_codes: JSON (backup codes list)
- mfa_enabled_at: DateTime

守卫说明（APR-PII-CI-001 空库全链迁移修复）：``users`` 表并非由本迁移创建，
而是由应用启动 ``Base.metadata.create_all`` 创建。空库执行 ``alembic upgrade``
全链时（CI 临时 PostgreSQL），0068 之前没有迁移创建 ``users``，直接
``op.add_column('users', ...)`` 会报 ``relation "users" does not exist``。
因此 online 模式下先检查 ``users`` 表是否存在，不存在则跳过（与 0087 一致）。
生产/既有库中 ``users`` 已存在，行为不变。
"""
from alembic import op
from alembic import context
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0068'
down_revision = '0067'
branch_labels = None
depends_on = None

_TABLE = "users"


def _has_users_table() -> bool:
    bind = op.get_bind()
    return _TABLE in sa.inspect(bind).get_table_names()


def upgrade():
    # 离线模式（deploy dry-run `alembic upgrade head --sql`）无连接可 inspect，
    # 直接生成 DDL；在线模式先做幂等表检查。
    if context.is_offline_mode():
        _add_mfa_columns()
        return
    if not _has_users_table():
        return
    _add_mfa_columns()


def _add_mfa_columns():
    # Add MFA columns to users table
    op.add_column('users', sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('users', sa.Column('mfa_secret', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('mfa_backup_codes', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('users', sa.Column('mfa_enabled_at', sa.DateTime(timezone=True), nullable=True))

    # Create index for MFA enabled users
    op.create_index('idx_users_mfa_enabled', 'users', ['mfa_enabled'])


def _drop_mfa_columns():
    # Drop index
    op.drop_index('idx_users_mfa_enabled', table_name='users')

    # Drop MFA columns
    op.drop_column('users', 'mfa_enabled_at')
    op.drop_column('users', 'mfa_backup_codes')
    op.drop_column('users', 'mfa_secret')
    op.drop_column('users', 'mfa_enabled')


def downgrade():
    if context.is_offline_mode():
        _drop_mfa_columns()
        return
    if not _has_users_table():
        return
    _drop_mfa_columns()
