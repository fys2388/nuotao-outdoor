"""Candidate detail editing service.

Provides a single service entry point for editing candidate product details
(PHASE 3 of V3.0 evaluation fix). The edit is atomic: either all fields are
updated or none are. The endpoint layer owns the transaction; this service
only flushes.

Edit scope (only candidate-status products, not winner/approved):
- name, description, category, brand
- weight_kg, dimensions, attributes, tags
- source_url, source_offer_id
- meta (retail_price, images, etc.)
- target_market

Fields that cannot be edited:
- id, sku, status, candidate_status, mastered_at, mastered_by
- data_integrity_* (set by integrity checker, not by humans)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services import event_service

logger = logging.getLogger(__name__)


class CandidateEditorError(Exception):
    """Raised when a candidate edit cannot complete."""


# Fields that are editable via PATCH /product-candidates/{id}
_EDITABLE_FIELDS = frozenset({
    "name",
    "description",
    "category",
    "brand",
    "weight_kg",
    "dimensions",
    "attributes",
    "tags",
    "source_url",
    "source_offer_id",
    "meta",
    "target_market",
})

# Fields that are NOT editable (enforced, never silently ignored)
_PROTECTED_FIELDS = frozenset({
    "id",
    "sku",
    "status",
    "candidate_status",
    "mastered_at",
    "mastered_by",
    "mastered_trace_id",
    "data_integrity_status",
    "data_integrity_score",
    "data_integrity_missing",
    "data_integrity_checked_at",
    "data_integrity_trace_id",
    "data_integrity_version",
    "deleted_at",
    "created_at",
    "updated_at",
    "workspace_id",
})

# Candidate statuses that allow editing
_EDITABLE_STATUSES = frozenset({"candidate", "approved", "testing"})


async def _load_product(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
) -> Product:
    """Load a live product by id, raising CandidateEditorError if not found."""
    product = (
        (
            await session.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.id == product_id,
                    Product.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .one_or_none()
    )
    if product is None:
        raise CandidateEditorError(
            f"product not found: {product_id}"
        )
    return product


async def edit_candidate(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    data: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Edit candidate product details.

    Args:
        session: DB session (caller owns the transaction).
        workspace_id: Workspace scope.
        product_id: Product to edit.
        data: Dict of fields to update. Only keys in _EDITABLE_FIELDS are
              accepted; unknown keys raise CandidateEditorError.
        trace_id: Audit trace id.

    Returns:
        Dict with product_id, updated_fields, and a full product summary.

    Raises:
        CandidateEditorError: Product not found, not editable, or invalid input.
    """
    product = await _load_product(
        session, workspace_id=workspace_id, product_id=product_id,
    )

    # Only candidate-lifecycle products can be edited
    if product.candidate_status not in _EDITABLE_STATUSES:
        raise CandidateEditorError(
            f"product {product_id} has candidate_status="
            f"{product.candidate_status!r}, not editable "
            f"(must be one of {sorted(_EDITABLE_STATUSES)})"
        )

    if not data:
        raise CandidateEditorError("no fields to edit (empty payload)")

    # Validate: reject protected and unknown fields
    unknown = set(data.keys()) - _EDITABLE_FIELDS
    protected = set(data.keys()) & _PROTECTED_FIELDS
    if protected:
        raise CandidateEditorError(
            f"protected fields cannot be edited: {sorted(protected)}"
        )
    if unknown:
        raise CandidateEditorError(
            f"unknown fields: {sorted(unknown)} "
            f"(editable: {sorted(_EDITABLE_FIELDS)})"
        )

    updated_fields: list[str] = []
    snapshot: dict[str, Any] = {}

    for key, value in data.items():
        if key not in _EDITABLE_FIELDS:
            continue

        old_value = getattr(product, key)
        snapshot[key] = old_value

        if key == "weight_kg":
            # Validate weight is positive if provided
            if value is not None:
                try:
                    decimal_val = Decimal(str(value))
                    if decimal_val <= 0:
                        raise CandidateEditorError("weight_kg must be positive")
                    value = decimal_val
                except (ArithmeticError, ValueError):
                    raise CandidateEditorError("weight_kg must be a valid number")
            product.weight_kg = value

        elif key == "dimensions":
            # Validate dimensions structure if provided
            if value is not None:
                if not isinstance(value, dict):
                    raise CandidateEditorError("dimensions must be a dict or null")
                for dim_key in ("length", "width", "height"):
                    raw = value.get(dim_key)
                    if raw is not None:
                        try:
                            num = float(raw)
                            if num <= 0:
                                raise CandidateEditorError(
                                    f"dimensions.{dim_key} must be positive"
                                )
                        except (TypeError, ValueError):
                            raise CandidateEditorError(
                                f"dimensions.{dim_key} must be a positive number"
                            )
            product.dimensions = value

        elif key == "meta":
            # Merge meta: preserve existing keys not in the patch
            if value is not None:
                if not isinstance(value, dict):
                    raise CandidateEditorError("meta must be a dict or null")
                new_meta = dict(product.meta or {})
                new_meta.update(value)
                product.meta = new_meta
                snapshot[key] = new_meta
            else:
                product.meta = {}

        elif key == "attributes":
            if value is not None:
                if not isinstance(value, dict):
                    raise CandidateEditorError("attributes must be a dict or null")
                new_attrs = dict(product.attributes or {})
                new_attrs.update(value)
                product.attributes = new_attrs
                snapshot[key] = new_attrs
            else:
                product.attributes = {}

        elif key == "tags":
            if value is not None and not isinstance(value, list):
                raise CandidateEditorError("tags must be a list or null")
            product.tags = value if value is not None else []

        else:
            # Simple string fields: direct assignment
            setattr(product, key, value)

        updated_fields.append(key)

    # Record audit event (in the caller's transaction)
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.candidate.edited",
        entity_type="product",
        entity_id=str(product_id),
        payload={
            "sku": product.sku,
            "candidate_status": product.candidate_status,
            "updated_fields": updated_fields,
            "changes": {
                k: {
                    "old": str(old_val)[:200] if old_val is not None else None,
                    "new": str(getattr(product, k))[:200]
                    if getattr(product, k) is not None else None,
                }
                for k, old_val in snapshot.items()
            },
        },
        trace_id=trace_id,
        commit=False,
    )
    await session.flush()

    return {
        "product_id": str(product.id),
        "sku": product.sku,
        "name": product.name,
        "candidate_status": product.candidate_status,
        "updated_fields": updated_fields,
    }


async def get_candidate_detail(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
) -> dict[str, Any]:
    """Return a full candidate detail view including related data.

    Includes product fields, latest cost, latest score, sources, and
    sourcing candidates. Unknown fields are reported as null, never fabricated.
    """
    from app.models.product_intelligence import (
        ProductScore,
        ProductSource,
        SourcingCandidate,
    )
    from app.services.product_cost_service import (
        latest_cost_for_product,
        is_effective_cost,
    )

    product = await _load_product(
        session, workspace_id=workspace_id, product_id=product_id,
    )

    # Latest cost
    cost = await latest_cost_for_product(
        session, workspace_id=workspace_id, product_id=product_id,
    )
    cost_summary = None
    if cost is not None:
        cost_summary = {
            "id": str(cost.id),
            "currency": cost.currency,
            "purchase_cost": str(cost.purchase_cost),
            "total_landed_cost": str(cost.total_landed_cost),
            "version": cost.version,
            "valid_from": str(cost.valid_from),
            "is_effective": is_effective_cost(cost),
        }

    # Latest score
    score_rows = (
        (
            await session.execute(
                select(ProductScore)
                .where(
                    ProductScore.workspace_id == workspace_id,
                    ProductScore.product_id == product_id,
                )
                .order_by(ProductScore.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .all()
    )
    score_summary = None
    if score_rows:
        s = score_rows[0]
        score_summary = {
            "id": str(s.id),
            "profit": str(s.profit),
            "logistics": str(s.logistics),
            "demand": str(s.demand),
            "competition": str(s.competition),
            "differentiation": str(s.differentiation),
            "compliance": str(s.compliance),
            "total": str(s.total),
            "model_version": s.model_version,
        }

    # Sources (limit 5)
    source_rows = (
        (
            await session.execute(
                select(ProductSource)
                .where(
                    ProductSource.workspace_id == workspace_id,
                    ProductSource.product_id == product_id,
                )
                .order_by(ProductSource.created_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    sources = [
        {
            "id": str(src.id),
            "source_type": src.source_type,
            "source_url": src.source_url,
            "supplier_id": str(src.supplier_id) if src.supplier_id else None,
            "captured_at": str(src.captured_at),
        }
        for src in source_rows
    ]

    # Sourcing candidates (limit 10)
    candidate_rows = (
        (
            await session.execute(
                select(SourcingCandidate)
                .where(
                    SourcingCandidate.workspace_id == workspace_id,
                    SourcingCandidate.product_id == product_id,
                )
                .order_by(SourcingCandidate.created_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    sourcing_candidates = [
        {
            "id": str(sc.id),
            "supplier_name": sc.supplier_name,
            "purchase_price": str(sc.purchase_price) if sc.purchase_price else None,
            "currency": sc.currency,
            "lead_time_days": sc.lead_time_days,
            "min_order_qty": sc.min_order_qty,
            "rating": str(sc.rating) if sc.rating else None,
            "notes": sc.notes,
        }
        for sc in candidate_rows
    ]

    return {
        "product": {
            "id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "description": product.description,
            "category": product.category,
            "brand": product.brand,
            "status": product.status,
            "candidate_status": product.candidate_status,
            "source": product.source,
            "source_url": product.source_url,
            "source_offer_id": product.source_offer_id,
            "tags": product.tags,
            "attributes": product.attributes,
            "meta": product.meta,
            "weight_kg": str(product.weight_kg) if product.weight_kg else None,
            "dimensions": product.dimensions,
            "target_market": product.target_market,
            "data_integrity_status": product.data_integrity_status,
            "data_integrity_score": str(product.data_integrity_score)
            if product.data_integrity_score else None,
            "data_integrity_missing": product.data_integrity_missing,
            "created_at": str(product.created_at),
            "updated_at": str(product.updated_at),
        },
        "cost": cost_summary,
        "score": score_summary,
        "sources": sources,
        "sourcing_candidates": sourcing_candidates,
    }
