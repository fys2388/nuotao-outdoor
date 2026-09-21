"""Gate-controlled WooCommerce publish endpoint.

Registered BEFORE the legacy ``products.router`` in ``app/api/v1/router.py``
using the same ``/products`` prefix, so this route wins for
``POST /products/{product_id}/push-woocommerce`` while every other route in
``products.py`` (including production-only ones such as the localization
approval endpoints) keeps working. No existing file is overwritten.

Response contract (matches the frontend's expected branches):
  200  pushed
  409  V3.0 gate: needs_review  -> frontend offers "我已人工复核，强制放行" (?force=true)
  422  V3.0 gate: blocked       -> hard stop, not forceable
  502  WooCommerce API rejected/failed (never reported as success)
"""
from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

import requests
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm.attributes import flag_modified

from app.services.listing_gate import (
    build_wc_payload,
    evaluate_gate,
    get_english_copy,
    resolve_prices,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["listing-publish"])

# nuotaooutdoor.com sits behind Cloudflare, which intermittently tears the TLS
# handshake down mid-flight (SSLEOFError / UNEXPECTED_EOF_WHILE_READING) - and
# once, part-way through a create, after WooCommerce had already committed the
# row. One push performs up to four sequential WooCommerce calls (SKU lookup,
# category resolution, the push itself, verification), so the retry budget is
# shared across all of them rather than per call: otherwise four independent
# budgets of 60s each multiply past Cloudflare's ~100s proxy limit and the
# browser only ever sees its own timeout.
_REQUEST_TIMEOUT = 12
_WC_MAX_ATTEMPTS = 4
_WC_RETRY_BACKOFF = (0.5, 1.5, 3.0)
_PUSH_BUDGET_SECONDS = 75.0


class _PushBudget:
    """Wall-clock budget shared by every WooCommerce call inside one push."""

    def __init__(self, seconds: float = _PUSH_BUDGET_SECONDS) -> None:
        self.deadline = time.monotonic() + seconds

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def per_attempt(self) -> float:
        """Timeout for a single attempt: leave headroom for the backoff."""
        return max(1.0, min(float(_REQUEST_TIMEOUT), self.remaining() - 1.0))

    def exhausted(self) -> bool:
        return self.remaining() < 2.0


def _wc_base_url() -> str:
    from app.services.woocommerce_sync_service import WC_URL

    return str(WC_URL).rstrip("/")


def _tag_attempts(exc: Exception, attempts: int) -> None:
    """Remember how many attempts were made, for honest error reporting."""
    try:
        exc.attempts = attempts
    except (AttributeError, TypeError):
        pass


def _wc_error_detail(exc: Exception) -> tuple[int | None, str]:
    """Return ``(status_code, response_body)`` for a failed WooCommerce call."""
    response = getattr(exc, "response", None)
    if response is not None:
        body = getattr(response, "text", "") or ""
        return response.status_code, body[:1000]
    return None, str(exc)


def _wc_call(method: str, url: str, *, auth: Any, headers: dict[str, str],
             json_body: dict[str, Any] | None = None,
             params: dict[str, Any] | None = None,
             budget: _PushBudget | None = None) -> requests.Response:
    """Call the WooCommerce REST API, retrying transient transport failures.

    nuotaooutdoor.com sits behind Cloudflare, which intermittently tears the TLS
    handshake down mid-flight (SSLEOFError / UNEXPECTED_EOF_WHILE_READING). In one
    observation window 4 of 8 requests died that way while the credentials and the
    store itself were healthy, so a single attempt reports false failures about
    half the time. Retries cover connection-level errors and 5xx; 4xx are answers
    and are raised immediately.
    """
    budget = budget or _PushBudget()
    last: Exception | None = None
    for attempt in range(1, _WC_MAX_ATTEMPTS + 1):
        if budget.exhausted():
            break
        try:
            response = requests.request(
                method,
                url,
                auth=auth,
                headers=headers,
                json=json_body,
                params=params,
                timeout=budget.per_attempt(),
            )
            if response.status_code >= 500:
                err = requests.exceptions.HTTPError(
                    f"{response.status_code} from {url}", response=response
                )
                if attempt >= _WC_MAX_ATTEMPTS:
                    _tag_attempts(err, attempt)
                    raise err
                last = err
                logger.warning(
                    "WooCommerce %s %s returned %s, retry %d/%d",
                    method, url, response.status_code, attempt, _WC_MAX_ATTEMPTS,
                )
                time.sleep(_WC_RETRY_BACKOFF[min(attempt - 1, len(_WC_RETRY_BACKOFF) - 1)])
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as exc:
            _tag_attempts(exc, attempt)
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last = exc
            if attempt >= _WC_MAX_ATTEMPTS:
                _tag_attempts(exc, attempt)
                break
            delay = _WC_RETRY_BACKOFF[min(attempt - 1, len(_WC_RETRY_BACKOFF) - 1)]
            logger.warning(
                "WooCommerce %s %s transport error (%s), retry %d/%d in %.1fs",
                method, url, type(exc).__name__, attempt, _WC_MAX_ATTEMPTS, delay,
            )
            time.sleep(delay)
    if last is not None:
        _tag_attempts(last, _WC_MAX_ATTEMPTS)
    raise last if last is not None else RuntimeError("WooCommerce call failed")


def _find_wc_id_by_sku(sku: str, *, auth: Any, headers: dict[str, str],
                       budget: _PushBudget | None = None) -> int | None:
    """Return the WooCommerce product id already holding this SKU, else None.

    Without this a retry of a create whose response was lost returns
    ``product_invalid_sku`` and the whole push is reported as a failure even
    though the product exists - and the local row never learns its
    ``woocommerce_id``, so every later attempt tries to create again instead of
    updating an existing product.
    """
    if not sku:
        return None
    try:
        response = _wc_call(
            "GET",
            f"{_wc_base_url()}/wp-json/wc/v3/products",
            auth=auth,
            headers=headers,
            params={"sku": sku, "per_page": 5, "status": "any"},
            budget=budget,
        )
        for item in response.json() or []:
            if str(item.get("sku", "")).strip() == sku:
                return int(item["id"])
    except requests.exceptions.RequestException as exc:
        logger.warning("SKU lookup failed for sku=%s: %s", sku, exc)
    return None


def _ensure_wc_category(name: str, *, auth: Any, headers: dict[str, str],
                        budget: _PushBudget | None = None) -> int | None:
    """Return a WooCommerce product-category id, creating the term if needed.

    WooCommerce silently ignores ``categories: [{"name": ...}]`` when the term
    does not exist yet - the product lands in "Uncategorized", which is a 10-point
    completeness loss. Terms must be created through the categories endpoint and
    then referenced by id.
    """
    base = f"{_wc_base_url()}/wp-json/wc/v3/products/categories"
    try:
        listed = _wc_call(
            "GET", base, auth=auth, headers=headers,
            params={"per_page": 100, "hide_empty": "false"},
            budget=budget,
        )
        wanted = str(name).strip().lower()
        for term in listed.json() or []:
            if str(term.get("name", "")).strip().lower() == wanted:
                return int(term["id"])
        created = _wc_call("POST", base, auth=auth, headers=headers,
                           json_body={"name": str(name).strip()},
                           budget=budget)
        return int(created.json()["id"])
    except requests.exceptions.RequestException as exc:
        logger.warning("Could not ensure WooCommerce category %r: %s", name, exc)
        return None


def _wc_credentials() -> tuple[Any, dict[str, str]]:
    from app.services.woocommerce_sync_service import _get_wc_auth, _get_wc_headers

    return _get_wc_auth(), _get_wc_headers()


async def _load_product(product_id: str) -> tuple[Any, Any | None]:
    """Return ``(session, product_or_None)``; caller must close the session."""
    from app.core.database import async_session_factory
    from app.models.product import Product

    session = async_session_factory()
    product: Any | None = None
    try:
        product = await session.get(Product, UUID(str(product_id)))
    except Exception as exc:  # malformed id, model mismatch, ...
        logger.warning("Failed to load product %s: %s", product_id, exc)
        product = None
    return session, product


@router.post(
    "/{product_id}/push-woocommerce",
    summary="推送商品到 WooCommerce（V3.0 闸门）",
)
async def push_product_to_woocommerce_gated(
    product_id: str,
    force: bool = Query(default=False, description="人工复核后强制放行 needs_review"),
) -> dict[str, Any]:
    session, product = await _load_product(product_id)
    try:
        if product is None:
            raise HTTPException(status_code=404, detail=f"产品不存在: {product_id}")

        meta = product.meta if isinstance(product.meta, dict) else {}
        english_copy = get_english_copy(meta)
        prices = resolve_prices(meta)
        gate = evaluate_gate(product, prices, english_copy)

        if gate["status"] == "blocked":
            logger.warning(
                "V3.0 gate BLOCKED sku=%s id=%s reasons=%s",
                product.sku, product_id, [r["code"] for r in gate["reasons"]],
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "gate": "V3.0",
                    "status": "blocked",
                    "message": "V3.0 选品闸门阻断，禁止上架",
                    "reasons": gate["reasons"],
                },
            )
        if gate["status"] == "needs_review" and not force:
            logger.warning(
                "V3.0 gate needs_review sku=%s id=%s reasons=%s",
                product.sku, product_id, [r["code"] for r in gate["reasons"]],
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "gate": "V3.0",
                    "status": "needs_review",
                    "message": "未通过 V3.0 选品闸门，需要人工复核",
                    "reasons": gate["reasons"],
                },
            )

        payload = build_wc_payload(product, prices, english_copy)
        wc_id = meta.get("woocommerce_id")
        base = _wc_base_url()
        auth, headers = _wc_credentials()

        wc_id_was_local = bool(wc_id)
        budget = _PushBudget()

        # Idempotency: the local row may not have learned its WooCommerce id when a
        # previous create's response was lost (Cloudflare tears the TLS connection
        # down after WooCommerce has already committed the row). Adopt the existing
        # product by SKU so this push becomes an update instead of a duplicate.
        if not wc_id:
            existing = _find_wc_id_by_sku(
                str(product.sku or ""), auth=auth, headers=headers, budget=budget,
            )
            if existing:
                wc_id = existing
                logger.info(
                    "Adopting existing WooCommerce product id=%s for sku=%s "
                    "(a previous create succeeded but its response was lost)",
                    existing,
                    product.sku,
                )

        action = "update" if wc_id else "create"
        url = (
            f"{base}/wp-json/wc/v3/products/{wc_id}"
            if wc_id
            else f"{base}/wp-json/wc/v3/products"
        )

        # WooCommerce ignores a category given by name when the term does not exist
        # yet, and the product then lands in "Uncategorized" (10 completeness
        # points). Resolve or create the term and reference it by id.
        categories = payload.get("categories")
        if isinstance(categories, list) and categories:
            first = categories[0]
            name = str(first.get("name", "")).strip() if isinstance(first, dict) else ""
            if name and "id" not in first:
                term_id = _ensure_wc_category(
                    name, auth=auth, headers=headers, budget=budget,
                )
                if term_id:
                    payload["categories"] = [{"id": term_id}]
                else:
                    payload.pop("categories", None)

        logger.info(
            "Publishing to WooCommerce: %s %s sku=%s regular_price=%s",
            "PUT" if wc_id else "POST",
            url,
            product.sku,
            payload.get("regular_price"),
        )

        try:
            response = _wc_call(
                "PUT" if wc_id else "POST",
                url,
                auth=auth,
                headers=headers,
                json_body=payload,
                budget=budget,
            )
        except requests.exceptions.RequestException as exc:
            attempts = int(getattr(exc, "attempts", 0)) or _WC_MAX_ATTEMPTS
            wc_status, wc_body = _wc_error_detail(exc)
            logger.error(
                "WooCommerce push failed after %d attempt(s) sku=%s action=%s wc_status=%s: %s",
                attempts, product.sku, action, wc_status, exc,
            )
            raise HTTPException(
                status_code=502,
                detail={
                    "gate": gate["status"],
                    "forced": bool(force),
                    "action": action,
                    "sku": product.sku,
                    "message": "推送到 WooCommerce 失败",
                    "attempts": attempts,
                    "woocommerce_status": wc_status,
                    "woocommerce_error": wc_body,
                    "error": str(exc),
                    "submitted_payload": payload,
                },
            ) from exc

        wc_result = response.json()
        new_wc_id = wc_result.get("id") or wc_id

        # Persist the id whenever the local row does not have it - including the
        # adopted case, where WooCommerce already held the product. Without this
        # every future push repeats the SKU lookup, and a row that is later deleted
        # from WooCommerce would be re-created instead of updated.
        if not wc_id_was_local and new_wc_id:
            meta["woocommerce_id"] = new_wc_id
            meta["woocommerce_slug"] = (
                wc_result.get("slug", "") or meta.get("woocommerce_slug", "")
            )
            meta["listing_published_by"] = "listing_publish_gate"
            meta["listing_published_price"] = payload.get("regular_price")
            meta["listing_published_at"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            # This model's meta column is a plain JSON column with no MutableDict,
            # and plain reassignment does not mark it dirty (flush emits no UPDATE
            # at all), so the id would be silently lost on every push. flag_modified
            # is the supported way to force a JSON column into the statement.
            product.meta = meta
            flag_modified(product, "meta")
            wc_id = new_wc_id
            await session.commit()
            logger.info(
                "Linked WooCommerce product id=%s to sku=%s via %s",
                new_wc_id,
                product.sku,
                action,
            )

        permalink = wc_result.get("permalink", "")
        verification: dict[str, Any] = {}
        try:
            verification = _wc_call(
                "GET",
                f"{base}/wp-json/wc/v3/products/{wc_id}",
                auth=auth,
                headers=headers,
                budget=budget,
            ).json()
            permalink = verification.get("permalink") or permalink
        except requests.exceptions.RequestException as exc:
            logger.warning("Post-push verification failed for wc_id=%s: %s", wc_id, exc)

        return {
            "success": True,
            "action": action,
            "gate": gate["status"],
            "gate_reasons": gate["reasons"],
            "forced": bool(force),
            "product_id": str(product.id),
            "sku": product.sku,
            "name": payload.get("name", ""),
            "woocommerce_id": wc_id,
            "woocommerce_slug": verification.get("slug") or meta.get("woocommerce_slug", ""),
            "woocommerce_url": permalink,
            "regular_price": payload.get("regular_price"),
            "sale_price": payload.get("sale_price"),
            "verified": bool(verification),
        }
    finally:
        await session.close()


class BatchPushRequest(BaseModel):
    """Body for the batch publish endpoint.

    ``force`` is applied to every item, so a batch run never silently mixes
    forceable and non-forceable items - the operator makes one explicit choice.
    """

    product_ids: list[str] = Field(default_factory=list)
    force: bool = False


# Hard cap: each item can spend up to _PUSH_BUDGET_SECONDS on WooCommerce calls
# and the batch runs them sequentially (Cloudflare in front of the store makes
# parallel pushes unreliable), so an unbounded list would hang the client.
_BATCH_PUSH_MAX = 25


@router.post(
    "/push-woocommerce",
    summary="批量推送商品到 WooCommerce（V3.0 闸门，逐个串行）",
)
async def push_products_to_woocommerce_gated(
    req: BatchPushRequest,
) -> dict[str, Any]:
    """Push several products through the same gated path as the single endpoint.

    The frontend's batch button (Products page) and the ``pushProductsToWooCommerce``
    API client both post to this route with ``{product_ids}`` and expect a
    ``{success, failed}`` summary. Neither worked before: no route existed at
    ``POST /products/push-woocommerce``, so every batch sync answered 404 while
    the single-product button - which calls ``/{product_id}/push-woocommerce`` -
    did work. That is why the loop looked half-wired.

    Each item is delegated to ``push_product_to_woocommerce_gated``, so the gate,
    SKU idempotency recovery, retry budget, category resolution, meta write-back
    and post-push verification are all shared rather than duplicated here. Its
    HTTPException is caught and recorded as that item's failure, which keeps the
    remaining items running instead of aborting the batch on the first block.
    """
    ids = [pid.strip() for pid in req.product_ids if str(pid).strip()]
    if not ids:
        return {
            "success": 0,
            "failed": 0,
            "total": 0,
            "results": [],
            "message": "product_ids 为空，未推送任何商品",
        }
    if len(ids) > _BATCH_PUSH_MAX:
        raise HTTPException(
            status_code=422,
            detail=(
                f"一次最多推送 {_BATCH_PUSH_MAX} 个商品，本次 {len(ids)} 个；"
                f"请分批提交（每个商品最多占用 {_PUSH_BUDGET_SECONDS:.0f}s 的"
                f" WooCommerce 调用预算，批量串行执行）"
            ),
        )

    results: list[dict[str, Any]] = []
    for product_id in ids:
        try:
            pushed = await push_product_to_woocommerce_gated(
                product_id, force=req.force
            )
            results.append({
                "product_id": product_id,
                "sku": pushed.get("sku"),
                "status": "pushed",
                "action": pushed.get("action"),
                "gate": pushed.get("gate"),
                "woocommerce_id": pushed.get("woocommerce_id"),
                "woocommerce_url": pushed.get("woocommerce_url"),
            })
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            gate = detail.get("status") if isinstance(detail, dict) else None
            # blocked/needs_review are operator decisions, not transport errors;
            # report them as "skipped" so the summary distinguishes "the store
            # rejected it" from "the operator has to look at it".
            status = (
                "blocked" if gate == "blocked"
                else "needs_review" if gate == "needs_review"
                else "error"
            )
            results.append({
                "product_id": product_id,
                "sku": detail.get("sku") if isinstance(detail, dict) else None,
                "status": status,
                "http_status": exc.status_code,
                "gate": gate,
                "reasons": detail.get("reasons") if isinstance(detail, dict) else None,
                "message": detail.get("message") if isinstance(detail, dict) else str(exc.detail),
            })

    pushed = sum(1 for r in results if r["status"] == "pushed")
    logger.info(
        "Batch WooCommerce push: %d/%d pushed, %d blocked, %d needs_review, %d error",
        pushed, len(results),
        sum(1 for r in results if r["status"] == "blocked"),
        sum(1 for r in results if r["status"] == "needs_review"),
        sum(1 for r in results if r["status"] == "error"),
    )
    return {
        "success": pushed,
        "failed": len(results) - pushed,
        "total": len(results),
        "blocked": sum(1 for r in results if r["status"] == "blocked"),
        "needs_review": sum(1 for r in results if r["status"] == "needs_review"),
        "results": results,
    }
