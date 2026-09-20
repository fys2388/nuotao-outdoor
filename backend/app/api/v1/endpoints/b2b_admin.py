"""B2B 管理端 API（内部管理员使用）。

路由前缀 /admin/b2b，需要内部用户认证（token_type=access）。
提供代理商管理、订单管理、定价管理、统计等功能。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.endpoints.auth import get_current_user, get_current_workspace_id
from app.core.database import get_db
from app.core.security import get_password_hash
from app.core.tracing import get_trace_id
from app.models.b2b import B2BAgent, B2BOrder, B2BProductPrice
from app.services.b2b_portal_service import (
    B2BOrderStateError,
    update_b2b_order_status,
)
from app.services.customer_account_service import get_or_create_b2b_account
from app.services.customer_identity_service import link_identity_to_account
from app.services.email_service import (
    get_email_service,
    render_b2b_approval_email,
    render_b2b_rejection_email,
)
from app.models.product import Product
from app.schemas.b2b_admin import (
    AdminB2BAgentCreate,
    AdminB2BAgentListResponse,
    AdminB2BAgentResponse,
    AdminB2BAgentStatusUpdate,
    AdminB2BAgentUpdate,
    AdminB2BOrderListResponse,
    AdminB2BOrderResponse,
    AdminB2BOrderStatusUpdate,
    AdminB2BPriceCreate,
    AdminB2BPriceListResponse,
    AdminB2BPriceResponse,
    AdminB2BPriceUpdate,
    AdminB2BResetPassword,
    AdminB2BStatsResponse,
)
from app.schemas.user import UserResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/b2b", tags=["admin-b2b"])
WorkspaceId = UUID


def _parse_uuid(value: str | UUID) -> UUID | None:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except ValueError:
        return None


async def _get_agent(
    db: AsyncSession, *, workspace_id: UUID, agent_id: str
) -> B2BAgent | None:
    parsed_agent_id = _parse_uuid(agent_id)
    if parsed_agent_id is None:
        return None
    return (
        await db.execute(
            select(B2BAgent).where(
                B2BAgent.workspace_id == workspace_id,
                B2BAgent.id == parsed_agent_id,
            )
        )
    ).scalar_one_or_none()


async def _get_product(
    db: AsyncSession, *, workspace_id: UUID, product_id: str
) -> Product | None:
    parsed_product_id = _parse_uuid(product_id)
    if parsed_product_id is None:
        return None
    return (
        await db.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.id == parsed_product_id,
            )
        )
    ).scalar_one_or_none()


# ============================================
# 辅助函数
# ============================================

def _agent_to_response(agent: B2BAgent, order_count: int = 0, total_revenue: Decimal = Decimal("0")) -> AdminB2BAgentResponse:
    available = agent.credit_limit - agent.current_balance
    return AdminB2BAgentResponse(
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
        available_credit=available if available > 0 else Decimal("0"),
        payment_terms_days=agent.payment_terms_days,
        currency=agent.currency,
        notes=agent.notes,
        last_login_at=agent.last_login_at,
        created_at=agent.created_at,
        order_count=order_count,
        total_revenue=total_revenue,
    )


def _order_to_response(order: B2BOrder) -> AdminB2BOrderResponse:
    return AdminB2BOrderResponse(
        id=str(order.id),
        order_number=order.order_number,
        agent_id=str(order.agent_id),
        agent_company=order.agent.company_name if order.agent else "",
        agent_email=order.agent.email if order.agent else "",
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
            AdminB2BOrderResponse.model_fields["items"].annotation.__args__[0](
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


# ============================================
# 统计
# ============================================

@router.get("/stats", response_model=AdminB2BStatsResponse)
async def admin_b2b_stats(
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BStatsResponse:
    """B2B 业务统计概览。"""
    # 代理商统计
    agent_counts = await db.execute(
        select(B2BAgent.status, func.count(B2BAgent.id))
        .where(B2BAgent.workspace_id == workspace_id)
        .group_by(B2BAgent.status)
    )
    status_map = {row[0]: row[1] for row in agent_counts.all()}

    # 订单统计
    order_stats = await db.execute(
        select(
            func.count(B2BOrder.id),
            func.coalesce(func.sum(B2BOrder.total), Decimal("0")),
            func.count(B2BOrder.id).filter(B2BOrder.status == "pending"),
        ).where(B2BOrder.workspace_id == workspace_id)
    )
    total_orders, total_revenue, pending_orders = order_stats.one()

    # 信用统计
    credit_stats = await db.execute(
        select(
            func.coalesce(func.sum(B2BAgent.credit_limit), Decimal("0")),
            func.coalesce(func.sum(B2BAgent.current_balance), Decimal("0")),
        ).where(B2BAgent.workspace_id == workspace_id)
    )
    total_credit, total_balance = credit_stats.one()

    return AdminB2BStatsResponse(
        total_agents=sum(status_map.values()),
        active_agents=status_map.get("active", 0),
        pending_agents=status_map.get("pending", 0),
        suspended_agents=status_map.get("suspended", 0),
        total_orders=total_orders or 0,
        total_revenue=total_revenue or Decimal("0"),
        pending_orders=pending_orders or 0,
        total_credit_limit=total_credit or Decimal("0"),
        total_outstanding_balance=total_balance or Decimal("0"),
    )


# ============================================
# 代理商管理
# ============================================

@router.get("/agents", response_model=AdminB2BAgentListResponse)
async def admin_b2b_list_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    tier: str | None = None,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BAgentListResponse:
    """代理商列表（支持搜索、状态筛选、等级筛选、分页）。"""
    query = select(B2BAgent).where(B2BAgent.workspace_id == workspace_id)
    count_query = select(func.count(B2BAgent.id)).where(B2BAgent.workspace_id == workspace_id)

    if search:
        search_pattern = f"%{search}%"
        filter_cond = or_(
            B2BAgent.company_name.ilike(search_pattern),
            B2BAgent.contact_name.ilike(search_pattern),
            B2BAgent.email.ilike(search_pattern),
            B2BAgent.agent_number.ilike(search_pattern),
        )
        query = query.where(filter_cond)
        count_query = count_query.where(filter_cond)

    if status_filter:
        query = query.where(B2BAgent.status == status_filter)
        count_query = count_query.where(B2BAgent.status == status_filter)

    if tier:
        query = query.where(B2BAgent.tier == tier)
        count_query = count_query.where(B2BAgent.tier == tier)

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(B2BAgent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    agents = (await db.execute(query)).scalars().all()

    # 批量查询每个代理商的订单数和营收
    items = []
    for agent in agents:
        order_stats = await db.execute(
            select(
                func.count(B2BOrder.id),
                func.coalesce(func.sum(B2BOrder.total), Decimal("0")),
            ).where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.agent_id == agent.id,
            )
        )
        order_count, total_rev = order_stats.one()
        items.append(_agent_to_response(agent, order_count or 0, total_rev or Decimal("0")))

    return AdminB2BAgentListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/agents", response_model=AdminB2BAgentResponse, status_code=201)
async def admin_b2b_create_agent(
    req: AdminB2BAgentCreate,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BAgentResponse:
    """创建代理商账号。"""
    # 检查邮箱是否已存在
    existing = await db.execute(
        select(B2BAgent).where(
            B2BAgent.workspace_id == workspace_id,
            B2BAgent.email == req.email.lower(),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists")

    now = datetime.now(timezone.utc)
    agent_id = uuid4()
    agent_number = f"AG-{now.strftime('%Y%m%d')}-{str(agent_id)[:8].upper()}"
    account = await get_or_create_b2b_account(
        db,
        workspace_id=workspace_id,
        agent_number=agent_number,
        company_name=req.company_name,
        country=req.country,
        default_currency=req.currency,
        trace_id=get_trace_id(),
    )

    agent = B2BAgent(
        id=agent_id,
        workspace_id=workspace_id,
        agent_number=agent_number,
        customer_account_id=account.id,
        company_name=req.company_name,
        contact_name=req.contact_name,
        email=req.email.lower(),
        phone=req.phone,
        country=req.country,
        city=req.city,
        address=req.address,
        hashed_password=get_password_hash(req.password),
        tier=req.tier,
        status=req.status,
        commission_rate=req.commission_rate,
        discount_percent=req.discount_percent,
        credit_limit=req.credit_limit,
        payment_terms_days=req.payment_terms_days,
        currency=req.currency,
        notes=req.notes,
    )
    db.add(agent)
    await db.flush()
    await link_identity_to_account(
        db,
        workspace_id=workspace_id,
        account_id=account.id,
        identity_type="email",
        identity_value=req.email,
        channel="b2b_portal",
        external_system="b2b_agent",
        source="b2b_agent_created",
        metadata={"agent_id": str(agent.id)},
        trace_id=get_trace_id(),
    )
    await db.commit()
    await db.refresh(agent)

    logger.info(f"Admin {current_user.email} created B2B agent {agent_number}")
    return _agent_to_response(agent)


@router.get("/agents/{agent_id}", response_model=AdminB2BAgentResponse)
async def admin_b2b_get_agent(
    agent_id: str,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BAgentResponse:
    """代理商详情。"""
    agent = await _get_agent(db, workspace_id=workspace_id, agent_id=agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    order_stats = await db.execute(
        select(
            func.count(B2BOrder.id),
            func.coalesce(func.sum(B2BOrder.total), Decimal("0")),
        ).where(
            B2BOrder.workspace_id == workspace_id,
            B2BOrder.agent_id == agent.id,
        )
    )
    order_count, total_rev = order_stats.one()
    return _agent_to_response(agent, order_count or 0, total_rev or Decimal("0"))


@router.put("/agents/{agent_id}", response_model=AdminB2BAgentResponse)
async def admin_b2b_update_agent(
    agent_id: str,
    req: AdminB2BAgentUpdate,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BAgentResponse:
    """更新代理商信息。"""
    agent = await _get_agent(db, workspace_id=workspace_id, agent_id=agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)
    logger.info(f"Admin {current_user.email} updated agent {agent.agent_number}")
    return _agent_to_response(agent)


@router.patch("/agents/{agent_id}/status", response_model=AdminB2BAgentResponse)
async def admin_b2b_update_agent_status(
    agent_id: str,
    req: AdminB2BAgentStatusUpdate,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BAgentResponse:
    """更改代理商状态（审核通过/停用/启用等）。"""
    agent = await _get_agent(db, workspace_id=workspace_id, agent_id=agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    old_status = agent.status
    agent.status = req.status
    await db.commit()
    await db.refresh(agent)
    logger.info(f"Admin {current_user.email} changed agent {agent.agent_number} status: {old_status} -> {req.status}")

    # 状态变更邮件通知
    try:
        email_service = get_email_service()
        agent_dict = {
            "company_name": agent.company_name,
            "contact_name": agent.contact_name,
            "email": agent.email,
            "tier": agent.tier,
        }
        if old_status == "pending" and req.status == "active":
            subject, html, text = render_b2b_approval_email(agent_dict)
            await email_service.send_email(
                to_email=agent.email,
                subject=subject,
                html_content=html,
                text_content=text,
                metadata={"type": "b2b_approval", "agent_id": str(agent.id)},
            )
            logger.info("Approval email sent to %s", agent.email)
        elif old_status == "pending" and req.status == "rejected":
            reason = getattr(req, "reason", "") or ""
            subject, html, text = render_b2b_rejection_email(agent_dict, reason)
            await email_service.send_email(
                to_email=agent.email,
                subject=subject,
                html_content=html,
                text_content=text,
                metadata={"type": "b2b_rejection", "agent_id": str(agent.id)},
            )
            logger.info("Rejection email sent to %s", agent.email)
    except Exception as e:
        logger.warning("B2B status notification email failed: %s", str(e))

    return _agent_to_response(agent)


@router.post("/agents/{agent_id}/reset-password")
async def admin_b2b_reset_password(
    agent_id: str,
    req: AdminB2BResetPassword,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """重置代理商密码。"""
    agent = await _get_agent(db, workspace_id=workspace_id, agent_id=agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.hashed_password = get_password_hash(req.new_password)
    await db.commit()
    logger.info(f"Admin {current_user.email} reset password for agent {agent.agent_number}")
    return {"message": "Password reset successfully"}


# ============================================
# 订单管理
# ============================================

@router.get("/orders", response_model=AdminB2BOrderListResponse)
async def admin_b2b_list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    payment_status: str | None = None,
    agent_id: str | None = None,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BOrderListResponse:
    """所有 B2B 订单列表。"""
    query = select(B2BOrder).where(B2BOrder.workspace_id == workspace_id)
    count_query = select(func.count(B2BOrder.id)).where(
        B2BOrder.workspace_id == workspace_id
    )

    if status_filter:
        query = query.where(B2BOrder.status == status_filter)
        count_query = count_query.where(B2BOrder.status == status_filter)
    if payment_status:
        query = query.where(B2BOrder.payment_status == payment_status)
        count_query = count_query.where(B2BOrder.payment_status == payment_status)
    if agent_id:
        agent = await _get_agent(db, workspace_id=workspace_id, agent_id=agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        query = query.where(B2BOrder.agent_id == agent.id)
        count_query = count_query.where(B2BOrder.agent_id == agent.id)

    total = (await db.execute(count_query)).scalar_one()
    query = (
        query.options(selectinload(B2BOrder.agent))
        .order_by(B2BOrder.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    orders = (await db.execute(query)).scalars().all()

    return AdminB2BOrderListResponse(
        items=[_order_to_response(o) for o in orders],
        total=total, page=page, page_size=page_size,
    )


@router.get("/orders/{order_id}", response_model=AdminB2BOrderResponse)
async def admin_b2b_get_order(
    order_id: str,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BOrderResponse:
    """订单详情。"""
    parsed_order_id = _parse_uuid(order_id)
    if parsed_order_id is None:
        raise HTTPException(status_code=404, detail="Order not found")
    result = await db.execute(
        select(B2BOrder)
        .options(selectinload(B2BOrder.agent))
        .where(
            B2BOrder.workspace_id == workspace_id,
            B2BOrder.id == parsed_order_id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_to_response(order)


@router.patch("/orders/{order_id}/status", response_model=AdminB2BOrderResponse)
async def admin_b2b_update_order_status(
    order_id: str,
    req: AdminB2BOrderStatusUpdate,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BOrderResponse:
    """更新非履约状态；发货和送达只能通过履约工作流完成。"""
    actor = current_user.email or current_user.username
    try:
        order = await update_b2b_order_status(
            db,
            workspace_id=workspace_id,
            order_id=order_id,
            new_status=req.status,
            actor=actor,
            trace_id=get_trace_id(),
        )
    except B2BOrderStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _order_to_response(order)


# ============================================
# 定价管理
# ============================================

@router.get("/prices", response_model=AdminB2BPriceListResponse)
async def admin_b2b_list_prices(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    product_id: str | None = None,
    tier: str | None = None,
    agent_id: str | None = None,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BPriceListResponse:
    """批发价列表。"""
    query = select(B2BProductPrice).where(B2BProductPrice.workspace_id == workspace_id)
    count_query = select(func.count(B2BProductPrice.id)).where(
        B2BProductPrice.workspace_id == workspace_id
    )

    if product_id:
        parsed_product_id = _parse_uuid(product_id)
        if parsed_product_id is None:
            return AdminB2BPriceListResponse(
                items=[], total=0, page=page, page_size=page_size
            )
        query = query.where(B2BProductPrice.product_id == parsed_product_id)
        count_query = count_query.where(B2BProductPrice.product_id == parsed_product_id)
    if tier:
        query = query.where(B2BProductPrice.tier == tier)
        count_query = count_query.where(B2BProductPrice.tier == tier)
    if agent_id:
        parsed_agent_id = _parse_uuid(agent_id)
        if parsed_agent_id is None:
            return AdminB2BPriceListResponse(
                items=[], total=0, page=page, page_size=page_size
            )
        query = query.where(B2BProductPrice.agent_id == parsed_agent_id)
        count_query = count_query.where(B2BProductPrice.agent_id == parsed_agent_id)

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(B2BProductPrice.product_id, B2BProductPrice.tier).offset((page - 1) * page_size).limit(page_size)
    prices = (await db.execute(query)).scalars().all()

    # 批量查询商品名和代理商名
    product_ids = {p.product_id for p in prices}
    agent_ids = {p.agent_id for p in prices if p.agent_id}

    products = {}
    if product_ids:
        prod_result = await db.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.id.in_(product_ids),
            )
        )
        products = {str(p.id): p for p in prod_result.scalars().all()}

    agents = {}
    if agent_ids:
        agent_result = await db.execute(
            select(B2BAgent).where(
                B2BAgent.workspace_id == workspace_id,
                B2BAgent.id.in_(agent_ids),
            )
        )
        agents = {str(a.id): a for a in agent_result.scalars().all()}

    items = []
    for p in prices:
        prod = products.get(str(p.product_id))
        ag = agents.get(str(p.agent_id)) if p.agent_id else None
        items.append(AdminB2BPriceResponse(
            id=str(p.id),
            product_id=str(p.product_id),
            product_name=prod.name if prod else "",
            product_sku=prod.sku if prod else "",
            tier=p.tier,
            agent_id=str(p.agent_id) if p.agent_id else None,
            agent_company=ag.company_name if ag else None,
            wholesale_price=p.wholesale_price,
            moq=p.moq,
            currency=p.currency,
            is_active=p.is_active,
            created_at=p.created_at,
            updated_at=p.updated_at,
        ))

    return AdminB2BPriceListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/prices", response_model=AdminB2BPriceResponse, status_code=201)
async def admin_b2b_create_price(
    req: AdminB2BPriceCreate,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BPriceResponse:
    """创建批发价（按等级或按代理商专属）。"""
    # 校验商品存在
    product = await _get_product(db, workspace_id=workspace_id, product_id=req.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if req.agent_id:
        agent = await _get_agent(db, workspace_id=workspace_id, agent_id=req.agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")

    # 校验唯一性
    parsed_product_id = _parse_uuid(req.product_id)
    parsed_agent_id = _parse_uuid(req.agent_id) if req.agent_id else None
    if parsed_product_id is None:
        raise HTTPException(status_code=404, detail="Product not found")
    existing = await db.execute(
        select(B2BProductPrice).where(
            B2BProductPrice.workspace_id == workspace_id,
            B2BProductPrice.product_id == parsed_product_id,
            B2BProductPrice.tier == req.tier if req.tier else B2BProductPrice.tier.is_(None),
            B2BProductPrice.agent_id == parsed_agent_id
            if parsed_agent_id
            else B2BProductPrice.agent_id.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Price already exists for this product/tier/agent combination")

    price = B2BProductPrice(
        workspace_id=workspace_id,
        product_id=parsed_product_id,
        tier=req.tier,
        agent_id=parsed_agent_id,
        wholesale_price=req.wholesale_price,
        moq=req.moq,
        currency=req.currency,
        is_active=req.is_active,
    )
    db.add(price)
    await db.commit()
    await db.refresh(price)

    return AdminB2BPriceResponse(
        id=str(price.id),
        product_id=str(price.product_id),
        product_name=product.name,
        product_sku=product.sku,
        tier=price.tier,
        agent_id=str(price.agent_id) if price.agent_id else None,
        wholesale_price=price.wholesale_price,
        moq=price.moq,
        currency=price.currency,
        is_active=price.is_active,
        created_at=price.created_at,
        updated_at=price.updated_at,
    )


@router.put("/prices/{price_id}", response_model=AdminB2BPriceResponse)
async def admin_b2b_update_price(
    price_id: str,
    req: AdminB2BPriceUpdate,
    current_user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AdminB2BPriceResponse:
    """更新批发价。"""
    parsed_price_id = _parse_uuid(price_id)
    if parsed_price_id is None:
        raise HTTPException(status_code=404, detail="Price not found")
    price = (
        await db.execute(
            select(B2BProductPrice).where(
                B2BProductPrice.workspace_id == workspace_id,
                B2BProductPrice.id == parsed_price_id,
            )
        )
    ).scalar_one_or_none()
    if not price:
        raise HTTPException(status_code=404, detail="Price not found")

    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(price, field, value)

    await db.commit()
    await db.refresh(price)

    product = await _get_product(
        db, workspace_id=workspace_id, product_id=str(price.product_id)
    )
    return AdminB2BPriceResponse(
        id=str(price.id),
        product_id=str(price.product_id),
        product_name=product.name if product else "",
        product_sku=product.sku if product else "",
        tier=price.tier,
        agent_id=str(price.agent_id) if price.agent_id else None,
        wholesale_price=price.wholesale_price,
        moq=price.moq,
        currency=price.currency,
        is_active=price.is_active,
        created_at=price.created_at,
        updated_at=price.updated_at,
    )
