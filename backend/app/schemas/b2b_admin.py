"""B2B 管理端 API 出入参模型（内部管理员使用）。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, EmailStr, Field, PlainSerializer

DecimalFloat = Annotated[
    Decimal, PlainSerializer(lambda x: float(x), return_type=float, when_used="json")
]


# ============================================
# 代理商管理
# ============================================

class AdminB2BAgentCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    company_name: str = Field(min_length=1, max_length=200)
    contact_name: str = Field(min_length=1, max_length=100)
    phone: str | None = None
    country: str | None = None
    city: str | None = None
    address: str | None = None
    tier: str = Field(default="bronze", pattern="^(bronze|silver|gold|platinum)$")
    status: str = Field(default="active", pattern="^(pending|active|suspended|rejected)$")
    commission_rate: DecimalFloat = Field(default=Decimal("0"), ge=0, le=100)
    discount_percent: DecimalFloat = Field(default=Decimal("0"), ge=0, le=100)
    credit_limit: DecimalFloat = Field(default=Decimal("0"), ge=0)
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    currency: str = Field(default="USD", max_length=8)
    notes: str | None = None


class AdminB2BAgentUpdate(BaseModel):
    company_name: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=100)
    phone: str | None = None
    country: str | None = None
    city: str | None = None
    address: str | None = None
    tier: str | None = Field(default=None, pattern="^(bronze|silver|gold|platinum)$")
    status: str | None = Field(default=None, pattern="^(pending|active|suspended|rejected)$")
    commission_rate: DecimalFloat | None = Field(default=None, ge=0, le=100)
    discount_percent: DecimalFloat | None = Field(default=None, ge=0, le=100)
    credit_limit: DecimalFloat | None = Field(default=None, ge=0)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    notes: str | None = None


class AdminB2BAgentStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|active|suspended|rejected)$")


class AdminB2BResetPassword(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class AdminB2BAgentResponse(BaseModel):
    id: str
    agent_number: str
    company_name: str
    contact_name: str
    email: str
    phone: str | None = None
    country: str | None = None
    city: str | None = None
    address: str | None = None
    tier: str
    status: str
    commission_rate: DecimalFloat
    discount_percent: DecimalFloat
    credit_limit: DecimalFloat
    current_balance: DecimalFloat
    available_credit: DecimalFloat
    payment_terms_days: int
    currency: str
    notes: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    order_count: int = 0
    total_revenue: DecimalFloat = Decimal("0")

    model_config = {"from_attributes": True}


class AdminB2BAgentListResponse(BaseModel):
    items: list[AdminB2BAgentResponse]
    total: int
    page: int
    page_size: int


# ============================================
# 订单管理
# ============================================

class AdminB2BOrderItemResponse(BaseModel):
    id: str
    product_id: str
    product_name: str
    sku: str
    quantity: int
    unit_price: DecimalFloat
    subtotal: DecimalFloat

    model_config = {"from_attributes": True}


class AdminB2BOrderResponse(BaseModel):
    id: str
    order_number: str
    agent_id: str
    agent_company: str = ""
    agent_email: str = ""
    status: str
    payment_status: str
    subtotal: DecimalFloat
    discount_amount: DecimalFloat
    shipping_cost: DecimalFloat
    total: DecimalFloat
    currency: str
    shipping_address: dict[str, Any] = Field(default_factory=dict)
    payment_due_date: date | None = None
    tracking_number: str | None = None
    tracking_carrier: str | None = None
    notes: str | None = None
    items: list[AdminB2BOrderItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminB2BOrderListResponse(BaseModel):
    items: list[AdminB2BOrderResponse]
    total: int
    page: int
    page_size: int


class AdminB2BOrderStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|confirmed|processing|shipped|delivered|cancelled)$")
    tracking_number: str | None = None
    tracking_carrier: str | None = None


# ============================================
# 定价管理
# ============================================

class AdminB2BPriceCreate(BaseModel):
    product_id: str
    tier: str | None = Field(default=None, pattern="^(bronze|silver|gold|platinum)$")
    agent_id: str | None = None
    wholesale_price: DecimalFloat = Field(gt=0)
    moq: int = Field(default=1, ge=1)
    currency: str = Field(default="USD", max_length=8)
    is_active: bool = True


class AdminB2BPriceUpdate(BaseModel):
    wholesale_price: DecimalFloat | None = Field(default=None, gt=0)
    moq: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class AdminB2BPriceResponse(BaseModel):
    id: str
    product_id: str
    product_name: str = ""
    product_sku: str = ""
    tier: str | None = None
    agent_id: str | None = None
    agent_company: str | None = None
    wholesale_price: DecimalFloat
    moq: int
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminB2BPriceListResponse(BaseModel):
    items: list[AdminB2BPriceResponse]
    total: int
    page: int
    page_size: int


# ============================================
# 统计
# ============================================

class AdminB2BStatsResponse(BaseModel):
    total_agents: int
    active_agents: int
    pending_agents: int
    suspended_agents: int
    total_orders: int
    total_revenue: DecimalFloat
    pending_orders: int
    total_credit_limit: DecimalFloat
    total_outstanding_balance: DecimalFloat
