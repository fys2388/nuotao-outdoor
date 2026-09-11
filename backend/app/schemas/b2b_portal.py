"""B2B 代理商门户 API 出入参模型。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, EmailStr, Field, PlainSerializer

# Decimal 序列化为 JSON number（而非 string），避免前端 toFixed 报错
DecimalFloat = Annotated[
    Decimal, PlainSerializer(lambda x: float(x), return_type=float, when_used="json")
]


# ============================================
# 认证
# ============================================

class B2BLoginRequest(BaseModel):
    email: EmailStr
    password: str


class B2BTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    agent: "B2BAgentProfile"


class B2BChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ============================================
# 代理商申请
# ============================================

class B2BApplicationRequest(BaseModel):
    """公开代理商申请表单。"""
    company_name: str = Field(min_length=2, max_length=200)
    contact_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str | None = Field(None, max_length=50)
    whatsapp: str | None = Field(None, max_length=50)
    wechat: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=64)
    city: str | None = Field(None, max_length=100)
    address: str | None = Field(None, max_length=500)
    password: str = Field(min_length=8, max_length=128)
    business_type: str | None = Field(None, max_length=100)
    website: str | None = Field(None, max_length=255)
    estimated_annual_volume: str | None = Field(None, max_length=100)
    product_interests: str | None = None
    message: str | None = None


class B2BApplicationResponse(BaseModel):
    id: str
    email: str
    company_name: str
    status: str
    message: str


# ============================================
# 代理商资料
# ============================================

class B2BAgentProfile(BaseModel):
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
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class B2BAccountSummary(BaseModel):
    agent: B2BAgentProfile
    total_orders: int
    total_revenue: DecimalFloat
    pending_payments: DecimalFloat
    payment_due_date: date | None = None


# ============================================
# 商品
# ============================================

class B2BProductItem(BaseModel):
    id: str
    sku: str
    name: str
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    wholesale_price: DecimalFloat
    retail_price: DecimalFloat | None = None
    moq: int
    currency: str
    in_stock: bool
    stock_quantity: int = 0
    images: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class B2BProductListResponse(BaseModel):
    items: list[B2BProductItem]
    total: int
    page: int
    page_size: int


class B2BProductDetail(B2BProductItem):
    weight_kg: DecimalFloat | None = None
    dimensions: dict[str, Any] | None = None
    cost_note: str | None = None


# ============================================
# 购物车与下单
# ============================================

class B2BCartItem(BaseModel):
    product_id: str
    quantity: int = Field(ge=1)


class B2BCreateOrderRequest(BaseModel):
    items: list[B2BCartItem] = Field(min_length=1)
    shipping_address: dict[str, Any] | None = None
    notes: str | None = None


class B2BOrderItemResponse(BaseModel):
    id: str
    product_id: str
    product_name: str
    sku: str
    quantity: int
    unit_price: DecimalFloat
    subtotal: DecimalFloat

    model_config = {"from_attributes": True}


class B2BOrderResponse(BaseModel):
    id: str
    order_number: str
    status: str
    payment_status: str
    subtotal: DecimalFloat
    discount_amount: DecimalFloat
    shipping_cost: DecimalFloat
    total: DecimalFloat
    currency: str
    shipping_address: dict[str, Any]
    payment_due_date: date | None = None
    tracking_number: str | None = None
    tracking_carrier: str | None = None
    notes: str | None = None
    items: list[B2BOrderItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class B2BOrderListResponse(BaseModel):
    items: list[B2BOrderResponse]
    total: int
    page: int
    page_size: int


# 解决前向引用
B2BTokenResponse.model_rebuild()
