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
from typing import Any
from uuid import UUID

import requests
from fastapi import APIRouter, HTTPException, Query

from app.services.listing_gate import (
    build_wc_payload,
    evaluate_gate,
    get_english_copy,
    resolve_prices,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["listing-publish"])

_REQUEST_TIMEOUT = 45


def _wc_base_url() -> str:
    from app.services.woocommerce_sync_service import WC_URL

    return str(WC_URL).rstrip("/")


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
        action = "update" if wc_id else "create"
        base = _wc_base_url()
        url = (
            f"{base}/wp-json/wc/v3/products/{wc_id}"
            if wc_id
            else f"{base}/wp-json/wc/v3/products"
        )
        auth, headers = _wc_credentials()

        logger.info(
            "Publishing to WooCommerce: %s %s sku=%s regular_price=%s",
            "PUT" if wc_id else "POST",
            url,
            product.sku,
            payload.get("regular_price"),
        )

        try:
            if wc_id:
                response = requests.put(
                    url, auth=auth, headers=headers, json=payload, timeout=_REQUEST_TIMEOUT
                )
            else:
                response = requests.post(
                    url, auth=auth, headers=headers, json=payload, timeout=_REQUEST_TIMEOUT
                )
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.error(
                "WooCommerce push failed sku=%s action=%s: %s", product.sku, action, exc
            )
            raise HTTPException(
                status_code=502,
                detail={
                    "gate": "passed" if force else gate["status"],
                    "action": action,
                    "sku": product.sku,
                    "message": "推送到 WooCommerce 失败",
                    "error": str(exc),
                    "submitted_payload": payload,
                },
            ) from exc

        wc_result = response.json()

        if not wc_id:
            new_wc_id = wc_result.get("id")
            if new_wc_id:
                meta["woocommerce_id"] = new_wc_id
                meta["woocommerce_slug"] = wc_result.get("slug", "")
                meta["listing_published_by"] = "listing_publish_gate"
                meta["listing_published_price"] = payload.get("regular_price")
                product.meta = meta
                wc_id = new_wc_id
                await session.commit()
                logger.info(
                    "Created WooCommerce product id=%s slug=%s for sku=%s",
                    new_wc_id,
                    wc_result.get("slug", ""),
                    product.sku,
                )

        permalink = wc_result.get("permalink", "")
        verification: dict[str, Any] = {}
        try:
            verify_response = requests.get(
                f"{base}/wp-json/wc/v3/products/{wc_id}",
                auth=auth,
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            verify_response.raise_for_status()
            verification = verify_response.json()
            permalink = verification.get("permalink") or permalink
        except requests.exceptions.RequestException:
            logger.warning("Post-push verification failed for wc_id=%s", wc_id)

        return {
            "success": True,
            "action": action,
            "gate": "passed" if force else "passed",
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
