"""B2B 代理商门户业务服务层。

代理商认证、分级定价、商品查询、批量下单、订单管理。
所有数据访问走数据库，代理商数据严格隔离。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, get_password_hash, verify_password
from app.core.tracing import get_trace_id
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import (
    B2BAgent,
    B2BOrder,
    B2BOrderItem,
)
from app.models.b2b_sales import B2BRFQ, B2BContract, B2BQuote
from app.models.product import Product
from app.services import (
    b2b_credit_service,
    b2b_pricing_service,
    b2b_sales_service,
    event_service,
)
from app.services.customer_account_service import get_or_create_b2b_account

logger = logging.getLogger(__name__)

B2B_ORDER_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"cancelled"},
    "processing": set(),
    "shipped": set(),
    "delivered": set(),
    "cancelled": set(),
}

PORTAL_RFQ_VISIBLE_STATUSES = {
    "submitted",
    "in_review",
    "quoted",
    "won",
    "lost",
    "cancelled",
}
PORTAL_QUOTE_VISIBLE_STATUSES = {
    "sent",
    "accepted",
    "rejected",
    "expired",
    "converted",
}
PORTAL_CONTRACT_VISIBLE_STATUSES = {
    "pending_signature",
    "active",
    "expired",
    "terminated",
}


class B2BOrderStateError(ValueError):
    """Raised when a B2B order attempts an invalid state transition."""


def _to_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


# ============================================
# 代理商认证
# ============================================

async def authenticate_agent(
    db: AsyncSession,
    email: str,
    password: str,
    *,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> B2BAgent | None:
    """验证代理商邮箱密码，返回代理商对象或 None。"""
    result = await db.execute(
        select(B2BAgent).where(
            B2BAgent.workspace_id == workspace_id,
            B2BAgent.email == email.lower().strip(),
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        return None
    if not verify_password(password, agent.hashed_password):
        return None
    if agent.status != "active":
        logger.warning("Agent login attempt for non-active agent: %s status=%s", email, agent.status)
        return None
    # 更新最后登录时间
    agent.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    return agent


def create_agent_token(agent: B2BAgent) -> str:
    """为代理商生成 JWT access token。

    token_type claim 设为 b2b_access，与内部用户 token 隔离。
    """
    return create_access_token(
        subject=str(agent.id),
        extra_claims={
            "type": "b2b_access",
            "role": "b2b_agent",
            "workspace_id": str(agent.workspace_id),
            "tier": agent.tier,
            "agent_number": agent.agent_number,
        },
        expires_delta=timedelta(hours=24),
    )


# ============================================
# 代理商申请
# ============================================

async def submit_application(
    db: AsyncSession,
    company_name: str,
    contact_name: str,
    email: str,
    password: str,
    phone: str | None = None,
    whatsapp: str | None = None,
    wechat: str | None = None,
    country: str | None = None,
    city: str | None = None,
    address: str | None = None,
    business_type: str | None = None,
    website: str | None = None,
    estimated_annual_volume: str | None = None,
    product_interests: str | None = None,
    message: str | None = None,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> B2BAgent:
    """提交代理商申请。

    创建 status="pending" 的代理商账号，等待管理端审核。
    审核通过后 status 变为 active，即可登录。
    """
    email_lower = email.lower().strip()

    # 检查邮箱是否已存在
    existing = await db.execute(
        select(B2BAgent).where(
            B2BAgent.workspace_id == workspace_id,
            B2BAgent.email == email_lower,
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Email already registered: {email_lower}")

    # 生成代理商编号
    now = datetime.now(timezone.utc)
    agent_number = f"AG-{now.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"

    # 申请备注（合并业务信息）
    notes_parts = []
    if phone:
        notes_parts.append(f"Phone: {phone}")
    if whatsapp:
        notes_parts.append(f"WhatsApp: {whatsapp}")
    if wechat:
        notes_parts.append(f"WeChat: {wechat}")
    if business_type:
        notes_parts.append(f"Business Type: {business_type}")
    if website:
        notes_parts.append(f"Website: {website}")
    if estimated_annual_volume:
        notes_parts.append(f"Est. Annual Volume: {estimated_annual_volume}")
    if product_interests:
        notes_parts.append(f"Product Interests: {product_interests}")
    if message:
        notes_parts.append(f"Message: {message}")
    notes = "\n".join(notes_parts) if notes_parts else None
    account = await get_or_create_b2b_account(
        db,
        workspace_id=workspace_id,
        agent_number=agent_number,
        company_name=company_name.strip(),
        country=country,
        default_currency="USD",
    )

    agent = B2BAgent(
        workspace_id=workspace_id,
        agent_number=agent_number,
        customer_account_id=account.id,
        company_name=company_name.strip(),
        contact_name=contact_name.strip(),
        email=email_lower,
        phone=phone,
        country=country,
        city=city,
        address=address,
        hashed_password=get_password_hash(password),
        tier="bronze",
        status="pending",
        commission_rate=Decimal("0"),
        discount_percent=Decimal("0"),
        credit_limit=Decimal("0"),
        payment_terms_days=30,
        currency="USD",
        notes=notes,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    logger.info("B2B application submitted: %s (%s)", agent_number, email_lower)
    return agent


async def get_agent_by_id(
    db: AsyncSession,
    agent_id: str,
    *,
    workspace_id: UUID,
) -> B2BAgent | None:
    result = await db.execute(
        select(B2BAgent).where(
            B2BAgent.workspace_id == workspace_id,
            B2BAgent.id == _to_uuid(agent_id),
        )
    )
    return result.scalar_one_or_none()


async def change_agent_password(
    db: AsyncSession,
    agent_id: str,
    old_password: str,
    new_password: str,
    *,
    workspace_id: UUID,
) -> bool:
    agent = await get_agent_by_id(db, agent_id, workspace_id=workspace_id)
    if not agent:
        return False
    if not verify_password(old_password, agent.hashed_password):
        return False
    agent.hashed_password = get_password_hash(new_password)
    await db.commit()
    return True


# ============================================
# 分级定价
# ============================================

async def get_wholesale_price(
    db: AsyncSession, product_id: str, agent: B2BAgent
) -> tuple[Decimal, int]:
    """Return the published customer-specific or tier price and its MOQ."""
    resolved = await b2b_pricing_service.resolve_b2b_display_price(
        db,
        workspace_id=agent.workspace_id,
        product_id=product_id,
        agent=agent,
    )
    return resolved.unit_price, resolved.min_quantity


async def get_matching_wholesale_price(
    db: AsyncSession,
    product_id: str,
    agent: B2BAgent,
    quantity: int,
) -> b2b_pricing_service.ResolvedB2BPrice:
    """Resolve the exact published tier for a requested quantity."""
    return await b2b_pricing_service.resolve_b2b_price(
        db,
        workspace_id=agent.workspace_id,
        product_id=product_id,
        agent=agent,
        quantity=quantity,
    )


# ============================================
# 商品查询
# ============================================

async def list_products_for_agent(
    db: AsyncSession,
    agent: B2BAgent,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    category: str | None = None,
    in_stock_only: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """获取代理商可见的商品列表（含批发价）。

    只展示 status=active/published 的商品。
    """
    query = select(Product).where(
        Product.workspace_id == agent.workspace_id,
        Product.status.in_(["active", "published"])
    )

    if search:
        like = f"%{search}%"
        query = query.where(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if category:
        query = query.where(Product.category == category)

    # 总数
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    # 分页
    query = query.order_by(Product.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    products = result.scalars().all()

    items = []
    for p in products:
        try:
            resolved = await b2b_pricing_service.resolve_b2b_display_price(
                db,
                workspace_id=agent.workspace_id,
                product_id=p.id,
                agent=agent,
            )
        except b2b_pricing_service.PricingError:
            resolved = None
        wholesale_price = resolved.unit_price if resolved else None
        moq = resolved.min_quantity if resolved else None
        # 库存（简化：从 meta 或 attributes 中取，没有则默认有货）
        stock_qty = int(p.attributes.get("stock_quantity", 100)) if p.attributes else 100
        in_stock = stock_qty > 0
        if in_stock_only and not in_stock:
            continue

        # 零售价（从 meta 取，没有则批发价 × 1.6）
        retail_price = None
        if p.meta and "retail_price" in p.meta:
            retail_price = Decimal(str(p.meta["retail_price"]))

        items.append({
            "id": str(p.id),
            "sku": p.sku,
            "name": p.name,
            "description": p.description,
            "category": p.category,
            "brand": p.brand,
            "wholesale_price": wholesale_price,
            "retail_price": retail_price,
            "moq": moq,
            "currency": agent.currency,
            "in_stock": in_stock,
            "stock_quantity": stock_qty,
            "images": p.attributes.get("images", []) if p.attributes else [],
            "attributes": p.attributes or {},
        })

    return items, total


async def get_product_detail_for_agent(
    db: AsyncSession, product_id: str, agent: B2BAgent
) -> dict[str, Any] | None:
    """获取商品详情（含批发价）。"""
    result = await db.execute(
        select(Product).where(
            Product.workspace_id == agent.workspace_id,
            Product.id == _to_uuid(product_id),
        )
    )
    p = result.scalar_one_or_none()
    if not p or p.status not in ("active", "published"):
        return None

    try:
        resolved = await b2b_pricing_service.resolve_b2b_display_price(
            db,
            workspace_id=agent.workspace_id,
            product_id=p.id,
            agent=agent,
        )
    except b2b_pricing_service.PricingError:
        resolved = None
    wholesale_price = resolved.unit_price if resolved else None
    moq = resolved.min_quantity if resolved else None
    stock_qty = int(p.attributes.get("stock_quantity", 100)) if p.attributes else 100

    return {
        "id": str(p.id),
        "sku": p.sku,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "brand": p.brand,
        "wholesale_price": wholesale_price,
        "retail_price": Decimal(str(p.meta["retail_price"])) if p.meta and "retail_price" in p.meta else None,
        "moq": moq,
        "currency": agent.currency,
        "in_stock": stock_qty > 0,
        "stock_quantity": stock_qty,
        "images": p.attributes.get("images", []) if p.attributes else [],
        "attributes": p.attributes or {},
        "weight_kg": p.weight_kg,
        "dimensions": p.dimensions,
    }


# ============================================
# 下单
# ============================================

async def create_b2b_order(
    db: AsyncSession,
    agent: B2BAgent,
    items: list[dict[str, Any]],
    shipping_address: dict[str, Any] | None = None,
    notes: str | None = None,
) -> B2BOrder:
    """创建 B2B 订单。

    校验：
    - 商品存在且在售
    - 数量 ≥ MOQ
    - 信用额度检查
    """
    now = datetime.now(timezone.utc)
    order_id = uuid4()
    order_number = f"B2B-{now.strftime('%Y%m%d')}-{str(order_id)[:8].upper()}"

    order_items = []
    subtotal = Decimal("0")

    for item in items:
        product_id = item["product_id"]
        quantity = int(item["quantity"])

        # 查商品
        result = await db.execute(
            select(Product).where(
                Product.workspace_id == agent.workspace_id,
                Product.id == _to_uuid(product_id),
            )
        )
        product = result.scalar_one_or_none()
        if not product or product.status not in ("active", "published"):
            raise ValueError(f"Product not found or unavailable: {product_id}")

        # 只使用已审批发布的客户专属价或等级价。
        try:
            resolved_price = await get_matching_wholesale_price(
                db,
                product_id,
                agent,
                quantity,
            )
        except b2b_pricing_service.PricingError as exc:
            raise ValueError(f"No active B2B price for {product.name}: {exc}") from exc
        if quantity < resolved_price.min_quantity:
            raise ValueError(
                f"Product {product.name} MOQ is {resolved_price.min_quantity}, got {quantity}"
            )

        line_subtotal = resolved_price.unit_price * quantity
        subtotal += line_subtotal

        order_items.append(B2BOrderItem(
            workspace_id=agent.workspace_id,
            order_id=order_id,
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            quantity=quantity,
            unit_price=resolved_price.unit_price,
            subtotal=line_subtotal,
            currency=resolved_price.currency,
            price_book_version_id=resolved_price.price_book_version_id,
            price_tier_id=resolved_price.price_tier_id,
            price_source=resolved_price.source,
        ))

    # 折扣
    discount_amount = (subtotal * agent.discount_percent / Decimal("100")).quantize(Decimal("0.01"))
    total = subtotal - discount_amount

    # 所有订单入口共享同一信用状态、冻结和额度准入规则。
    await b2b_credit_service.assert_order_credit(
        db,
        workspace_id=agent.workspace_id,
        agent_id=agent.id,
        additional_amount=total,
    )

    # 账期到期日
    payment_due_date = (now + timedelta(days=agent.payment_terms_days)).date()

    # 收货地址
    address = shipping_address or {
        "company": agent.company_name,
        "contact": agent.contact_name,
        "phone": agent.phone,
        "country": agent.country,
        "city": agent.city,
        "address": agent.address,
    }

    order = B2BOrder(
        id=order_id,
        workspace_id=agent.workspace_id,
        order_number=order_number,
        agent_id=agent.id,
        customer_account_id=agent.customer_account_id,
        business_model="B2B",
        status="pending",
        payment_status="unpaid",
        subtotal=subtotal,
        discount_amount=discount_amount,
        shipping_cost=Decimal("0"),
        total=total,
        currency=agent.currency,
        shipping_address=address,
        payment_due_date=payment_due_date,
        notes=notes,
        items=order_items,
    )

    # 更新代理商欠款
    agent.current_balance += total

    db.add(order)
    db.add_all(order_items)
    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=agent.workspace_id,
        event_type="b2b_order.created",
        entity_type="b2b_order",
        entity_id=str(order.id),
        payload={
            "order_number": order.order_number,
            "agent_id": str(agent.id),
            "customer_account_id": (
                str(order.customer_account_id) if order.customer_account_id else None
            ),
            "total": str(order.total),
            "currency": order.currency,
            "status": order.status,
        },
    )
    await db.commit()
    await db.refresh(order, ["agent", "items"])

    logger.info(
        "B2B order created: %s agent=%s total=%.2f items=%d",
        order_number, agent.agent_number, total, len(order_items),
    )
    return order


async def update_b2b_order_status(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: str,
    new_status: str,
    actor: str,
    trace_id: str | None = None,
) -> B2BOrder:
    """Apply a non-fulfillment status transition and append an audit event.

    Inventory reservation, shipment, and delivery are driven by the
    fulfillment service so stock and TMS records cannot be bypassed.
    """
    if new_status not in {"confirmed", "cancelled"}:
        raise B2BOrderStateError(
            f"status '{new_status}' must be applied through the fulfillment workflow "
            "or a dedicated lifecycle service"
        )
    order = (
        await db.execute(
            select(B2BOrder)
            .where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.id == _to_uuid(order_id),
            )
            .options(selectinload(B2BOrder.agent), selectinload(B2BOrder.items))
        )
    ).scalar_one_or_none()
    if order is None:
        raise ValueError("B2B order not found")

    old_status = order.status
    allowed = B2B_ORDER_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        raise B2BOrderStateError(f"invalid transition: {old_status} -> {new_status}")

    order.status = new_status

    await db.flush()
    await event_service.create_event(
        db,
        workspace_id=workspace_id,
        event_type="b2b_order.status_changed",
        entity_type="b2b_order",
        entity_id=str(order.id),
        payload={
            "order_number": order.order_number,
            "previous_status": old_status,
            "new_status": new_status,
            "actor": actor,
        },
        trace_id=trace_id,
    )
    await db.commit()
    await db.refresh(order, ["agent", "items"])
    logger.info(
        "B2B order status changed: %s %s -> %s actor=%s",
        order.order_number,
        old_status,
        new_status,
        actor,
    )
    return order


# ============================================
# 订单查询
# ============================================

async def list_agent_orders(
    db: AsyncSession,
    agent_id: str,
    workspace_id: UUID,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[B2BOrder], int]:
    """获取代理商的订单列表（严格隔离，只查自己的订单）。"""
    query = select(B2BOrder).where(
        B2BOrder.workspace_id == workspace_id,
        B2BOrder.agent_id == _to_uuid(agent_id),
    )
    if status:
        query = query.where(B2BOrder.status == status)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    query = query.order_by(B2BOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query.options(selectinload(B2BOrder.items)))
    orders = result.scalars().all()
    return list(orders), total


async def get_agent_order(
    db: AsyncSession,
    agent_id: str,
    order_id: str,
    workspace_id: UUID,
) -> B2BOrder | None:
    """获取代理商订单详情（严格隔离）。"""
    result = await db.execute(
        select(B2BOrder).where(
            and_(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.id == _to_uuid(order_id),
                B2BOrder.agent_id == _to_uuid(agent_id),
            )
        ).options(selectinload(B2BOrder.items))
    )
    return result.scalar_one_or_none()


# ============================================
# 账户概览
# ============================================

async def get_account_summary(db: AsyncSession, agent: B2BAgent) -> dict[str, Any]:
    """获取代理商账户概览。"""
    orders_result = await db.execute(
        select(func.count(), func.coalesce(func.sum(B2BOrder.total), 0)).where(
            B2BOrder.workspace_id == agent.workspace_id,
            B2BOrder.agent_id == agent.id,
        )
    )
    total_orders, total_revenue = orders_result.one()

    pending_result = await db.execute(
        select(func.coalesce(func.sum(B2BOrder.total), 0)).where(
            and_(
                B2BOrder.workspace_id == agent.workspace_id,
                B2BOrder.agent_id == agent.id,
                B2BOrder.payment_status.in_(["unpaid", "partial", "overdue"]),
            )
        )
    )
    pending_payments = pending_result.scalar_one()

    # 最近一笔未付订单的到期日
    due_result = await db.execute(
        select(B2BOrder.payment_due_date).where(
            and_(
                B2BOrder.workspace_id == agent.workspace_id,
                B2BOrder.agent_id == agent.id,
                B2BOrder.payment_status.in_(["unpaid", "partial"]),
                B2BOrder.payment_due_date.isnot(None),
            )
        ).order_by(B2BOrder.payment_due_date.asc()).limit(1)
    )
    next_due = due_result.scalar_one_or_none()

    return {
        "agent": agent,
        "total_orders": int(total_orders),
        "total_revenue": Decimal(str(total_revenue)),
        "pending_payments": Decimal(str(pending_payments)),
        "payment_due_date": next_due,
    }


# ============================================
# 门户销售自助：RFQ、报价与合同
# ============================================

async def create_agent_rfq(
    db: AsyncSession,
    agent: B2BAgent,
    *,
    items: list[dict[str, Any]],
    requested_currency: str = "USD",
    destination_country: str | None = None,
    incoterm: str | None = None,
    requested_delivery_date: date | None = None,
    notes: str | None = None,
) -> B2BRFQ:
    """Create an RFQ for the authenticated agent and submit it immediately."""
    rfq = await b2b_sales_service.create_rfq(
        db,
        workspace_id=agent.workspace_id,
        agent_id=agent.id,
        items=items,
        created_by=agent.email,
        source="portal",
        requested_currency=requested_currency,
        destination_country=destination_country,
        incoterm=incoterm,
        requested_delivery_date=requested_delivery_date,
        notes=notes,
    )
    if rfq.status == "draft":
        rfq = await b2b_sales_service.update_rfq_status(
            db,
            workspace_id=agent.workspace_id,
            rfq_id=rfq.id,
            new_status="submitted",
            actor=agent.email,
        )
    return rfq


async def list_agent_rfqs(
    db: AsyncSession,
    agent: B2BAgent,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[B2BRFQ], int]:
    """List only RFQs owned by the authenticated agent."""
    if status and status not in PORTAL_RFQ_VISIBLE_STATUSES:
        raise ValueError("invalid portal RFQ status")
    query = select(B2BRFQ).where(
        B2BRFQ.workspace_id == agent.workspace_id,
        B2BRFQ.agent_id == agent.id,
        B2BRFQ.status.in_(PORTAL_RFQ_VISIBLE_STATUSES),
    )
    count_query = select(func.count(B2BRFQ.id)).where(
        B2BRFQ.workspace_id == agent.workspace_id,
        B2BRFQ.agent_id == agent.id,
        B2BRFQ.status.in_(PORTAL_RFQ_VISIBLE_STATUSES),
    )
    if status:
        query = query.where(B2BRFQ.status == status)
        count_query = count_query.where(B2BRFQ.status == status)
    total = int((await db.execute(count_query)).scalar_one())
    rows = (
        await db.execute(
            query.options(selectinload(B2BRFQ.items))
            .order_by(B2BRFQ.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), total


async def get_agent_rfq(
    db: AsyncSession,
    agent: B2BAgent,
    rfq_id: str,
) -> B2BRFQ | None:
    """Return an RFQ only when it belongs to the authenticated agent."""
    return (
        await db.execute(
            select(B2BRFQ)
            .where(
                B2BRFQ.workspace_id == agent.workspace_id,
                B2BRFQ.agent_id == agent.id,
                B2BRFQ.id == _to_uuid(rfq_id),
                B2BRFQ.status.in_(PORTAL_RFQ_VISIBLE_STATUSES),
            )
            .options(selectinload(B2BRFQ.items))
        )
    ).scalar_one_or_none()


async def list_agent_quotes(
    db: AsyncSession,
    agent: B2BAgent,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[B2BQuote], int]:
    """List only quotes that have been released to the authenticated agent."""
    if status and status not in PORTAL_QUOTE_VISIBLE_STATUSES:
        raise ValueError("invalid portal quote status")
    query = select(B2BQuote).where(
        B2BQuote.workspace_id == agent.workspace_id,
        B2BQuote.agent_id == agent.id,
        B2BQuote.status.in_(PORTAL_QUOTE_VISIBLE_STATUSES),
    )
    count_query = select(func.count(B2BQuote.id)).where(
        B2BQuote.workspace_id == agent.workspace_id,
        B2BQuote.agent_id == agent.id,
        B2BQuote.status.in_(PORTAL_QUOTE_VISIBLE_STATUSES),
    )
    if status:
        query = query.where(B2BQuote.status == status)
        count_query = count_query.where(B2BQuote.status == status)
    total = int((await db.execute(count_query)).scalar_one())
    rows = (
        await db.execute(
            query.options(
                selectinload(B2BQuote.items),
                selectinload(B2BQuote.contract),
                selectinload(B2BQuote.rfq),
            )
            .order_by(B2BQuote.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), total


async def get_agent_quote(
    db: AsyncSession,
    agent: B2BAgent,
    quote_id: str,
) -> B2BQuote | None:
    """Return a released quote only when it belongs to the authenticated agent."""
    return (
        await db.execute(
            select(B2BQuote)
            .where(
                B2BQuote.workspace_id == agent.workspace_id,
                B2BQuote.agent_id == agent.id,
                B2BQuote.id == _to_uuid(quote_id),
                B2BQuote.status.in_(PORTAL_QUOTE_VISIBLE_STATUSES),
            )
            .options(
                selectinload(B2BQuote.items),
                selectinload(B2BQuote.contract),
                selectinload(B2BQuote.rfq),
            )
        )
    ).scalar_one_or_none()


async def accept_agent_quote(
    db: AsyncSession,
    agent: B2BAgent,
    quote_id: str,
) -> B2BQuote:
    """Accept one of the authenticated agent's sent quotes."""
    quote = await get_agent_quote(db, agent, quote_id)
    if quote is None or quote.status != "sent":
        raise ValueError("Quote not found or is not awaiting a customer decision")
    return await b2b_sales_service.transition_quote(
        db,
        workspace_id=agent.workspace_id,
        quote_id=quote.id,
        new_status="accepted",
        actor=agent.email,
        reason="accepted in customer portal",
        trace_id=get_trace_id(),
    )


async def reject_agent_quote(
    db: AsyncSession,
    agent: B2BAgent,
    quote_id: str,
    *,
    reason: str | None = None,
) -> B2BQuote:
    """Reject one of the authenticated agent's sent quotes."""
    quote = await get_agent_quote(db, agent, quote_id)
    if quote is None or quote.status != "sent":
        raise ValueError("Quote not found or is not awaiting a customer decision")
    return await b2b_sales_service.transition_quote(
        db,
        workspace_id=agent.workspace_id,
        quote_id=quote.id,
        new_status="rejected",
        actor=agent.email,
        reason=reason or "rejected in customer portal",
        trace_id=get_trace_id(),
    )


async def list_agent_contracts(
    db: AsyncSession,
    agent: B2BAgent,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[B2BContract], int]:
    """List only contracts owned by the authenticated agent."""
    if status and status not in PORTAL_CONTRACT_VISIBLE_STATUSES:
        raise ValueError("invalid portal contract status")
    query = select(B2BContract).where(
        B2BContract.workspace_id == agent.workspace_id,
        B2BContract.agent_id == agent.id,
        B2BContract.status.in_(PORTAL_CONTRACT_VISIBLE_STATUSES),
    )
    count_query = select(func.count(B2BContract.id)).where(
        B2BContract.workspace_id == agent.workspace_id,
        B2BContract.agent_id == agent.id,
        B2BContract.status.in_(PORTAL_CONTRACT_VISIBLE_STATUSES),
    )
    if status:
        query = query.where(B2BContract.status == status)
        count_query = count_query.where(B2BContract.status == status)
    total = int((await db.execute(count_query)).scalar_one())
    rows = (
        await db.execute(
            query.options(
                selectinload(B2BContract.quote).selectinload(B2BQuote.items)
            )
            .order_by(B2BContract.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), total


async def get_agent_contract(
    db: AsyncSession,
    agent: B2BAgent,
    contract_id: str,
) -> B2BContract | None:
    """Return a visible contract only when it belongs to the authenticated agent."""
    return (
        await db.execute(
            select(B2BContract)
            .where(
                B2BContract.workspace_id == agent.workspace_id,
                B2BContract.agent_id == agent.id,
                B2BContract.id == _to_uuid(contract_id),
                B2BContract.status.in_(PORTAL_CONTRACT_VISIBLE_STATUSES),
            )
            .options(
                selectinload(B2BContract.quote).selectinload(B2BQuote.items)
            )
        )
    ).scalar_one_or_none()


async def sign_agent_contract(
    db: AsyncSession,
    agent: B2BAgent,
    contract_id: str,
    *,
    signed_by: str,
) -> B2BContract:
    """Record only the customer-side signature for the authenticated agent."""
    contract = await get_agent_contract(db, agent, contract_id)
    if contract is None:
        raise ValueError("Contract not found")
    if contract.status != "pending_signature":
        raise b2b_sales_service.B2BSalesStateError(
            "contract must be pending_signature before customer signing"
        )
    return await b2b_sales_service.sign_contract(
        db,
        workspace_id=agent.workspace_id,
        contract_id=contract.id,
        party="customer",
        signed_by=signed_by,
        trace_id=get_trace_id(),
    )


async def convert_agent_contract_to_order(
    db: AsyncSession,
    agent: B2BAgent,
    contract_id: str,
) -> B2BOrder:
    """Idempotently convert the accepted quote behind an active customer contract."""
    contract = await get_agent_contract(db, agent, contract_id)
    if contract is None:
        raise ValueError("Contract not found")
    if contract.status != "active":
        raise b2b_sales_service.B2BSalesStateError(
            "contract must be active before order conversion"
        )
    if contract.quote is None or contract.quote.status not in {"accepted", "converted"}:
        raise b2b_sales_service.B2BSalesStateError(
            "an accepted quote is required before order conversion"
        )
    return await b2b_sales_service.convert_quote_to_order(
        db,
        workspace_id=agent.workspace_id,
        quote_id=contract.quote_id,
        actor=agent.email,
        trace_id=get_trace_id(),
    )
