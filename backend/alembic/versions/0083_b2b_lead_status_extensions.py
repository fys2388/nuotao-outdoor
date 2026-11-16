"""0083_b2b_lead_status_extensions

M2.5.1: finalize the B2B lead lifecycle so commercial reporting can distinguish
won, lost and junk enquiries instead of lumping them into a single "closed".

- Extend the ``b2b_leads.status`` CHECK constraint from
  ``new/reviewing/qualified/contacted/closed`` to add three explicit terminal
  states: ``converted`` (won - linked to a real partner application),
  ``closed_lost`` (documented loss) and ``spam`` (junk).
- Add ``closed_lost_reason`` and ``spam_reason`` so those terminal states carry
  a documented reason (required by the service layer).

Forward-only migration: this does NOT rewrite 0081/0082. The old CHECK
constraint is dropped and recreated with the wider allow-list; existing rows
keep their status. Any existing ``closed`` rows are intentionally left as-is by
this migration (a backfill, if ever needed, must be explicit and reversible) -
the application layer treats legacy ``closed`` as closed_lost for reporting.

Idempotent (inspector-guarded): on a database where the b2b_leads table already
exists with these columns/constraint (e.g. a previously hand-built schema), the
migration skips the already-applied pieces instead of failing with a duplicate
column / duplicate constraint error. In offline (dry-run) mode Alembic has no
live schema to inspect, so we emit the plain SQL statements directly - offline
generation only compiles SQL and never executes it, so the idempotency guard
is unnecessary there.

Spec: reports/b2b/CHATGPT_M25_SPEC.md (M2.5.1)

Revision ID: 0083
Revises: 0082
Create Date: 2026-11-12

"""
from alembic import context
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

_OLD_STATUS_CHECK = "ck_b2b_leads_status"
_WIDE_STATUS = (
    "status IN ('new','reviewing','qualified','contacted',"
    "'converted','closed_lost','spam')"
)


def _emit(offline: bool) -> None:
    """Emit the migration regardless of offline/online mode.

    In offline mode Alembic only compiles SQL (never executes), so emitting
    the plain statements is safe even when the objects already exist.
    """
    op.drop_constraint(_OLD_STATUS_CHECK, "b2b_leads", type_="check")
    op.create_check_constraint(_OLD_STATUS_CHECK, "b2b_leads", sa.text(_WIDE_STATUS))
    op.add_column(
        "b2b_leads",
        sa.Column(
            "closed_lost_reason",
            sa.Text(),
            nullable=True,
            comment="Why the lead was lost (required when status=closed_lost)",
        ),
    )
    op.add_column(
        "b2b_leads",
        sa.Column(
            "spam_reason",
            sa.Text(),
            nullable=True,
            comment="Why the lead was classified as spam (required when status=spam)",
        ),
    )


def upgrade() -> None:
    if context.is_offline_mode():
        _emit(offline=True)
        return

    bind = op.get_bind()
    insp = sa.inspect(bind)
    table_cols = [c["name"] for c in insp.get_columns("b2b_leads")]
    check_names = [c["name"] for c in insp.get_check_constraints("b2b_leads")]

    # 1. Widen the status CHECK constraint to the finalised lifecycle.
    if _OLD_STATUS_CHECK in check_names:
        op.drop_constraint(_OLD_STATUS_CHECK, "b2b_leads", type_="check")
    op.create_check_constraint(_OLD_STATUS_CHECK, "b2b_leads", sa.text(_WIDE_STATUS))

    # 2. Documented reasons for the new terminal states (only if missing).
    if "closed_lost_reason" not in table_cols:
        op.add_column(
            "b2b_leads",
            sa.Column(
                "closed_lost_reason",
                sa.Text(),
                nullable=True,
                comment="Why the lead was lost (required when status=closed_lost)",
            ),
        )
    if "spam_reason" not in table_cols:
        op.add_column(
            "b2b_leads",
            sa.Column(
                "spam_reason",
                sa.Text(),
                nullable=True,
                comment="Why the lead was classified as spam (required when status=spam)",
            ),
        )


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_column("b2b_leads", "spam_reason")
        op.drop_column("b2b_leads", "closed_lost_reason")
        op.drop_constraint(_OLD_STATUS_CHECK, "b2b_leads", type_="check")
        op.create_check_constraint(
            _OLD_STATUS_CHECK,
            "b2b_leads",
            sa.text("status IN ('new','reviewing','qualified','contacted','closed')"),
        )
        return

    bind = op.get_bind()
    insp = sa.inspect(bind)
    table_cols = [c["name"] for c in insp.get_columns("b2b_leads")]

    if "spam_reason" in table_cols:
        op.drop_column("b2b_leads", "spam_reason")
    if "closed_lost_reason" in table_cols:
        op.drop_column("b2b_leads", "closed_lost_reason")

    check_names = [c["name"] for c in insp.get_check_constraints("b2b_leads")]
    if _OLD_STATUS_CHECK in check_names:
        op.drop_constraint(_OLD_STATUS_CHECK, "b2b_leads", type_="check")
    op.create_check_constraint(
        _OLD_STATUS_CHECK,
        "b2b_leads",
        sa.text("status IN ('new','reviewing','qualified','contacted','closed')"),
    )
