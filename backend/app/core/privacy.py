"""PII guards for free-form metadata and evidence payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence


class PIIPayloadError(ValueError):
    """Raised when a payload contains fields reserved for direct identifiers."""


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SUSPICIOUS_KEY_SEGMENTS = {
    "address",
    "contact",
    "email",
    "idcard",
    "mobile",
    "name",
    "passport",
    "phone",
    "ssn",
    "tax",
    "taxid",
}


def _key_segments(key: object) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
    return {segment for segment in normalized.split("_") if segment}


def _contains_pii_value(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_EMAIL_PATTERN.fullmatch(value.strip()))


def assert_no_pii(payload: object | None, *, field_name: str) -> None:
    """Reject direct identifiers recursively.

    Free-form metadata must never become a shadow storage location for raw
    customer identifiers. The guard is intentionally independent from the
    persistence models so API schemas and service calls enforce the same rule.
    """
    if payload is None:
        return
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if _key_segments(key) & _SUSPICIOUS_KEY_SEGMENTS:
                raise PIIPayloadError(
                    f"{field_name} contains a PII field key: {key}"
                )
            assert_no_pii(value, field_name=field_name)
        return
    if isinstance(payload, Sequence) and not isinstance(
        payload, (str, bytes, bytearray)
    ):
        for item in payload:
            assert_no_pii(item, field_name=field_name)
        return
    if _contains_pii_value(payload):
        raise PIIPayloadError(
            f"{field_name} must not contain direct identifiers"
        )
