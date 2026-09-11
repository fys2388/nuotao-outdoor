"""B2B 代理商门户业务服务层。

代理商认证、分级定价、商品查询、批量下单、订单管理。
所有数据访问走数据库，代理商数据严格隔离。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.b2b import (
    B2BAgent,
    B2BOrder,
    B2BOrderItem,
    B2BProductPrice,
)
from app.models.product import Product, ProductCost

logger = logging.getLogger(__name__)


# ============================================
# 代理商认证
# ============================================

async def authenticate_agent(
    db: AsyncSession, email: str, password: str
) -> B2BAgent | None:
    """验证代理商邮箱密码，返回代理商对象或 None。"""
    result = await db.execute(
        select(B2BAgent).where(B2BAgent.email == email.lower().strip())
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
) -> B2BAgent:
    """提交代理商申请。

    创建 status="pending" 的代理商账号，等待管理端审核。
    审核通过后 status 变为 active，即可登录。
    """
    email_lower = email.lower().strip()

    # 检查邮箱是否已存在
    existing = await db.execute(select(B2BAgent).where(B2BAgent.email == email_lower))
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

    agent = B2BAgent(
        agent_number=agent_number,
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


async def get_agent_by_id(db: AsyncSession, agent_id: str) -> B2BAgent | None:
    result = await db.execute(select(B2BAgent).where(B2BAgent.id == agent_id))
    return result.scalar_one_or_none()


async def change_agent_password(
    db: AsyncSession, agent_id: str, old_password: str, new_password: str
) -> bool:
    agent = await get_agent_by_id(db, agent_id)
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
    """获取某商品对该代理商的批发价和 MOQ。

    优先级：代理商专属定价 > 等级定价 > 成本价 × 1.4（兜底）
    返回 (wholesale_price, moq)
    """
    # 1. 代理商专属定价
    result = await db.execute(
        select(B2BProductPrice).where(
            and_(
                B2BProductPrice.product_id == product_id,
                B2BProductPrice.agent_id == agent.id,
                B2BProductPrice.is_active.is_(True),
            )
        )
    )
    agent_price = result.scalar_one_or_none()
    if agent_price:
        return Decimal(agent_price.wholesale_price), int(agent_price.moq)

    # 2. 等级定价
    result = await db.execute(
        select(B2BProductPrice).where(
            and_(
                B2BProductPrice.product_id == product_id,
                B2BProductPrice.tier == agent.tier,
                B2BProductPrice.agent_id.is_(None),
                B2BProductPrice.is_active.is_(True),
            )
        )
    )
    tier_price = result.scalar_one_or_none()
    if tier_price:
        return Decimal(tier_price.wholesale_price), int(tier_price.moq)

    # 3. 兜底：成本价 × 1.4，MOQ=10
    cost_result = await db.execute(
        select(ProductCost).where(ProductCost.product_id == product_id)
    )
    cost = cost_result.scalar_one_or_none()
    if cost and cost.total_cost > 0:
        fallback_price = (Decimal(cost.total_cost) * Decimal("1.4")).quantize(Decimal("0.01"))
        return fallback_price, 10

    return Decimal("0.00"), 10


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
        wholesale_price, moq = await get_wholesale_price(db, str(p.id), agent)
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
        select(Product).where(Product.id == product_id)
    )
    p = result.scalar_one_or_none()
    if not p or p.status not in ("active", "published"):
        return None

    wholesale_price, moq = await get_wholesale_price(db, str(p.id), agent)
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
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product or product.status not in ("active", "published"):
            raise ValueError(f"Product not found or unavailable: {product_id}")

        # 查批发价和 MOQ
        wholesale_price, moq = await get_wholesale_price(db, product_id, agent)
        if quantity < moq:
            raise ValueError(
                f"Product {product.name} MOQ is {moq}, got {quantity}"
            )

        line_subtotal = wholesale_price * quantity
        subtotal += line_subtotal

        order_items.append(B2BOrderItem(
            order_id=order_id,
            product_id=product_id,
            product_name=product.name,
            sku=product.sku,
            quantity=quantity,
            unit_price=wholesale_price,
            subtotal=line_subtotal,
        ))

    # 折扣
    discount_amount = (subtotal * agent.discount_percent / Decimal("100")).quantize(Decimal("0.01"))
    total = subtotal - discount_amount

    # 信用额度检查
    if agent.credit_limit > 0:
        if agent.current_balance + total > agent.credit_limit:
            raise ValueError(
                f"Credit limit exceeded. Available: {agent.credit_limit - agent.current_balance}, "
                f"Order total: {total}"
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
        order_number=order_number,
        agent_id=agent.id,
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
    await db.commit()
    await db.refresh(order)

    logger.info(
        "B2B order created: %s agent=%s total=%.2f items=%d",
        order_number, agent.agent_number, total, len(order_items),
    )
    return order


# ============================================
# 订单查询
# ============================================

async def list_agent_orders(
    db: AsyncSession,
    agent_id: str,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[B2BOrder], int]:
    """获取代理商的订单列表（严格隔离，只查自己的订单）。"""
    query = select(B2BOrder).where(B2BOrder.agent_id == agent_id)
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
    db: AsyncSession, agent_id: str, order_id: str
) -> B2BOrder | None:
    """获取代理商订单详情（严格隔离）。"""
    result = await db.execute(
        select(B2BOrder).where(
            and_(B2BOrder.id == order_id, B2BOrder.agent_id == agent_id)
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
            B2BOrder.agent_id == agent.id
        )
    )
    total_orders, total_revenue = orders_result.one()

    pending_result = await db.execute(
        select(func.coalesce(func.sum(B2BOrder.total), 0)).where(
            and_(
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
