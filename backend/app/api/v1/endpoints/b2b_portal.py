"""B2B 代理商门户 API 端点。

独立路由前缀 /b2b-portal，面向外部代理商。
代理商认证与内部用户认证隔离（token_type=b2b_access）。
所有接口严格数据隔离：代理商只能访问自己的数据。
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import validate_token
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import B2BAgent, B2BOrder
from app.models.b2b_sales import B2BRFQ, B2BContract, B2BQuote
from app.schemas.b2b_portal import (
    B2BAccountSummary,
    B2BAgentProfile,
    B2BApplicationRequest,
    B2BApplicationResponse,
    B2BChangePasswordRequest,
    B2BCreateOrderRequest,
    B2BLoginRequest,
    B2BOrderItemResponse,
    B2BOrderListResponse,
    B2BOrderResponse,
    B2BPortalContractListResponse,
    B2BPortalContractResponse,
    B2BPortalContractSignRequest,
    B2BPortalOrderConversionResponse,
    B2BPortalQuoteDecisionRequest,
    B2BPortalQuoteItemResponse,
    B2BPortalQuoteListResponse,
    B2BPortalQuoteResponse,
    B2BPortalRFQCreate,
    B2BPortalRFQItemResponse,
    B2BPortalRFQListResponse,
    B2BPortalRFQResponse,
    B2BProductDetail,
    B2BProductListResponse,
    B2BTokenResponse,
)
from app.services import b2b_credit_service, b2b_sales_service
from app.services.b2b_portal_service import (
    accept_agent_quote,
    change_agent_password,
    convert_agent_contract_to_order,
    create_agent_rfq,
    create_agent_token,
    create_b2b_order,
    get_account_summary,
    get_agent_by_id,
    get_agent_contract,
    get_agent_order,
    get_agent_quote,
    get_agent_rfq,
    get_product_detail_for_agent,
    list_agent_contracts,
    list_agent_orders,
    list_agent_quotes,
    list_agent_rfqs,
    list_products_for_agent,
    reject_agent_quote,
    sign_agent_contract,
    submit_application,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/b2b-portal", tags=["b2b-portal"])

# B2B 专用 token 方案（与内部用户的 /auth/login 区分）
b2b_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/b2b-portal/auth/login")


async def get_current_b2b_agent(
    token: str = Depends(b2b_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
) -> B2BAgent:
    """B2B 代理商认证依赖注入。

    校验 token_type 必须为 b2b_access，防止内部用户 token 越权访问 B2B 门户。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = validate_token(token, token_type="b2b_access")
    if not payload:
        raise credentials_exception

    agent_id = payload.get("sub")
    if not agent_id:
        raise credentials_exception

    token_workspace = payload.get("workspace_id")
    if not token_workspace:
        raise credentials_exception
    try:
        workspace_id = UUID(str(token_workspace))
    except ValueError as exc:
        raise credentials_exception from exc

    if x_workspace_id is not None:
        try:
            requested_workspace = UUID(x_workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid X-Workspace-Id") from exc
        if requested_workspace != workspace_id:
            raise HTTPException(status_code=403, detail="workspace header mismatch")

    agent = await get_agent_by_id(db, agent_id, workspace_id=workspace_id)
    if not agent:
        raise credentials_exception
    if agent.status != "active":
        raise HTTPException(status_code=403, detail="Agent account is not active")

    return agent


def _agent_to_profile(agent: B2BAgent) -> B2BAgentProfile:
    """将 ORM 对象转为响应模型（计算 available_credit）。"""
    available = agent.credit_limit - agent.current_balance
    return B2BAgentProfile(
        id=str(agent.id),
        agent_number=agent.agent_number,
        company_name=agent.company_name,
        contact_name=agent.contact_name,
        email=agent.email,
        phone=agent.phone,
        country=agent.country,
        city=agent.city,
        address=agent.address,
        tier=agent.tier,
        status=agent.status,
        commission_rate=agent.commission_rate,
        discount_percent=agent.discount_percent,
        credit_limit=agent.credit_limit,
        current_balance=agent.current_balance,
        available_credit=available if available > 0 else 0,
        payment_terms_days=agent.payment_terms_days,
        currency=agent.currency,
        last_login_at=agent.last_login_at,
    )


# ============================================
# 代理商申请（公开）
# ============================================

@router.post("/applications", response_model=B2BApplicationResponse, status_code=201)
async def b2b_submit_application(
    req: B2BApplicationRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """公开提交代理商申请。

    创建 pending 状态账号，管理端审核通过后激活。
    审核期间无法登录。
    """
    try:
        agent = await submit_application(
            db,
            company_name=req.company_name,
            contact_name=req.contact_name,
            email=req.email,
            password=req.password,
            phone=req.phone,
            whatsapp=req.whatsapp,
            wechat=req.wechat,
            country=req.country,
            city=req.city,
            address=req.address,
            business_type=req.business_type,
            website=req.website,
            estimated_annual_volume=req.estimated_annual_volume,
            product_interests=req.product_interests,
            message=req.message,
            workspace_id=DEFAULT_WORKSPACE_ID,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return B2BApplicationResponse(
        id=str(agent.id),
        email=agent.email,
        company_name=agent.company_name,
        status=agent.status,
        message="Application submitted successfully. Our team will review and contact you within 1-2 business days.",
    )


# ============================================
# 认证
# ============================================

@router.post("/auth/login", response_model=B2BTokenResponse)
async def b2b_login(
    req: B2BLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """代理商登录（邮箱+密码），返回 JWT。"""
    from sqlalchemy import select

    from app.core.security import verify_password

    # 先查账号，区分"不存在/密码错误"和"状态未激活"
    result = await db.execute(
        select(B2BAgent).where(
            B2BAgent.workspace_id == DEFAULT_WORKSPACE_ID,
            B2BAgent.email == req.email.lower().strip(),
        )
    )
    agent = result.scalar_one_or_none()

    if not agent or not verify_password(req.password, agent.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if agent.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your application is pending approval. We will notify you once it's reviewed.",
        )
    if agent.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your application was rejected. Please contact support for more information.",
        )
    if agent.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended. Please contact support.",
        )

    # 更新最后登录时间
    from datetime import datetime, timezone
    agent.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    token = create_agent_token(agent)
    return B2BTokenResponse(
        access_token=token,
        token_type="bearer",
        agent=_agent_to_profile(agent),
    )


@router.get("/auth/me", response_model=B2BAgentProfile)
async def b2b_me(
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
) -> Any:
    """获取当前登录代理商资料。"""
    return _agent_to_profile(current_agent)


@router.post("/auth/change-password")
async def b2b_change_password(
    req: B2BChangePasswordRequest,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """修改密码。"""
    success = await change_agent_password(
        db,
        str(current_agent.id),
        req.old_password,
        req.new_password,
        workspace_id=current_agent.workspace_id,
    )
    if not success:
        raise HTTPException(status_code=400, detail="Old password is incorrect")
    return {"message": "Password changed successfully"}


# ============================================
# 商品
# ============================================

@router.get("/products", response_model=B2BProductListResponse)
async def b2b_list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    category: str | None = None,
    in_stock_only: bool = False,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """商品列表（含该代理商批发价、MOQ、库存）。"""
    items, total = await list_products_for_agent(
        db, current_agent, page, page_size, search, category, in_stock_only
    )
    return B2BProductListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/products/{product_id}", response_model=B2BProductDetail)
async def b2b_get_product(
    product_id: str,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """商品详情。"""
    product = await get_product_detail_for_agent(db, product_id, current_agent)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# ============================================
# 订单
# ============================================

def _order_to_response(order: B2BOrder) -> B2BOrderResponse:
    """将 ORM 订单对象转为响应模型（手动转换 UUID 为 str）。"""
    return B2BOrderResponse(
        id=str(order.id),
        order_number=order.order_number,
        status=order.status,
        payment_status=order.payment_status,
        subtotal=order.subtotal,
        discount_amount=order.discount_amount,
        shipping_cost=order.shipping_cost,
        total=order.total,
        currency=order.currency,
        shipping_address=order.shipping_address or {},
        payment_due_date=order.payment_due_date,
        tracking_number=order.tracking_number,
        tracking_carrier=order.tracking_carrier,
        notes=order.notes,
        items=[
            B2BOrderItemResponse(
                id=str(item.id),
                product_id=str(item.product_id),
                product_name=item.product_name,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.subtotal,
            )
            for item in order.items
        ],
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _portal_rfq_item_response(item) -> B2BPortalRFQItemResponse:
    return B2BPortalRFQItemResponse(
        id=str(item.id),
        product_id=str(item.product_id),
        sku_snapshot=item.sku_snapshot,
        product_name_snapshot=item.product_name_snapshot,
        requested_quantity=item.requested_quantity,
        target_unit_price=item.target_unit_price,
        specifications=item.specifications or {},
        notes=item.notes,
    )


def _portal_rfq_response(rfq: B2BRFQ) -> B2BPortalRFQResponse:
    return B2BPortalRFQResponse(
        id=str(rfq.id),
        rfq_number=rfq.rfq_number,
        status=rfq.status,
        source=rfq.source,
        requested_currency=rfq.requested_currency,
        destination_country=rfq.destination_country,
        incoterm=rfq.incoterm,
        requested_delivery_date=rfq.requested_delivery_date,
        notes=rfq.notes,
        submitted_at=rfq.submitted_at,
        closed_at=rfq.closed_at,
        items=[_portal_rfq_item_response(item) for item in rfq.items],
        created_at=rfq.created_at,
        updated_at=rfq.updated_at,
    )


def _portal_quote_item_response(item) -> B2BPortalQuoteItemResponse:
    return B2BPortalQuoteItemResponse(
        id=str(item.id),
        product_id=str(item.product_id),
        sku_snapshot=item.sku_snapshot,
        product_name_snapshot=item.product_name_snapshot,
        quantity=item.quantity,
        unit_price=item.unit_price,
        discount_percent=item.discount_percent,
        line_subtotal=item.line_subtotal,
        line_total=item.line_total,
        price_source=item.price_source,
        specifications=item.specifications or {},
    )


def _portal_quote_response(quote: B2BQuote) -> B2BPortalQuoteResponse:
    contract = quote.contract
    return B2BPortalQuoteResponse(
        id=str(quote.id),
        quote_number=quote.quote_number,
        version_number=quote.version_number,
        rfq_id=str(quote.rfq_id) if quote.rfq_id else None,
        rfq_number=quote.rfq.rfq_number if quote.rfq else None,
        status=quote.status,
        currency=quote.currency,
        valid_until=quote.valid_until,
        payment_terms_days=quote.payment_terms_days,
        incoterm=quote.incoterm,
        shipping_terms=quote.shipping_terms,
        subtotal=quote.subtotal,
        discount_amount=quote.discount_amount,
        shipping_cost=quote.shipping_cost,
        tax_amount=quote.tax_amount,
        total=quote.total,
        sent_at=quote.sent_at,
        accepted_at=quote.accepted_at,
        rejected_at=quote.rejected_at,
        rejection_reason=quote.rejection_reason,
        notes=quote.notes,
        items=[_portal_quote_item_response(item) for item in quote.items],
        contract=(
            {
                "id": str(contract.id),
                "contract_number": contract.contract_number,
                "status": contract.status,
                "customer_signed_at": contract.customer_signed_at,
                "company_signed_at": contract.company_signed_at,
                "activated_at": contract.activated_at,
            }
            if contract
            else None
        ),
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


def _portal_contract_response(contract: B2BContract) -> B2BPortalContractResponse:
    quote = contract.quote
    return B2BPortalContractResponse(
        id=str(contract.id),
        contract_number=contract.contract_number,
        quote_id=str(contract.quote_id),
        quote_number=quote.quote_number if quote else None,
        version_number=quote.version_number if quote else None,
        status=contract.status,
        effective_from=contract.effective_from,
        effective_to=contract.effective_to,
        currency=contract.currency,
        total=contract.total,
        document_url=contract.document_url,
        terms=contract.terms or {},
        customer_signed_by=contract.customer_signed_by,
        customer_signed_at=contract.customer_signed_at,
        company_signed_at=contract.company_signed_at,
        activated_at=contract.activated_at,
        terminated_at=contract.terminated_at,
        items=[_portal_quote_item_response(item) for item in quote.items] if quote else [],
        created_at=contract.created_at,
        updated_at=contract.updated_at,
    )


def _portal_sales_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, b2b_credit_service.B2BCreditError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, b2b_sales_service.B2BSalesStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 422
        return HTTPException(status_code=status_code, detail=message)
    return HTTPException(status_code=500, detail="B2B portal operation failed")


def _require_portal_uuid(value: str, resource: str) -> None:
    try:
        UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"{resource} not found") from exc


@router.post("/orders", response_model=B2BOrderResponse, status_code=201)
async def b2b_create_order(
    req: B2BCreateOrderRequest,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """创建 B2B 订单（提交购物车）。"""
    try:
        order = await create_b2b_order(
            db,
            current_agent,
            [item.model_dump() for item in req.items],
            req.shipping_address,
            req.notes,
        )
    except Exception as exc:
        raise _portal_sales_http_error(exc) from exc
    return _order_to_response(order)


@router.get("/orders", response_model=B2BOrderListResponse)
async def b2b_list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """我的订单列表。"""
    orders, total = await list_agent_orders(
        db,
        str(current_agent.id),
        current_agent.workspace_id,
        page,
        page_size,
        status_filter,
    )
    return B2BOrderListResponse(
        items=[_order_to_response(o) for o in orders], total=total, page=page, page_size=page_size
    )


@router.get("/orders/{order_id}", response_model=B2BOrderResponse)
async def b2b_get_order(
    order_id: str,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """订单详情（含明细、物流）。"""
    order = await get_agent_order(
        db,
        str(current_agent.id),
        order_id,
        current_agent.workspace_id,
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_to_response(order)


# ============================================
# 门户自助销售：RFQ、报价与合同
# ============================================

@router.post("/rfqs", response_model=B2BPortalRFQResponse, status_code=201)
async def b2b_create_rfq(
    req: B2BPortalRFQCreate,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Submit an RFQ for the authenticated agent."""
    try:
        rfq = await create_agent_rfq(
            db,
            current_agent,
            items=[item.model_dump() for item in req.items],
            requested_currency=req.requested_currency,
            destination_country=req.destination_country,
            incoterm=req.incoterm,
            requested_delivery_date=req.requested_delivery_date,
            notes=req.notes,
        )
    except ValueError as exc:
        raise _portal_sales_http_error(exc) from exc
    return _portal_rfq_response(rfq)


@router.get("/rfqs", response_model=B2BPortalRFQListResponse)
async def b2b_list_rfqs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status", max_length=24),
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List RFQs owned by the authenticated agent."""
    try:
        rfqs, total = await list_agent_rfqs(
            db,
            current_agent,
            page=page,
            page_size=page_size,
            status=status_filter,
        )
    except ValueError as exc:
        raise _portal_sales_http_error(exc) from exc
    return B2BPortalRFQListResponse(
        items=[_portal_rfq_response(rfq) for rfq in rfqs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/rfqs/{rfq_id}", response_model=B2BPortalRFQResponse)
async def b2b_get_rfq(
    rfq_id: str,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return one RFQ owned by the authenticated agent."""
    _require_portal_uuid(rfq_id, "RFQ")
    rfq = await get_agent_rfq(db, current_agent, rfq_id)
    if rfq is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return _portal_rfq_response(rfq)


@router.get("/quotes", response_model=B2BPortalQuoteListResponse)
async def b2b_list_quotes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status", max_length=24),
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List quotes released to the authenticated agent."""
    try:
        quotes, total = await list_agent_quotes(
            db,
            current_agent,
            page=page,
            page_size=page_size,
            status=status_filter,
        )
    except ValueError as exc:
        raise _portal_sales_http_error(exc) from exc
    return B2BPortalQuoteListResponse(
        items=[_portal_quote_response(quote) for quote in quotes],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/quotes/{quote_id}", response_model=B2BPortalQuoteResponse)
async def b2b_get_quote(
    quote_id: str,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return one released quote owned by the authenticated agent."""
    _require_portal_uuid(quote_id, "Quote")
    quote = await get_agent_quote(db, current_agent, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")
    return _portal_quote_response(quote)


@router.post("/quotes/{quote_id}/accept", response_model=B2BPortalQuoteResponse)
async def b2b_accept_quote(
    quote_id: str,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Accept a sent quote as the authenticated customer."""
    _require_portal_uuid(quote_id, "Quote")
    try:
        quote = await accept_agent_quote(db, current_agent, quote_id)
    except ValueError as exc:
        raise _portal_sales_http_error(exc) from exc
    return _portal_quote_response(quote)


@router.post("/quotes/{quote_id}/reject", response_model=B2BPortalQuoteResponse)
async def b2b_reject_quote(
    quote_id: str,
    req: B2BPortalQuoteDecisionRequest,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Reject a sent quote as the authenticated customer."""
    _require_portal_uuid(quote_id, "Quote")
    try:
        quote = await reject_agent_quote(
            db,
            current_agent,
            quote_id,
            reason=req.reason,
        )
    except ValueError as exc:
        raise _portal_sales_http_error(exc) from exc
    return _portal_quote_response(quote)


@router.get("/contracts", response_model=B2BPortalContractListResponse)
async def b2b_list_contracts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status", max_length=24),
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List contracts owned by the authenticated agent."""
    try:
        contracts, total = await list_agent_contracts(
            db,
            current_agent,
            page=page,
            page_size=page_size,
            status=status_filter,
        )
    except ValueError as exc:
        raise _portal_sales_http_error(exc) from exc
    return B2BPortalContractListResponse(
        items=[_portal_contract_response(contract) for contract in contracts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/contracts/{contract_id}", response_model=B2BPortalContractResponse)
async def b2b_get_contract(
    contract_id: str,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return one contract owned by the authenticated agent."""
    _require_portal_uuid(contract_id, "Contract")
    contract = await get_agent_contract(db, current_agent, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return _portal_contract_response(contract)


@router.post("/contracts/{contract_id}/sign", response_model=B2BPortalContractResponse)
async def b2b_sign_contract(
    contract_id: str,
    req: B2BPortalContractSignRequest,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Record the authenticated customer's signature."""
    _require_portal_uuid(contract_id, "Contract")
    try:
        contract = await sign_agent_contract(
            db,
            current_agent,
            contract_id,
            signed_by=req.signed_by,
        )
    except ValueError as exc:
        raise _portal_sales_http_error(exc) from exc
    return _portal_contract_response(contract)


@router.post(
    "/contracts/{contract_id}/convert-to-order",
    response_model=B2BPortalOrderConversionResponse,
    status_code=201,
)
async def b2b_convert_contract_to_order(
    contract_id: str,
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Idempotently convert an active contract's accepted quote to an order."""
    _require_portal_uuid(contract_id, "Contract")
    try:
        order = await convert_agent_contract_to_order(
            db,
            current_agent,
            contract_id,
        )
    except ValueError as exc:
        raise _portal_sales_http_error(exc) from exc
    return B2BPortalOrderConversionResponse(
        id=str(order.id),
        order_number=order.order_number,
        quote_id=str(order.quote_id),
        contract_id=str(order.contract_id),
        status=order.status,
        payment_status=order.payment_status,
        total=order.total,
        currency=order.currency,
    )


# ============================================
# 账户
# ============================================

@router.get("/account/summary", response_model=B2BAccountSummary)
async def b2b_account_summary(
    current_agent: B2BAgent = Depends(get_current_b2b_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """账户概览（信用额度、欠款、订单统计）。"""
    summary = await get_account_summary(db, current_agent)
    summary["agent"] = _agent_to_profile(summary["agent"])
    return summary
