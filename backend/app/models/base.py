"""Shared model helpers: mixins and JSON column type.

``Base`` is the single declarative base defined in ``app.core.database``;
importing it here (and importing this package from ``app.models``) registers
all models on the same metadata used by Alembic and tests.
"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

__all__ = ["AI_JSON", "BIGINT_PK", "Base", "TimestampMixin", "WorkspaceMixin"]

# JSON column that stores as JSONB on PostgreSQL (for AI/JSONB features) and
# plain JSON elsewhere (e.g. SQLite in tests).
AI_JSON = JSON().with_variant(JSONB(), "postgresql")

# BigInteger on PostgreSQL; INTEGER on SQLite so autoincrement keeps working
# in tests (SQLite only aliases rowid for INTEGER PRIMARY KEY).
BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class TimestampMixin:
    """Adds created_at/updated_at columns maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkspaceMixin:
    """Adds a workspace_id column for future multi-workspace/market isolation.

    M1 stores the default workspace for all rows; the column exists now so the
    schema does not need destructive changes when workspaces are enabled.
    """

    workspace_id: Mapped[Uuid] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
    )
