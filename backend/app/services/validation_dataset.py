"""M5.7 real-validation dataset: staging validation cases.

Every case explicitly declares whether it comes from real business data
(``staging_real``) or a synthetic fixture (``staging_synthetic``). Reports and
scorecards can therefore never confuse the two; synthetic data is never
reported as a real business result.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_intelligence import ProductValidationCase

logger = logging.getLogger(__name__)

VALIDATION_SOURCES: tuple[str, ...] = ("staging_real", "staging_synthetic")


class ValidationDatasetError(Exception):
    """Raised when a validation case cannot be registered."""


async def register_case(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID | None,
    source: str,
    run_id: UUID | None = None,
    trace_id: str | None = None,
    category: str | None = None,
    notes: str | None = None,
) -> ProductValidationCase:
    """Register one validation case (append-only; source is validated).

    ``source`` must be ``staging_real`` or ``staging_synthetic`` - synthetic
    data can never be marked as real business data.
    """
    if source not in VALIDATION_SOURCES:
        raise ValidationDatasetError(f"source must be one of {VALIDATION_SOURCES}, got '{source}'")
    case = ProductValidationCase(
        workspace_id=workspace_id,
        product_id=product_id,
        category=category,
        source=source,
        run_id=run_id,
        trace_id=trace_id,
        notes=notes,
    )
    session.add(case)
    await session.flush()
    logger.info(
        "validation case %s registered source=%s product=%s trace=%s",
        case.id,
        source,
        product_id,
        trace_id,
    )
    return case


async def list_cases(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    source: str | None = None,
    product_id: UUID | None = None,
    limit: int = 100,
) -> list[ProductValidationCase]:
    """List the workspace validation cases (optional source/product filter)."""
    query = select(ProductValidationCase).where(ProductValidationCase.workspace_id == workspace_id)
    if source is not None:
        query = query.where(ProductValidationCase.source == source)
    if product_id is not None:
        query = query.where(ProductValidationCase.product_id == product_id)
    query = query.order_by(ProductValidationCase.created_at.desc()).limit(limit)
    rows = (await session.execute(query)).scalars().all()
    return list(rows)
