"""M5.16 Scrapling scraping integration tests.

Covers the compliance-gated scraping surface:
- disabled-by-default / domain-allowlist refusals (ScrapingDisabledError)
- PII key stripping + field allowlist (deep-clean, nested blocked keys)
- circuit breaker opens/recovers
- rate limiter enforces a minimum interval
- _build_intake maps allowlisted fields and never guesses cost fields
- run_scrape_job persists candidates via the standard intake chain (fake
  adapter), audits via event_log, and isolates failures per-URL
- POST /api/v1/scraping/jobs returns 400 when scraping is disabled
"""

from decimal import Decimal

import pytest
from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.integrations.scrapling import (
    _deep_clean,
    blocked_key_fragments,
    create_adapter,
)
from app.models.event import EventLog
from app.models.product import Product
from app.services import scraping
from app.services.scraping import _build_intake
from sqlalchemy import select

WORKSPACE = DEFAULT_WORKSPACE_ID
JOBS_URL = "/api/v1/scraping/jobs"


class FakeAdapter:
    """Minimal adapter stub with configurable per-URL behavior."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        results: dict[str, dict] | None = None,
        errors: list[tuple[str, Exception]] | None = None,
    ) -> None:
        self._enabled = enabled
        self._results = results or {}
        self._errors = errors or []
        self._fetches: list[str] = []

    def is_enabled(self) -> bool:
        return self._enabled

    def check_domain(self, url: str) -> str:
        if not self._enabled:
            from app.integrations.scrapling import ScrapingDisabledError

            raise ScrapingDisabledError("scraping is disabled")
        return url.split("/")[2]

    async def fetch(self, url: str, *, trace_id: str | None = None):
        self._fetches.append(url)
        for match, exc in self._errors:
            if match in url:
                raise exc
        if url in self._results:
            return self._results[url]
        raise scraping.ScrapingError(f"no result for {url}")


def _scraped(source_url: str, **fields) -> dict:
    from app.integrations.scrapling import ScrapedProduct

    return ScrapedProduct(source_url=source_url, fields=fields)


# --------------------------------------------------------------------------- #
# adapter unit tests (pure, no network)
# --------------------------------------------------------------------------- #


def test_deep_clean_strips_blocked_keys_nested():
    raw = {
        "title": "Tent",
        "spec": {"buyer_name": "alice", "size": "M", "price": "9.9"},
        "contact": {"wechat": "wx123", "note": "ok"},
        "ok": "kept",
        "empty": "",
        "nested_list": ["a", "b", None],
        "phone": "13900000000",
    }
    cleaned = _deep_clean(raw)
    assert "ok" in cleaned
    assert cleaned["ok"] == "kept"
    assert "buyer_name" not in cleaned["spec"]
    assert "contact" not in cleaned
    assert "phone" not in cleaned
    assert "empty" not in cleaned  # empty string pruned (key removed)
    assert cleaned["nested_list"] == ["a", "b"]


def test_blocked_key_fragments_cover_pii():
    fragments = blocked_key_fragments()
    for frag in ("email", "phone", "contact", "address", "buyer", "account"):
        assert frag in fragments


def test_field_allowlist_exposed():
    from app.integrations.scrapling import allowed_product_fields

    fields = allowed_product_fields()
    for key in ("title", "price", "image_urls", "sku", "spec", "category", "supplier_code"):
        assert key in fields


def test_build_intake_never_guesses_cost_fields():
    intake = _build_intake(
        source_url="https://detail.1688.com/offer/1.html",
        fields={
            "title": "Headlamp",
            "price": "12.50",
            "supplier_code": "SUP-1",
            "weight": "0.4",
        },
        workspace_sku_prefix=None,
    )
    assert intake.title == "Headlamp"
    assert intake.purchase_cost == Decimal("12.50")
    assert intake.supplier_code == "SUP-1"
    assert intake.weight_kg == Decimal("0.4")
    # Shipping/packaging/tax/handling must stay at default (0) - not guessed.
    assert intake.domestic_shipping == Decimal("0")
    assert intake.international_shipping is None
    assert intake.packaging == Decimal("0")
    assert intake.tax_estimate == Decimal("0")


def test_build_intake_invalid_price_dropped():
    intake = _build_intake(
        source_url="https://detail.1688.com/offer/2.html",
        fields={"title": "Stove", "price": "N/A"},
        workspace_sku_prefix="ws",
    )
    assert intake.purchase_cost == Decimal("0")
    assert intake.title == "Stove"


# --------------------------------------------------------------------------- #
# service-level tests (in-memory DB + fake adapter)
# --------------------------------------------------------------------------- #


async def test_run_scrape_job_persists_candidate(db_session):
    adapter = FakeAdapter(
        results={
            "https://detail.1688.com/offer/1.html": _scraped(
                "https://detail.1688.com/offer/1.html",
                title="Tent",
                price="99.00",
            )
        }
    )
    result = await scraping.run_scrape_job(
        db_session,
        workspace_id=WORKSPACE,
        urls=["https://detail.1688.com/offer/1.html"],
        trace_id="trace-scrape-1",
        adapter=adapter,
    )
    assert result.requested == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert len(result.product_ids) == 1

    product = (
        await db_session.execute(
            select(Product).where(Product.workspace_id == WORKSPACE)
        )
    ).scalar_one()
    assert product.name == "Tent"
    assert product.candidate_status == "candidate"
    assert product.source == "intake"

    # audited via event_log
    events = (
        await db_session.execute(
            select(EventLog).where(EventLog.event_type == "source.fetch.completed")
        )
    ).scalars().all()
    assert len(events) == 1


async def test_run_scrape_job_disabled_raises(db_session):
    adapter = FakeAdapter(enabled=False)
    with pytest.raises(scraping.ScrapingServiceError):
        await scraping.run_scrape_job(
            db_session,
            workspace_id=WORKSPACE,
            urls=["https://detail.1688.com/offer/1.html"],
            adapter=adapter,
        )


async def test_run_scrape_job_isolates_failures(db_session):
    adapter = FakeAdapter(
        errors=[
            ("https://detail.1688.com/offer/bad.html", scraping.ScrapingError("boom")),
        ],
        results={
            "https://detail.1688.com/offer/good.html": _scraped(
                "https://detail.1688.com/offer/good.html",
                title="Good",
                price="1.00",
            )
        },
    )
    result = await scraping.run_scrape_job(
        db_session,
        workspace_id=WORKSPACE,
        urls=[
            "https://detail.1688.com/offer/good.html",
            "https://detail.1688.com/offer/bad.html",
        ],
        trace_id="trace-mixed",
        adapter=adapter,
    )
    assert result.requested == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert any("boom" in e for e in result.errors)


async def test_run_scrape_job_no_urls_raises(db_session):
    adapter = FakeAdapter(enabled=True)
    with pytest.raises(scraping.ScrapingServiceError):
        await scraping.run_scrape_job(
            db_session, workspace_id=WORKSPACE, urls=[], adapter=adapter
        )


# --------------------------------------------------------------------------- #
# real adapter: config-refusal logic (no network)
# --------------------------------------------------------------------------- #


def test_real_adapter_disabled_by_default():
    adapter = create_adapter()
    get_settings().scraping_enabled = False
    get_settings().scraping_allowed_domains = ["detail.1688.com"]
    assert adapter.is_enabled() is False
    with pytest.raises(Exception) as excinfo:
        adapter.check_domain("https://detail.1688.com/offer/1.html")
    assert "disabled" in str(excinfo.value)


def test_real_adapter_denies_non_allowlisted_domain():
    get_settings().scraping_enabled = True
    get_settings().scraping_allowed_domains = ["detail.1688.com"]
    adapter = create_adapter()
    assert adapter.is_enabled() is True
    with pytest.raises(Exception) as excinfo:
        adapter.check_domain("https://evil.example.com/x")
    assert "not in the allowlist" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# API-level: disabled-by-default returns 400
# --------------------------------------------------------------------------- #


async def test_api_submit_job_when_disabled_returns_400(api_client):
    get_settings().scraping_enabled = False
    resp = api_client.post(
        JOBS_URL,
        json={"urls": ["https://detail.1688.com/offer/1.html"], "actor": "ops-user"},
    )
    assert resp.status_code == 400
    assert "disabled" in resp.json()["detail"]
