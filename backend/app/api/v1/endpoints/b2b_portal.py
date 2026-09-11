"""B2B 代理商门户 API 端点。

独立路由前缀 /b2b-portal，面向外部代理商。
代理商认证与内部用户认证隔离（token_type=b2b_access）。
所有接口严格数据隔离：代理商只能访问自己的数据。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import validate_token
from app.models.b2b import B2BAgent
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
    B2BProductDetail,
    B2BProductListResponse,
    B2BTokenResponse,
)
from app.services.b2b_portal_service import (
    authenticate_agent,
    change_agent_password,
    create_agent_token,
    create_b2b_order,
    get_account_summary,
    get_agent_by_id,
    get_agent_order,
    get_product_detail_for_agent,
    list_agent_orders,
    list_products_for_agent,
    submit_application,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/b2b-portal", tags=["b2b-portal"])

# B2B 专用 token 方案（与内部用户的 /auth/login 区分）
b2b_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/b2b-portal/auth/login")


async def get_current_b2b_agent(
    token: str = Depends(b2b_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
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

    agent = await get_agent_by_id(db, agent_id)
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
    result = await db.execute(select(B2BAgent).where(B2BAgent.email == req.email.lower().strip()))
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
        db, str(current_agent.id), req.old_password, req.new_password
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
        db, str(current_agent.id), page, page_size, status_filter
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
    order = await get_agent_order(db, str(current_agent.id), order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_to_response(order)


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
