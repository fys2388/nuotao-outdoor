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


# ============================================
# 门户自助销售：RFQ、报价与合同
# ============================================

class B2BPortalRFQItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(ge=1)
    target_unit_price: DecimalFloat | None = Field(default=None, gt=0)
    specifications: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=2000)


class B2BPortalRFQCreate(BaseModel):
    requested_currency: str = Field(default="USD", min_length=3, max_length=8)
    destination_country: str | None = Field(default=None, max_length=8)
    incoterm: str | None = Field(default=None, max_length=16)
    requested_delivery_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)
    items: list[B2BPortalRFQItemCreate] = Field(min_length=1)


class B2BPortalRFQItemResponse(BaseModel):
    id: str
    product_id: str
    sku_snapshot: str
    product_name_snapshot: str
    requested_quantity: int
    target_unit_price: DecimalFloat | None = None
    specifications: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class B2BPortalRFQResponse(BaseModel):
    id: str
    rfq_number: str
    status: str
    source: str
    requested_currency: str
    destination_country: str | None = None
    incoterm: str | None = None
    requested_delivery_date: date | None = None
    notes: str | None = None
    submitted_at: datetime | None = None
    closed_at: datetime | None = None
    items: list[B2BPortalRFQItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class B2BPortalRFQListResponse(BaseModel):
    items: list[B2BPortalRFQResponse]
    total: int
    page: int
    page_size: int


class B2BPortalQuoteItemResponse(BaseModel):
    id: str
    product_id: str
    sku_snapshot: str
    product_name_snapshot: str
    quantity: int
    unit_price: DecimalFloat
    discount_percent: DecimalFloat
    line_subtotal: DecimalFloat
    line_total: DecimalFloat
    price_source: str
    specifications: dict[str, Any] = Field(default_factory=dict)


class B2BPortalContractSummary(BaseModel):
    id: str
    contract_number: str
    status: str
    customer_signed_at: datetime | None = None
    company_signed_at: datetime | None = None
    activated_at: datetime | None = None


class B2BPortalQuoteResponse(BaseModel):
    id: str
    quote_number: str
    version_number: int
    rfq_id: str | None = None
    rfq_number: str | None = None
    status: str
    currency: str
    valid_until: date
    payment_terms_days: int
    incoterm: str | None = None
    shipping_terms: str | None = None
    subtotal: DecimalFloat
    discount_amount: DecimalFloat
    shipping_cost: DecimalFloat
    tax_amount: DecimalFloat
    total: DecimalFloat
    sent_at: datetime | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    notes: str | None = None
    items: list[B2BPortalQuoteItemResponse] = Field(default_factory=list)
    contract: B2BPortalContractSummary | None = None
    created_at: datetime
    updated_at: datetime


class B2BPortalQuoteListResponse(BaseModel):
    items: list[B2BPortalQuoteResponse]
    total: int
    page: int
    page_size: int


class B2BPortalQuoteDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class B2BPortalContractResponse(BaseModel):
    id: str
    contract_number: str
    quote_id: str
    quote_number: str | None = None
    version_number: int | None = None
    status: str
    effective_from: date
    effective_to: date | None = None
    currency: str
    total: DecimalFloat
    document_url: str | None = None
    terms: dict[str, Any] = Field(default_factory=dict)
    customer_signed_by: str | None = None
    customer_signed_at: datetime | None = None
    company_signed_at: datetime | None = None
    activated_at: datetime | None = None
    terminated_at: datetime | None = None
    items: list[B2BPortalQuoteItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class B2BPortalContractListResponse(BaseModel):
    items: list[B2BPortalContractResponse]
    total: int
    page: int
    page_size: int


class B2BPortalContractSignRequest(BaseModel):
    signed_by: str = Field(min_length=1, max_length=128)


class B2BPortalOrderConversionResponse(BaseModel):
    id: str
    order_number: str
    quote_id: str
    contract_id: str
    status: str
    payment_status: str
    total: DecimalFloat
    currency: str


# 解决前向引用
B2BTokenResponse.model_rebuild()
