"""WooCommerce webhook signature verification (P0 Commerce Integrity).

WooCommerce signs every webhook delivery with HMAC-SHA256 over the **raw**
request body and sends the **base64-encoded raw digest** in
``X-WC-Webhook-Signature``:

    signature = base64( HMAC-SHA256(secret, raw_body_bytes) )

There are two independent M2M signature boundaries in this codebase and they
MUST NOT be mixed up:

- ``app.core.woocommerce_security`` (this module) - WooCommerce:
  single HMAC-SHA256 over the raw body, base64-encoded digest.
- ``app.core.feishu_security`` - Feishu card callbacks:
  ``sha256(timestamp + nonce + encrypt_key + body)`` as **hex**, plus three
  ``X-Lark-Request-*`` headers and a timestamp freshness window.

Feishu is hex and carries a timestamp; WooCommerce is base64 and carries no
timestamp at all. Reusing one verifier for the other protocol silently
rejects every legitimate delivery (a hex digest is never a valid base64 digest
of the same HMAC output and vice versa).

Hard boundaries (never relaxed):

- The signature is computed over the **raw body bytes** exactly as received.
  Re-serializing the parsed JSON first is a bug: key ordering, whitespace and
  Unicode escaping all change the bytes and the signature stops matching.
- The digest is **base64** of the raw HMAC output. ``hexdigest()`` is NOT a
  valid WooCommerce signature - accepting it would be a wrong-format tolerance.
- Comparison is constant-time (``hmac.compare_digest``).
- A missing, empty or whitespace-only secret FAILS CLOSED (503). Without a
  secret there is nothing to verify against, and "verify with an empty secret"
  would let any caller compute a valid signature.
- A missing or mismatched signature DENIES (401). There is no unsigned
  fallback and no unsigned debug mode on this endpoint.
- Neither the secret nor the signature is ever logged. WooCommerce does not
  provide a timestamp or nonce in this protocol, so no replay window is
  invented here; replay protection is provided downstream by the idempotency
  guard on ``(workspace_id, external_order_id)`` in
  ``app.services.order_service.ingest_order``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: Header WooCommerce sends the signature in (lookup is case-insensitive).
HEADER_SIGNATURE = "X-WC-Webhook-Signature"


class WooCommerceSignatureError(Exception):
    """Signature missing or mismatched (mapped to 401)."""


class WooCommerceNotConfiguredError(Exception):
    """No webhook secret configured - fail closed (mapped to 503)."""


def compute_signature(*, secret: str, body: bytes) -> str:
    """Return the expected WooCommerce webhook signature.

    HMAC-SHA256 over the raw body bytes, base64-encoded raw digest. This is
    the WooCommerce contract; ``hexdigest()`` is deliberately NOT returned.
    """
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _require_secret(secret: str | None) -> str:
    """Return a usable secret or fail closed."""
    if not secret or not secret.strip():
        raise WooCommerceNotConfiguredError(
            "woocommerce webhook secret is not configured"
        )
    return secret


def verify(body: bytes, signature: str | None, secret: str | None) -> None:
    """Verify one delivery; raise :class:`WooCommerceSignatureError` on failure.

    Pure and synchronous so it can be unit-tested without an HTTP request.
    Raises :class:`WooCommerceNotConfiguredError` when the secret is missing.
    """
    _require_secret(secret)
    if not signature or not signature.strip():
        raise WooCommerceSignatureError("missing webhook signature")
    expected = compute_signature(secret=secret, body=body)
    if not hmac.compare_digest(signature.strip(), expected):
        raise WooCommerceSignatureError("invalid webhook signature")


async def verify_webhook_signature(
    request: Request,
    *,
    body: bytes | None = None,
    settings: object | None = None,
) -> bytes:
    """Verify the WooCommerce signature of one delivery.

    Raises :class:`HTTPException` with the mapped status code:

    - 503 no webhook secret configured (fail closed)
    - 401 signature header missing
    - 401 signature mismatched

    Returns the **raw body bytes** on success. Pass ``body`` to verify the
    exact bytes already read; otherwise the body is read from the request
    (Starlette caches it, so this is not a second read).
    """
    cfg = settings if settings is not None else get_settings()
    secret = getattr(cfg, "woocommerce_webhook_secret", None)

    raw = body if body is not None else await request.body()
    try:
        verify(
            body=raw,
            signature=request.headers.get(HEADER_SIGNATURE),
            secret=secret,
        )
    except WooCommerceNotConfiguredError as exc:
        logger.warning("webhook rejected: webhook secret not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except WooCommerceSignatureError as exc:
        logger.warning("webhook rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid webhook signature",
        ) from exc
    return raw
