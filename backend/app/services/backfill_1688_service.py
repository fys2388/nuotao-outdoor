"""1688 数据自动回填服务。

自动识别从 1688 导入但数据不完整的候选产品，重新从 1688 拉取详情并
回填缺失字段（属性表、图片、重量、尺寸、供应商信息、采购成本等）。

设计原则：
- 宁缺勿造（AGENTS.md §1.2.5）：只回填 1688 API 实际返回的字段，不凭空生成。
- 幂等：回填操作可重复执行，已有有效数据不会被 mock 覆盖。
- 可审计：每次回填记录操作日志事件。
- 降级：1688 API 未配置或调用失败时，跳过该商品并在结果中标记原因。

回填字段优先级（已有有效数据 > 回填数据 > 空值）：
1. 属性表 (attributes)
2. 商品图片 (meta.images / meta.main_images)
3. 重量 (weight_kg)
4. 尺寸 (dimensions)
5. 描述 (description)
6. 类目 (category)
7. 采购成本 (product_cost.purchase_cost)
8. 供应商信息 (supplier_code / meta)
"""

from __future__ import annotations

import asyncio
import logging
import re
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.product import Product, ProductCost
from app.services import event_service
from app.services.product_cost_service import landed_breakdown

logger = logging.getLogger(__name__)

# ── 1688 回填扫描配置 ──────────────────────────────────────────

# 每个回填批次最多处理多少商品（防止单次请求超时）
DEFAULT_BATCH_LIMIT = 50

# 1688 回填最大并发数（1688 API 限流保护）
BACKFILL_CONCURRENCY = 3

# 单个商品回填超时秒数
BACKFILL_TIMEOUT_SECONDS = 60

# 哪些 source 值视为 1688 来源
_1688_SOURCES = {"1688", "newton_ai"}

# 回填字段名列表（用于审计日志和结果展示）
_BACKFILL_FIELDS = frozenset(
    {
        "attributes",
        "images",
        "weight_kg",
        "dimensions",
        "description",
        "category",
        "purchase_cost",
        "supplier_info",
        "raw_data",
    }
)


class BackfillResult:
    """单个商品的回填结果。"""

    __slots__ = (
        "product_id",
        "sku",
        "name",
        "status",
        "fetched_fields",
        "skipped_fields",
        "errors",
    )

    def __init__(self, product_id: str, sku: str, name: str) -> None:
        self.product_id = product_id
        self.sku = sku
        self.name = name
        self.status: Literal["success", "partial", "failed", "skipped"] = "success"
        self.fetched_fields: list[str] = []
        self.skipped_fields: list[str] = []
        self.errors: list[str] = []

    def mark_success(self) -> None:
        self.status = "success"

    def mark_partial(self) -> None:
        self.status = "partial"

    def mark_failed(self, reason: str) -> None:
        self.status = "failed"
        self.errors.append(reason)

    def mark_skipped(self, reason: str) -> None:
        self.status = "skipped"
        self.errors.append(reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "sku": self.sku,
            "name": self.name,
            "status": self.status,
            "fetched_fields": list(self.fetched_fields),
            "skipped_fields": list(self.skipped_fields),
            "errors": list(self.errors),
        }


# ── 内部工具函数 ────────────────────────────────────────────────


def _is_incomplete_product(product: Product) -> bool:
    """判断 1688 来源产品是否存在需要回填的缺失字段。"""
    missing_any = False

    # 属性表缺失
    if not product.attributes:
        missing_any = True

    # 图片缺失（meta.images / meta.main_images / meta.media）
    meta = product.meta or {}
    has_images = bool(
        meta.get("images")
        or meta.get("main_images")
        or (meta.get("media") or {}).get("images")
    )
    if not has_images:
        missing_any = True

    # 重量缺失
    if product.weight_kg is None:
        missing_any = True

    # 尺寸缺失
    if not product.dimensions:
        missing_any = True

    # 描述缺失
    if not product.description:
        missing_any = True

    # 类目缺失
    if not product.category:
        missing_any = True

    return missing_any


def _parse_decimal(value: Any) -> Decimal | None:
    """安全解析 1688 返回的价格字符串为 Decimal。"""
    if value is None or value == "":
        return None
    raw = str(value).strip()
    # 1688 常返回 "¥20" 或 "6.7-19.7" 区间
    if raw.startswith("¥"):
        raw = raw[1:]
    # 区间取最低价
    if "-" in raw:
        raw = raw.split("-")[0]
    raw = re.sub(r"[^\d.]", "", raw)
    if not raw:
        return None
    try:
        result = Decimal(raw)
        return result if result > 0 else None
    except Exception:
        return None


def _parse_weight_kg(value: Any) -> Decimal | None:
    """解析重量字符串为 kg。"""
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if not text:
        return None

    # 提取数值和单位
    match = re.search(r"([\d.]+)\s*(kg|g|克|千克|kg|kgs?)?", text)
    if not match:
        return None

    num = Decimal(match.group(1))
    unit = (match.group(2) or "g").lower()

    # 单位转换到 kg
    if unit in ("kg", "千克"):
        return num
    elif unit in ("g", "克"):
        return (num / Decimal("1000")).quantize(Decimal("0.001"))
    return num


def _parse_dimensions(value: Any) -> dict[str, Any] | None:
    """解析尺寸字符串为结构化对象。"""
    if not value or not str(value).strip():
        return None
    text = str(value).strip()

    # 格式: "60*40*115" 或 "60x40x115" 或 "60×40×115"
    parts = re.split(r"[*x×]", text)
    if len(parts) >= 3:
        try:
            length = float(parts[0])
            width = float(parts[1])
            height = float(parts[2])
            if length > 0 and width > 0 and height > 0:
                return {
                    "length": length,
                    "width": width,
                    "height": height,
                    "unit": "mm",
                }
        except (ValueError, IndexError):
            pass

    # 单值格式（如 "47x47x90" 的简写）
    if len(parts) == 1:
        return {"raw": text}

    return None


def _extract_attributes(product_detail: dict[str, Any]) -> list[dict[str, str]]:
    """从 1688 商品详情中提取属性列表。"""
    product = product_detail.get("product", {})
    raw_attrs = product.get("attributes", [])
    if not isinstance(raw_attrs, list):
        return []

    result: list[dict[str, str]] = []
    for attr in raw_attrs:
        if not isinstance(attr, dict):
            continue
        name = str(
            attr.get("attributeName")
            or attr.get("name")
            or attr.get("attributeID")
            or ""
        ).strip()
        value = str(attr.get("value") or "").strip()
        if name and value:
            result.append({"name": name, "value": value})
    return result


def _extract_images(product_detail: dict[str, Any]) -> list[str]:
    """从 1688 商品详情中提取图片 URL 列表。"""
    product = product_detail.get("product", {})

    images = product.get("images") or product.get("imageUrls") or []
    if not images:
        main_image = product.get("mainImage") or ""
        if main_image:
            images = [main_image]

    urls: list[str] = []
    if isinstance(images, list):
        for img in images:
            if isinstance(img, dict):
                url = (
                    img.get("url")
                    or img.get("imageUrl")
                    or img.get("urls")
                    or ""
                )
            else:
                url = str(img)
            if url and url.strip():
                urls.append(url.strip())
    elif isinstance(images, str) and images.strip():
        urls = [images.strip()]

    return urls[:10]


def _extract_category(product_detail: dict[str, Any]) -> str | None:
    """从 1688 商品详情中提取类目名称。"""
    product = product_detail.get("product", {})
    category = (
        product.get("category_name")
        or product.get("categoryName")
        or product.get("category")
        or ""
    )
    return str(category).strip() or None


def _extract_description(product_detail: dict[str, Any]) -> str | None:
    """从 1688 商品详情中提取描述。"""
    product = product_detail.get("product", {})
    desc = (
        product.get("description")
        or product.get("detail")
        or ""
    )
    result = str(desc).strip()
    return result if result else None


def _extract_purchase_cost(product_detail: dict[str, Any]) -> Decimal | None:
    """从 1688 商品详情中提取采购成本（最低批发价）。"""
    product = product_detail.get("product", {})
    return _parse_decimal(
        product.get("price") or product.get("price_range")
    )


def _extract_supplier_info(product_detail: dict[str, Any]) -> dict[str, str]:
    """从 1688 商品详情中提取供应商信息。"""
    product = product_detail.get("product", {})
    supplier = product.get("supplier") or {}

    return {
        "login_id": str(
            product.get("supplier_login_id")
            or supplier.get("login_id")
            or supplier.get("loginId")
            or ""
        ),
        "company_name": str(
            product.get("company_name")
            or supplier.get("company_name")
            or supplier.get("companyName")
            or ""
        ),
    }


# ── 核心回填逻辑 ────────────────────────────────────────────────


async def _backfill_single_product(
    session: AsyncSession,
    product: Product,
    *,
    workspace_id: Any,
    trace_id: str | None = None,
) -> BackfillResult:
    """对单个商品执行 1688 数据回填。

    1. 解析 1688 商品 ID（优先 source_offer_id，其次从 source_url 提取）
    2. 调用 1688 API 获取商品详情
    3. 对比现有数据，只回填缺失字段
    4. 写入数据库
    """
    result = BackfillResult(
        product_id=str(product.id),
        sku=product.sku,
        name=product.name,
    )

    # Step 1: 解析 1688 商品 ID
    product_id_1688 = None
    if product.source_offer_id:
        product_id_1688 = str(product.source_offer_id).strip()
    elif product.source_url:
        try:
            from app.services.product_source_identity import extract_1688_offer_id
            product_id_1688 = extract_1688_offer_id(product.source_url)
        except Exception:
            pass

    if not product_id_1688:
        result.mark_skipped("无法解析 1688 商品 ID（source_offer_id 和 source_url 均为空）")
        return result

    # Step 2: 调用 1688 API
    try:
        product_detail = await asyncio.wait_for(
            asyncio.to_thread(_fetch_from_1688, product_id_1688),
            timeout=BACKFILL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        result.mark_failed(f"1688 API 调用超时（{BACKFILL_TIMEOUT_SECONDS}s）")
        return result
    except Exception as exc:
        result.mark_failed(f"1688 API 调用异常: {exc}")
        return result

    if not product_detail.get("success"):
        error_msg = product_detail.get("error", "未知错误")
        # 跳过 mock 数据（记入 errors，保证 to_dict 的 errors 非空）
        if product_detail.get("source") == "mock":
            result.mark_skipped("1688 API 未配置，返回 mock 数据，跳过回填")
        else:
            result.mark_failed(f"1688 API 返回错误: {error_msg}")
        return result

    # success=True 但来源是 mock：同样跳过（真实数据不可用）
    if product_detail.get("source") == "mock":
        result.mark_skipped("1688 API 未配置，返回 mock 数据，跳过回填")
        return result

    detail = product_detail.get("product", {})

    # Step 3: 逐字段对比并回填
    for field in _BACKFILL_FIELDS:
        try:
            was_filled = await _backfill_field(
                session, product, field, detail, workspace_id
            )
            if was_filled:
                result.fetched_fields.append(field)
            else:
                result.skipped_fields.append(field)
        except Exception as exc:
            logger.warning(
                "回填字段 %s 失败 product_id=%s: %s",
                field,
                product.id,
                exc,
            )
            result.skipped_fields.append(field)
            result.errors.append(f"字段 {field} 回填失败: {exc}")

    # Step 4: 记录审计事件（append-only；与业务事实同事务，不自动 commit）
    if result.fetched_fields:
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="product.1688_backfill",
            entity_type="product",
            entity_id=str(product.id),
            payload={
                "source": "backfill_1688_service",
                "product_id_1688": product_id_1688,
                "fetched_fields": result.fetched_fields,
                "skipped_fields": result.skipped_fields,
                "status": result.status,
            },
            trace_id=trace_id or f"backfill-{product.id}",
            commit=False,
        )
        await session.flush()

    # Step 5: 判定最终状态
    if result.fetched_fields and not result.skipped_fields:
        result.mark_success()
    elif result.fetched_fields:
        result.mark_partial()

    return result


def _attribute_value(
    detail: dict[str, Any], *names: str
) -> str:
    """从 1688 属性表中按属性名取值（如「重量」「尺寸」「规格」）。"""
    attrs = detail.get("attributes") or []
    if not isinstance(attrs, list):
        return ""
    wanted = {n.lower() for n in names}
    for attr in attrs:
        if not isinstance(attr, dict):
            continue
        name_raw = str(attr.get("attributeName") or attr.get("name") or "")
        if name_raw in names or name_raw.lower() in wanted:
            return str(attr.get("value") or "")
    return ""


async def _backfill_field(
    session: AsyncSession,
    product: Product,
    field: str,
    detail: dict[str, Any],
    workspace_id: Any,
) -> bool:
    """回填单个字段。返回 True 表示字段被更新，False 表示跳过。"""
    meta = dict(product.meta or {})

    if field == "attributes":
        new_attrs = _extract_attributes({"product": detail})
        if not new_attrs:
            return False
        if product.attributes and len(product.attributes) >= len(new_attrs):
            return False
        product.attributes = new_attrs
        return True

    elif field == "images":
        new_images = _extract_images({"product": detail})
        if not new_images:
            return False
        existing = (
            meta.get("images")
            or meta.get("main_images")
            or (meta.get("media") or {}).get("images")
            or []
        )
        if existing:
            return False
        meta["images"] = new_images
        product.meta = meta
        flag_modified(product, "meta")
        return True

    elif field == "weight_kg":
        if product.weight_kg is not None:
            return False
        # 优先顶层 weight 字段；1688 属性表里的「重量」作为兜底
        weight_raw = detail.get("weight", "") or _attribute_value(detail, "重量")
        if not weight_raw:
            return False
        weight_kg = _parse_weight_kg(weight_raw)
        if weight_kg is None:
            return False
        product.weight_kg = weight_kg
        return True

    elif field == "dimensions":
        if product.dimensions:
            return False
        # 优先顶层 dimensions 字段；属性表里的「尺寸/规格」作为兜底
        dims_raw = detail.get("dimensions", "") or _attribute_value(
            detail, "尺寸", "规格"
        )
        if not dims_raw:
            return False
        dims = _parse_dimensions(dims_raw)
        if not dims:
            return False
        product.dimensions = dims
        return True

    elif field == "description":
        if product.description:
            return False
        desc = _extract_description({"product": detail})
        if not desc:
            return False
        product.description = desc[:2000]
        return True

    elif field == "category":
        if product.category:
            return False
        cat = _extract_category({"product": detail})
        if not cat:
            return False
        product.category = cat
        return True

    elif field == "purchase_cost":
        return await _backfill_purchase_cost(session, product, detail, workspace_id)

    elif field == "supplier_info":
        supplier = _extract_supplier_info({"product": detail})
        if not any(supplier.values()):
            return False
        existing_meta = meta or {}
        existing_supplier = existing_meta.get("supplier") or {}
        if existing_supplier.get("login_id") or existing_supplier.get("company_name"):
            return False
        meta["supplier"] = {k: v for k, v in supplier.items() if v}
        product.meta = meta
        flag_modified(product, "meta")
        return True

    elif field == "raw_data":
        # 保存 1688 原始数据快照到 ProductSource
        return False  # 由上层批量处理

    return False


async def _backfill_purchase_cost(
    session: AsyncSession,
    product: Product,
    detail: dict[str, Any],
    workspace_id: Any,
) -> bool:
    """回填采购成本（创建或更新 ProductCost）。"""
    # 检查是否已有有效成本
    existing_cost = await _get_latest_cost(session, product.id, workspace_id)
    if existing_cost and existing_cost.purchase_cost > 0:
        return False  # 已有有效成本，不覆盖

    purchase_cost = _extract_purchase_cost({"product": detail})
    if not purchase_cost or purchase_cost <= 0:
        return False

    # 创建或更新成本记录
    if existing_cost:
        # 更新现有成本记录
        existing_cost.purchase_cost = purchase_cost
        intl, total_landed, total_cost = landed_breakdown(
            purchase_cost=purchase_cost,
            domestic_shipping=existing_cost.domestic_shipping,
            first_leg_shipping=existing_cost.first_leg_shipping,
            last_leg_shipping=existing_cost.last_leg_shipping,
            international_shipping=existing_cost.international_shipping,
            packaging=existing_cost.packaging,
            tax_estimate=existing_cost.tax_estimate,
            handling=existing_cost.handling,
        )
        existing_cost.international_shipping = intl
        existing_cost.total_landed_cost = total_landed
        existing_cost.total_cost = total_cost
        existing_cost.notes = {
            **(existing_cost.notes or {}),
            "backfill_source": "1688_api",
            "backfill_1688_price": str(purchase_cost),
        }
    else:
        # 创建新成本记录
        intl, total_landed, total_cost = landed_breakdown(
            purchase_cost=purchase_cost,
            domestic_shipping=Decimal("0"),
            first_leg_shipping=Decimal("0"),
            last_leg_shipping=Decimal("0"),
            international_shipping=None,
            packaging=Decimal("0"),
            tax_estimate=Decimal("0"),
            handling=Decimal("0"),
        )
        new_cost = ProductCost(
            workspace_id=workspace_id,
            product_id=product.id,
            currency="CNY",
            purchase_cost=purchase_cost,
            international_shipping=intl,
            total_landed_cost=total_landed,
            total_cost=total_cost,
            version="v1",
            notes={
                "backfill_source": "1688_api",
                "backfill_1688_price": str(purchase_cost),
            },
        )
        session.add(new_cost)
        await session.flush()

    return True


async def _get_latest_cost(
    session: AsyncSession,
    product_id: Any,
    workspace_id: Any,
) -> ProductCost | None:
    """获取产品的最新成本记录。"""
    rows = (
        (
            await session.execute(
                select(ProductCost)
                .where(
                    ProductCost.workspace_id == workspace_id,
                    ProductCost.product_id == product_id,
                )
                .order_by(ProductCost.valid_from.desc())
            )
        )
        .scalars()
        .all()
    )
    return rows[0] if rows else None


def _fetch_from_1688(product_id: str) -> dict[str, Any]:
    """从 1688 获取商品详情（同步函数，在线程池中运行）。"""
    try:
        from app.services.sourcing_1688_service import get_product_detail
        result = get_product_detail(product_id)
        if not result.get("success"):
            return result
        product = result.get("product", {})
        # 补充重量和尺寸（从属性表中提取）
        attrs = product.get("attributes", [])
        if isinstance(attrs, list):
            for attr in attrs:
                if not isinstance(attr, dict):
                    continue
                name_raw = str(attr.get("attributeName") or attr.get("name") or "")
                name_lower = name_raw.lower()
                value = str(attr.get("value", ""))
                if not product.get("weight") and ("重量" in name_raw or "weight" in name_lower):
                    product["weight"] = value
                if not product.get("dimensions") and (
                    "尺寸" in name_raw or "dimension" in name_lower or "规格" in name_raw
                ):
                    product["dimensions"] = value
        return result
    except Exception as exc:
        return {"success": False, "error": str(exc), "source": "1688_open_api"}


# ── 批量回填入口 ────────────────────────────────────────────────


async def scan_incomplete_products(
    session: AsyncSession,
    *,
    workspace_id: Any,
    candidate_only: bool = True,
    limit: int = DEFAULT_BATCH_LIMIT,
) -> list[dict[str, Any]]:
    """扫描需要回填的 1688 来源产品。

    Returns:
        产品列表，每项包含 product_id, sku, name, missing_fields。
    """
    query = select(Product).where(
        Product.workspace_id == workspace_id,
        Product.deleted_at.is_(None),
        Product.source.in_(list(_1688_SOURCES)),
    )
    if candidate_only:
        query = query.where(Product.candidate_status == "candidate")

    products = (
        (await session.execute(query.limit(limit * 3))).scalars().all()
    )

    incomplete: list[dict[str, Any]] = []
    for product in products:
        if _is_incomplete_product(product):
            incomplete.append(
                {
                    "product_id": str(product.id),
                    "sku": product.sku,
                    "name": product.name,
                    "source_offer_id": product.source_offer_id,
                    "source_url": product.source_url,
                }
            )
        if len(incomplete) >= limit:
            break

    return incomplete


async def backfill_1688_products(
    session: AsyncSession,
    *,
    workspace_id: Any,
    product_ids: list[str] | None = None,
    candidate_only: bool = True,
    batch_limit: int = DEFAULT_BATCH_LIMIT,
    trace_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """批量回填 1688 数据。

    Args:
        session: 数据库会话
        workspace_id: 工作空间 ID
        product_ids: 指定商品 ID 列表；None 表示扫描所有不完整商品
        candidate_only: 仅回填候选状态商品
        batch_limit: 最大处理数量
        trace_id: 追踪 ID
        dry_run: 仅扫描不执行

    Returns:
        回填结果摘要
    """
    # Step 1: 确定待回填商品
    if product_ids:
        products_to_backfill: list[Product] = []
        ids_set = set(product_ids)
        query = select(Product).where(
            Product.workspace_id == workspace_id,
            Product.deleted_at.is_(None),
            Product.source.in_(list(_1688_SOURCES)),
            Product.id.in_([__import__("uuid").UUID(pid) for pid in product_ids]),
        )
        rows = (await session.execute(query)).scalars().all()
        for row in rows:
            if _is_incomplete_product(row):
                products_to_backfill.append(row)
    else:
        incomplete_info = await scan_incomplete_products(
            session,
            workspace_id=workspace_id,
            candidate_only=candidate_only,
            limit=batch_limit,
        )
        products_to_backfill = []
        for info in incomplete_info:
            product = (
                (
                    await session.execute(
                        select(Product).where(
                            Product.id == __import__("uuid").UUID(info["product_id"]),
                            Product.deleted_at.is_(None),
                        )
                    )
                )
                .scalars()
                .first()
            )
            if product:
                products_to_backfill.append(product)

    total = len(products_to_backfill)

    if not products_to_backfill:
        return {
            "success": True,
            "total_scanned": total,
            "backfilled": 0,
            "partial": 0,
            "failed": 0,
            "skipped": 0,
            "results": [],
            "message": "无需回填的商品",
        }

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "total_scanned": total,
            "backfilled": 0,
            "partial": 0,
            "failed": 0,
            "skipped": 0,
            "results": [
                {
                    "product_id": str(p.id),
                    "sku": p.sku,
                    "name": p.name,
                    "status": "would_backfill",
                }
                for p in products_to_backfill
            ],
            "message": f"dry_run 模式：发现 {total} 个待回填商品",
        }

    # Step 2: 并发回填
    sem = asyncio.Semaphore(BACKFILL_CONCURRENCY)
    results: list[BackfillResult] = []

    async def _backfill_with_limit(product: Product) -> BackfillResult:
        async with sem:
            return await _backfill_single_product(
                session,
                product,
                workspace_id=workspace_id,
                trace_id=trace_id,
            )

    tasks = [_backfill_with_limit(p) for p in products_to_backfill]
    results = await asyncio.gather(*tasks)

    # Step 3: 汇总
    summary = {
        "success": True,
        "total_scanned": total,
        "backfilled": sum(1 for r in results if r.status == "success"),
        "partial": sum(1 for r in results if r.status == "partial"),
        "failed": sum(1 for r in results if r.status == "failed"),
        "skipped": sum(1 for r in results if r.status == "skipped"),
        "results": [r.to_dict() for r in results],
        "trace_id": trace_id,
    }

    await session.flush()

    logger.info(
        "1688 数据回填完成: total=%d success=%d partial=%d failed=%d skipped=%d",
        total,
        summary["backfilled"],
        summary["partial"],
        summary["failed"],
        summary["skipped"],
    )

    return summary


async def get_backfill_status(
    session: AsyncSession,
    *,
    workspace_id: Any,
) -> dict[str, Any]:
    """获取 1688 回填状态概览。"""
    # 统计 1688 来源产品总数
    total_1688 = (
        (
            await session.execute(
                select(Product.id)
                .where(
                    Product.workspace_id == workspace_id,
                    Product.deleted_at.is_(None),
                    Product.source.in_(list(_1688_SOURCES)),
                )
            )
        )
        .scalars()
        .all()
    )

    # 扫描不完整产品
    incomplete_info = await scan_incomplete_products(
        session,
        workspace_id=workspace_id,
        candidate_only=False,
        limit=1000,
    )

    return {
        "total_1688_products": len(total_1688),
        "incomplete_count": len(incomplete_info),
        "complete_count": len(total_1688) - len(incomplete_info),
        "incomplete_products": incomplete_info[:50],
        "api_configured": _check_1688_configured(),
    }


def _check_1688_configured() -> bool:
    """检查 1688 API 是否已配置。"""
    try:
        from app.services.sourcing_1688_service import is_configured
        return is_configured()
    except Exception:
        return False
