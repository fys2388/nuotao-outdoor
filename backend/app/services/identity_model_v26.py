"""M4 V2.6 Product / Variation 身份模型服务。

三态身份判定(PRODUCT / VARIATION / UNKNOWN_LEGACY)与数据关联:

- ``identity_state``:纯函数判定(无 DB/无 IO),与 V2.5 设计一致。
- ``classify_rows``:批量分类(71 行校验 → 70 VARIATION + 1 PRODUCT + 0 UNKNOWN)。
- 商品级/变体级 ``upsert_*_mapping``:走 ``event_service.create_event``(写 event_log,
  保留 trace_id),与业务同事务。
- ``upsert_offer_mapping``:Supplier/1688 Offer 独立映射,冲突保留最新 effective_at,
  旧版本 archived(历史报价不删除)。
- ``update_inventory_variation``:库存以确定的 Variation 身份为主;禁止仅凭父 SKU
  更新整个变体集合(guard:无 wc_variation_id 且商品有变体 ⇒ 跳过/UNKNOWN)。
- ``append_cost_snapshot``:成本快照明确对应 Product 或 Variation,append-only,
  供应商报价变化不覆盖已形成的历史快照。
- ``backfill_71_rows``:71 行历史回填模拟(隔离数据,幂等;**不写生产**)。

所有写操作继续走 event_service,身份/历史关系变更保留 trace_id。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.event import EventLog
from app.models.order import OrderItem
from app.models.product_intelligence import ProductCostSnapshot
from app.models.product_mapping import (
    IDENTITY_STATE_PRODUCT,
    IDENTITY_STATE_UNKNOWN_LEGACY,
    IDENTITY_STATE_VARIATION,
    ProductMapping,
)
from app.models.supplier_offer_mapping import (
    MAPPING_STATUS_ARCHIVED,
    MAPPING_STATUS_MAPPED,
    MAPPING_STATUS_UNCONFIRMED,
    SupplierOfferMapping,
)
from app.models.supply_chain import InventorySnapshot
from app.services import event_service

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

# --- M4 V2.7 Supplier/Offer 冲突策略(指令 §五) -----------------------------
# 禁止直接用最新 effective_at 自动覆盖规格映射冲突。区分四类:
# 1) 同一 Offer 报价更新(规格未变)      -> 正常 mapped,旧版本 archived。
# 2) 同一 Offer 规格映射变更(已验证行)  -> 不覆盖已验证映射,新证据 unconfirmed
#    等人工审核;记录冲突原因 + trace_id。
# 3) 多供应商独立报价                    -> 不同 supplier_id 各自独立,无冲突。
# 4) 同一 Offer 冲突规格证据             -> 冲突行 unconfirmed/archived,保留全部历史。
CONFLICT_REASON_SPEC_CHANGED = "spec_mapping_changed"
CONFLICT_REASON_CONFLICTING_EVIDENCE = "conflicting_spec_evidence"

# --- M4 V2.7 身份判定边界:5 种证据情况 -------------------------------------
# 指令 §四:只有「A. 已确认商品无变体」可判定为 PRODUCT;
# B/C/D/E 必须保持 UNKNOWN_LEGACY(或未确认态),禁止自动归类。
# 这些 reason 用于区分「为什么无法确定身份」,全部映射到 UNKNOWN_LEGACY。
IDENTITY_REASON_CONFIRMED_NO_VARIATION = "confirmed_no_variation"  # A -> PRODUCT
IDENTITY_REASON_VARIATION_LIST_INCOMPLETE = "variation_list_incomplete"  # B -> UNKNOWN
IDENTITY_REASON_WC_API_FAILED = "wc_api_failed"  # C -> UNKNOWN
IDENTITY_REASON_LOCAL_SYNC_INCOMPLETE = "local_sync_incomplete"  # D -> UNKNOWN
IDENTITY_REASON_VARIATION_ID_MISSING = "variation_id_missing"  # E -> UNKNOWN

# 无法确定身份的 reason 集合(B/C/D/E):一律 UNKNOWN_LEGACY。
UNKNOWN_IDENTITY_REASONS = frozenset(
    {
        IDENTITY_REASON_VARIATION_LIST_INCOMPLETE,
        IDENTITY_REASON_WC_API_FAILED,
        IDENTITY_REASON_LOCAL_SYNC_INCOMPLETE,
        IDENTITY_REASON_VARIATION_ID_MISSING,
    }
)

__all__ = [
    "CONFLICT_REASON_CONFLICTING_EVIDENCE",
    "CONFLICT_REASON_SPEC_CHANGED",
    "IDENTITY_REASON_CONFIRMED_NO_VARIATION",
    "IDENTITY_REASON_LOCAL_SYNC_INCOMPLETE",
    "IDENTITY_REASON_VARIATION_ID_MISSING",
    "IDENTITY_REASON_VARIATION_LIST_INCOMPLETE",
    "IDENTITY_REASON_WC_API_FAILED",
    "IDENTITY_STATE_PRODUCT",
    "IDENTITY_STATE_UNKNOWN_LEGACY",
    "IDENTITY_STATE_VARIATION",
    "IdentityClassification",
    "append_cost_snapshot",
    "archive_offer_mapping",
    "backfill_71_rows",
    "classify_csv_rows",
    "classify_rows",
    "identity_state",
    "record_order_item",
    "row_from_csv_row",
    "update_inventory_variation",
    "upsert_offer_mapping",
    "upsert_product_mapping",
    "upsert_variation_mapping",
]


@dataclass
class IdentityClassification:
    """单行身份判定结果."""

    wc_product_id: int | None = None
    wc_variation_id: int | None = None
    identity_state: str = IDENTITY_STATE_UNKNOWN_LEGACY
    product_has_variations: bool | None = None
    variation_sku: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "wc_product_id": self.wc_product_id,
            "wc_variation_id": self.wc_variation_id,
            "identity_state": self.identity_state,
            "product_has_variations": self.product_has_variations,
            "variation_sku": self.variation_sku,
            "reason": self.reason,
        }


@dataclass
class ClassificationBatch:
    """批量分类结果(含汇总与逐行明细)."""

    rows: list[IdentityClassification] = field(default_factory=list)
    variation_count: int = 0
    product_count: int = 0
    unknown_count: int = 0

    def summary(self) -> dict[str, int]:
        return {
            "VARIATION": self.variation_count,
            "PRODUCT": self.product_count,
            "UNKNOWN_LEGACY": self.unknown_count,
            "total": len(self.rows),
        }

    def to_dicts(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.rows]


def identity_state(
    wc_product_id: int | None,
    wc_variation_id: int | None,
    product_has_variations: bool | None,
    record_has_variation_context: bool = False,
    identity_reason: str | None = None,
) -> str:
    """三态身份判定(纯函数).

    V2.5 核心规则:wc_variation_id 为空**不代表商品级**,必须显式判定。

    - wc_variation_id 非空 ⇒ VARIATION(WC 变体存在,有唯一变体 SKU)。
    - wc_variation_id 为空 + 商品无变体(A: confirmed_no_variation)⇒ PRODUCT。
    - wc_variation_id 为空 + 商品有变体:
        - record_has_variation_context ⇒ VARIATION(按上下文变体归类)。
        - 否则 ⇒ UNKNOWN_LEGACY(不猜测)。
    - 无证据 ⇒ UNKNOWN_LEGACY(不猜测)。

    V2.7 边界(指令 §四):当显式给出 ``identity_reason`` ∈
    {B 变体列表未完整获取, C WC API 请求失败, D 本地变体数据未同步完整,
    E 有变体但记录缺 Variation ID} 时,**一律返回 UNKNOWN_LEGACY**,不猜测、
    不自动归类为 PRODUCT。只有 A(商品确认无变体)才是 PRODUCT。
    """
    # V2.7:显式未确认原因(B/C/D/E)强制 UNKNOWN_LEGACY,优先于其它判定.
    if identity_reason in UNKNOWN_IDENTITY_REASONS:
        return IDENTITY_STATE_UNKNOWN_LEGACY
    if wc_variation_id is not None:
        return IDENTITY_STATE_VARIATION
    # wc_variation_id 为空
    if product_has_variations is False:
        return IDENTITY_STATE_PRODUCT
    if product_has_variations is True:
        if record_has_variation_context:
            return IDENTITY_STATE_VARIATION
        return IDENTITY_STATE_UNKNOWN_LEGACY
    return IDENTITY_STATE_UNKNOWN_LEGACY


def classify_rows(rows: list[dict[str, Any]]) -> ClassificationBatch:
    """批量分类行(每行含 wc_variation_id / product_has_variations / 可选变体上下文).

    不猜测:无证据 ⇒ UNKNOWN_LEGACY。返回分类批次(含 70/1/0 校验可用 summary)。
    """
    batch = ClassificationBatch()
    for row in rows:
        vid = row.get("wc_variation_id")
        vid = int(vid) if vid not in (None, "", "0") else None
        product_has_variations = row.get("product_has_variations")
        if product_has_variations in (None, ""):
            product_has_variations = None
        elif isinstance(product_has_variations, str):
            product_has_variations = product_has_variations.lower() in ("1", "true", "yes", "y")
        else:
            product_has_variations = bool(product_has_variations)
        ctx = bool(row.get("record_has_variation_context", False))
        # V2.7:行可携带显式未确认原因(B/C/D/E),强制 UNKNOWN_LEGACY.
        identity_reason = row.get("identity_reason") or None
        state = identity_state(
            row.get("wc_product_id"),
            vid,
            product_has_variations,
            ctx,
            identity_reason=identity_reason,
        )
        cls = IdentityClassification(
            wc_product_id=int(row["wc_product_id"]) if row.get("wc_product_id") else None,
            wc_variation_id=vid,
            identity_state=state,
            product_has_variations=product_has_variations,
            variation_sku=row.get("variation_sku") or row.get("wc_real_variation_sku"),
            reason=_classify_reason(vid, product_has_variations, ctx, identity_reason),
        )
        batch.rows.append(cls)
        if state == IDENTITY_STATE_VARIATION:
            batch.variation_count += 1
        elif state == IDENTITY_STATE_PRODUCT:
            batch.product_count += 1
        else:
            batch.unknown_count += 1
    return batch


def _classify_reason(
    vid: int | None,
    product_has_variations: bool | None,
    record_has_variation_context: bool,
    identity_reason: str | None = None,
) -> str:
    # V2.7:显式未确认原因优先呈现(B/C/D/E)。
    if identity_reason in UNKNOWN_IDENTITY_REASONS:
        return f"unconfirmed ({identity_reason}) -> UNKNOWN_LEGACY"
    if vid is not None:
        return "wc_variation_id present -> VARIATION"
    if product_has_variations is False:
        return "no variation id + product has no variations -> PRODUCT"
    if product_has_variations is True:
        if record_has_variation_context:
            return "no variation id + product has variations + record context -> VARIATION"
        return "no variation id + product has variations + no context -> UNKNOWN_LEGACY"
    return "no evidence -> UNKNOWN_LEGACY"


def row_from_csv_row(csv_row: dict[str, Any]) -> dict[str, Any]:
    """把 71 行 CSV 行(字符串值)规范化为身份判定输入(幂等).

    关键:2687 父商品行(无 wc_variation_id)显式标记 ``product_has_variations=False``
    (attrs 含 '父商品' 或 has_unique_variation_id='NO_MISSING_ID' 且无变体 SKU),
    从而判定为 PRODUCT,不会被误归为 UNKNOWN_LEGACY。

    幂等:若输入已是归一化行(含 bool ``product_has_variations``),原样返回。
    """
    if isinstance(csv_row.get("product_has_variations"), bool):
        return csv_row
    raw_vid = (str(csv_row.get("wc_variation_id") or "")).strip()
    vid = int(raw_vid) if raw_vid else None
    product_has_variations: bool | None = None
    if vid is not None:
        product_has_variations = True
    else:
        attrs = csv_row.get("attrs") or ""
        has_unique = (csv_row.get("has_unique_variation_id") or "").strip()
        real_sku = (csv_row.get("wc_real_variation_sku") or "").strip()
        if "父商品" in attrs or (has_unique == "NO_MISSING_ID" and not real_sku):
            product_has_variations = False
    return {
        "wc_product_id": int(csv_row["wc_product_id"]) if csv_row.get("wc_product_id") else None,
        "wc_variation_id": vid,
        "product_has_variations": product_has_variations,
        "record_has_variation_context": False,
        "variation_sku": (csv_row.get("wc_real_variation_sku") or "").strip() or None,
        "product_name": csv_row.get("product_name"),
    }


def classify_csv_rows(csv_rows: list[dict[str, Any]]) -> ClassificationBatch:
    """对 CSV 行(字符串值)批量分类,返回 70 VARIATION / 1 PRODUCT / 0 UNKNOWN 可校验批次."""
    normalized = [row_from_csv_row(r) for r in csv_rows]
    return classify_rows(normalized)


async def upsert_product_mapping(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    nuotao_product_id: UUID,
    woocommerce_id: int,
    woocommerce_slug: str | None = None,
    variation_sku: str | None = None,
    source_offer_id: str | None = None,
    source_variation_spec: dict[str, Any] | None = None,
    trace_id: str | None = None,
    sync_status: str = "synced",
) -> ProductMapping:
    """商品级映射 upsert(identity_state='PRODUCT').

    走 event_service 写 event_log(同事务,保留 trace_id)。重复执行幂等:
    命中商品级部分唯一键则更新,否则插入。
    """
    stmt = select(ProductMapping).where(
        ProductMapping.workspace_id == workspace_id,
        ProductMapping.woocommerce_id == woocommerce_id,
        ProductMapping.identity_state == IDENTITY_STATE_PRODUCT,
        ProductMapping.woocommerce_variation_id.is_(None),
    )
    mapping = (await session.execute(stmt)).scalars().first()
    if mapping is None:
        mapping = ProductMapping(
            workspace_id=workspace_id,
            nuotao_product_id=nuotao_product_id,
            woocommerce_id=woocommerce_id,
            woocommerce_slug=woocommerce_slug,
            woocommerce_variation_id=None,
            variation_sku=variation_sku,
            source_offer_id=source_offer_id,
            source_variation_spec=source_variation_spec,
            identity_state=IDENTITY_STATE_PRODUCT,
            sync_status=sync_status,
            trace_id=trace_id,
        )
        session.add(mapping)
        await session.flush()
        event_type = "product_mapping.product_created"
    else:
        mapping.nuotao_product_id = nuotao_product_id
        mapping.woocommerce_slug = woocommerce_slug or mapping.woocommerce_slug
        mapping.variation_sku = variation_sku or mapping.variation_sku
        mapping.source_offer_id = source_offer_id or mapping.source_offer_id
        mapping.source_variation_spec = source_variation_spec or mapping.source_variation_spec
        mapping.sync_status = sync_status
        mapping.trace_id = trace_id
        await session.flush()
        event_type = "product_mapping.product_updated"

    await _emit_mapping_event(
        session, workspace_id=workspace_id, mapping=mapping, event_type=event_type, trace_id=trace_id
    )
    return mapping


async def upsert_variation_mapping(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    nuotao_product_id: UUID,
    woocommerce_id: int,
    woocommerce_variation_id: int,
    variation_sku: str | None = None,
    source_offer_id: str | None = None,
    source_variation_spec: dict[str, Any] | None = None,
    trace_id: str | None = None,
    sync_status: str = "synced",
) -> ProductMapping:
    """变体级映射 upsert(identity_state='VARIATION').

    走 event_service 写 event_log(同事务,保留 trace_id)。幂等。
    """
    stmt = select(ProductMapping).where(
        ProductMapping.workspace_id == workspace_id,
        ProductMapping.woocommerce_id == woocommerce_id,
        ProductMapping.woocommerce_variation_id == woocommerce_variation_id,
        ProductMapping.identity_state == IDENTITY_STATE_VARIATION,
    )
    mapping = (await session.execute(stmt)).scalars().first()
    if mapping is None:
        mapping = ProductMapping(
            workspace_id=workspace_id,
            nuotao_product_id=nuotao_product_id,
            woocommerce_id=woocommerce_id,
            woocommerce_variation_id=woocommerce_variation_id,
            variation_sku=variation_sku,
            source_offer_id=source_offer_id,
            source_variation_spec=source_variation_spec,
            identity_state=IDENTITY_STATE_VARIATION,
            sync_status=sync_status,
            trace_id=trace_id,
        )
        session.add(mapping)
        await session.flush()
        event_type = "product_mapping.variation_created"
    else:
        mapping.nuotao_product_id = nuotao_product_id
        mapping.variation_sku = variation_sku or mapping.variation_sku
        mapping.source_offer_id = source_offer_id or mapping.source_offer_id
        mapping.source_variation_spec = source_variation_spec or mapping.source_variation_spec
        mapping.sync_status = sync_status
        mapping.trace_id = trace_id
        await session.flush()
        event_type = "product_mapping.variation_updated"

    await _emit_mapping_event(
        session, workspace_id=workspace_id, mapping=mapping, event_type=event_type, trace_id=trace_id
    )
    return mapping


async def _emit_mapping_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    mapping: ProductMapping,
    event_type: str,
    trace_id: str | None,
) -> EventLog:
    """统一写 event_log(与业务同事务,commit=False)."""
    return await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type=event_type,
        entity_type="product_mapping",
        entity_id=str(mapping.id),
        payload=mapping.to_summary(),
        trace_id=trace_id,
        commit=False,
    )


def _as_utc(value: datetime | None) -> datetime | None:
    """把可能 naive 的 datetime 统一为 tz-aware UTC(SQLite 存 naive,PG 存 aware)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _canonical_spec(spec: dict[str, Any] | None) -> str:
    """把规格映射规范化为可比较的 JSON 字符串(键排序,忽略顺序差异)."""
    return json.dumps(spec or {}, sort_keys=True, ensure_ascii=False, default=str)


async def _find_unconfirmed_conflict(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    supplier_id: UUID | None,
    source_offer_id: str,
    wc_variation_id: int | None,
    specification_mapping: dict[str, Any] | None,
) -> SupplierOfferMapping | None:
    """按冲突指纹探测已存在的未确认冲突证据(幂等键).

    幂等键 = workspace + supplier + offer + variation + 冲突规格指纹(canonical spec)。
    命中则复用该 unconfirmed 行,避免同一冲突证据因重试/重复提交无限新建。
    """
    fingerprint = _canonical_spec(specification_mapping)
    stmt = select(SupplierOfferMapping).where(
        SupplierOfferMapping.workspace_id == workspace_id,
        SupplierOfferMapping.supplier_id == supplier_id,
        SupplierOfferMapping.source_offer_id == source_offer_id,
        SupplierOfferMapping.wc_variation_id == wc_variation_id,
        SupplierOfferMapping.mapping_status == MAPPING_STATUS_UNCONFIRMED,
    )
    for row in (await session.execute(stmt)).scalars().all():
        if _canonical_spec(row.specification_mapping) == fingerprint:
            return row
    return None


async def upsert_offer_mapping(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    supplier_id: UUID | None,
    source_offer_id: str,
    wc_product_id: int,
    wc_variation_id: int | None,
    specification_mapping: dict[str, Any] | None = None,
    evidence_source: str | None = None,
    effective_at: datetime | None = None,
    source_timestamp: datetime | None = None,
    trace_id: str | None = None,
) -> SupplierOfferMapping:
    """Supplier / 1688 Offer 独立映射 upsert(多对多,独立实体).

    V2.7 冲突策略(指令 §五):**禁止直接用最新 effective_at 自动覆盖规格映射冲突**。
    区分四类:
    - 同一 Offer 报价更新(规格未变)    ⇒ 新行 mapped,旧版本 archived(历史报价保留)。
    - 同一 Offer 规格映射变更(已验证行)⇒ **不覆盖已验证映射**;新证据 unconfirmed,
      记录冲突原因(CONFLICT_REASON_SPEC_CHANGED)+ trace_id,等人工审核。
    - 多供应商独立报价                  ⇒ 不同 supplier_id 键不同,各自独立无冲突。
    - 同一 Offer 冲突规格证据(未验证)  ⇒ 冲突行 archived,新证据 mapped(可推进)。

    全部保留历史证据(行永不删除)。走 event_service 写 event_log。
    """
    effective_at = effective_at or datetime.now(UTC)
    stmt = select(SupplierOfferMapping).where(
        SupplierOfferMapping.workspace_id == workspace_id,
        SupplierOfferMapping.supplier_id == supplier_id,
        SupplierOfferMapping.source_offer_id == source_offer_id,
        SupplierOfferMapping.wc_variation_id == wc_variation_id,
        SupplierOfferMapping.mapping_status != MAPPING_STATUS_ARCHIVED,
    )
    existing = (await session.execute(stmt)).scalars().all()

    newest_existing: SupplierOfferMapping | None = None
    newest_unconfirmed: SupplierOfferMapping | None = None
    for row in existing:
        if newest_existing is None or (
            row.effective_at
            and (newest_existing.effective_at is None or row.effective_at > newest_existing.effective_at)
        ):
            newest_existing = row
        if row.mapping_status == MAPPING_STATUS_UNCONFIRMED and (
            newest_unconfirmed is None
            or (
                row.effective_at
                and (newest_unconfirmed.effective_at is None or row.effective_at > newest_unconfirmed.effective_at)
            )
        ):
            newest_unconfirmed = row

    # 幂等优先:最新 unconfirmed 证据与新提交的冲突规格一致 ⇒ 复用该行(更新 trace_id),
    # 不再判定为冲突也不新建(同一冲突证据重复提交/不同 trace_id 重试均幂等)。
    if newest_unconfirmed is not None and _canonical_spec(newest_unconfirmed.specification_mapping) == _canonical_spec(
        specification_mapping
    ):
        newest_unconfirmed.trace_id = trace_id or newest_unconfirmed.trace_id
        newest_unconfirmed.effective_at = effective_at
        if evidence_source:
            newest_unconfirmed.evidence_source = evidence_source
        await session.flush()
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="supplier_offer_mapping.conflict_reused",
            entity_type="supplier_offer_mapping",
            entity_id=str(newest_unconfirmed.id),
            payload={
                "source_offer_id": source_offer_id,
                "wc_variation_id": wc_variation_id,
                "reused_unconfirmed_id": str(newest_unconfirmed.id),
                "requires_manual_review": True,
            },
            trace_id=trace_id,
            commit=False,
        )
        return newest_unconfirmed

    # 新请求比现有最新版本更旧 ⇒ 视为历史,归档,保留现有映射(不覆盖).
    if (
        newest_existing is not None
        and newest_existing.effective_at is not None
        and _as_utc(newest_existing.effective_at) > _as_utc(effective_at)
    ):
        mapping = SupplierOfferMapping(
            workspace_id=workspace_id,
            supplier_id=supplier_id,
            source_offer_id=source_offer_id,
            wc_product_id=wc_product_id,
            wc_variation_id=wc_variation_id,
            specification_mapping=specification_mapping,
            mapping_status=MAPPING_STATUS_ARCHIVED,
            evidence_source=evidence_source,
            effective_at=effective_at,
            source_timestamp=source_timestamp,
            trace_id=trace_id,
        )
        session.add(mapping)
        await session.flush()
        await _emit_offer_event(
            session,
            workspace_id=workspace_id,
            mapping=mapping,
            event_type="supplier_offer_mapping.archived_stale",
            trace_id=trace_id,
        )
        return mapping

    # 新请求更新/持平:检查是否为「规格映射变更」冲突(V2.7).
    spec_conflict = newest_existing is not None and _canonical_spec(
        newest_existing.specification_mapping
    ) != _canonical_spec(specification_mapping)
    if spec_conflict and newest_existing.mapping_status == MAPPING_STATUS_MAPPED:
        # 已验证映射不允许被新规格证据自动覆盖:保留现有 mapped 行,
        # 新证据降级为 unconfirmed 等人工审核(保留全部历史证据).
        # 幂等:同一冲突指纹(workspace+supplier+offer+variation+冲突规格)若已有
        # unconfirmed 证据,复用该行并更新 trace_id,不重复新建(防重试无限重复)。
        dup = await _find_unconfirmed_conflict(
            session,
            workspace_id=workspace_id,
            supplier_id=supplier_id,
            source_offer_id=source_offer_id,
            wc_variation_id=wc_variation_id,
            specification_mapping=specification_mapping,
        )
        if dup is not None:
            dup.trace_id = trace_id or dup.trace_id
            dup.effective_at = effective_at
            if evidence_source:
                dup.evidence_source = evidence_source
            await session.flush()
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="supplier_offer_mapping.spec_conflict_deduplicated",
                entity_type="supplier_offer_mapping",
                entity_id=str(dup.id),
                payload={
                    "conflict_reason": CONFLICT_REASON_SPEC_CHANGED,
                    "source_offer_id": source_offer_id,
                    "wc_variation_id": wc_variation_id,
                    "kept_mapped_id": str(newest_existing.id),
                    "reused_unconfirmed_id": str(dup.id),
                    "requires_manual_review": True,
                },
                trace_id=trace_id,
                commit=False,
            )
            return dup
        mapping = SupplierOfferMapping(
            workspace_id=workspace_id,
            supplier_id=supplier_id,
            source_offer_id=source_offer_id,
            wc_product_id=wc_product_id,
            wc_variation_id=wc_variation_id,
            specification_mapping=specification_mapping,
            mapping_status=MAPPING_STATUS_UNCONFIRMED,
            evidence_source=evidence_source,
            effective_at=effective_at,
            source_timestamp=source_timestamp,
            trace_id=trace_id,
        )
        session.add(mapping)
        await session.flush()
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="supplier_offer_mapping.spec_conflict",
            entity_type="supplier_offer_mapping",
            entity_id=str(mapping.id),
            payload={
                "conflict_reason": CONFLICT_REASON_SPEC_CHANGED,
                "source_offer_id": source_offer_id,
                "wc_variation_id": wc_variation_id,
                "kept_mapped_id": str(newest_existing.id),
                "new_evidence_id": str(mapping.id),
                "requires_manual_review": True,
            },
            trace_id=trace_id,
            commit=False,
        )
        return mapping

    # 非冲突(报价更新)或冲突但现有未验证 ⇒ 现有全部归档,新行 mapped 生效.
    for row in existing:
        row.mapping_status = MAPPING_STATUS_ARCHIVED

    mapping = SupplierOfferMapping(
        workspace_id=workspace_id,
        supplier_id=supplier_id,
        source_offer_id=source_offer_id,
        wc_product_id=wc_product_id,
        wc_variation_id=wc_variation_id,
        specification_mapping=specification_mapping,
        mapping_status=MAPPING_STATUS_MAPPED,
        evidence_source=evidence_source,
        effective_at=effective_at,
        source_timestamp=source_timestamp,
        trace_id=trace_id,
    )
    session.add(mapping)
    await session.flush()
    await _emit_offer_event(
        session,
        workspace_id=workspace_id,
        mapping=mapping,
        event_type="supplier_offer_mapping.mapped",
        trace_id=trace_id,
    )
    return mapping


async def archive_offer_mapping(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    source_offer_id: str,
    wc_product_id: int,
    wc_variation_id: int | None = None,
    trace_id: str | None = None,
) -> int:
    """Offer 失效 ⇒ 该键全部活映射 archived(历史报价保留,不删除).

    返回归档行数。走 event_service 写 event_log。
    """
    stmt = select(SupplierOfferMapping).where(
        SupplierOfferMapping.workspace_id == workspace_id,
        SupplierOfferMapping.source_offer_id == source_offer_id,
        SupplierOfferMapping.wc_product_id == wc_product_id,
        SupplierOfferMapping.mapping_status != MAPPING_STATUS_ARCHIVED,
    )
    if wc_variation_id is not None:
        stmt = stmt.where(SupplierOfferMapping.wc_variation_id == wc_variation_id)
    rows = (await session.execute(stmt)).scalars().all()
    count = 0
    for row in rows:
        row.mapping_status = MAPPING_STATUS_ARCHIVED
        count += 1
    await session.flush()
    if count:
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="supplier_offer_mapping.offer_invalidated",
            entity_type="supplier_offer_mapping",
            entity_id=source_offer_id,
            payload={"wc_product_id": wc_product_id, "wc_variation_id": wc_variation_id, "archived": count},
            trace_id=trace_id,
            commit=False,
        )
    return count


async def _emit_offer_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    mapping: SupplierOfferMapping,
    event_type: str,
    trace_id: str | None,
) -> EventLog:
    return await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type=event_type,
        entity_type="supplier_offer_mapping",
        entity_id=str(mapping.id),
        payload=mapping.to_summary(),
        trace_id=trace_id,
        commit=False,
    )


async def record_order_item(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    order_id: UUID,
    product_id: UUID | None,
    name: str,
    quantity: int,
    unit_price: Any,
    line_total: Any,
    wc_product_id: int | None,
    wc_variation_id: int | None,
    variation_sku: str | None,
    product_has_variations: bool | None,
    external_item_id: str | None = None,
    trace_id: str | None = None,
) -> OrderItem:
    """订单行变体身份记录.

    新订单优先记录确定的 Product / Variation 身份;历史无法确定 ⇒ UNKNOWN_LEGACY
    (不猜测)。走 event_service 写 event_log。
    """
    state = identity_state(wc_product_id, wc_variation_id, product_has_variations)
    item = OrderItem(
        workspace_id=workspace_id,
        order_id=order_id,
        external_item_id=external_item_id,
        product_id=product_id,
        sku=variation_sku,
        name=name,
        quantity=quantity,
        unit_price=unit_price,
        line_total=line_total,
        wc_variation_id=wc_variation_id,
        variation_sku=variation_sku,
        identity_state=state,
    )
    session.add(item)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="order_item.identity_recorded",
        entity_type="order_item",
        entity_id=str(item.id),
        payload={
            "wc_product_id": wc_product_id,
            "wc_variation_id": wc_variation_id,
            "identity_state": state,
        },
        trace_id=trace_id,
        commit=False,
    )
    return item


async def update_inventory_variation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    wc_product_id: int,
    wc_variation_id: int | None,
    product_has_variations: bool | None,
    location: str,
    quantity: int,
    variation_sku: str | None = None,
    reserved: int = 0,
    in_transit: int = 0,
    source_timestamp: datetime | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """库存变体级更新(带 guard).

    Guard(禁止仅凭父 SKU 更新整个变体集合):
    - wc_variation_id 为空 且 商品有变体 ⇒ 跳过/UNKNOWN,不批量覆盖。
    - wc_variation_id 非空 ⇒ 变体级库存行(variation_id 非空)。
    - wc_variation_id 为空 且 商品无变体 ⇒ 商品级库存行(variation_id NULL)。

    返回结果 dict(含 status 与行)。走 event_service 写 event_log。
    """
    if wc_variation_id is None and product_has_variations is True:
        return {
            "status": "skipped_unknown_variation",
            "reason": "no wc_variation_id but product has variations; refusing parent-level bulk update",
            "wc_product_id": wc_product_id,
        }

    variation_id = wc_variation_id
    stmt = select(InventorySnapshot).where(
        InventorySnapshot.workspace_id == workspace_id,
        InventorySnapshot.product_id == product_id,
        InventorySnapshot.location == location,
    )
    if variation_id is None:
        stmt = stmt.where(InventorySnapshot.variation_id.is_(None))
    else:
        stmt = stmt.where(InventorySnapshot.variation_id == variation_id)
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        row = InventorySnapshot(
            workspace_id=workspace_id,
            product_id=product_id,
            location=location,
            quantity=quantity,
            reserved=reserved,
            available=quantity - reserved,
            in_transit=in_transit,
            variation_id=variation_id,
            variation_sku=variation_sku,
            source_timestamp=source_timestamp or datetime.now(UTC),
            trace_id=trace_id,
        )
        session.add(row)
        await session.flush()
        event_type = "inventory.variation_snapshot_created"
    else:
        row.quantity = quantity
        row.reserved = reserved
        row.available = quantity - reserved
        row.in_transit = in_transit
        row.variation_sku = variation_sku or row.variation_sku
        row.source_timestamp = source_timestamp or row.source_timestamp
        row.trace_id = trace_id
        await session.flush()
        event_type = "inventory.variation_snapshot_updated"

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type=event_type,
        entity_type="inventory_snapshot",
        entity_id=str(row.id),
        payload={
            "wc_product_id": wc_product_id,
            "wc_variation_id": wc_variation_id,
            "variation_sku": variation_sku,
            "quantity": quantity,
        },
        trace_id=trace_id,
        commit=False,
    )
    return {"status": "updated", "identity_state": "VARIATION" if variation_id else "PRODUCT"}


async def append_cost_snapshot(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    purchase_cost: Any,
    total_landed_cost: Any,
    wc_variation_id: int | None,
    variation_sku: str | None = None,
    currency: str = "USD",
    source: str = "supplier_offer",
    trace_id: str | None = None,
    notes: dict[str, Any] | None = None,
) -> ProductCostSnapshot:
    """成本快照(append-only,历史永不覆盖).

    明确对应 Product(variation_id NULL)或 Variation(variation_id 非空)。
    供应商报价变化 ⇒ 新增快照行,不覆盖已形成的历史快照。走 event_service。
    """
    snapshot = ProductCostSnapshot(
        workspace_id=workspace_id,
        product_id=product_id,
        variation_id=wc_variation_id,
        variation_sku=variation_sku,
        currency=currency,
        purchase_cost=purchase_cost,
        total_landed_cost=total_landed_cost,
        total_cost=total_landed_cost,
        source=source,
        trace_id=trace_id,
    )
    session.add(snapshot)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="cost_snapshot.appended",
        entity_type="product_cost_snapshot",
        entity_id=str(snapshot.id),
        payload={
            "wc_variation_id": wc_variation_id,
            "variation_sku": variation_sku,
            "purchase_cost": str(purchase_cost),
            "total_landed_cost": str(total_landed_cost),
        },
        trace_id=trace_id,
        commit=False,
    )
    return snapshot


async def backfill_71_rows(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    rows: list[dict[str, Any]],
    product_ids: dict[int, UUID],
    trace_id: str = "v26-71row-backfill",
) -> dict[str, Any]:
    """71 行历史身份回填(隔离数据,幂等;**不写生产**).

    - ``rows`` 可为 CSV 原始行(字符串值)或已归一化行(``row_from_csv_row`` 输出),
      内部统一归一化后再判定身份。
    - 仅面向隔离测试数据/内存 SQLite 使用;生产回填需 Owner 单独书面授权。
    - 幂等:命中商品级/变体级部分唯一键则跳过,不重复创建。
    - 返回统计(created / skipped / errors)。
    """
    normalized_rows = [row_from_csv_row(r) for r in rows]
    batch = classify_rows(normalized_rows)
    created = 0
    skipped = 0
    errors: list[dict[str, Any]] = []
    for cls in batch.rows:
        nuotao_product_id = product_ids.get(cls.wc_product_id) if cls.wc_product_id else None
        if nuotao_product_id is None:
            errors.append({"wc_product_id": cls.wc_product_id, "error": "no local product"})
            continue
        # 幂等:先按部分唯一键探测,已存在 ⇒ 跳过,不重复创建.
        exists = await _mapping_exists(
            session,
            workspace_id=workspace_id,
            woocommerce_id=cls.wc_product_id,
            wc_variation_id=cls.wc_variation_id,
            identity_state=cls.identity_state,
        )
        if exists:
            skipped += 1
            continue
        try:
            if cls.identity_state == IDENTITY_STATE_VARIATION:
                await upsert_variation_mapping(
                    session,
                    workspace_id=workspace_id,
                    nuotao_product_id=nuotao_product_id,
                    woocommerce_id=cls.wc_product_id,
                    woocommerce_variation_id=cls.wc_variation_id,  # type: ignore[arg-type]
                    variation_sku=cls.variation_sku,
                    trace_id=trace_id,
                )
            elif cls.identity_state == IDENTITY_STATE_PRODUCT:
                await upsert_product_mapping(
                    session,
                    workspace_id=workspace_id,
                    nuotao_product_id=nuotao_product_id,
                    woocommerce_id=cls.wc_product_id,
                    variation_sku=cls.variation_sku,
                    trace_id=trace_id,
                )
            else:
                errors.append({"wc_product_id": cls.wc_product_id, "error": "UNKNOWN_LEGACY not auto-assigned"})
                continue
            created += 1
        except Exception as exc:
            errors.append({"wc_product_id": cls.wc_product_id, "error": str(exc)})
    return {
        "classified": batch.summary(),
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


async def _mapping_exists(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    woocommerce_id: int,
    wc_variation_id: int | None,
    identity_state: str,
) -> bool:
    """按身份键探测映射是否存在(幂等用)."""
    stmt = select(ProductMapping.id).where(
        ProductMapping.workspace_id == workspace_id,
        ProductMapping.woocommerce_id == woocommerce_id,
        ProductMapping.identity_state == identity_state,
    )
    if identity_state == IDENTITY_STATE_VARIATION:
        stmt = stmt.where(ProductMapping.woocommerce_variation_id == wc_variation_id)
    else:
        stmt = stmt.where(ProductMapping.woocommerce_variation_id.is_(None))
    return (await session.execute(stmt)).scalars().first() is not None
