"""0084_b2b_agent_self_registration

M3.37: Enable B2B agent self-registration with email verification.

- Add verification_token and verification_token_expiry to b2b_agents
- Change default status from 'pending' to 'pending_verification'
- Add email_verified_at timestamp column
- Update CHECK constraint for new status values

Forward-only migration. Downgrade removes the new columns.

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add email verification columns
    op.add_column(
        "b2b_agents",
        sa.Column(
            "verification_token",
            sa.String(length=64),
            nullable=True,
            comment="Email verification token (hashed)",
        ),
    )
    op.add_column(
        "b2b_agents",
        sa.Column(
            "verification_token_expiry",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Token expiry timestamp (24 hours from creation)",
        ),
    )
    op.add_column(
        "b2b_agents",
        sa.Column(
            "email_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when email was verified",
        ),
    )
    
    # 2. Update CHECK constraint for status to include pending_verification
    op.drop_constraint("ck_b2b_agents_status", "b2b_agents", type_="check")
    op.create_check_constraint(
        "ck_b2b_agents_status",
        "b2b_agents",
        sa.text(
            "status IN ('pending','pending_verification','active','suspended','rejected')"
        ),
    )
    
    # 3. Update existing pending agents to pending_verification
    op.execute(
        "UPDATE b2b_agents SET status = 'pending_verification' WHERE status = 'pending'"
    )
    
    # 4. Add index for verification_token lookup
    op.create_index(
        "ix_b2b_agents_verification_token",
        "b2b_agents",
        ["verification_token"],
        unique=True,
        postgresql_where=sa.text("verification_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_b2b_agents_verification_token", "b2b_agents")
    op.drop_column("b2b_agents", "email_verified_at")
    op.drop_column("b2b_agents", "verification_token_expiry")
    op.drop_column("b2b_agents", "verification_token")
    
    # Restore original CHECK constraint
    op.drop_constraint("ck_b2b_agents_status", "b2b_agents", type_="check")
    op.create_check_constraint(
        "ck_b2b_agents_status",
        "b2b_agents",
        sa.text(
            "status IN ('pending','active','suspended','rejected')"
        ),
    )
    
    # Revert status back to pending for downgraded agents
    op.execute(
        "UPDATE b2b_agents SET status = 'pending' WHERE status = 'pending_verification'"
    )
