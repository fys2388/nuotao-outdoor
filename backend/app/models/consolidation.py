"""Brand, legal-entity, and commerce-attribution reporting dimensions."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - SQLAlchemy resolves annotations
from decimal import Decimal  # noqa: TC003 - SQLAlchemy resolves annotations
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

ATTRIBUTION_ENTITY_TYPES = [
    "b2c_order",
    "b2b_order",
    "b2b_invoice",
]
ELIMINATION_STATUSES = [
    "not_applicable",
    "pending",
    "approved",
    "rejected",
]


class LegalEntity(Base, TimestampMixin, WorkspaceMixin):
    """One reporting and contracting legal entity inside a workspace."""

    __tablename__ = "legal_entities"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False, default="US")
    functional_currency: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="USD",
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "code",
            name="uq_legal_entities_workspace_code",
        ),
        CheckConstraint(
            "status IN ('active','inactive')",
            name="ck_legal_entities_status",
        ),
        Index("ix_legal_entities_workspace_status", "workspace_id", "status"),
    )


class Brand(Base, TimestampMixin, WorkspaceMixin):
    """A customer-facing brand that can be reported independently."""

    __tablename__ = "brands"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    default_legal_entity_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("legal_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "code", name="uq_brands_workspace_code"),
        CheckConstraint("status IN ('active','inactive')", name="ck_brands_status"),
        Index("ix_brands_workspace_status", "workspace_id", "status"),
    )


class CommerceAttribution(Base, TimestampMixin, WorkspaceMixin):
    """Auditable brand and legal-entity attribution for one commerce fact.

    ``entity_id`` intentionally has no database FK because one attribution
    table covers B2C orders, B2B orders, and invoices. The service layer
    validates that the referenced fact exists inside the same workspace.
    """

    __tablename__ = "commerce_attributions"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    entity_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False, index=True)
    brand_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("brands.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    legal_entity_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("legal_entities.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    assignment_source: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="manual",
    )
    is_intercompany: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    counterparty_legal_entity_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("legal_entities.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    elimination_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="not_applicable",
    )
    elimination_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=0,
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON,
        nullable=False,
        default=dict,
    )
    assigned_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "entity_type",
            "entity_id",
            name="uq_commerce_attributions_workspace_entity",
        ),
        CheckConstraint(
            "entity_type IN ('b2c_order','b2b_order','b2b_invoice')",
            name="ck_commerce_attributions_entity_type",
        ),
        CheckConstraint(
            "assignment_source IN ('auto','manual','invoice_copy','migration')",
            name="ck_commerce_attributions_source",
        ),
        CheckConstraint(
            "elimination_status IN "
            "('not_applicable','pending','approved','rejected')",
            name="ck_commerce_attributions_elimination_status",
        ),
        CheckConstraint(
            "elimination_amount >= 0",
            name="ck_commerce_attributions_elimination_amount",
        ),
        CheckConstraint(
            "NOT is_intercompany OR counterparty_legal_entity_id IS NOT NULL",
            name="ck_commerce_attributions_intercompany_counterparty",
        ),
        CheckConstraint(
            "counterparty_legal_entity_id IS NULL "
            "OR counterparty_legal_entity_id <> legal_entity_id",
            name="ck_commerce_attributions_counterparty_distinct",
        ),
        Index(
            "ix_commerce_attributions_workspace_dimensions",
            "workspace_id",
            "brand_id",
            "legal_entity_id",
        ),
        Index(
            "ix_commerce_attributions_workspace_entity",
            "workspace_id",
            "entity_type",
            "entity_id",
        ),
        Index(
            "ix_commerce_attributions_workspace_elimination",
            "workspace_id",
            "elimination_status",
        ),
    )
