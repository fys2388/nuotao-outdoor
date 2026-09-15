"""B2B 代理商门户领域模型。

代理商账号、分级定价、B2B 订单与订单明细。
与内部 users 表隔离，代理商是外部实体。
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

# 代理商等级
B2B_TIERS = ["bronze", "silver", "gold", "platinum"]
# 代理商状态
B2B_AGENT_STATUSES = ["pending", "active", "suspended", "rejected"]
# B2B 订单状态
B2B_ORDER_STATUSES = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]
# B2B 支付状态
B2B_PAYMENT_STATUSES = ["unpaid", "partial", "paid", "overdue"]
# 价格簿状态
B2B_PRICE_BOOK_STATUSES = ["draft", "active", "archived"]
# 价格版本状态
B2B_PRICE_VERSION_STATUSES = [
    "draft",
    "pending_approval",
    "active",
    "rejected",
    "superseded",
]
# 价格来源
B2B_PRICE_SOURCES = ["TIER", "AGENT", "QUOTE"]


class B2BPriceBook(Base, TimestampMixin, WorkspaceMixin):
    """B2B 价格簿：同一工作区内可用多个币种或业务用途的价格集合。"""

    __tablename__ = "b2b_price_books"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    versions: Mapped[list["B2BPriceVersion"]] = relationship(
        back_populates="price_book",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "code",
            name="uq_b2b_price_books_workspace_code",
        ),
        Index("ix_b2b_price_books_workspace_status", "workspace_id", "status"),
        Index("ix_b2b_price_books_workspace_default", "workspace_id", "is_default"),
    )


class B2BPriceVersion(Base, TimestampMixin, WorkspaceMixin):
    """价格簿版本：价格只能在草稿版本修改，审批后不可变。"""

    __tablename__ = "b2b_price_versions"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    price_book_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_price_books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    price_book: Mapped["B2BPriceBook"] = relationship(back_populates="versions")
    tiers: Mapped[list["B2BPriceTier"]] = relationship(
        back_populates="price_version",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "price_book_id",
            "version_number",
            name="uq_b2b_price_versions_book_version",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_b2b_price_version_effective_period",
        ),
        Index(
            "ix_b2b_price_versions_book_status",
            "workspace_id",
            "price_book_id",
            "status",
        ),
        Index(
            "ix_b2b_price_versions_effective",
            "workspace_id",
            "effective_from",
            "effective_to",
        ),
    )


class B2BPriceTier(Base, TimestampMixin, WorkspaceMixin):
    """已发布价格版本中的阶梯价或客户专属价。"""

    __tablename__ = "b2b_price_tiers"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    price_version_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_price_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    agent_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_agents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    min_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    max_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    price_version: Mapped["B2BPriceVersion"] = relationship(back_populates="tiers")

    __table_args__ = (
        CheckConstraint(
            "(tier IS NOT NULL AND agent_id IS NULL) "
            "OR (tier IS NULL AND agent_id IS NOT NULL)",
            name="ck_b2b_price_tier_exactly_one_scope",
        ),
        CheckConstraint("min_quantity >= 1", name="ck_b2b_price_tier_min_quantity"),
        CheckConstraint(
            "max_quantity IS NULL OR max_quantity > min_quantity",
            name="ck_b2b_price_tier_quantity_range",
        ),
        CheckConstraint("unit_price > 0", name="ck_b2b_price_tier_unit_price"),
        Index(
            "ix_b2b_price_tiers_version_product_tier",
            "workspace_id",
            "price_version_id",
            "product_id",
            "tier",
        ),
        Index(
            "ix_b2b_price_tiers_version_product_agent",
            "workspace_id",
            "price_version_id",
            "product_id",
            "agent_id",
        ),
    )


class B2BAgent(Base, TimestampMixin, WorkspaceMixin):
    """B2B 代理商账号（外部实体，独立于内部 users 表）。"""

    __tablename__ = "b2b_agents"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_number: Mapped[str] = mapped_column(String(32), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="bronze")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    credit_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="normal",
        index=True,
    )
    credit_status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    credit_status_updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    credit_status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    credit_policy_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_credit_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer_account_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("customer_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    orders: Mapped[list["B2BOrder"]] = relationship(back_populates="agent", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("workspace_id", "agent_number", name="uq_b2b_agents_workspace_number"),
        UniqueConstraint("workspace_id", "email", name="uq_b2b_agents_workspace_email"),
        CheckConstraint(
            "credit_status IN ('normal', 'watch', 'hold', 'frozen')",
            name="ck_b2b_agents_credit_status",
        ),
        Index("ix_b2b_agents_workspace_status", "workspace_id", "status"),
        Index(
            "ix_b2b_agents_workspace_credit_status",
            "workspace_id",
            "credit_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<B2BAgent id={self.id} company={self.company_name} tier={self.tier} status={self.status}>"


class B2BProductPrice(Base, TimestampMixin, WorkspaceMixin):
    """B2B 分级定价。

    支持按等级定价（tier 非空，agent_id 为空）
    和代理商专属定价（agent_id 非空，tier 为空）。
    定价优先级：专属 > 等级 > 默认。
    """

    __tablename__ = "b2b_product_prices"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    agent_id: Mapped[Uuid | None] = mapped_column(
        Uuid, ForeignKey("b2b_agents.id", ondelete="CASCADE"), nullable=True
    )
    wholesale_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    moq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "(tier IS NOT NULL AND agent_id IS NULL) "
            "OR (tier IS NULL AND agent_id IS NOT NULL)",
            name="ck_b2b_price_exactly_one_scope",
        ),
        UniqueConstraint(
            "workspace_id", "product_id", "tier", name="uq_b2b_price_workspace_product_tier"
        ),
        UniqueConstraint(
            "workspace_id", "product_id", "agent_id", name="uq_b2b_price_workspace_product_agent"
        ),
        Index("ix_b2b_product_prices_tier", "tier"),
        Index("ix_b2b_product_prices_agent_id", "agent_id"),
    )

    def __repr__(self) -> str:
        return f"<B2BProductPrice product={self.product_id} tier={self.tier} price={self.wholesale_price}>"


class B2BOrder(Base, TimestampMixin, WorkspaceMixin):
    """B2B 批量订单。"""

    __tablename__ = "b2b_orders"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    order_number: Mapped[str] = mapped_column(String(32), nullable=False)
    agent_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("b2b_agents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    payment_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unpaid", index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    shipping_address: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    payment_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tracking_carrier: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_model: Mapped[str] = mapped_column(String(8), nullable=False, default="B2B")
    customer_account_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("customer_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quote_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_quotes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    contract_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    agent: Mapped["B2BAgent"] = relationship(back_populates="orders")
    items: Mapped[list["B2BOrderItem"]] = relationship(
        back_populates="order", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "order_number", name="uq_b2b_orders_workspace_number"),
        UniqueConstraint(
            "workspace_id",
            "quote_id",
            name="uq_b2b_orders_workspace_quote",
        ),
        Index("ix_b2b_orders_workspace_agent", "workspace_id", "agent_id"),
        Index("ix_b2b_orders_workspace_status", "workspace_id", "status"),
        Index("ix_b2b_orders_workspace_payment_status", "workspace_id", "payment_status"),
    )

    def __repr__(self) -> str:
        return f"<B2BOrder {self.order_number} agent={self.agent_id} status={self.status}>"


class B2BOrderItem(Base, WorkspaceMixin):
    """B2B 订单明细（下单时快照商品信息与价格）。"""

    __tablename__ = "b2b_order_items"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    order_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("b2b_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[Uuid] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    price_book_version_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_price_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    price_tier_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_price_tiers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    price_source: Mapped[str] = mapped_column(String(16), nullable=False, default="TIER")
    quote_item_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("b2b_quote_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    order: Mapped["B2BOrder"] = relationship(back_populates="items")

    def __repr__(self) -> str:
        return f"<B2BOrderItem order={self.order_id} sku={self.sku} qty={self.quantity}>"
