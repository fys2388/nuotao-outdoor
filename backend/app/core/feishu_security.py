"""Feishu card-callback authentication boundary (P0-Critical-1).

``POST /api/v1/feishu/card-callback`` used to read the approving operator from
an unverified request body and to auto-execute an Agent suggestion from any
caller that could reach the backend IP. There was no HMAC, no timestamp
freshness check and no permission check.

Feishu signs card action callbacks over the whole request:

    signature = sha256_hex(timestamp + nonce + encrypt_key + raw_body)

carried in ``X-Lark-Request-Signature``, together with
``X-Lark-Request-Timestamp`` and ``X-Lark-Request-Nonce``. The encrypt key is
the app's ``encrypt_key`` from the Feishu developer console.

Hard boundaries (never relaxed):

- The body is authentic ONLY when the signature verifies. ``operator`` fields
  are trusted solely as a consequence of a valid signature - never on their
  own.
- The timestamp must be within ``feishu_clock_skew_seconds`` of now, which
  bounds the replay window (the nonce is additionally bound to the timestamp
  by the hash above).
- Comparison is constant-time. A missing header, a missing key or a bad
  signature all DENY. There is no unsigned fallback.
- This is an M2M boundary. Human JWT authentication is NOT applied here;
  conversely a webhook must never be handed a human-JWT dependency.

Audit events record only non-sensitive fields (result, reason) - never the
signature, the encrypt key or the raw body.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)

HEADER_TIMESTAMP = "X-Lark-Request-Timestamp"
HEADER_NONCE = "X-Lark-Request-Nonce"
HEADER_SIGNATURE = "X-Lark-Request-Signature"

MAX_NONCE_LENGTH = 256


class FeishuSignatureError(Exception):
    """Signature missing, malformed or mismatched (mapped to 401)."""


class FeishuReplayError(Exception):
    """Timestamp outside the freshness window (mapped to 403)."""


class FeishuNotConfiguredError(Exception):
    """Signature verification is required but no encrypt key is set (503)."""


class FeishuOperatorError(Exception):
    """A verified callback carries no usable operator identity (403)."""


@dataclass(frozen=True)
class FeishuCallbackAuth:
    """Result of a verified Feishu callback.

    ``operator_open_id`` is the stable Feishu user id (``operator.open_id``).
    It is trusted ONLY because the signature verified; it must never be read
    from an unverified body. ``operator_name`` is display metadata only.
    """

    signature_verified: bool = True
    timestamp: str = ""
    nonce: str = ""
    operator_open_id: str | None = None
    operator_name: str | None = None


def compute_signature(
    *, timestamp: str, nonce: str, encrypt_key: str, body: bytes
) -> str:
    """Return the expected Feishu callback signature (hex sha256)."""
    material = timestamp.encode("utf-8") + nonce.encode("utf-8") + encrypt_key.encode("utf-8")
    return hashlib.sha256(material + body).hexdigest()


def _timestamp_is_fresh(timestamp: str, *, max_skew_seconds: int) -> bool:
    """Return True when the callback timestamp is inside the replay window."""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    now = int(datetime.now(timezone.utc).timestamp())
    return abs(now - ts) <= max_skew_seconds


async def verify_callback(
    request: Request,
    *,
    settings: type | None = None,
) -> bytes:
    """Verify the Feishu callback signature and return the RAW body bytes.

    Raises :class:`HTTPException` with the mapped status code:

    - 503 signature verification is on but no encrypt key is configured
    - 401 signature header missing / mismatched
    - 403 timestamp outside the freshness window

    Callers must only parse the returned bytes - parsing the request body
    directly would let an unsigned body through.
    """
    cfg = (settings or get_settings)()
    if not cfg.feishu_verify_signature:
        # Explicitly opted out (local 演练 only). Fail closed by default is the
        # point of this module, so never silently accept unsigned callbacks.
        logger.warning(
            "feishu signature verification disabled - refusing unsigned callback",
            exc_info=False,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="feishu signature verification is disabled",
        )
    if not cfg.feishu_encrypt_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="feishu encrypt key is not configured",
        )

    body = await request.body()
    timestamp = request.headers.get(HEADER_TIMESTAMP, "") or ""
    nonce = request.headers.get(HEADER_NONCE, "") or ""
    provided = request.headers.get(HEADER_SIGNATURE)

    if not provided or not timestamp or not nonce:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing feishu signature headers",
        )
    if len(nonce) > MAX_NONCE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="malformed feishu signature headers",
        )

    if not _timestamp_is_fresh(timestamp, max_skew_seconds=cfg.feishu_clock_skew_seconds):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="feishu callback timestamp is outside the allowed window",
        )

    expected = compute_signature(
        timestamp=timestamp, nonce=nonce, encrypt_key=cfg.feishu_encrypt_key, body=body
    )
    if not hmac.compare_digest(provided.strip().lower(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid feishu callback signature",
        )
    return body


def extract_operator(body: bytes) -> FeishuCallbackAuth:
    """Extract the Feishu operator identity from a signature-verified body.

    Prefers the stable ``operator.open_id``; falls back to ``operator.user_id``
    for older tenants. ``operator.name`` is display-only and never used as the
    identity key. Raises :class:`HTTPException` 403 when no operator is present
    - a verified-but-anonymous callback cannot approve anything.
    """
    import json

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid callback body"
        ) from exc

    event = payload.get("event")
    if not isinstance(event, dict):
        event = payload
    operator = event.get("operator") if isinstance(event, dict) else None
    if not isinstance(operator, dict):
        operator = {}

    open_id = operator.get("open_id") or operator.get("user_id") or operator.get("union_id")
    open_id = str(open_id).strip() if open_id else None
    if not open_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="callback carries no operator identity",
        )

    name = operator.get("name")
    name = str(name).strip() if isinstance(name, str) else None

    return FeishuCallbackAuth(
        signature_verified=True,
        operator_open_id=open_id,
        operator_name=name,
    )
