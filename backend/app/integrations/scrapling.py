"""Scrapling integration adapter (M5.16, compliance-gated).

This is the ONLY place the scraping library is touched. It exposes a small,
defensively-guarded surface used by :mod:`app.services.scraping`:

- A **domain allowlist** sourced from settings (default empty -> disabled).
- A per-domain **rate limiter** so we never hammer a host.
- **Timeouts**, **retries** (idempotent GET, exponential backoff) and a
  per-domain **circuit breaker** (consecutive failures -> open -> cooldown).
- A **field allowlist** that strips any non-public field before it leaves this
  module (personal data / paywalled content is dropped, never persisted).

Stealth / Cloudflare bypass / login-wall scraping is intentionally **not**
exposed here. Only the plain-request ``Fetcher`` path is used, matching the
approved compliance scope in ``docs/M5.16``.

External errors never surface raw stacks - callers get :class:`ScrapingError`
with a stable message and the underlying cause logged.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Only these fields may leave this module. Anything scraped that is not in
# this set (names, addresses, contact info, paywalled body, etc.) is dropped.
ALLOWED_PRODUCT_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "price",
        "image_urls",
        "sku",
        "spec",
        "category",
        "supplier_code",
        "moq",
        "lead_time_days",
        "weight",
        "dimensions",
        "sales_volume",
        "trend_score_inputs",
    }
)
ALLOWED_SUPPLIER_FIELDS: frozenset[str] = frozenset(
    {
        "supplier_shop",
        "rating",
        "location",
        "since_year",
    }
)
# Personal-data markers - any key matching these is dropped outright.
_BLOCKED_KEY_FRAGMENTS: tuple[str, ...] = (
    "phone",
    "email",
    "mobile",
    "address",
    "contact",
    "buyer",
    "account",
    "name",
    "wechat",
    "qq",
)


class ScrapingError(Exception):
    """Raised when a scrape cannot complete (stable, non-internal message)."""


class ScrapingDisabledError(ScrapingError):
    """Raised when scraping is disabled or the domain is not allowlisted."""


class FieldAllowlistError(ScrapingError):
    """Raised when a scraped record contains no allowed fields."""


class _RateLimiter:
    """Minimal per-domain rate limiter (token-style, min-interval based)."""

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._last: dict[str, float] = {}

    async def wait(self, domain: str) -> None:
        last = self._last.get(domain, 0.0)
        now = time.monotonic()
        wait = max(0.0, last + self._min_interval - now)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last[domain] = time.monotonic()


class _CircuitBreaker:
    """Per-domain open/closed circuit breaker on consecutive failures."""

    def __init__(self, max_failures: int, cooldown_seconds: int) -> None:
        self._max_failures = max_failures
        self._cooldown = cooldown_seconds
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def _is_open(self, domain: str) -> bool:
        opened = self._opened_at.get(domain)
        if opened is None:
            return False
        if time.monotonic() - opened >= self._cooldown:
            # cooldown elapsed -> half-open: let a single probe through
            self._opened_at.pop(domain, None)
            self._failures[domain] = 0
            return False
        return True

    async def guard(self, domain: str) -> None:
        """Raise when the circuit is open for ``domain``."""
        if self._is_open(domain):
            raise ScrapingError(f"circuit open for domain '{domain}' (cooldown active)")

    def record_success(self, domain: str) -> None:
        self._failures.pop(domain, None)
        self._opened_at.pop(domain, None)

    def record_failure(self, domain: str) -> None:
        failures = self._failures.get(domain, 0) + 1
        self._failures[domain] = failures
        if failures >= self._max_failures:
            self._opened_at[domain] = time.monotonic()
            logger.warning("scraping circuit opened for domain '%s'", domain)


def _host_of(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        raise ScrapingError("invalid URL: missing host")
    return host


def _domain_allowed(host: str, allowed: list[str]) -> bool:
    if not allowed:
        return False
    host = host.lower()
    for entry in allowed:
        entry = entry.lower().strip()
        if host == entry or host.endswith("." + entry):
            return True
    return False


def _deep_clean(value: object) -> object:
    """Recursively drop blocked keys and prune None/empty containers.

    Personal-data fields are removed at any nesting depth so a nested
    ``{"spec": {"contact": "..."}}`` cannot smuggle a blocked value through.
    """
    if isinstance(value, dict):
        cleaned: dict[str, object] = {}
        for key, item in value.items():
            low = str(key).lower()
            if any(frag in low for frag in _BLOCKED_KEY_FRAGMENTS):
                continue
            nested = _deep_clean(item)
            if nested is None:
                continue
            cleaned[key] = nested
        return cleaned or None
    if isinstance(value, list):
        nested = [_deep_clean(item) for item in value]
        nested = [item for item in nested if item is not None]
        return nested or None
    if isinstance(value, str) and not value.strip():
        return None
    return value


@dataclass
class ScrapedProduct:
    """A sanitized scraped product that is safe to persist."""

    source_url: str
    fields: dict[str, object]
    captured_at: float = field(default_factory=time.time)
    trace_id: str | None = None


class ScraplingAdapter:
    """Guarded wrapper around the Scrapling ``Fetcher`` plain-request path."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._limiter = _RateLimiter(
            min_interval=(1.0 / self._settings.scraping_qps_per_domain)
            if self._settings.scraping_qps_per_domain > 0
            else 2.0
        )
        self._circuit = _CircuitBreaker(
            max_failures=self._settings.scraping_circuit_failures,
            cooldown_seconds=self._settings.scraping_circuit_cooldown_seconds,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def is_enabled(self) -> bool:
        """Return whether scraping is enabled AND a domain is allowlisted."""
        return self._settings.scraping_enabled and bool(self._settings.scraping_allowed_domains)

    def check_domain(self, url: str) -> str:
        """Return the allowlisted host for ``url`` or raise ``ScrapingError``."""
        if not self.is_enabled():
            raise ScrapingDisabledError("scraping is disabled (SCRAPING_ENABLED=false)")
        host = _host_of(url)
        if not _domain_allowed(host, self._settings.scraping_allowed_domains):
            raise ScrapingDisabledError(
                f"domain '{host}' is not in the allowlist; scrape refused"
            )
        return host

    async def fetch(self, url: str, *, trace_id: str | None = None) -> ScrapedProduct:
        """Fetch a public page and return a sanitized ``ScrapedProduct``.

        Raises :class:`ScrapingError` on any refusal, timeout or persistent
        failure. Never returns blocked/personal fields.
        """
        host = self.check_domain(url)
        await self._circuit.guard(host)
        await self._limiter.wait(host)

        last_error: Exception | None = None
        for attempt in range(self._settings.scraping_max_retries + 1):
            if attempt > 0:
                backoff = (2.0 ** attempt)
                logger.warning("scraping retry %s for %s after %.0fs", attempt, url, backoff)
                await asyncio.sleep(backoff)
            try:
                raw = await self._fetch_once(url, host)
                self._circuit.record_success(host)
                return self._sanitize(url, raw, trace_id=trace_id)
            except ScrapingError as exc:
                if isinstance(exc, ScrapingDisabledError):
                    raise  # config refusal - not retryable
                self._circuit.record_failure(host)
                last_error = exc
                # 4xx-ish / not-retryable
                if getattr(exc, "retryable", True) is False:
                    break
        raise ScrapingError(f"scrape failed after retries: {last_error}") from last_error

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    async def _fetch_once(self, url: str, host: str) -> dict[str, object]:
        """Run one plain GET through Scrapling's ``Fetcher``.

        The import is deferred so the module imports cleanly when the optional
        ``scrapling`` dependency is absent (tests / thin environments).
        """
        try:
            from scrapling.fetchers import Fetcher
        except Exception as exc:
            raise ScrapingError("scrapling library is not installed") from exc

        try:
            page = await asyncio.to_thread(
                Fetcher.get,
                url,
                timeout=self._settings.scraping_read_timeout_seconds,
            )
        except Exception as exc:
            raise ScrapingError(f"request failed: {exc}") from exc

        status = getattr(page, "status", None)
        if status is not None and int(status) >= 400:
            err = ScrapingError(f"HTTP {status} for {host}")
            err.retryable = int(status) >= 500  # type: ignore[attr-defined]
            raise err

        # Plain-request text extraction; no stealth, no JS rendering.
        try:
            text = getattr(page, "text", None)
            if text is None:
                # fall back to the body renderer if the page exposes it
                text = page.get_text() if hasattr(page, "get_text") else None
            return {"html": text or ""}
        except Exception as exc:
            raise ScrapingError(f"failed to extract page text: {exc}") from exc

    def _sanitize(
        self, url: str, raw: dict[str, object], *, trace_id: str | None
    ) -> ScrapedProduct:
        """Apply the field allowlist and blocklist to a raw page payload."""
        # The raw dict carries only the page html keyed under "html"; the
        # caller (services.scraping) is responsible for field-level parsing
        # via the allowlists. We enforce the blocklist defensively here so no
        # blocked key can be persisted regardless of what was scraped.
        cleaned = _deep_clean(raw)
        fields = {k: v for k, v in (cleaned or {}).items() if k in ALLOWED_PRODUCT_FIELDS}
        if not fields:
            raise FieldAllowlistError("scraped content contained no allowed fields")
        return ScrapedProduct(source_url=url, fields=fields, trace_id=trace_id)


def create_adapter() -> ScraplingAdapter:
    """Return a configured adapter (fresh settings snapshot each call)."""
    return ScraplingAdapter()


def allowed_product_fields() -> frozenset[str]:
    """Expose the product field allowlist for validation/tests."""
    return ALLOWED_PRODUCT_FIELDS


def blocked_key_fragments() -> tuple[str, ...]:
    """Expose the PII key blocklist for tests."""
    return _BLOCKED_KEY_FRAGMENTS
