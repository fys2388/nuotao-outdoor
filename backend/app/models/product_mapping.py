"""
Product Mapping model
Maps Nuotao products to WooCommerce products
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class ProductMapping(Base):
    """Product mapping between Nuotao and WooCommerce"""
    __tablename__ = "product_mappings"
    __table_args__ = (
        # 唯一约束必须带 workspace 维度：WooCommerce 是按店铺隔离的，同一个数字商品
        # ID 在不同 workspace 里完全可能是两个不同的商品。原来的全局唯一约束会把它们
        # 错误地互斥——B 空间无法映射到一个 A 空间已经在用的 WC 商品 ID。
        UniqueConstraint(
            "workspace_id",
            "nuotao_product_id",
            name="uq_product_mappings_workspace_nuotao",
        ),
        UniqueConstraint(
            "workspace_id",
            "woocommerce_id",
            name="uq_product_mappings_workspace_woo",
        ),
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
