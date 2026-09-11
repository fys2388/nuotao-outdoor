"""Identity foundation models (M5.14, staging only).

``WorkspaceIdentityLink`` maps a verified identity organization (Clerk ``org``
claim) to a Nuotao workspace. The mapping is the ONLY server-side source of
truth for the request workspace: ``X-Workspace-Id`` is at most a routing hint
and is rejected when it disagrees with the mapped workspace.

Every row is workspace-scoped and carries a ``trace_id``; no JWT, credential
or secret is ever stored here.
"""

from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin


class WorkspaceIdentityLink(Base, TimestampMixin, WorkspaceMixin):
    """One organization -> workspace mapping (unique per pair)."""

    __tablename__ = "workspace_identity_links"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    organization_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mapping_metadata: Mapped[dict[str, Any] | None] = mapped_column(AI_JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "organization_id", name="uq_workspace_identity_links_ws_org"
        ),
    )
