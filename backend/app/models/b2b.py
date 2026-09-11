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
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AI_JSON, Base, TimestampMixin

# 代理商等级
B2B_TIERS = ["bronze", "silver", "gold", "platinum"]
# 代理商状态
B2B_AGENT_STATUSES = ["pending", "active", "suspended", "rejected"]
# B2B 订单状态
B2B_ORDER_STATUSES = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]
# B2B 支付状态
B2B_PAYMENT_STATUSES = ["unpaid", "partial", "paid", "overdue"]


class B2BAgent(Base, TimestampMixin):
    """B2B 代理商账号（外部实体，独立于内部 users 表）。"""

    __tablename__ = "b2b_agents"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    agent_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
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
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    orders: Mapped[list["B2BOrder"]] = relationship(back_populates="agent", lazy="selectin")

    def __repr__(self) -> str:
        return f"<B2BAgent id={self.id} company={self.company_name} tier={self.tier} status={self.status}>"


class B2BProductPrice(Base, TimestampMixin):
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
        UniqueConstraint("product_id", "tier", name="uq_b2b_price_product_tier"),
        UniqueConstraint("product_id", "agent_id", name="uq_b2b_price_product_agent"),
        Index("ix_b2b_product_prices_tier", "tier"),
        Index("ix_b2b_product_prices_agent_id", "agent_id"),
    )

    def __repr__(self) -> str:
        return f"<B2BProductPrice product={self.product_id} tier={self.tier} price={self.wholesale_price}>"


class B2BOrder(Base, TimestampMixin):
    """B2B 批量订单。"""

    __tablename__ = "b2b_orders"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    order_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
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

    agent: Mapped["B2BAgent"] = relationship(back_populates="orders")
    items: Mapped[list["B2BOrderItem"]] = relationship(
        back_populates="order", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<B2BOrder {self.order_number} agent={self.agent_id} status={self.status}>"


class B2BOrderItem(Base):
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    order: Mapped["B2BOrder"] = relationship(back_populates="items")

    def __repr__(self) -> str:
        return f"<B2BOrderItem order={self.order_id} sku={self.sku} qty={self.quantity}>"
