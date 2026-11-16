"""0084_b2b_agent_self_registration

M3.37: Enable B2B agent self-registration with email verification.

- Add verification_token and verification_token_expiry to b2b_agents
- Change default status from 'pending' to 'pending_verification'
- Add email_verified_at timestamp column
- Update CHECK constraint for new status values

Forward-only migration. Downgrade removes the new columns.

Idempotent (inspector-guarded): on a database where b2b_agents already has the
verification columns and/or the ck_b2b_agents_status CHECK (e.g. a previously
hand-built schema), the migration only applies the missing pieces instead of
failing with duplicate column / duplicate constraint errors. In offline
(dry-run) mode Alembic only compiles SQL, so the plain statements are emitted
directly without inspecting live schema.

"""
from alembic import context
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None

_STATUS_CHECK = "ck_b2b_agents_status"
_INDEX = "ix_b2b_agents_verification_token"


def _emit_offline() -> None:
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
    op.drop_constraint(_STATUS_CHECK, "b2b_agents", type_="check")
    op.create_check_constraint(
        _STATUS_CHECK,
        "b2b_agents",
        sa.text(
            "status IN ('pending','pending_verification','active','suspended','rejected')"
        ),
    )
    op.execute(
        "UPDATE b2b_agents SET status = 'pending_verification' WHERE status = 'pending'"
    )
    op.create_index(
        _INDEX,
        "b2b_agents",
        ["verification_token"],
        unique=True,
        postgresql_where=sa.text("verification_token IS NOT NULL"),
    )


def upgrade() -> None:
    if context.is_offline_mode():
        _emit_offline()
        return

    bind = op.get_bind()
    insp = sa.inspect(bind)
    table_cols = [c["name"] for c in insp.get_columns("b2b_agents")]
    check_names = [c["name"] for c in insp.get_check_constraints("b2b_agents")]
    index_names = [i["name"] for i in insp.get_indexes("b2b_agents")]

    # 1. Add email verification columns (only if missing).
    if "verification_token" not in table_cols:
        op.add_column(
            "b2b_agents",
            sa.Column(
                "verification_token",
                sa.String(length=64),
                nullable=True,
                comment="Email verification token (hashed)",
            ),
        )
    if "verification_token_expiry" not in table_cols:
        op.add_column(
            "b2b_agents",
            sa.Column(
                "verification_token_expiry",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="Token expiry timestamp (24 hours from creation)",
            ),
        )
    if "email_verified_at" not in table_cols:
        op.add_column(
            "b2b_agents",
            sa.Column(
                "email_verified_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="Timestamp when email was verified",
            ),
        )

    # 2. Widen status CHECK constraint (drop existing, recreate wider).
    if _STATUS_CHECK in check_names:
        op.drop_constraint(_STATUS_CHECK, "b2b_agents", type_="check")
    op.create_check_constraint(
        _STATUS_CHECK,
        "b2b_agents",
        sa.text(
            "status IN ('pending','pending_verification','active','suspended','rejected')"
        ),
    )

    # 3. Update existing pending agents to pending_verification.
    op.execute(
        "UPDATE b2b_agents SET status = 'pending_verification' WHERE status = 'pending'"
    )

    # 4. Add index for verification_token lookup (only if missing).
    if _INDEX not in index_names:
        op.create_index(
            _INDEX,
            "b2b_agents",
            ["verification_token"],
            unique=True,
            postgresql_where=sa.text("verification_token IS NOT NULL"),
        )


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_index(_INDEX, "b2b_agents")
        op.drop_column("b2b_agents", "email_verified_at")
        op.drop_column("b2b_agents", "verification_token_expiry")
        op.drop_column("b2b_agents", "verification_token")
        op.drop_constraint(_STATUS_CHECK, "b2b_agents", type_="check")
        op.create_check_constraint(
            _STATUS_CHECK,
            "b2b_agents",
            sa.text("status IN ('pending','active','suspended','rejected')"),
        )
        op.execute(
            "UPDATE b2b_agents SET status = 'pending' WHERE status = 'pending_verification'"
        )
        return

    bind = op.get_bind()
    insp = sa.inspect(bind)
    table_cols = [c["name"] for c in insp.get_columns("b2b_agents")]
    check_names = [c["name"] for c in insp.get_check_constraints("b2b_agents")]

    if "email_verified_at" in table_cols:
        op.drop_column("b2b_agents", "email_verified_at")
    if "verification_token_expiry" in table_cols:
        op.drop_column("b2b_agents", "verification_token_expiry")
    if "verification_token" in table_cols:
        op.drop_column("b2b_agents", "verification_token")

    if _STATUS_CHECK in check_names:
        op.drop_constraint(_STATUS_CHECK, "b2b_agents", type_="check")
    op.create_check_constraint(
        _STATUS_CHECK,
        "b2b_agents",
        sa.text("status IN ('pending','active','suspended','rejected')"),
    )
    op.execute(
        "UPDATE b2b_agents SET status = 'pending' WHERE status = 'pending_verification'"
    )
