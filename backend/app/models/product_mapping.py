"""
Product Mapping model
Maps Nuotao products to WooCommerce products / variations (M4 V2.6).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import AI_JSON

# 商品身份状态（M4 V2.5 / V2.6 三态）。
# - PRODUCT:记录绑定商品级(产品本身无变体),wc_variation_id 为空且 WC 商品无变体。
# - VARIATION:记录绑定变体级,wc_variation_id 非空。
# - UNKNOWN_LEGACY:历史记录无法确定商品级/变体级,wc_variation_id 为空但无足够证据,
#   保留未知状态,禁止自动归类。
IDENTITY_STATE_PRODUCT = "PRODUCT"
IDENTITY_STATE_VARIATION = "VARIATION"
IDENTITY_STATE_UNKNOWN_LEGACY = "UNKNOWN_LEGACY"
IDENTITY_STATES = (
    IDENTITY_STATE_PRODUCT,
    IDENTITY_STATE_VARIATION,
    IDENTITY_STATE_UNKNOWN_LEGACY,
)


class ProductMapping(Base):
    """Product mapping between Nuotao and WooCommerce (product or variation).

    唯一约束改造(M4 V2.6):
    - 移除原全局唯一 ``uq_product_mappings_workspace_woo``:同一 workspace 内一个
      WooCommerce 商品 ID 只能映射一次。该全局约束无法表达"一个商品多个变体映射",
      故改为两个部分唯一索引(商品级/变体级分别唯一)。
    - 移除 ``uq_product_mappings_workspace_nuotao``:同一 workspace 内一个本地商品
      只映射一条。一变体一映射后,一个本地商品可对应 1 条商品级 + N 条变体级映射,
      该全局约束会阻止多变异体共存,故移除(商品级唯一由部分唯一索引兜底)。
    - ``identity_state='PRODUCT'``:每个 (workspace, woocommerce_id) 仅一条商品级映射。
    - ``identity_state='VARIATION'``:每个 (workspace, woocommerce_id, wc_variation_id)
      仅一条变体级映射。
    - SKU 仅作辅助识别字段,非唯一主键(SKU 可重/可空/可变)。
    """

    __tablename__ = "product_mappings"
    __table_args__ = (
        # 商品级唯一:每个商品仅一条商品级映射(PostgreSQL 部分唯一索引)。
        Index(
            "ux_product_mapping_product",
            "workspace_id",
            "woocommerce_id",
            unique=True,
            postgresql_where=text("identity_state = 'PRODUCT'"),
            sqlite_where=text("identity_state = 'PRODUCT'"),
        ),
        # 变体级唯一:每个 (商品, 变体) 仅一条(PostgreSQL 部分唯一索引)。
        Index(
            "ux_product_mapping_variation",
            "workspace_id",
            "woocommerce_id",
            "woocommerce_variation_id",
            unique=True,
            postgresql_where=text("identity_state = 'VARIATION' AND woocommerce_variation_id IS NOT NULL"),
            sqlite_where=text("identity_state = 'VARIATION' AND woocommerce_variation_id IS NOT NULL"),
        ),
        # SKU 辅助索引(非唯一,允许重/空/历史 SKU)。
        Index(
            "ix_product_mapping_variation_sku",
            "workspace_id",
            "variation_sku",
            unique=False,
            postgresql_where=text("variation_sku IS NOT NULL"),
            sqlite_where=text("variation_sku IS NOT NULL"),
        ),
    )

    # 跨方言 UUID:核心 Uuid 在 PostgreSQL 编译为原生 UUID,在 SQLite 编译为
    # CHAR(32)(TEXT affinity),避免 postgresql.UUID 在 SQLite 下 NUMERIC affinity
    # 把全数字 UUID(如 '0000...0001')误转成整数导致读取失败。
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id = Column(Uuid, nullable=False)
    nuotao_product_id = Column(
        Uuid,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    woocommerce_id = Column(Integer, nullable=False)
    woocommerce_slug = Column(String(255))
    sync_status = Column(String(32), default="synced")
    last_synced_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- M4 V2.6 身份维度 ---
    # WooCommerce 变体 ID.非空 ⇒ VARIATION;为空不自动推断为 PRODUCT(需证据).
    woocommerce_variation_id = Column(Integer, nullable=True)
    # 变体 SKU(辅助识别,非身份主键;可重/可空/可变).
    variation_sku = Column(String(191), nullable=True)
    # 1688 Offer 来源标识(规范化后的数字 offer id).注意:同一变体可对应多个
    # 供应商/多个 Offer,故这里只记录"主要来源"作快速参考,完整映射见
    # supplier_offer_mappings 表(独立多对多实体).
    source_offer_id = Column(String(32), nullable=True)
    # 来源变体规格(颜色/尺码/容量等),JSON 可空.
    source_variation_spec = Column(AI_JSON, nullable=True)
    # 身份状态:PRODUCT / VARIATION / UNKNOWN_LEGACY.默认 UNKNOWN_LEGACY,
    # 空 wc_variation_id 不会自动成为 PRODUCT.
    identity_state = Column(
        String(16), nullable=False, default="UNKNOWN_LEGACY", server_default=text("'UNKNOWN_LEGACY'")
    )
    # 写入链路 trace_id(审计).
    trace_id = Column(String(64), nullable=True)

    # Relationship
    product = relationship("Product", backref="mapping")

    @property
    def is_product_level(self) -> bool:
        """True 当且仅当身份为商品级(有明确证据)."""
        return self.identity_state == IDENTITY_STATE_PRODUCT

    @property
    def is_variation_level(self) -> bool:
        """True 当且仅当身份为变体级."""
        return self.identity_state == IDENTITY_STATE_VARIATION

    def to_summary(self) -> dict[str, Any]:
        """稳定摘要(用于审计/日志,不暴露敏感信息)."""
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "nuotao_product_id": str(self.nuotao_product_id),
            "woocommerce_id": self.woocommerce_id,
            "woocommerce_variation_id": self.woocommerce_variation_id,
            "variation_sku": self.variation_sku,
            "identity_state": self.identity_state,
        }
