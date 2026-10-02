"""
Revision ID: 0068
Revises: 0067
Create Date: 2026-10-02

Add MFA columns to users table:
- mfa_enabled: Boolean
- mfa_secret: String (TOTP secret)
- mfa_backup_codes: JSON (backup codes list)
- mfa_enabled_at: DateTime
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0068'
down_revision = '0067'
branch_labels = None
depends_on = None


def upgrade():
    # Add MFA columns to users table
    op.add_column('users', sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('users', sa.Column('mfa_secret', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('mfa_backup_codes', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('users', sa.Column('mfa_enabled_at', sa.DateTime(timezone=True), nullable=True))
    
    # Create index for MFA enabled users
    op.create_index('idx_users_mfa_enabled', 'users', ['mfa_enabled'])


def downgrade():
    # Drop index
    op.drop_index('idx_users_mfa_enabled', table_name='users')
    
    # Drop MFA columns
    op.drop_column('users', 'mfa_enabled_at')
    op.drop_column('users', 'mfa_backup_codes')
    op.drop_column('users', 'mfa_secret')
    op.drop_column('users', 'mfa_enabled')