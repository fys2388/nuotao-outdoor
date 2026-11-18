"""B2B 公开展示站（showcase）API 出入参模型。

公开目录响应严格遵循字段白名单——绝不返回价格、成本、库存、内部 SKU、
供应商信息或内部管理字段。线索（lead）创建响应只返回通用确认信息。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ============================================
# 公开产品目录（字段白名单，无价格）
# ============================================

class B2BPublicProduct(BaseModel):
    """公开产品详情——仅白名单字段，绝无价格/成本/库存/供应商。"""
    slug: str
    title: str
    images: list[str] = []
    category: str | None = None
    description: str | None = None
    specifications: dict[str, Any] | None = None
    enquiry_cta_context: dict[str, Any] | None = None


class B2BPublicCategory(BaseModel):
    slug: str
    name: str
    product_count: int = 0


class B2BPublicProductListResponse(BaseModel):
    items: list[B2BPublicProduct]
    total: int
    page: int
    page_size: int


# ============================================
# 公开线索提交（Request a Quote）
# ============================================

class B2BPublicLeadCreate(BaseModel):
    """公开 Request a Quote 表单。source 由服务端固定，不信任客户端。"""
    company_name: str = Field(min_length=2, max_length=200)
    contact_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    country: str = Field(min_length=2, max_length=64)
    business_type: str = Field(min_length=2, max_length=32)
    products_of_interest: list[str] | None = None
    message: str = Field(min_length=1, max_length=5000)
    privacy_consent: bool = Field(...)  # 必须为 True
    # 可选
    company_website: str | None = Field(None, max_length=255)
    whatsapp: str | None = Field(None, max_length=64)
    wechat: str | None = Field(None, max_length=64)
    estimated_order_quantity: str | None = Field(None, max_length=64)
    annual_purchase_range: str | None = Field(None, max_length=64)
    destination_market: str | None = Field(None, max_length=120)


class B2BPublicLeadCreatedResponse(BaseModel):
    """持久化成功后的通用确认——不暴露内部数据库 ID 或管理数据。"""
    success: bool
    reference_number: str
    message: str


# ============================================
# 内部 admin：线索管理（含内部字段）
# ============================================

class B2BLeadAdminResponse(BaseModel):
    id: str
    reference_number: str
    company_name: str
    contact_name: str
    email: str
    country: str
    business_type: str
    products_of_interest: list[str] | None = None
    message: str
    privacy_consent: bool
    consent_at: datetime
    company_website: str | None = None
    whatsapp: str | None = None
    wechat: str | None = None
    estimated_order_quantity: str | None = None
    annual_purchase_range: str | None = None
    destination_market: str | None = None
    source: str
    status: str
    assigned_to: str | None = None
    internal_notes: str | None = None
    follow_ups: list[dict[str, Any]] | None = None
    converted_application_id: str | None = None
    converted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class B2BLeadListResponse(BaseModel):
    items: list[B2BLeadAdminResponse]
    total: int
    page: int
    page_size: int


class B2BLeadUpdateRequest(BaseModel):
    status: str | None = Field(None, max_length=16)
    assigned_to: str | None = Field(None, max_length=128)
    internal_notes: str | None = None
    follow_up: dict[str, Any] | None = None


class B2BQuoteCreate(BaseModel):
    """Create the next quote version for a lead (internal only, M440-04)."""

    unit_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=8, default="USD")
    quantity: int = Field(ge=1, default=1)
    shipping_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2, default=0)
    valid_until: datetime | None = None
    payment_terms: str | None = Field(max_length=64)
    shipping_terms: str | None = Field(max_length=64)
    notes: str | None = None


class B2BQuoteResponse(BaseModel):
    quote_id: UUID
    lead_id: UUID
    quote_number: str
    quote_version: int
    currency: str
    unit_price: Decimal
    quantity: int
    shipping_cost: Decimal
    estimated_total: Decimal
    valid_until: datetime | None
    payment_terms: str | None
    shipping_terms: str | None
    approval_status: str
    approved_by: str | None
    approved_at: datetime | None
    created_by: str | None
    notes: str | None
    created_at: datetime


class B2BQuoteListResponse(BaseModel):
    total: int
    items: list[B2BQuoteResponse]


class B2BLeadStatsResponse(BaseModel):
    """M440-08: lead commercial statistics.

    Test / spam / invalid leads are excluded from valid counts (``valid_*``),
    never fabricated when data is missing.
    """

    total_leads: int
    valid_leads: int
    by_status: dict[str, int]
    by_country: dict[str, int]
    quotes_total: int
    quotes_approved: int
    converted_leads: int
    conversion_rate: float | None


class B2BLeadConvertResponse(BaseModel):
    success: bool
    lead_id: str
    reference_number: str
    application_id: str
    message: str