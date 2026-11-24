"""Tests for ``scripts/v28_export_desensitize.py`` (plan §3/§4.7, T4-T8 subset).

Runs the desensitization script end-to-end on the **synthetic** fixture
``tests/fixtures/v28_export_sample/raw/`` — no production data, no DB, no
network. The synthetic salt lives in the fixture (test-only; the real salt
is Owner-delivered and never committed, plan §1.3/§6).
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "tests" / "fixtures" / "v28_export_sample" / "raw"
SALT = REPO / "tests" / "fixtures" / "v28_export_sample" / "test-salt.txt"
OUT = REPO / "tests" / "fixtures" / "v28_export_sample" / "out"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CARD_RE = re.compile(r"\b(?:\d[ \-]?){12,18}\d\b")
TOKEN_KEY_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|cookie|cvv|client[_-]?secret)\b\s*[:=]\s*[^\s,;]+"
)

sys.path.insert(0, str(REPO))
from scripts.v28_export_desensitize import pseudo_id  # noqa: E402


def _ensure_salt() -> None:
    SALT.write_text("v28-test-only-salt-do-not-use-in-prod", encoding="utf-8")


def _run_script() -> dict:
    _ensure_salt()
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
    assert result.returncode == 0, f"script failed: {result.stdout}\n{result.stderr}"
    report = json.loads(
        (OUT / "desensitization_report.json").read_text(encoding="utf-8")
    )
    return report


def _read(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_salt_missing_fails_closed():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "v28_export_desensitize.py"),
            "--raw-dir",
            str(RAW),
            "--out-dir",
            str(OUT),
            "--salt-file",
            str(REPO / "does-not-exist.txt"),
            "--workspace-id",
            "ws-test-1",
        ],
        capture_output=True,
        text=True,
    )
    # A missing salt file must never proceed.
    assert result.returncode != 0, "missing salt must abort the run"


def test_all_self_checks_pass():
    report = _run_script()
    regression = report["regression"]
    for name, check in regression["checks"].items():
        assert check["ok"], f"{name} failed: {check['detail']}"


def test_no_pii_residue_in_outputs():
    _run_script()
    for fname in (p.name for p in OUT.iterdir() if p.name.endswith(".csv")):
        text = (OUT / fname).read_text(encoding="utf-8")
        assert not EMAIL_RE.search(text), f"email residue in {fname}"
        assert not CARD_RE.search(text), f"card residue in {fname}"
        assert not TOKEN_KEY_RE.search(text), f"token/secret residue in {fname}"


def test_pii_keys_dropped_and_pseudo_ids_applied():
    _run_script()
    orders = _read("orders.csv")
    # PII columns are gone from the header.
    header_keys = set(orders[0].keys())
    for pii in (
        "billing_email",
        "billing_first_name",
        "billing_last_name",
        "card_number",
        "email",
        "phone",
        "display_name",
    ):
        assert pii not in header_keys, f"PII column {pii} survived"
    # Pseudo-IDs: deterministic 32-char hex, stable across the 7 files.
    ext_ids = {o["external_order_id"] for o in orders}
    assert len(ext_ids) == 3
    for pseudo in ext_ids:
        assert re.fullmatch(
            r"[0-9a-f]{32}", pseudo
        ), f"not a stable hex pseudo-id: {pseudo}"
    # Same original -> same pseudo across two independent calls.
    a = pseudo_id("external_order_id", "ws-test-1", "WC-1001", "fixed")
    b = pseudo_id("external_order_id", "ws-test-1", "WC-1001", "fixed")
    assert a == b


def test_missing_values_not_zero_filled():
    _run_script()
    marketing = _read("order_marketing.csv")
    row2 = next(r for r in marketing if r["order_pk"] == "o-002")
    assert row2["advertising_cost"] in ("", "null"), "NULL must stay blank"
    assert row2["missing_reason"] == "not_collected"
    # Legit business zero in orders (o-003 tax_total=0.00) is preserved as 0.
    orders = _read("orders.csv")
    row3 = next(o for o in orders if o["order_pk"] == "o-003")
    assert row3["tax_total"] == "0.00"
    assert row3["value_is_zero"] == "true"


def test_isolated_refund_detected(tmp_path: Path):
    """T8-style: a refund pointing to an order that is not in A must be
    reported as isolated (V2 detail), not silently accepted."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [{"order_pk": "o-001"}],
        "refunds.csv": [{"order_pk": "o-999", "refund_pk": "r-404"}],
    }
    des_files = {
        "orders.csv": [{"order_pk": "o-001"}],
        "refunds.csv": [{"order_pk": "o-999", "refund_pk": "r-404"}],
    }
    rep = mod.verify(raw_files, des_files, pseudo_map={})
    v2 = rep.checks["V2_referential"]
    assert not v2["ok"]
    assert v2["detail"]["samples"] == ["r-404"]


def test_row_count_mismatch_detected(tmp_path: Path):
    """T7-style: dropping one row must fail V1."""
    import scripts.v28_export_desensitize as mod

    raw_files = {"orders.csv": [{"order_pk": "o-001"}, {"order_pk": "o-002"}]}
    des_files = {"orders.csv": [{"order_pk": "o-001"}]}
    rep = mod.verify(raw_files, des_files, pseudo_map={})
    assert not rep.checks["V1_row_counts"]["ok"]
    assert rep.checks["V1_row_counts"]["detail"]["mismatch"] == ["orders.csv"]
