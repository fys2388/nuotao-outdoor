"""Image generation task models (M6): AI-generated product/marketing images.

All rows are workspace-scoped. Images are generated through the pluggable
``integrations/image_gen.py`` gateway; this table only records the task
lifecycle, cost and artifact reference. No image is ever used in production
without human review (status flows through ``pending -> generated ->
approved -> published``).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

# Image use-case whitelist (e-commerce scenarios).
USE_CASES: tuple[str, ...] = (
    "main_image",       # product main image (white bg / lifestyle)
    "detail_image",     # detail page illustration
    "lifestyle_image",  # lifestyle / scene image
    "marketing_image",  # marketing / ad creative
    "variant_image",    # variant / colorway image
)

# Task lifecycle: pending -> generating -> generated -> failed
# Post-generation human review: generated -> approved -> rejected
IMAGE_STATUSES: tuple[str, ...] = (
    "pending", "generating", "generated", "failed",
    "approved", "rejected", "published",
)


class ImageGenerationTask(Base, TimestampMixin, WorkspaceMixin):
    """One AI image generation request and its outcome (M6).

    ``prompt`` is the text prompt sent to the model; ``negative_prompt``
    is optional. ``model`` records the actual backend used (may differ from
    requested after fallback). ``cost_cny`` is the per-image cost in CNY
    for budget tracking.
    """

    __tablename__ = "image_generation_tasks"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prompt: Mapped[str] = mapped_column(String(4000), nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    use_case: Mapped[str] = mapped_column(String(32), nullable=False, default="main_image")
    requested_model: Mapped[str] = mapped_column(String(64), nullable=False, default="wan2.7-image")
    actual_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int] = mapped_column(default=1024)
    height: Mapped[int] = mapped_column(default=1024)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cost_cny: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", AI_JSON, nullable=False, default=dict
    )
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_image_gen_workspace_status", "workspace_id", "status"),
        Index("ix_image_gen_workspace_product", "workspace_id", "product_id"),
        Index("ix_image_gen_workspace_use_case", "workspace_id", "use_case"),
    )
