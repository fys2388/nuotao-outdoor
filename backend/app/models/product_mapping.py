"""
Product Mapping model
Maps Nuotao products to WooCommerce products
"""
from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class ProductMapping(Base):
    """Product mapping between Nuotao and WooCommerce"""
    __tablename__ = "product_mappings"
    __table_args__ = (
        UniqueConstraint("nuotao_product_id", name="uq_product_mappings_nuotao_id"),
        UniqueConstraint("woocommerce_id", name="uq_product_mappings_woo_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    nuotao_product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    woocommerce_id = Column(Integer, nullable=False)
    woocommerce_slug = Column(String(255))
    sync_status = Column(String(32), default="synced")
    last_synced_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    product = relationship("Product", backref="mapping")
