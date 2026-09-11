"""Supplier model."""

from typing import Any
from uuid import uuid4

from sqlalchemy import String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin


class Supplier(Base, TimestampMixin, WorkspaceMixin):
    """Supplier master data (1688 and other sourcing channels)."""

    __tablename__ = "suppliers"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="1688")
    shop_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rating: Mapped[str] = mapped_column(String(8), nullable=False, default="C")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    contact: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)

    __table_args__ = (
        # Unique within a workspace; referenced by product import supplier_code.
        UniqueConstraint("workspace_id", "code", name="uq_suppliers_workspace_code"),
    )
