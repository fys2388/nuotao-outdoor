"""0085_b2b_lead_workflow

M440-02 (M4.4): expand the B2B lead lifecycle from the M2.5.1 7-state machine
to the full sales-workflow state machine required by the M4.4 instruction:

- Widen ``b2b_leads.status`` CHECK to the 11-state workflow:
  ``new/assigned/contacted/qualified/quoting/quoted/negotiating/converted/
  closed_won/closed_lost/spam`` (drops ``reviewing``; adds ``assigned``,
  ``quoting``, ``quoted``, ``negotiating``, ``closed_won``).
- Add ``closed_won_reason`` so the new won terminal state carries a documented
  note (required by the service layer for reporting).
- Add ``trace_id`` (M440-01 audit finding: lead provenance trace for the
  full request chain).
- Add ``is_test`` (M440-07: mark validation/test leads so they are excluded
  from real commercial statistics).
- Add notification-reliability columns (M440-05): ``notify_status``,
  ``notify_attempts``, ``notify_last_error``, ``notified_at`` so notification
  failures are tracked, retryable and never double-notify.

Forward-only, inspector-guarded (idempotent) like 0083; offline mode emits the
plain SQL without executing it.

Revision ID: 0085
Revises: 0084
Create Date: 2026-11-17

"""
from alembic import context
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None

_STATUS_CHECK = "ck_b2b_leads_status"
_WIDE_STATUS = (
    "status IN ('new','assigned','contacted','qualified','quoting',"
    "'quoted','negotiating','converted','closed_won','closed_lost','spam')"
)

_ADDED_COLUMNS = [
    ("closed_won_reason", sa.Text(), "Why the lead won (recorded when status=closed_won)"),
    ("trace_id", sa.String(64), "Request/execution trace id for the lead provenance chain"),
    ("is_test", sa.Boolean(), "Validation/test lead; excluded from real commercial stats"),
    ("notify_status", sa.String(16), "Notification lifecycle: pending/sent/failed/skipped"),
    ("notify_attempts", sa.Integer(), "Notification attempt counter (for retry)"),
    ("notify_last_error", sa.Text(), "Last notification error (no PII)"),
    ("notified_at", sa.DateTime(timezone=True), "Timestamp of successful notification"),
]


def upgrade() -> None:
    if context.is_offline_mode():
        op.drop_constraint(_STATUS_CHECK, "b2b_leads", type_="check")
        op.create_check_constraint(_STATUS_CHECK, "b2b_leads", sa.text(_WIDE_STATUS))
        for name, coltype, comment in _ADDED_COLUMNS:
            op.add_column(
                "b2b_leads",
                sa.Column(name, coltype, nullable=True, comment=comment),
            )
        return

    bind = op.get_bind()
    insp = sa.inspect(bind)
    table_cols = [c["name"] for c in insp.get_columns("b2b_leads")]
    check_names = [c["name"] for c in insp.get_check_constraints("b2b_leads")]

    # 1. Widen the status CHECK constraint to the 11-state workflow.
    if _STATUS_CHECK in check_names:
        op.drop_constraint(_STATUS_CHECK, "b2b_leads", type_="check")
    op.create_check_constraint(_STATUS_CHECK, "b2b_leads", sa.text(_WIDE_STATUS))

    # 2. Add the new columns (only if missing).
    for name, coltype, comment in _ADDED_COLUMNS:
        if name not in table_cols:
            op.add_column(
                "b2b_leads",
                sa.Column(name, coltype, nullable=True, comment=comment),
            )


def downgrade() -> None:
    if context.is_offline_mode():
        for name, _, _ in reversed(_ADDED_COLUMNS):
            op.drop_column("b2b_leads", name)
        op.drop_constraint(_STATUS_CHECK, "b2b_leads", type_="check")
        op.create_check_constraint(
            _STATUS_CHECK,
            "b2b_leads",
            sa.text("status IN ('new','reviewing','qualified','contacted','converted','closed_lost','spam')"),
        )
        return

    bind = op.get_bind()
    insp = sa.inspect(bind)
    table_cols = [c["name"] for c in insp.get_columns("b2b_leads")]

    for name, _, _ in reversed(_ADDED_COLUMNS):
        if name in table_cols:
            op.drop_column("b2b_leads", name)

    check_names = [c["name"] for c in insp.get_check_constraints("b2b_leads")]
    if _STATUS_CHECK in check_names:
        op.drop_constraint(_STATUS_CHECK, "b2b_leads", type_="check")
    op.create_check_constraint(
        _STATUS_CHECK,
        "b2b_leads",
        sa.text("status IN ('new','reviewing','qualified','contacted','converted','closed_lost','spam')"),
    )
