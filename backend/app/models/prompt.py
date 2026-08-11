"""Prompt registry model (M2.2).

Prompts are versioned, database-backed, and never hardcoded in business code.
Each row declares the template plus the variable names it expects, so the
rendering layer can validate inputs before any LLM call.
"""

from typing import Any
from uuid import uuid4

from sqlalchemy import String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin


class Prompt(Base, TimestampMixin, WorkspaceMixin):
    """A versioned prompt template in the registry.

    ``name`` is the logical identifier (e.g. ``PRODUCT_ANALYST``); ``version``
    follows the ``vN`` convention. At most one version of a name can be
    ``active`` at a time (enforced by the service layer). Template placeholders
    use ``{variable}`` syntax and must match ``variables``.
    """

    __tablename__ = "prompts"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    prompt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    template: Mapped[str] = mapped_column(String(12000), nullable=False)
    variables: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "name",
            "version",
            name="uq_prompts_workspace_name_version",
        ),
    )
