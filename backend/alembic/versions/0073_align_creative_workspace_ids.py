"""align creative_* workspace_id type with the ORM (varchar -> uuid)

Revision ID: 0073
Revises: 0072
Create Date: 2026-10-05

Why
---
``WorkspaceMixin.workspace_id`` is declared ``Mapped[Uuid]``, and 130 tables in
this database store it as ``uuid``. Six ``creative_*`` tables were created with
``String(36)`` instead (migration 0060 and siblings), so every workspace-scoped
ORM query against them failed with::

    asyncpg.exceptions.UndefinedFunctionError:
    operator does not exist: character varying = uuid

This blocked creative generation entirely (``_find_template_for_asset_type`` is
the first workspace-scoped query on the creative path).

Scope
-----
Only these six tables are affected. All six are EMPTY in this environment, so
the conversion is lossless. The stray ``workspace_id -> workspaces(id)`` foreign
keys are dropped rather than recreated: no other table in the database declares
one (``workspaces.id`` is ``String(36)`` per the ORM, which cannot be a uuid FK
target), so dropping them restores the project-wide convention instead of
leaving a type-incompatible constraint with nothing to reference.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, has_workspace_fk)
_CREATIVE_TABLES: tuple[tuple[str, bool], ...] = (
    ("creative_approval_requests", True),
    ("creative_automation_workflows", False),
    ("creative_calibration_runs", True),
    ("creative_cost_events", True),
    ("creative_knowledge_entries", True),
    ("creative_prompt_templates", True),
)


def upgrade() -> None:
    for table, has_fk in _CREATIVE_TABLES:
        if has_fk:
            op.drop_constraint(
                f"{table}_workspace_id_fkey", table, type_="foreignkey"
            )
        op.alter_column(
            table,
            "workspace_id",
            existing_type=sa.String(length=36),
            type_=sa.Uuid(),
            existing_nullable=False,
            postgresql_using="workspace_id::uuid",
        )


def downgrade() -> None:
    for table, has_fk in reversed(_CREATIVE_TABLES):
        op.alter_column(
            table,
            "workspace_id",
            existing_type=sa.Uuid(),
            type_=sa.String(length=36),
            existing_nullable=False,
            postgresql_using="workspace_id::text",
        )
        if has_fk:
            op.create_foreign_key(
                f"{table}_workspace_id_fkey",
                table,
                "workspaces",
                ["workspace_id"],
                ["id"],
                ondelete="CASCADE",
            )
