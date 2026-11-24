"""Tests for ``scripts/v28_recalc_quantify.py`` (plan §4.3-§4.6).

Runs on the desensitized synthetic fixture only — no production data, no DB.
Verifies the quantification *algorithms* (tier logic, R1/R2/R7 aggregation);
the production numbers are produced at plan §5 step ⑤ after Owner approval.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "tests" / "fixtures" / "v28_export_sample" / "raw"
SALT = REPO / "tests" / "fixtures" / "v28_export_sample" / "test-salt.txt"
OUT = REPO / "tests" / "fixtures" / "v28_export_sample" / "out"

sys.path.insert(0, str(REPO))
import subprocess  # noqa: E402

import scripts.v28_recalc_quantify as rq  # noqa: E402
from scripts.v28_export_desensitize import read_csv  # noqa: E402


def _prepare_des() -> None:
    SALT.write_text("v28-test-only-salt-do-not-use-in-prod", encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "v28_export_desensitize.py"),
            "--raw-dir",
            str(RAW),
            "--out-dir",
            str(OUT),
            "--salt-file",
            str(SALT),
            "--workspace-id",
            "ws-test-1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _load() -> tuple[list[dict], list[dict], list[dict]]:
    orders = _load_json_orders(read_csv(OUT / "orders.csv"))
    lines = read_csv(OUT / "orders_lines.csv")
    snapshots = read_csv(OUT / "cost_snapshots.csv")
    return orders, lines, snapshots


def _load_json_orders(rows: list[dict]) -> list[dict]:
    """Parse JSON columns back into objects (desensitization re-serializes them)."""
    for o in rows:
        for col in ("profit_snapshot", "rule_results"):
            raw = o.get(col)
            if raw in (None, "", "null"):
                continue
            try:
                o[col] = json.loads(raw)
            except json.JSONDecodeError:
                o[col] = {}
    return rows


def test_recalc_tiers_and_missing_reasons():
    _prepare_des()
    orders, lines, snapshots = _load()
    report = rq.quantify_recalc(orders, lines, snapshots)
    tiers = report["order_counts_by_tier"]
    # o-003 lines: l-003 pins cost_snapshot s-003/v2 (evidence missing only
    # downgrades when versioned -> partial candidate), but l-004 lacks
    # cost_snapshot_id => order-level NOT_RECALC. o-001/o-002 lines lack
    # cost_snapshot_id (schema stores none) => NOT_RECALC (LEGACY_UNKNOWN).
    assert tiers["not_recalculable"] == 3, tiers
    assert tiers["partial"] == 0
    assert tiers["exact"] == 0
    reasons = report["missing_reason_counts"]
    assert reasons.get("not_collected", 0) >= 1


def test_recalc_tier_unit_logic():
    """Direct tier logic: a fully versioned order with a missing component is
    PARTIAL; a versioned + component-complete order is EXACT."""
    order = {
        "order_pk": "o-x",
        "tax_total": "8.00",
        "payment_fee": "3.78",
        "refunded_amount": "0.00",
        "shipping_total": "5.00",
        "discount_total": "0.00",
        "advertising_cost": "1.00",
        "last_leg_shipping": "10.00",
        "marketing_amortization": "8.38",
        "after_sales_loss": "1.68",
    }
    lines = [
        {
            "line_pk": "l-x",
            "cost_snapshot_id": "s-1",
            "cost_snapshot_version": "v2",
            "pricing_rule_version": "v1",
            "pricing_engine_version": "v2",
            "evidence_grade": "B",
        }
    ]
    snapshots = [{"product_id": "P-1", "version": "v2"}]
    assert rq.classify_order(order, lines, snapshots).tier == "exact"
    # missing one optional component => partial
    order2 = dict(order, advertising_cost=None)
    assert rq.classify_order(order2, lines, snapshots).tier == "partial"
    # missing cost version => not recalculable. In the current schema the
    # version fields are structurally absent (exported as blank cells), so the
    # blank is tagged not_collected; the structural field_not_stored reason is
    # attached by the exporter at ingest time.
    lines2 = [dict(lines[0], cost_snapshot_id="")]
    cls = rq.classify_order(order, lines2, snapshots)
    assert cls.tier == "not_recalculable"
    assert any(
        r.startswith("field_not_stored:") and r.endswith("cost_snapshot_id")
        for r in cls.reasons()
    ), cls.reasons()


def test_r1_overstatement_amount_and_ratio():
    _prepare_des()
    orders, _, _ = _load()
    report = rq.quantify_r1(orders)
    usd = report["by_currency"]["USD"]
    # gross = 103.00 + 49.50 + 132.00 = 284.50; tax = 8.00 + 4.50 + 0 = 12.50
    assert usd["gross_revenue"] == "284.50"
    assert usd["tax_inflated_amount"] == "12.50"
    assert usd["net_revenue"] == "272.00"
    # 12.50 / 272.00 = 0.045955... -> 0.0460 (HALF_UP at 4 decimals)
    assert Decimal(usd["overstatement_ratio"]) == Decimal("0.0460")
    assert report["totals"]["tax_inflated_amount"] == "12.50"


def test_r2_baseline_difference_direction():
    _prepare_des()
    orders, _, _ = _load()
    report = rq.quantify_r2(orders)
    assert report["comparable_orders"] >= 1
    for row in report["per_order"]:
        # Legacy cost_prefill CM keeps marketing in CM and uses tax-inclusive
        # revenue, so it must exceed the unified CP (which nets tax, deducts
        # payment fee and refunds once).
        assert Decimal(row["delta"]) >= 0, row
        assert row["legacy_metric_label"] == "LEGACY_COST_PREFILL"
        assert row["unified_metric_version"] == "v28-pricing-3a"


def test_r7_version_gap_quantification():
    _prepare_des()
    _, lines, _ = _load()
    report = rq.quantify_r7(lines)
    assert report["line_total"] == 4
    # l-003 carries snapshot-701/v2; the other three lines lack version fields.
    assert report["lines_without_cost_snapshot"] == 3
    assert report["lines_with_cost_snapshot"] == 1
    assert report["legacy_unknown_lines"] == 3
    assert "LEGACY_UNKNOWN" in report["handling"]


def test_full_analysis_endpoint():
    _prepare_des()
    report = rq.analyze(RAW, OUT)
    for key, section in report.items():
        assert isinstance(section, dict), key
    assert set(report) == {"recalc", "r1", "r2", "r7"}
    json.dumps(report)  # must be serializable for the Owner-facing report
