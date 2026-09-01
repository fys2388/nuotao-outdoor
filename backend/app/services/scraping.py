"""Scraping orchestration service (M5.16, compliance-gated).

This is the business layer that bridges the guarded Scrapling adapter
(:mod:`app.integrations.scrapling`) and the existing Product Candidate intake
(:func:`app.services.product_intelligence.intake_product`).

Rules enforced here (never by the caller):
- Scraping is **disabled by default**; it only runs when the adapter reports
  it enabled (domain allowlisted).
- Only a **concurrency-bounded** number of URLs run at once.
- The scraped result is mapped onto a :class:`ProductIntakeRequest` and fed
  through the standard candidate intake, so the result enters the SAME
  human-approval chain as manual/CSV intake (M5.13). **No automatic commerce
  action and no auto-publish.**
- Every job is audited via ``event_log`` (``source.fetch.*``).
- Field mapping is bounded to the adapter's allowlist; personal data never
  reaches the DB.

A scraping job never invokes an LLM. Agents cannot call this directly; only
the API layer (RBAC-guarded) may submit jobs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.scrapling import (
    FieldAllowlistError,
    ScrapingError,
    ScraplingAdapter,
    create_adapter,
)
from app.schemas.product_intelligence import ProductIntakeRequest
from app.services import event_service
from app.services.product_intelligence import (
    ProductIntelligenceError,
    intake_product,
)

logger = logging.getLogger(__name__)


class ScrapingServiceError(Exception):
    """Raised for configuration/validation errors (stable messages)."""


@dataclass
class ScrapeJobResult:
    """Outcome of a scraping job."""

    requested: int = 0
    succeeded: int = 0
    failed: int = 0
    product_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _clean_text(value: object, *, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _clean_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return None


def _build_intake(
    *,
    source_url: str,
    fields: dict[str, object],
    workspace_sku_prefix: str | None,
) -> ProductIntakeRequest:
    """Map a sanitized scraped field dict onto a candidate intake request.

    Only allowlisted fields are read; anything missing is left as a default
    for the human operator to fill in during approval. Price/moq/etc. that
    cannot be parsed as Decimal are dropped rather than guessed.
    """
    title = _clean_text(fields.get("title"), default="(scraped product)") or "(scraped product)"
    sku_raw = _clean_text(fields.get("sku"))
    sku = None
    if sku_raw:
        sku = f"{workspace_sku_prefix}-{sku_raw}" if workspace_sku_prefix else sku_raw
    price = _clean_decimal(fields.get("price"))
    return ProductIntakeRequest(
        sku=sku,
        title=title,
        description=_clean_text(fields.get("description")),
        category=_clean_text(fields.get("category")),
        source_type="1688",
        source_url=source_url,
        supplier_code=_clean_text(fields.get("supplier_code")),
        purchase_cost=price or Decimal("0"),
        # The remaining cost fields (shipping, packaging, tax, handling) are
        # deliberately NOT guessed from public page data - a human provides
        # them at approval time. This keeps the cost model trustworthy.
        weight_kg=_clean_decimal(fields.get("weight")),
        target_market="US",
        currency="USD",
    )


async def run_scrape_job(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    urls: list[str],
    trace_id: str | None = None,
    adapter: ScraplingAdapter | None = None,
) -> ScrapeJobResult:
    """Run a bounded scrape over ``urls`` and persist results as candidates.

    Raises :class:`ScrapingServiceError` for config refusal (disabled / empty
    URL list). Per-URL failures are collected and reported without aborting
    the whole job.
    """
    adapter = adapter or create_adapter()
    if not urls:
        raise ScrapingServiceError("no URLs provided for scraping job")
    if not adapter.is_enabled():
        raise ScrapingServiceError(
            "scraping is disabled (SCRAPING_ENABLED=false or no allowlisted domain)"
        )

    requested = len(urls)
    result = ScrapeJobResult(requested=requested)

    # Validate every URL's domain up front so a single bad host does not waste
    # the whole job; also fails fast on a global config refusal.
    for url in urls:
        try:
            adapter.check_domain(url)
        except ScrapingError as exc:
            result.failed += 1
            result.errors.append(str(exc))
    if result.failed == requested:
        await _audit_job(
            session,
            workspace_id=workspace_id,
            result=result,
            trace_id=trace_id,
        )
        return result

    for url in urls:
        try:
            scraped = await adapter.fetch(url, trace_id=trace_id)
            request = _build_intake(
                source_url=scraped.source_url,
                fields=scraped.fields,
                workspace_sku_prefix=_workspace_sku_prefix(workspace_id),
            )
            intake = await intake_product(
                session,
                workspace_id=workspace_id,
                data=request,
                trace_id=trace_id,
            )
            result.succeeded += 1
            result.product_ids.append(str(intake.product.id))
        except (ScrapingError, FieldAllowlistError, ProductIntelligenceError) as exc:
            result.failed += 1
            result.errors.append(str(exc))

    await _audit_job(
        session,
        workspace_id=workspace_id,
        result=result,
        trace_id=trace_id,
    )
    logger.info(
        "scrape job done requested=%s succeeded=%s failed=%s trace=%s",
        result.requested,
        result.succeeded,
        result.failed,
        trace_id,
    )
    return result


def _workspace_sku_prefix(workspace_id: UUID) -> str:
    """Return a short, stable prefix for scraped SKUs.

    The adapter/SKU are deduplicated per workspace via the intake (sku unique
    per workspace), so a derived sku must be stable for a given source. A
    truncated workspace id gives a deterministic prefix without leaking PII.
    """
    return f"sc-{str(workspace_id)[:8]}"


async def _audit_job(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    result: ScrapeJobResult,
    trace_id: str | None,
) -> None:
    """Persist one ``source.fetch.completed`` audit event for the job."""
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="source.fetch.completed",
        entity_type="scraping_job",
        entity_id=str(workspace_id),
        payload={
            "requested": result.requested,
            "succeeded": result.succeeded,
            "failed": result.failed,
            "product_ids": result.product_ids,
            "errors": result.errors,
            "finished_at": datetime.now(UTC).isoformat(),
        },
        trace_id=trace_id,
    )
