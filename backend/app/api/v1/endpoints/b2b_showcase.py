"""B2B 公开展示站 API（公开目录 + 公开线索）与内部 admin 线索管理。

公开端点（免登录，字段白名单，绝无价格）挂 /b2b-showcase。
内部线索管理挂 /admin/b2b/leads，需内部用户认证。
Spec: reports/b2b/CHATGPT_M1_M2_SPEC.md (M1.4 / M1.5 / M2.0)
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import (
    UserResponse,
    get_current_user,
    get_current_workspace_id,
    require_role,
)
from app.core.database import get_db
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import Product
from app.services import event_service
from app.schemas.b2b_showcase import (
    B2BLeadAdminResponse,
    B2BLeadConvertResponse,
    B2BLeadListResponse,
    B2BLeadStatsResponse,
    B2BLeadUpdateRequest,
    B2BPublicCategory,
    B2BQuoteCreate,
    B2BQuoteListResponse,
    B2BQuoteResponse,
    B2BPublicLeadCreate,
    B2BPublicLeadCreatedResponse,
    B2BPublicProduct,
    B2BPublicProductListResponse,
)
from app.services.b2b_lead_notification import notify_new_lead
from app.services.b2b_showcase_service import (
    LeadConversionError,
    LeadStateError,
    convert_lead_to_application,
    create_public_lead,
    get_lead,
    lead_stats,
    get_public_product,
    list_leads,
    list_public_categories,
    list_public_products,
    update_lead,
)

logger = logging.getLogger(__name__)

# 公开端点（免登录）
public_router = APIRouter(prefix="/b2b-showcase", tags=["b2b-showcase"])
# 内部线索管理（需认证）
admin_router = APIRouter(prefix="/admin/b2b/leads", tags=["admin-b2b-leads"])
# M2.5.3: 内部商品展示审核（需认证）——控制哪些产品出现在公开无价格目录。
showcase_admin_router = APIRouter(prefix="/admin/b2b/showcase", tags=["admin-b2b-showcase"])


# ============================================
# 公开：无价格产品目录
# ============================================

@public_router.get("/categories", response_model=list[B2BPublicCategory])
async def get_categories(
    db: AsyncSession = Depends(get_db),
) -> list[B2BPublicCategory]:
    items = await list_public_categories(db)
    return [B2BPublicCategory(**i) for i in items]


@public_router.get("/products", response_model=B2BPublicProductListResponse)
async def get_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> B2BPublicProductListResponse:
    items, total = await list_public_products(
        db, page=page, page_size=page_size, category=category
    )
    return B2BPublicProductListResponse(
        items=[B2BPublicProduct(**i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@public_router.get("/products/{slug}", response_model=B2BPublicProduct)
async def get_product(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> B2BPublicProduct:
    product = await get_public_product(db, slug)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return B2BPublicProduct(**product)


# ============================================
# 公开：提交线索（Request a Quote）
# ============================================

@public_router.post("/leads", response_model=B2BPublicLeadCreatedResponse, status_code=201)
async def submit_lead(
    payload: B2BPublicLeadCreate,
    db: AsyncSession = Depends(get_db),
) -> B2BPublicLeadCreatedResponse:
    if not payload.privacy_consent:
        raise HTTPException(status_code=422, detail="Privacy consent is required")
    try:
        lead = await create_public_lead(
            db,
            company_name=payload.company_name,
            contact_name=payload.contact_name,
            email=payload.email,
            country=payload.country,
            business_type=payload.business_type,
            message=payload.message,
            privacy_consent=payload.privacy_consent,
            products_of_interest=payload.products_of_interest,
            company_website=payload.company_website,
            whatsapp=payload.whatsapp,
            wechat=payload.wechat,
            estimated_order_quantity=payload.estimated_order_quantity,
            annual_purchase_range=payload.annual_purchase_range,
            destination_market=payload.destination_market,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # M2.5.5: the lead is persisted; notify internal B2B owner(s) after the
    # business fact is committed. notify_new_lead never raises and a failure
    # must not roll back the lead nor surface as a submission error here.
    try:
        await notify_new_lead(db, lead)
    except Exception:  # pragma: no cover - defensive, notification is best-effort
        logger.exception("B2B lead notification raised unexpectedly for %s", lead.reference_number)
    return B2BPublicLeadCreatedResponse(
        success=True,
        reference_number=lead.reference_number,
        message="Thank you. Your enquiry has been received and our team will be in touch.",
    )


# ============================================
# 内部 admin：线索管理
# ============================================

def _lead_to_response(lead) -> B2BLeadAdminResponse:
    return B2BLeadAdminResponse(
        id=str(lead.id),
        reference_number=lead.reference_number,
        company_name=lead.company_name,
        contact_name=lead.contact_name,
        email=lead.email,
        country=lead.country,
        business_type=lead.business_type,
        products_of_interest=lead.products_of_interest,
        message=lead.message,
        privacy_consent=lead.privacy_consent,
        consent_at=lead.consent_at,
        company_website=lead.company_website,
        whatsapp=lead.whatsapp,
        wechat=lead.wechat,
        estimated_order_quantity=lead.estimated_order_quantity,
        annual_purchase_range=lead.annual_purchase_range,
        destination_market=lead.destination_market,
        source=lead.source,
        status=lead.status,
        assigned_to=lead.assigned_to,
        internal_notes=lead.internal_notes,
        follow_ups=lead.follow_ups,
        converted_application_id=(
            str(lead.converted_application_id) if lead.converted_application_id else None
        ),
        converted_at=lead.converted_at,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


@admin_router.get("/stats", response_model=B2BLeadStatsResponse)
async def admin_lead_stats(
    db: AsyncSession = Depends(get_db),
    workspace_id: UUID = Depends(get_current_workspace_id),
    _user=Depends(get_current_user),
) -> B2BLeadStatsResponse:
    """Lead 经营统计（M440-08）：排除测试/垃圾/无效 Lead；缺失数据不补造。"""
    return B2BLeadStatsResponse(**lead_stats(db, workspace_id=workspace_id))


@admin_router.get("", response_model=B2BLeadListResponse)
async def admin_list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    assigned_to: str | None = None,
    db: AsyncSession = Depends(get_db),
    workspace_id: UUID = Depends(get_current_workspace_id),
    _user=Depends(get_current_user),
) -> B2BLeadListResponse:
    leads, total = await list_leads(
        db, page=page, page_size=page_size, status=status, assigned_to=assigned_to,
        workspace_id=workspace_id,
    )
    return B2BLeadListResponse(
        items=[_lead_to_response(l) for l in leads],
        total=total,
        page=page,
        page_size=page_size,
    )


@admin_router.get("/{lead_id}", response_model=B2BLeadAdminResponse)
async def admin_get_lead(
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    workspace_id: UUID = Depends(get_current_workspace_id),
    _user=Depends(get_current_user),
) -> B2BLeadAdminResponse:
    lead = await get_lead(db, lead_id, workspace_id=workspace_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _lead_to_response(lead)


@admin_router.patch("/{lead_id}", response_model=B2BLeadAdminResponse)
async def admin_update_lead(
    lead_id: UUID,
    payload: B2BLeadUpdateRequest,
    db: AsyncSession = Depends(get_db),
    workspace_id: UUID = Depends(get_current_workspace_id),
    _user: UserResponse = Depends(require_role("operator")),
) -> B2BLeadAdminResponse:
    lead = await get_lead(db, lead_id, workspace_id=workspace_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    try:
        lead = await update_lead(
            db,
            lead,
            status=payload.status,
            assigned_to=payload.assigned_to,
            internal_notes=payload.internal_notes,
            follow_up=payload.follow_up,
            actor=str(getattr(_user, "email", None) or getattr(_user, "id", _user)),
        )
    except LeadStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _lead_to_response(lead)


class B2BLeadConvertRequest(BaseModel):
    agent_id: UUID


@admin_router.post("/{lead_id}/convert", response_model=B2BLeadConvertResponse)
async def admin_convert_lead(
    lead_id: UUID,
    payload: B2BLeadConvertRequest,
    db: AsyncSession = Depends(get_db),
    workspace_id: UUID = Depends(get_current_workspace_id),
    _user: UserResponse = Depends(require_role("operator")),
) -> B2BLeadConvertResponse:
    lead = await get_lead(db, lead_id, workspace_id=workspace_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    try:
        lead = await convert_lead_to_application(db, lead, agent_id=payload.agent_id)
    except LeadConversionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return B2BLeadConvertResponse(
        success=True,
        lead_id=str(lead.id),
        reference_number=lead.reference_number,
        application_id=str(lead.converted_application_id),
        message="Lead converted into a formal B2B partner application.",
    )


# ============================================
# 内部 admin：报价管理（M440-04）
# ============================================


def _quote_to_schema(quote) -> B2BQuoteResponse:
    return B2BQuoteResponse(
        quote_id=quote.id,
        lead_id=quote.lead_id,
        quote_number=quote.quote_number,
        quote_version=quote.quote_version,
        currency=quote.currency,
        unit_price=quote.unit_price,
        quantity=quote.quantity,
        shipping_cost=quote.shipping_cost,
        estimated_total=quote.estimated_total,
        valid_until=quote.valid_until,
        payment_terms=quote.payment_terms,
        shipping_terms=quote.shipping_terms,
        approval_status=quote.approval_status,
        approved_by=quote.approved_by,
        approved_at=quote.approved_at,
        created_by=quote.created_by,
        notes=quote.notes,
        created_at=quote.created_at,
    )


@admin_router.post("/{lead_id}/quotes", response_model=B2BQuoteResponse)
async def admin_create_quote(
    lead_id: UUID,
    body: B2BQuoteCreate,
    db: AsyncSession = Depends(get_db),
    workspace_id: UUID = Depends(get_current_workspace_id),
    _user: UserResponse = Depends(require_role("operator")),
) -> B2BQuoteResponse:
    """创建 Lead 的下一版报价（内部，未审批；不会自动发送给客户）。"""
    from app.services.b2b_lead_quote_service import QuoteError, create_quote

    lead = await get_lead(db, lead_id, workspace_id=workspace_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    try:
        quote = await create_quote(
            db,
            lead=lead,
            unit_price=float(body.unit_price),
            currency=body.currency,
            quantity=body.quantity,
            shipping_cost=float(body.shipping_cost),
            valid_until=body.valid_until,
            payment_terms=body.payment_terms,
            shipping_terms=body.shipping_terms,
            notes=body.notes,
            actor=str(getattr(_user, "email", None) or getattr(_user, "id", _user)),
            workspace_id=workspace_id,
        )
    except QuoteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _quote_to_schema(quote)


@admin_router.get("/{lead_id}/quotes", response_model=B2BQuoteListResponse)
async def admin_list_quotes(
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    workspace_id: UUID = Depends(get_current_workspace_id),
    _user=Depends(get_current_user),
) -> B2BQuoteListResponse:
    """列出 Lead 的全部报价版本（内部）。"""
    from app.services.b2b_lead_quote_service import list_quotes

    lead = await get_lead(db, lead_id, workspace_id=workspace_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    quotes = await list_quotes(db, lead_id=lead_id, workspace_id=workspace_id)
    return B2BQuoteListResponse(total=len(quotes), items=[_quote_to_schema(q) for q in quotes])


@admin_router.post("/quotes/{quote_id}/approve", response_model=B2BQuoteResponse)
async def admin_approve_quote(
    quote_id: UUID,
    db: AsyncSession = Depends(get_db),
    workspace_id: UUID = Depends(get_current_workspace_id),
    _user: UserResponse = Depends(require_role("operator")),
) -> B2BQuoteResponse:
    """审批报价（人工闸门；审批后报价不可覆盖，只能创建新版本）。"""
    from app.services.b2b_lead_quote_service import QuoteError, approve_quote

    actor = str(getattr(_user, "email", None) or getattr(_user, "id", _user))
    try:
        quote = await approve_quote(db, quote_id=quote_id, actor=actor, workspace_id=workspace_id)
    except QuoteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _quote_to_schema(quote)


@admin_router.post("/quotes/{quote_id}/reject", response_model=B2BQuoteResponse)
async def admin_reject_quote(
    quote_id: UUID,
    db: AsyncSession = Depends(get_db),
    workspace_id: UUID = Depends(get_current_workspace_id),
    _user: UserResponse = Depends(require_role("operator")),
) -> B2BQuoteResponse:
    """拒绝报价（人工闸门）。"""
    from app.services.b2b_lead_quote_service import QuoteError, reject_quote

    actor = str(getattr(_user, "email", None) or getattr(_user, "id", _user))
    try:
        quote = await reject_quote(db, quote_id=quote_id, actor=actor, workspace_id=workspace_id)
    except QuoteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _quote_to_schema(quote)


# ============================================
# M2.5.3: 内部商品展示审核（受控 curation）
# ============================================


class ShowcaseProductOut(BaseModel):
    id: str
    name: str
    category: str | None
    sku: str | None
    b2b_showcase_enabled: bool
    b2b_public_slug: str | None
    has_images: bool
    has_specifications: bool
    image_count: int
    # M2.5.3: explicit approval evidence for public description/specs, held in
    # product.attributes (never exposed publicly with pricing/cost fields).
    description_approved: bool
    specs_approved: bool
    missing_evidence: list[str]


class ShowcaseProductUpdate(BaseModel):
    b2b_showcase_enabled: bool | None = None
    b2b_public_slug: str | None = None
    description_approved: bool | None = None
    specs_approved: bool | None = None


def _showcase_product_to_out(p: Product) -> ShowcaseProductOut:
    images = []
    specs = None
    for container in (p.attributes, p.meta):
        if isinstance(container, dict):
            imgs = container.get("images") or container.get("image_urls")
            if isinstance(imgs, list):
                images = [u for u in imgs if isinstance(u, str)]
            if isinstance(container.get("specifications"), dict):
                specs = container["specifications"]
    attrs = p.attributes if isinstance(p.attributes, dict) else {}
    description_approved = bool(attrs.get("b2b_description_approved"))
    specs_approved = bool(attrs.get("b2b_specs_approved"))
    missing: list[str] = []
    if not p.description:
        missing.append("public_description")
    if not images:
        missing.append("approved_image")
    if not p.category:
        missing.append("public_category")
    if specs is None:
        missing.append("specifications")
    if not p.b2b_public_slug:
        missing.append("public_slug")
    return ShowcaseProductOut(
        id=str(p.id),
        name=p.name,
        category=p.category,
        sku=p.sku,
        b2b_showcase_enabled=bool(p.b2b_showcase_enabled),
        b2b_public_slug=p.b2b_public_slug,
        has_images=bool(images),
        has_specifications=specs is not None,
        image_count=len(images),
        description_approved=description_approved,
        specs_approved=specs_approved,
        missing_evidence=missing,
    )


@showcase_admin_router.get("/products")
async def admin_list_showcase_products(
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    workspace_id: UUID = Depends(get_current_workspace_id),
    _user=Depends(get_current_user),
) -> dict:
    """列出可审核商品（含展示状态、缺失证据）。内部专用，可含成本字段但**本端点不返回价格/成本**。"""
    stmt = select(Product).where(
        Product.workspace_id == workspace_id, Product.deleted_at.is_(None)
    )
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(func.lower(Product.name).like(like))
    result = await db.execute(stmt.order_by(Product.created_at.desc()).limit(200))
    products = result.scalars().all()
    return {"items": [_showcase_product_to_out(p).model_dump() for p in products]}


@showcase_admin_router.patch("/products/{product_id}")
async def admin_update_showcase_product(
    product_id: UUID,
    payload: ShowcaseProductUpdate,
    db: AsyncSession = Depends(get_db),
    workspace_id: UUID = Depends(get_current_workspace_id),
    _user=Depends(get_current_user),
) -> dict:
    """更新商品展示设置（启用开关 / 公开 slug / 描述·规格批准）。绝不写入价格/成本。"""
    product = await db.get(Product, product_id)
    if product is None or product.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Product not found")
    if payload.b2b_showcase_enabled is not None:
        product.b2b_showcase_enabled = payload.b2b_showcase_enabled
    if payload.b2b_public_slug is not None:
        product.b2b_public_slug = payload.b2b_public_slug.strip() or None
    if payload.description_approved is not None or payload.specs_approved is not None:
        attrs = dict(product.attributes) if isinstance(product.attributes, dict) else {}
        if payload.description_approved is not None:
            attrs["b2b_description_approved"] = payload.description_approved
        if payload.specs_approved is not None:
            attrs["b2b_specs_approved"] = payload.specs_approved
        product.attributes = attrs
    await db.commit()
    await db.refresh(product)
    # M2.5.4-style audit trail for showcase curation decisions.
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_showcase.product_updated",
        entity_type="product",
        entity_id=str(product.id),
        payload={
            "b2b_showcase_enabled": bool(product.b2b_showcase_enabled),
            "b2b_public_slug": product.b2b_public_slug,
            "description_approved": bool(
                isinstance(product.attributes, dict)
                and product.attributes.get("b2b_description_approved")
            ),
            "specs_approved": bool(
                isinstance(product.attributes, dict)
                and product.attributes.get("b2b_specs_approved")
            ),
        },
    )
    return _showcase_product_to_out(product).model_dump()