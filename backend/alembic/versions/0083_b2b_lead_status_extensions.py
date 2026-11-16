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

Spec: reports/b2b/CHATGPT_M25_SPEC.md (M2.5.1)

Revision ID: 0083
Revises: 0082
Create Date: 2026-11-12

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

_OLD_STATUS_CHECK = "ck_b2b_leads_status"


def upgrade() -> None:
    # 1. Widen the status CHECK constraint to the finalised lifecycle.
    op.drop_constraint(_OLD_STATUS_CHECK, "b2b_leads", type_="check")
    op.create_check_constraint(
        _OLD_STATUS_CHECK,
        "b2b_leads",
        sa.text(
            "status IN ('new','reviewing','qualified','contacted',"
            "'converted','closed_lost','spam')"
        ),
    )
    # 2. Documented reasons for the new terminal states.
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


def downgrade() -> None:
    op.drop_column("b2b_leads", "spam_reason")
    op.drop_column("b2b_leads", "closed_lost_reason")
    op.drop_constraint(_OLD_STATUS_CHECK, "b2b_leads", type_="check")
    op.create_check_constraint(
        _OLD_STATUS_CHECK,
        "b2b_leads",
        sa.text(
            "status IN ('new','reviewing','qualified','contacted','closed')"
        ),
    )