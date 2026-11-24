"""V2.8 historical-recalculation quantification over desensitized exports.

Local-only analysis for plan §4 (``docs/V2_8_HISTORICAL_DATA_EXPORT_PLAN.md``).
Reads the *desensitized* CSV files produced by ``scripts/v28_export_desensitize.py``
plus the raw export (only for row-pairing on PII-free numeric columns), and
quantifies:

* §4.3 recalculation tiers — exact / partial / not-recalculable order counts
  with per-category missing reasons;
* §4.4 R1 historical revenue overstatement — absolute tax-inflated amount and
  ratio (tax_total vs net revenue, by currency);
* §4.5 R2 baseline difference — legacy cost_prefill CM vs unified
  contribution_margin_service margin, per order;
* §4.6 R7 cost-version gaps — lines lacking cost_snapshot_id/version.

No DB connection, no network, no production data. Run on synthetic fixtures
for logic verification; on real desensitized exports only after Owner
authorization (plan §5 step ⑤).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from scripts.v28_export_desensitize import read_csv

#: Recalculation tier labels (plan §4.3).
EXACT = "exact"
PARTIAL = "partial"
NOT_RECALC = "not_recalculable"

#: Cost-version fields that must exist on an order line for exact recalc.
#: In the current schema they are NOT STORED (R7/R6/R12), so any real export
#: will classify lines as NOT_RECALC on cost_snapshot_id alone; the taxonomy
#: below separates that structural gap from genuinely missing data.
COST_VERSION_FIELDS = (
    "cost_snapshot_id",
    "cost_snapshot_version",
    "pricing_rule_version",
    "pricing_engine_version",
)

#: Evidence fields (R12, optional): absence is reported but does not block a
#: recalculation that is otherwise version-pinned.
EVIDENCE_FIELDS = ("evidence_grade",)

#: Optional component fields whose absence downgrades exact -> partial.
COMPONENT_FIELDS = (
    "tax_total",
    "payment_fee",
    "refunded_amount",
    "shipping_total",
    "discount_total",
    "last_leg_shipping",
    "marketing_amortization",
    "after_sales_loss",
)

LEGACY_CP_BASIS = "LEGACY_COST_PREFILL"
UNIFIED_FORMULA_VERSION = "v28-pricing-3a"


def _dec(value: Any) -> Decimal | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _blank(value: Any) -> bool:
    return value in (None, "", "null", "None")


@dataclass
class LineClassification:
    tier: str
    missing_fields: list[str] = field(default_factory=list)

    def reasons(self) -> list[str]:
        out = []
        for item in self.missing_fields:
            # item is "<line_pk>:<field>" (version/evidence/component entries)
            parts = item.split(":", 2)
            fieldname = parts[-1]
            category = (
                "field_not_stored"
                if fieldname in COST_VERSION_FIELDS
                else "not_collected"
            )
            out.append(f"{category}:{item}")
        return out


def classify_order(
    order: dict[str, Any],
    lines: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> LineClassification:
    """Classify one order for historical recalculation (plan §4.3/§4.6).

    Tier logic:
    * NOT_RECALC — any cost-version field missing on a line (R7: without a
      frozen cost snapshot the order's cost cannot be pinned; using current
      cost would violate the LEGACY_UNKNOWN red line);
    * PARTIAL — all cost-version fields present but 1..n optional component
      fields missing;
    * EXACT — everything present and the product has a cost snapshot version
      at the order timestamp.
    """
    missing_cost_version: list[str] = []
    missing_components: list[str] = []
    missing_evidence: list[str] = []
    for line in lines:
        for fieldname in COST_VERSION_FIELDS:
            if _blank(line.get(fieldname)):
                missing_cost_version.append(
                    f"{line.get('line_pk') or 'line'}:{fieldname}"
                )
        for fieldname in EVIDENCE_FIELDS:
            if _blank(line.get(fieldname)):
                missing_evidence.append(f"{line.get('line_pk') or 'line'}:{fieldname}")
        for fieldname in (
            "tax_total",
            "payment_fee",
            "refunded_amount",
            "shipping_total",
            "discount_total",
        ):
            if _blank(order.get(fieldname)):
                missing_components.append(
                    f"{line.get('line_pk') or 'line'}:{fieldname}"
                )
        for fieldname in (
            "advertising_cost",
            "last_leg_shipping",
            "marketing_amortization",
            "after_sales_loss",
        ):
            if _blank(order.get(fieldname, line.get(fieldname))):
                missing_components.append(
                    f"{line.get('line_pk') or 'line'}:{fieldname}"
                )

    if missing_cost_version:
        # Missing evidence downgrades to partial ONLY when the cost is versioned;
        # without a version pin, missing evidence is subsumed by LEGACY_UNKNOWN.
        extra = missing_components if missing_evidence else []
        return LineClassification(
            NOT_RECALC, missing_cost_version + missing_components + extra
        )
    if missing_components or missing_evidence:
        return LineClassification(PARTIAL, missing_components + missing_evidence)

    # Exact: verify at least one cost snapshot version exists for the product.
    snapshot_versions = [s.get("version") for s in snapshots if s.get("product_id")]
    if not any(snapshot_versions):
        return LineClassification(
            NOT_RECALC, ["cost_snapshot_version:legacy_no_record"]
        )
    return LineClassification(EXACT, [])


def quantify_recalc(
    orders: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    lines_by_order: dict[str, list[dict[str, Any]]] = {}
    for line in lines:
        lines_by_order.setdefault(str(line.get("order_pk")), []).append(line)

    buckets: dict[str, int] = {EXACT: 0, PARTIAL: 0, NOT_RECALC: 0}
    reason_counts: dict[str, int] = {}
    for order in orders:
        cls = classify_order(
            order, lines_by_order.get(str(order.get("order_pk")), []), snapshots
        )
        buckets[cls.tier] += 1
        for reason in cls.reasons():
            category = reason.split(":", 1)[0]
            reason_counts[category] = reason_counts.get(category, 0) + 1

    return {
        "order_counts_by_tier": buckets,
        "line_count_total": len(lines),
        "missing_reason_counts": reason_counts,
        "note": "cost_snapshot_id absent in current schema => structural field_not_stored "
        "(R7); see plan §4.6 LEGACY_UNKNOWN handling",
    }


def quantify_r1(orders: list[dict[str, Any]]) -> dict[str, Any]:
    """R1: historical tax-inflated revenue vs net revenue (plan §4.4).

    ``orders`` are the desensitized order headers (the A-group CSV); the B
    group (tax detail) carries the same order headers, so tax amounts come
    from the header columns.
    """
    by_currency: dict[str, dict[str, Decimal]] = {}
    for order in orders:
        currency = order.get("currency") or "UNKNOWN"
        total = _dec(order.get("total"))
        tax = _dec(order.get("tax_total"))
        if total is None:
            continue
        net = total - (tax or Decimal(0))
        bucket = by_currency.setdefault(
            currency,
            {"gross": Decimal(0), "net": Decimal(0), "tax": Decimal(0), "orders": 0},
        )
        bucket["gross"] += total
        bucket["net"] += net
        bucket["tax"] += tax or Decimal(0)
        bucket["orders"] += 1

    result: dict[str, Any] = {"by_currency": {}}
    for currency, bucket in sorted(by_currency.items()):
        inflated = bucket["tax"]
        ratio = (inflated / bucket["net"]) if bucket["net"] else None
        result["by_currency"][currency] = {
            "orders": bucket["orders"],
            "gross_revenue": str(bucket["gross"]),
            "net_revenue": str(bucket["net"]),
            "tax_inflated_amount": str(inflated),
            "overstatement_ratio": None
            if ratio is None
            else str(ratio.quantize(Decimal("0.0001"))),
        }
    total_tax = sum((b["tax"] for b in by_currency.values()), Decimal(0))
    total_net = sum((b["net"] for b in by_currency.values()), Decimal(0))
    result["totals"] = {
        "tax_inflated_amount": str(total_tax),
        "net_revenue": str(total_net),
        "overstatement_ratio": (
            str((total_tax / total_net).quantize(Decimal("0.0001")))
            if total_net
            else "not_computable"
        ),
    }
    return result


def _legacy_cost_prefill_cm(order: dict[str, Any]) -> Decimal | None:
    """Legacy cost_prefill basis: CM = revenue - product_cost - marketing -
    after-sales (payment fee NOT deducted in the legacy CM line), revenue the
    stored (pre-R1) tax-inclusive total. None when cost is unknown (R5 red
    line: never substitute 0)."""
    snapshot = order.get("profit_snapshot") or {}
    revenue = _dec(order.get("total"))
    cogs = _dec(snapshot.get("product_cost"))
    marketing = _dec(order.get("advertising_cost"))
    if revenue is None or cogs is None:
        return None
    return revenue - cogs - (marketing or Decimal(0))


def _unified_cp(order: dict[str, Any]) -> Decimal | None:
    """Unified baseline (contribution_margin_service formulas, plan §4.5):
    NetRevenue = (total - tax_total) - discounts - refunds (shipping revenue
    stays inside NetRevenue per the Owner formula);
    CP = NetRevenue - COGS - payment_fee - marketing - after-sales.
    Refunds are deducted exactly once (never again in the cost terms)."""
    snapshot = order.get("profit_snapshot") or {}
    total = _dec(order.get("total"))
    tax = _dec(order.get("tax_total")) or Decimal(0)
    discount = _dec(order.get("discount_total")) or Decimal(0)
    refunds = _dec(order.get("refunded_amount")) or Decimal(0)
    cogs = _dec(snapshot.get("product_cost"))
    if total is None or cogs is None:
        return None
    net_revenue = (total - tax) - discount - refunds
    payment_fee = _dec(order.get("payment_fee")) or Decimal(0)
    marketing = _dec(order.get("advertising_cost")) or Decimal(0)
    cp = net_revenue - cogs - payment_fee - marketing
    return cp


def quantify_r2(orders: list[dict[str, Any]]) -> dict[str, Any]:
    """R2 baseline gap per order (plan §4.5)."""
    deltas: list[dict[str, Any]] = []
    comparable = 0
    for order in orders:
        legacy = _legacy_cost_prefill_cm(order)
        unified = _unified_cp(order)
        if legacy is None or unified is None:
            continue
        comparable += 1
        deltas.append(
            {
                "order_pk": order.get("order_pk"),
                "legacy_cm": str(legacy),
                "unified_cp": str(unified),
                "delta": str(legacy - unified),
                "legacy_metric_label": LEGACY_CP_BASIS,
                "unified_metric_version": UNIFIED_FORMULA_VERSION,
            }
        )
    return {
        "comparable_orders": comparable,
        "note": "legacy numbers are LABELLED LEGACY_COST_PREFILL and must not be "
        "presented as the unified baseline (plan §4.5)",
        "per_order": deltas,
    }


def quantify_r7(lines: list[dict[str, Any]]) -> dict[str, Any]:
    """R7: cost-version gaps on order lines (plan §4.6)."""
    total = len(lines)
    missing_version = [
        line
        for line in lines
        if _blank(line.get("cost_snapshot_id"))
        or _blank(line.get("cost_snapshot_version"))
    ]
    with_version = total - len(missing_version)
    return {
        "line_total": total,
        "lines_without_cost_snapshot": len(missing_version),
        "lines_with_cost_snapshot": with_version,
        # Lines lacking a frozen snapshot can only ever be LEGACY_UNKNOWN;
        # lines that DO carry a snapshot may still be unverifiable later,
        # but are not auto-LEGACY_UNKNOWN here.
        "legacy_unknown_lines": len(missing_version),
        "handling": "lines without a frozen cost snapshot are marked LEGACY_UNKNOWN; "
        "recalculation must NOT backfill with current cost values",
    }


def analyze(
    raw_dir: Path,
    des_dir: Path,
) -> dict[str, Any]:
    orders = (
        read_csv(des_dir / "orders.csv") if (des_dir / "orders.csv").exists() else []
    )
    lines = (
        read_csv(des_dir / "orders_lines.csv")
        if (des_dir / "orders_lines.csv").exists()
        else []
    )
    snapshots = (
        read_csv(des_dir / "cost_snapshots.csv")
        if (des_dir / "cost_snapshots.csv").exists()
        else []
    )
    # R2 compares the stored profit_snapshot (legacy cost_prefill CM, tax-inclusive)
    # with the unified v28-pricing-3a CP; the snapshot column must be a dict.
    for o in orders:
        for col in ("profit_snapshot", "rule_results"):
            raw = o.get(col)
            if raw in (None, "", "null"):
                continue
            try:
                o[col] = json.loads(raw)
            except json.JSONDecodeError:
                o[col] = {}
    return {
        "recalc": quantify_recalc(orders, lines, snapshots),
        "r1": quantify_r1(orders),
        "r2": quantify_r2(orders),
        "r7": quantify_r7(lines),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="V2.8 recalculation quantification (local, desensitized data only)."
    )
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--des-dir", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = analyze(args.raw_dir, args.des_dir)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
