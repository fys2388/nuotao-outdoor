"""Inventory models for stock tracking."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InventoryItem(Base):
    """Inventory tracking for products across workspaces."""

    __tablename__ = "inventory_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sku: Mapped[Optional[String(100)]] = mapped_column(String(100), nullable=True)
    quantity_available: Mapped[BigInteger] = mapped_column(BigInteger, default=0)
    reorder_threshold: Mapped[BigInteger] = mapped_column(BigInteger, default=0)
    warehouse_location: Mapped[Optional[String(200)]] = mapped_column(String(200), nullable=True)
    last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<InventoryItem(id={self.id}, sku={self.sku}, qty={self.quantity_available})>"
