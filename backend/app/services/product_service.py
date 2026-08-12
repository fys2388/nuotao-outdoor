"""Product service: CSV import and queries."""

import csv
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductCost
from app.models.product_intelligence import ProductCostSnapshot
from app.models.supplier import Supplier
from app.schemas.product import ImportRowError, ProductImportResult
from app.services import event_service

# CSV -> model field mapping; only these columns are accepted.
_IMPORT_FIELDS = (
    "sku",
    "name",
    "description",
    "category",
    "brand",
    "tags",
    "attributes",
    "source_url",
    "supplier_code",
    "weight_kg",
    "dimensions",
    "purchase_cost",
    "target_market",
)


class ProductImportError(Exception):
    """Raised when the CSV payload itself is invalid."""


def _parse_tags(raw: str) -> list[str]:
    """Parse a semicolon-separated tag list into a JSON-safe list."""
    return [tag.strip() for tag in raw.split(";") if tag.strip()]


def _parse_attributes(raw: str) -> dict[str, Any]:
    """Parse a JSON object string; empty values become an empty dict."""
    text = raw.strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"attributes must be a JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("attributes must be a JSON object")
    return value


def _normalize_row(row: dict[str, str]) -> dict[str, Any]:
    """Validate and normalize one CSV row into product fields."""
    sku = (row.get("sku") or "").strip()
    name = (row.get("name") or "").strip()
    if not sku or not name:
        raise ValueError("sku and name are required")

    weight_raw = (row.get("weight_kg") or "").strip()
    weight_kg: Decimal | None = None
    if weight_raw:
        try:
            parsed = Decimal(weight_raw)
        except Exception as exc:  # noqa: BLE001 - row-level validation
            raise ValueError("weight_kg must be a positive number") from exc
        if parsed <= 0:
            raise ValueError("weight_kg must be positive")
        weight_kg = parsed

    cost_raw = (row.get("purchase_cost") or "").strip()
    purchase_cost: Decimal | None = None
    if cost_raw:
        try:
            parsed = Decimal(cost_raw)
        except Exception as exc:  # noqa: BLE001 - row-level validation
            raise ValueError("purchase_cost must be a number") from exc
        if parsed < 0:
            raise ValueError("purchase_cost must be >= 0")
        purchase_cost = parsed

    dimensions: dict[str, Any] | None = None
    dims_raw = (row.get("dimensions") or "").strip()
    if dims_raw:
        dims = _parse_attributes(dims_raw)
        for key in ("length", "width", "height"):
            if key not in dims:
                raise ValueError("dimensions must include length/width/height")
        dimensions = dims

    return {
        "sku": sku,
        "name": name,
        "description": (row.get("description") or "").strip() or None,
        "category": (row.get("category") or "").strip() or None,
        "brand": (row.get("brand") or "").strip() or None,
        "source_url": (row.get("source_url") or "").strip() or None,
        "tags": _parse_tags(row.get("tags") or ""),
        "attributes": _parse_attributes(row.get("attributes") or ""),
        "supplier_code": (row.get("supplier_code") or "").strip() or None,
        "weight_kg": weight_kg,
        "dimensions": dimensions,
        "purchase_cost": purchase_cost,
        "target_market": (row.get("target_market") or "US").strip() or "US",
    }


async def import_products(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    csv_content: str,
    trace_id: str | None = None,
) -> ProductImportResult:
    """Import products from CSV content (upsert by workspace + sku).

    Every successful row publishes a ``product.created``/``product.updated``
    event; a bulk ``product.imported`` event summarizes the run.
    """
    reader = csv.DictReader(StringIO(csv_content))
    # Only sku/name are mandatory; the remaining columns are optional.
    missing = [f for f in ("sku", "name") if f not in (reader.fieldnames or [])]
    if missing:
        raise ProductImportError(f"CSV is missing required columns: {', '.join(missing)}")

    imported = 0
    updated = 0
    failed = 0
    errors: list[ImportRowError] = []

    for raw_row in reader:
        row_number = reader.line_num
        try:
            data = _normalize_row(dict(raw_row))
        except ValueError as exc:
            failed += 1
            errors.append(ImportRowError(row=row_number, message=str(exc)))
            continue

        # Resolve supplier by code (optional; missing supplier is not fatal).
        supplier_id: UUID | None = None
        if data["supplier_code"]:
            supplier = (
                await session.execute(
                    select(Supplier.id).where(
                        Supplier.workspace_id == workspace_id,
                        Supplier.code == data["supplier_code"],
                    )
                )
            ).scalar_one_or_none()
            if supplier is None:
                failed += 1
                errors.append(
                    ImportRowError(
                        row=row_number,
                        message=f"supplier_code '{data['supplier_code']}' not found",
                    )
                )
                continue
            supplier_id = supplier

        existing = (
            await session.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.sku == data["sku"],
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            product = Product(
                workspace_id=workspace_id,
                sku=data["sku"],
                name=data["name"],
                description=data["description"],
                category=data["category"],
                brand=data["brand"],
                source_url=data["source_url"],
                tags=data["tags"],
                attributes=data["attributes"],
                source="csv-import",
                status="draft",
                weight_kg=data["weight_kg"],
                dimensions=data["dimensions"],
                target_market=data["target_market"],
            )
            if supplier_id is not None:
                product.meta = {"supplier_id": str(supplier_id)}
            session.add(product)
            await session.flush()
            imported += 1
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="product.created",
                entity_type="product",
                entity_id=str(product.id),
                payload={"sku": data["sku"]},
                trace_id=trace_id,
            )
        else:
            existing.name = data["name"]
            existing.description = data["description"]
            existing.category = data["category"]
            existing.brand = data["brand"]
            existing.source_url = data["source_url"]
            existing.tags = data["tags"]
            existing.attributes = data["attributes"]
            existing.weight_kg = data["weight_kg"]
            existing.dimensions = data["dimensions"]
            existing.target_market = data["target_market"]
            if supplier_id is not None:
                existing.meta = {"supplier_id": str(supplier_id)}
            updated += 1
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="product.updated",
                entity_type="product",
                entity_id=str(existing.id),
                payload={"sku": data["sku"]},
                trace_id=trace_id,
            )

    if data["purchase_cost"] is not None:
        product_id = product.id if existing is None else existing.id
        total_cost = data["purchase_cost"]
        current = (
            await session.execute(
                select(ProductCost).where(
                    ProductCost.workspace_id == workspace_id,
                    ProductCost.product_id == product_id,
                )
            )
        ).scalar_one_or_none()
        if current is None:
            session.add(
                ProductCost(
                    workspace_id=workspace_id,
                    product_id=product_id,
                    purchase_cost=data["purchase_cost"],
                    total_cost=total_cost,
                    total_landed_cost=total_cost,
                    version="v1",
                    valid_from=datetime.now(UTC),
                )
            )
        else:
            current.purchase_cost = data["purchase_cost"]
            current.total_cost = total_cost
            current.total_landed_cost = total_cost
            current.valid_from = datetime.now(UTC)
        session.add(
            ProductCostSnapshot(
                workspace_id=workspace_id,
                product_id=product_id,
                purchase_cost=data["purchase_cost"],
                total_cost=total_cost,
                total_landed_cost=total_cost,
                version="v1",
                weight_kg=data["weight_kg"],
                source="csv-import",
                valid_from=datetime.now(UTC),
                trace_id=trace_id,
            )
        )

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.imported",
        entity_type="product",
        entity_id="*",
        payload={
            "imported": imported,
            "updated": updated,
            "failed": failed,
        },
        trace_id=trace_id,
    )

    return ProductImportResult(
        imported=imported,
        updated=updated,
        failed=failed,
        errors=errors,
    )


async def list_products(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Product], int]:
    """List products with optional filters, newest first."""
    filters = [Product.workspace_id == workspace_id]
    if status is not None:
        filters.append(Product.status == status)
    if category is not None:
        filters.append(Product.category == category)

    total = (
        await session.execute(select(func.count()).select_from(Product).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(Product)
                .where(*filters)
                .order_by(Product.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return rows, total
