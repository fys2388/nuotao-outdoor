"""Normalize AI-supplied V3.0 assessment into deterministic veto/score signals.

Pure and side-effect free. The Product Analyst may return a
``nuotao_assessment`` block (schema in app.schemas.product_analyst) that closes
the AI-dependent veto rules V1/V2/V3/V5 and supplies Brand Fit (which has no
structured source). This module turns that block — which originates from an LLM
and must therefore be treated as untrusted — into a narrow, validated shape:

* verdicts are restricted to pass/fail/uncertain; anything malformed becomes
  ``uncertain`` (kept pending, never silently passed);
* Brand Fit is clamped to 0-10 or dropped;
* only the AI-owned rules V1/V2/V3/V5 are accepted.

No exception is raised for malformed input: the worst case is an empty signal
set, which leaves every AI rule exactly where P1 left it (pending).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.product_analyst import AI_VETO_RULES

PASS = "pass"
FAIL = "fail"
UNCERTAIN = "uncertain"
_VALID_VERDICTS = (PASS, FAIL, UNCERTAIN)
_TENTH = Decimal("0.1")


@dataclass(frozen=True)
class AiVerdict:
    verdict: str
    reason: str = ""


@dataclass(frozen=True)
class NormalizedAiSignals:
    veto_signals: dict[str, AiVerdict] = field(default_factory=dict)
    brand_fit: Decimal | None = None
    why_we_recommend: tuple[str, ...] = ()

    def verdict_of(self, rule_id: str) -> AiVerdict | None:
        return self.veto_signals.get(rule_id)

    @property
    def has_any(self) -> bool:
        return bool(self.veto_signals) or self.brand_fit is not None


_EMPTY = NormalizedAiSignals()


def _normalize_verdict(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return value if value in _VALID_VERDICTS else UNCERTAIN


def _normalize_brand_fit(raw: Any) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite():
        return None
    if value < 0:
        value = Decimal("0")
    elif value > 10:
        value = Decimal("10")
    return value.quantize(_TENTH)


def normalize_ai_assessment(raw: Any) -> NormalizedAiSignals:
    """Convert an untrusted ``nuotao_assessment`` dict to validated signals."""
    if not isinstance(raw, dict):
        return _EMPTY

    signals: dict[str, AiVerdict] = {}
    raw_signals = raw.get("veto_signals")
    if isinstance(raw_signals, dict):
        for rule_id in AI_VETO_RULES:
            item = raw_signals.get(rule_id)
            if item is None:
                continue
            if isinstance(item, dict):
                verdict = _normalize_verdict(item.get("verdict"))
                reason = str(item.get("reason") or "")[:500]
            else:
                verdict = _normalize_verdict(item)
                reason = ""
            signals[rule_id] = AiVerdict(verdict, reason)

    brand_fit = _normalize_brand_fit(raw.get("brand_fit"))

    raw_why = raw.get("why_we_recommend")
    if isinstance(raw_why, (list, tuple)):
        why = tuple(str(item)[:300] for item in raw_why if item)[:5]
    else:
        why = ()

    return NormalizedAiSignals(
        veto_signals=signals,
        brand_fit=brand_fit,
        why_we_recommend=why,
    )
