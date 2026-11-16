"""B2B 公开展示站（showcase）业务服务层。

职责：
- 公开无价格产品目录（严格字段白名单，绝不返回价格/成本/库存/内部 SKU/供应商）。
- 公开线索（lead）创建：写入 ``b2b_leads``，绝不创建 ``b2b_agents``。
- 内部 admin 线索管理：列表/详情/分配/状态推进/备注/转正式伙伴申请。

所有公开读取与写入均服务端控制来源与白名单，客户端不可影响。
Spec: reports/b2b/CHATGPT_M1_M2_SPEC.md (M1.3 / M1.4 / M1.5)
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.b2b import B2BAgent
from app.models.b2b_leads import B2B_LEAD_STATUSES, B2BLead
from app.models.product import Product
from app.services import event_service

logger = logging.getLogger(__name__)

# 合法的线索状态迁移（内部管理用）。M2.5.1 终态拆分：
# - converted: 赢单（由 convert_lead_to_application 显式设置，须关联真实 agent）。
# - closed_lost: 有记录的流失（须提供 reason）。
# - spam: 垃圾询盘（须提供 reason，区别于正当 closed_lost）。
LEAD_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "new": {"reviewing", "qualified", "closed_lost", "spam"},
    "reviewing": {"qualified", "contacted", "closed_lost", "spam"},
    "qualified": {"contacted", "closed_lost", "spam"},
    "contacted": {"qualified", "closed_lost", "spam"},
    # converted / closed_lost / spam 是终态（converted 由专门的 convert 动作进入）。
    "converted": set(),
    "closed_lost": set(),
    "spam": set(),
}


class LeadStateError(ValueError):
    """Raised when a lead status transition is invalid."""


class LeadConversionError(ValueError):
    """Raised when a lead cannot be converted into a partner application."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug[:160] or "product"


def _public_slug(product: Product) -> str:
    """公开 URL slug：优先用显式 b2b_public_slug，否则由 name 派生（绝不暴露内部 SKU）。"""
    if product.b2b_public_slug:
        return product.b2b_public_slug
    return _slugify(product.name)


def _extract_images(product: Product) -> list[str]:
    """从 attributes/meta 中提取公开图片 URL 列表（无则空列表）。"""
    for container in (product.attributes, product.meta):
        if isinstance(container, dict):
            imgs = container.get("images") or container.get("image_urls")
            if isinstance(imgs, list):
                return [u for u in imgs if isinstance(u, str)]
    return []


def _extract_specs(product: Product) -> dict[str, Any] | None:
    """提取已批准的规格（attributes 中的 specs 键），不含任何定价/成本/供应商。"""
    if isinstance(product.attributes, dict) and isinstance(
        product.attributes.get("specifications"), dict
    ):
        return product.attributes["specifications"]
    return None


# ============================================
# 公开无价格目录（M1.3）
# ============================================

async def list_public_products(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> tuple[list[dict[str, Any]], int]:
    """返回公开无价格产品目录（白名单字段）。仅显式开启展示且未软删的产品。"""
    base = select(Product).where(
        Product.workspace_id == workspace_id,
        Product.b2b_showcase_enabled.is_(True),
        Product.deleted_at.is_(None),
    )
    if category:
        base = base.where(Product.category == category)

    total_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = int(total_result.scalar_one())

    result = await db.execute(
        base.order_by(Product.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    products = result.scalars().all()

    items = [
        {
            "slug": _public_slug(p),
            "title": p.name,
            "images": _extract_images(p),
            "category": p.category,
            "description": p.description,
            "specifications": _extract_specs(p),
            "enquiry_cta_context": {"product": _public_slug(p), "title": p.name},
        }
        for p in products
    ]
    return items, total


async def get_public_product(
    db: AsyncSession,
    slug: str,
    *,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> dict[str, Any] | None:
    """按公开 slug 取单个无价格产品；绝不返回价格/成本/库存/内部 SKU/供应商。"""
    result = await db.execute(
        select(Product).where(
            Product.workspace_id == workspace_id,
            Product.b2b_showcase_enabled.is_(True),
            Product.deleted_at.is_(None),
        )
    )
    for p in result.scalars():
        if _public_slug(p) == slug:
            return {
                "slug": _public_slug(p),
                "title": p.name,
                "images": _extract_images(p),
                "category": p.category,
                "description": p.description,
                "specifications": _extract_specs(p),
                "enquiry_cta_context": {"product": _public_slug(p), "title": p.name},
            }
    return None


async def list_public_categories(
    db: AsyncSession,
    *,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> list[dict[str, Any]]:
    """返回公开展示产品的分类及数量。"""
    result = await db.execute(
        select(Product.category, func.count())
        .where(
            Product.workspace_id == workspace_id,
            Product.b2b_showcase_enabled.is_(True),
            Product.deleted_at.is_(None),
            Product.category.is_not(None),
        )
        .group_by(Product.category)
        .order_by(Product.category)
    )
    return [
        {"slug": _slugify(category), "name": category, "product_count": int(count)}
        for category, count in result.all()
    ]


# ============================================
# 公开线索提交（M1.4）
# ============================================

async def _next_reference_number(db: AsyncSession) -> str:
    """生成唯一的线索参考号 LD-YYYYMMDD-XXXXXX。"""
    while True:
        stamp = _now().strftime("%Y%m%d")
        suffix = f"{uuid4().hex[:6].upper()}"
        ref = f"LD-{stamp}-{suffix}"
        existing = await db.execute(
            select(B2BLead.id).where(B2BLead.reference_number == ref)
        )
        if existing.scalar_one_or_none() is None:
            return ref


async def create_public_lead(
    db: AsyncSession,
    *,
    company_name: str,
    contact_name: str,
    email: str,
    country: str,
    business_type: str,
    message: str,
    privacy_consent: bool,
    products_of_interest: list[str] | None = None,
    company_website: str | None = None,
    whatsapp: str | None = None,
    wechat: str | None = None,
    estimated_order_quantity: str | None = None,
    annual_purchase_range: str | None = None,
    destination_market: str | None = None,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> B2BLead:
    """创建公开线索。source 服务端固定，绝不创建 b2b_agents 账号。"""
    if not privacy_consent:
        raise ValueError("privacy_consent must be true")
    now = _now()
    lead = B2BLead(
        id=uuid4(),
        workspace_id=workspace_id,
        reference_number=await _next_reference_number(db),
        company_name=company_name.strip(),
        contact_name=contact_name.strip(),
        email=email.lower().strip(),
        country=country.strip(),
        business_type=business_type.strip(),
        products_of_interest=products_of_interest or [],
        message=message.strip(),
        privacy_consent=True,
        consent_at=now,
        company_website=company_website,
        whatsapp=whatsapp,
        wechat=wechat,
        estimated_order_quantity=estimated_order_quantity,
        annual_purchase_range=annual_purchase_range,
        destination_market=destination_market,
        source="b2b_public_website",
        status="new",
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    # M2.5.4: append-only event. Never log full contact details / enquiry text.
    await event_service.create_event(
        db,
        workspace_id=lead.workspace_id,
        event_type="b2b_lead.created",
        entity_type="b2b_lead",
        entity_id=str(lead.id),
        payload={
            "reference_number": lead.reference_number,
            "source": lead.source,
            "business_type": lead.business_type,
            "country": lead.country,
            "consent": True,
        },
    )
    logger.info("Public B2B lead created: %s company=%s", lead.reference_number, lead.company_name)
    return lead


# ============================================
# 内部 admin 线索管理（M1.5）
# ============================================

async def list_leads(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    assigned_to: str | None = None,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> tuple[list[B2BLead], int]:
    stmt = select(B2BLead).where(B2BLead.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(B2BLead.status == status)
    if assigned_to:
        stmt = stmt.where(B2BLead.assigned_to == assigned_to)
    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = int(total_result.scalar_one())
    result = await db.execute(
        stmt.order_by(B2BLead.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_lead(
    db: AsyncSession,
    lead_id: UUID,
    *,
    workspace_id: UUID = DEFAULT_WORKSPACE_ID,
) -> B2BLead | None:
    result = await db.execute(
        select(B2BLead).where(
            B2BLead.id == lead_id, B2BLead.workspace_id == workspace_id
        )
    )
    return result.scalar_one_or_none()


async def update_lead(
    db: AsyncSession,
    lead: B2BLead,
    *,
    status: str | None = None,
    assigned_to: str | None = None,
    internal_notes: str | None = None,
    follow_up: dict[str, Any] | None = None,
    actor: str | None = None,
) -> B2BLead:
    """推进线索状态/分配/备注/跟进。非法状态迁移抛错；每次业务变更写 event_log。

    M2.5.1: 进入 closed_lost / spam 必须提供书面原因，写入对应列。
    M2.5.4: 每次业务状态变更 append 一条事件（append-only）。
    """
    previous_status = lead.status
    events: list[tuple[str, dict[str, Any]]] = []

    if status is not None:
        if status not in B2B_LEAD_STATUSES:
            raise LeadStateError(f"Unknown lead status: {status}")
        allowed = LEAD_STATUS_TRANSITIONS.get(lead.status, set())
        if status != lead.status and status not in allowed:
            raise LeadStateError(
                f"Invalid lead transition {lead.status} -> {status}"
            )
        lead.status = status
        if status == "closed_lost":
            lead.closed_lost_reason = (internal_notes or "").strip() or lead.closed_lost_reason
            if not (lead.closed_lost_reason or "").strip():
                raise LeadStateError("closed_lost requires a documented reason")
        if status == "spam":
            lead.spam_reason = (internal_notes or "").strip() or lead.spam_reason
            if not (lead.spam_reason or "").strip():
                raise LeadStateError("spam requires a documented reason")
        events.append(
            (
                "b2b_lead.status_changed",
                {"previous_state": previous_status, "new_state": status},
            )
        )
    if assigned_to is not None and assigned_to != lead.assigned_to:
        lead.assigned_to = assigned_to
        events.append(("b2b_lead.assigned", {"assigned_to": assigned_to}))
    if internal_notes is not None:
        lead.internal_notes = internal_notes
        # Reason columns may have been captured above; don't double-log a pure
        # status-reason write as a note event unless it accompanied a status move.
        if status is None:
            events.append(("b2b_lead.note_added", {}))
    if follow_up is not None:
        follow_ups = list(lead.follow_ups or [])
        follow_ups.append({**follow_up, "at": _now().isoformat()})
        lead.follow_ups = follow_ups
        events.append(("b2b_lead.followup_scheduled", {}))

    await db.commit()
    await db.refresh(lead)

    # Append events after the business fact is committed (append-only audit).
    for event_type, extra in events:
        await event_service.create_event(
            db,
            workspace_id=lead.workspace_id,
            event_type=event_type,
            entity_type="b2b_lead",
            entity_id=str(lead.id),
            payload={
                "reference_number": lead.reference_number,
                "previous_state": previous_status,
                "new_state": lead.status,
                "actor": actor,
                **extra,
            },
        )
    return lead


async def convert_lead_to_application(
    db: AsyncSession,
    lead: B2BLead,
    *,
    agent_id: UUID,
) -> B2BLead:
    """把合格线索显式转换为已存在的正式 B2B 合作伙伴申请（agent）。

    幂等：已转换过则直接返回，不重复转换。
    M2.5.1: 转化同时把 status 置为 converted（赢单终态，须关联真实 agent）。
    """
    if lead.converted_application_id is not None:
        return lead
    if lead.status not in ("qualified", "contacted"):
        raise LeadConversionError(
            "Only qualified/contacted leads can be converted into a partner application"
        )
    agent = await db.get(B2BAgent, agent_id)
    if agent is None or agent.workspace_id != lead.workspace_id:
        raise LeadConversionError("Target agent not found in the same workspace")
    previous_status = lead.status
    lead.converted_application_id = agent_id
    lead.converted_at = _now()
    lead.status = "converted"
    await db.commit()
    await db.refresh(lead)
    # M2.5.4: append-only conversion event (business fact committed above).
    await event_service.create_event(
        db,
        workspace_id=lead.workspace_id,
        event_type="b2b_lead.converted",
        entity_type="b2b_lead",
        entity_id=str(lead.id),
        payload={
            "reference_number": lead.reference_number,
            "previous_state": previous_status,
            "new_state": "converted",
            "converted_application_id": str(agent_id),
        },
    )
    logger.info(
        "Lead %s converted to agent %s", lead.reference_number, agent_id
    )
    return lead