"""Tests for ``scripts/v28_export_desensitize.py`` (plan §3/§4.7, T4-T8 subset).

Runs the desensitization script end-to-end on the **synthetic** fixture
``tests/fixtures/v28_export_sample/raw/`` — no production data, no DB, no
network. The synthetic salt lives in the fixture (test-only; the real salt
is Owner-delivered and never committed, plan §1.3/§6).
"""

from __future__ import annotations

import csv
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

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


def _script_cmd(
    out_dir: Path,
    *,
    id_map_dir: Path | None = None,
    retention_days: int = 7,
    salt_file: Path = SALT,
) -> list[str]:
    cmd = [
        sys.executable,
        str(REPO / "scripts" / "v28_export_desensitize.py"),
        "--raw-dir",
        str(RAW),
        "--out-dir",
        str(out_dir),
        "--salt-file",
        str(salt_file),
        "--workspace-id",
        "ws-test-1",
    ]
    if id_map_dir is not None:
        cmd.extend(["--id-map-dir", str(id_map_dir)])
        cmd.extend(["--id-map-retention-days", str(retention_days)])
    return cmd


def _run_script(
    *,
    id_map_dir: Path | None = None,
    out_dir: Path | None = None,
    retention_days: int = 7,
) -> dict:
    """Run the full pipeline into a fresh restricted dir/out dir when omitted."""
    if id_map_dir is None:
        with tempfile.TemporaryDirectory(prefix="v28-secure-id-map-") as tmp:
            return _run_script(
                id_map_dir=Path(tmp),
                out_dir=out_dir,
                retention_days=retention_days,
            )
    target_out = out_dir or OUT
    _ensure_salt()
    target_out.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        _script_cmd(target_out, id_map_dir=id_map_dir, retention_days=retention_days),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"script failed: {result.stdout}\n{result.stderr}"
    return json.loads(
        (target_out / "desensitization_report.json").read_text(encoding="utf-8")
    )


def _read(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_salt_missing_fails_closed(tmp_path: Path):
    with tempfile.TemporaryDirectory(prefix="v28-secure-id-map-") as tmp:
        id_map = Path(tmp)
        result = subprocess.run(
            _script_cmd(
                tmp_path / "out",
                id_map_dir=id_map,
                salt_file=REPO / "does-not-exist.txt",
            ),
            capture_output=True,
            text=True,
        )
        # A missing salt file must never proceed.
        assert result.returncode != 0, "missing salt must abort the run"
        assert not (tmp_path / "out" / "orders.csv").exists()


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


# ---------------------------------------------------------------------------
# G4: referential / PK / workspace integrity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fname", "row", "label"),
    [
        (
            "orders_lines.csv",
            {"order_pk": "o-999", "line_pk": "l-404", "workspace_id": "ws-test-1"},
            "l-404",
        ),
        (
            "tax.csv",
            {"order_pk": "o-999", "workspace_id": "ws-test-1"},
            "o-999",
        ),
        (
            "payments.csv",
            {"order_pk": "o-999", "workspace_id": "ws-test-1"},
            "o-999",
        ),
        (
            "order_marketing.csv",
            {"order_pk": "o-999", "workspace_id": "ws-test-1"},
            "o-999",
        ),
        (
            "refunds.csv",
            {"order_pk": "o-999", "refund_pk": "r-404", "workspace_id": "ws-test-1"},
            "r-404",
        ),
    ],
)
def test_isolated_order_pk_detected_per_file(
    fname: str, row: dict[str, str], label: str
):
    """G4: an isolated order_pk in any of the five order-linked files FAILS."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [{"order_pk": "o-001", "workspace_id": "ws-test-1"}],
        fname: [row],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    v2 = rep.checks["V2_referential"]
    assert not v2["ok"], f"{fname} orphan was not detected"
    assert label in v2["detail"]["order_pk_orphans"][fname]


def test_workspace_mismatch_detected():
    """G4: a child row whose workspace differs from the exported workspace FAILS."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [
            {"order_pk": "o-001", "workspace_id": "ws-test-1"},
        ],
        "tax.csv": [
            {"order_pk": "o-001", "workspace_id": "ws-other"},
        ],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    ws = rep.checks["V2_workspace_consistency"]
    assert not ws["ok"]
    assert ws["detail"]["mismatch_count"] >= 1


def test_missing_workspace_column_is_marked_not_skipped():
    """G4: missing workspace_id is an explicit structural gap, never silent."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [{"order_pk": "o-001"}],
        "refunds.csv": [{"order_pk": "o-001", "refund_pk": "r-001"}],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    ws = rep.checks["V2_workspace_consistency"]
    assert not ws["ok"]
    assert "orders.csv" in ws["detail"]["missing_workspace_columns"]
    assert ws["detail"]["structural_limitations"]


def test_duplicate_primary_key_detected():
    """G4: duplicate order_pk in orders FAILS V2 primary-key integrity."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [
            {"order_pk": "o-001", "workspace_id": "ws-test-1"},
            {"order_pk": "o-001", "workspace_id": "ws-test-1"},
        ],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    pk = rep.checks["V2_primary_key_integrity"]
    assert not pk["ok"]
    assert pk["detail"]["files"]["orders.csv"]["duplicate_samples"] == ["o-001"]


def test_empty_primary_key_detected():
    """G4: blank order_pk in orders FAILS V2 primary-key integrity."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [
            {"order_pk": "", "workspace_id": "ws-test-1"},
            {"order_pk": "o-002", "workspace_id": "ws-test-1"},
        ],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    pk = rep.checks["V2_primary_key_integrity"]
    assert not pk["ok"]
    assert pk["detail"]["files"]["orders.csv"]["empty_count"] == 1


def test_missing_required_association_field_marked():
    """G4: a file with no order_pk column is flagged, not skipped, and no fake
    FK is synthesized (structural limitation recorded)."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [
            {"order_pk": "o-001", "workspace_id": "ws-test-1"},
        ],
        "tax.csv": [
            {"subtotal": "10.00", "workspace_id": "ws-test-1"},
        ],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    v2 = rep.checks["V2_referential"]
    assert not v2["ok"]
    assert v2["detail"]["missing_required_association_fields"]["tax.csv"] == [
        "order_pk"
    ]
    assert v2["detail"]["structural_limitations"]


# ---------------------------------------------------------------------------
# G4 supplement: full-manifest workspace consistency + cross-workspace
# ---------------------------------------------------------------------------

#: Non-order-linked export files that the G4 supplement must also cover.
EXTRA_WS_FILES = (
    "cost_snapshots.csv",
    "cost_current.csv",
    "price_history.csv",
    "shipments.csv",
    "logistics_events.csv",
    "campaigns.csv",
)


@pytest.mark.parametrize(
    ("fname", "row", "pk"),
    [
        ("cost_snapshots.csv", {"snapshot_pk": "s-001"}, "snapshot_pk"),
        ("cost_current.csv", {"order_pk": "o-001"}, "order_pk"),
        ("price_history.csv", {"product_pk": "P-01"}, "product_pk"),
        ("shipments.csv", {"shipment_pk": "sh-001"}, "shipment_pk"),
        (
            "logistics_events.csv",
            {"event_pk": "e-001", "shipment_id": "sh-001"},
            "event_pk",
        ),
        ("campaigns.csv", {"campaign_pk": "c-001"}, "campaign_pk"),
    ],
)
def test_extra_entity_workspace_mismatch_detected(fname: str, row: dict, pk: str):
    """G4 supplement: EVERY export entity (not just order-linked) must match the
    CLI workspace. A non-matching row in cost_snapshots / price_history /
    shipments / logistics_events / campaigns / cost_current FAILS."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [{"order_pk": "o-001", "workspace_id": "ws-test-1"}],
        "shipments.csv": [{"shipment_pk": "sh-001", "workspace_id": "ws-test-1"}],
        fname: [{"workspace_id": "ws-other", **row}],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    ws = rep.checks["V2_workspace_consistency"]
    assert not ws["ok"], f"{fname} workspace mismatch was not detected"
    assert any(
        m["file"] == fname and m["reason"] == "workspace_mismatch"
        for m in ws["detail"]["mismatch_rows"]
    ), f"{fname} not in mismatch rows"
    assert ws["detail"]["manifest"][fname]["status"] == "workspace_mismatch_fail"


@pytest.mark.parametrize(
    ("fname", "row", "pk"),
    [
        ("cost_snapshots.csv", {"snapshot_pk": "s-001"}, "snapshot_pk"),
        ("cost_current.csv", {"order_pk": "o-001"}, "order_pk"),
        ("price_history.csv", {"product_pk": "P-01"}, "product_pk"),
        ("shipments.csv", {"shipment_pk": "sh-001"}, "shipment_pk"),
        (
            "logistics_events.csv",
            {"event_pk": "e-001", "shipment_id": "sh-001"},
            "event_pk",
        ),
        ("campaigns.csv", {"campaign_pk": "c-001"}, "campaign_pk"),
    ],
)
def test_extra_entity_empty_workspace_detected(fname: str, row: dict, pk: str):
    """G4 supplement: a blank workspace_id in ANY export entity FAILS."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [{"order_pk": "o-001", "workspace_id": "ws-test-1"}],
        "shipments.csv": [{"shipment_pk": "sh-001", "workspace_id": "ws-test-1"}],
        fname: [{"workspace_id": "", **row}],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    ws = rep.checks["V2_workspace_consistency"]
    assert not ws["ok"], f"{fname} empty workspace was not detected"
    assert any(
        m["file"] == fname and m["reason"] == "missing"
        for m in ws["detail"]["mismatch_rows"]
    ), f"{fname} empty workspace not in mismatch rows"


def test_missing_workspace_column_fails_for_any_entity():
    """G4 supplement: a schema-workspace-scoped file exported WITHOUT
    workspace_id is a FAIL (schema-requires-but-export-missing), regardless of
    whether it is order-linked. It is never downgraded to a structural limit."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [{"order_pk": "o-001", "workspace_id": "ws-test-1"}],
        # shipments.csv source table IS workspace-scoped but the export omits it.
        "shipments.csv": [{"shipment_pk": "sh-001"}],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    ws = rep.checks["V2_workspace_consistency"]
    assert not ws["ok"]
    assert "shipments.csv" in ws["detail"]["missing_workspace_columns"]
    assert (
        ws["detail"]["missing_workspace_reasons"]["shipments.csv"]
        == "schema_requires_workspace_but_export_missing"
    )
    assert ws["detail"]["manifest"]["shipments.csv"]["status"] == (
        "missing_workspace_column_fail"
    )


def test_cross_workspace_same_order_pk_never_matched():
    """G4 supplement: the same order_pk under a DIFFERENT workspace must never
    satisfy a foreign reference. order_pk-only matching would conflate ws-B's
    o-001 with ws-A's o-001; the (workspace_id, order_pk) resolution must
    report it as isolated AND as a workspace mismatch."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [{"order_pk": "o-001", "workspace_id": "ws-test-1"}],
        "tax.csv": [{"order_pk": "o-001", "workspace_id": "ws-other"}],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    v2 = rep.checks["V2_referential"]
    assert not v2["ok"], "cross-workspace order_pk must be isolated"
    assert "o-001" in v2["detail"]["order_pk_orphans"]["tax.csv"]
    ws = rep.checks["V2_workspace_consistency"]
    assert not ws["ok"]
    assert any(
        m["file"] == "tax.csv" and m["reason"] == "workspace_mismatch"
        for m in ws["detail"]["mismatch_rows"]
    )
    # The cross-workspace collision is reported by key, not silently merged.
    assert ws["detail"]["cross_workspace_keys"].get("o-001") == [
        "ws-other",
        "ws-test-1",
    ]


def test_cross_workspace_same_order_pk_in_orders_detected():
    """G4 supplement: orders.csv holding the same order_pk under two workspaces
    FAILS both PK uniqueness and workspace consistency, and the cross-workspace
    key is reported."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [
            {"order_pk": "o-001", "workspace_id": "ws-test-1"},
            {"order_pk": "o-001", "workspace_id": "ws-other"},
        ],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    pk = rep.checks["V2_primary_key_integrity"]
    assert not pk["ok"], "duplicate order_pk across workspaces must fail PK check"
    ws = rep.checks["V2_workspace_consistency"]
    assert not ws["ok"]
    assert ws["detail"]["cross_workspace_keys"].get("o-001") == [
        "ws-other",
        "ws-test-1",
    ]


def test_logistics_event_parent_workspace_mismatch():
    """G4 supplement: logistics_events.shipment_id -> shipments.shipment_pk is
    resolved by (workspace_id, shipment_id). An event whose workspace differs
    from its shipment's workspace FAILS parent_workspace_mismatch."""
    import scripts.v28_export_desensitize as mod

    raw_files = {
        "orders.csv": [{"order_pk": "o-001", "workspace_id": "ws-test-1"}],
        "shipments.csv": [
            {"shipment_pk": "sh-001", "workspace_id": "ws-test-1"},
        ],
        "logistics_events.csv": [
            {"event_pk": "e-001", "shipment_id": "sh-001", "workspace_id": "ws-other"},
        ],
    }
    des_files = {k: [dict(r) for r in v] for k, v in raw_files.items()}
    rep = mod.verify(raw_files, des_files, pseudo_map={}, workspace_id="ws-test-1")
    ws = rep.checks["V2_workspace_consistency"]
    assert not ws["ok"]
    assert any(
        m["file"] == "logistics_events.csv"
        and m["reason"] == "parent_workspace_mismatch"
        for m in ws["detail"]["mismatch_rows"]
    )


def test_workspace_manifest_complete_and_ok():
    """G4 supplement: the full-pipeline manifest covers every actual output
    file, all carry workspace_id, and all rows are consistent (status ok)."""
    report = _run_script()
    ws = report["regression"]["checks"]["V2_workspace_consistency"]
    assert ws["ok"]
    detail = ws["detail"]
    manifest = detail["manifest"]
    # Every CSV written by the pipeline is in the manifest.
    for csv_name in sorted(p.name for p in OUT.iterdir() if p.name.endswith(".csv")):
        assert csv_name in manifest, f"{csv_name} missing from workspace manifest"
    assert detail["checked_files"] == len(manifest)
    for name, entry in manifest.items():
        assert entry["has_workspace_id"], f"{name} lost workspace_id"
        assert entry["schema_requires_workspace_id"], f"{name} schema contract unclear"
        assert entry["status"] == "ok", f"{name} workspace status: {entry['status']}"
        assert entry["empty_workspace_rows"] == 0
        assert entry["workspace_mismatch_rows"] == 0
    assert not detail["missing_workspace_columns"]
    assert not detail["cross_workspace_keys"]


# ---------------------------------------------------------------------------
# G3: restricted id-map storage
# ---------------------------------------------------------------------------


def test_id_map_written_to_restricted_dir(tmp_path: Path):
    """G3: mapping lands in the restricted dir with 0600, retention metadata,
    no salt, and never inside the ordinary delivery package."""
    secure = tmp_path / "restricted"
    secure.mkdir()
    out = tmp_path / "out"
    report = _run_script(id_map_dir=secure, out_dir=out)

    map_path = secure / "_id_map_pseudo.json"
    assert map_path.exists(), "id-map was not written to the restricted dir"
    assert not (out / "_id_map_pseudo.json").exists(), "id-map leaked into out_dir"
    assert report["id_map"]["written"] is True
    assert report["id_map"]["entry_count"] > 0
    assert report["id_map"]["delivered_with_package"] is False

    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    assert mapping["schema_version"] == "v28-id-map-v1"
    assert mapping["security"]["file_mode_octal"] == "0600"
    assert mapping["security"]["directory_mode_octal"] == "0700"
    assert mapping["security"]["git_tracked"] is False
    assert mapping["security"]["salt_included"] is False
    assert mapping["security"]["retention_days"] == 7
    assert mapping["security"]["destruction_owner_decision_required"] is True
    # No salt (neither as a key nor as a value) anywhere in the payload.
    assert "v28-test-only-salt" not in json.dumps(mapping).lower()
    assert "_salt" not in mapping
    assert all("_salt" not in v for v in mapping["entries"].values())
    # Mapping is actually usable for reversal when protected by Owner custody.
    salt = SALT.read_text(encoding="utf-8").strip()
    assert mapping["entries"]["external_order_id"]["WC-1001"] == pseudo_id(
        "external_order_id", "ws-test-1", "WC-1001", salt
    )
    if os.name != "nt":
        mode = stat.S_IMODE(map_path.stat().st_mode)
        assert mode & 0o077 == 0, f"id-map is world/group accessible: {oct(mode)}"
        assert mode == 0o600


def test_id_map_not_in_git_and_rejected_inside_worktree(tmp_path: Path):
    """G3: mapping is outside the Git worktree and the file is ignore-listed;
    an id-map dir inside the worktree is refused fail-closed."""
    secure = tmp_path / "restricted"
    secure.mkdir()
    out = tmp_path / "out"
    _run_script(id_map_dir=secure, out_dir=out)

    assert REPO not in secure.resolve().parents
    git = subprocess.run(
        [
            "git",
            "-C",
            str(REPO),
            "check-ignore",
            "-q",
            "--no-index",
            "_id_map_pseudo.json",
        ],
        capture_output=True,
        text=True,
    )
    assert git.returncode == 0, "_id_map_pseudo.json is not Git-ignored"

    bad = REPO / "tests" / "fixtures" / "v28_export_sample" / "restricted_bad"
    bad.mkdir(parents=True, exist_ok=True)
    out2 = tmp_path / "out2"
    out2.mkdir()
    _ensure_salt()
    result = subprocess.run(
        _script_cmd(out2, id_map_dir=bad),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert not (out2 / "orders.csv").exists()


def test_missing_id_map_dir_fails_closed(tmp_path: Path):
    """G3: no restricted path => the run aborts and produces no outputs."""
    out = tmp_path / "out"
    out.mkdir()
    _ensure_salt()
    result = subprocess.run(_script_cmd(out), capture_output=True, text=True)
    assert result.returncode == 2
    assert not (out / "orders.csv").exists()


def test_secure_path_overlapping_out_fails_closed(tmp_path: Path):
    """G3: an id-map dir that is the ordinary out_dir is refused."""
    out = tmp_path / "out"
    out.mkdir()
    _ensure_salt()
    result = subprocess.run(
        _script_cmd(out, id_map_dir=out),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert not (out / "orders.csv").exists()


def test_logs_and_errors_do_not_leak_original_ids(tmp_path: Path):
    """G3/G4: stdout, stderr and the report never contain original IDs."""
    _ensure_salt()
    secure = tmp_path / "restricted"
    secure.mkdir()
    out = tmp_path / "out"
    ok = subprocess.run(
        _script_cmd(out, id_map_dir=secure),
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, f"run failed: {ok.stdout}\n{ok.stderr}"
    report_text = (out / "desensitization_report.json").read_text(encoding="utf-8")
    for original in ("WC-1001", "ca-9001", "ref-7001", "v28-test-only-salt"):
        assert original not in ok.stdout
        assert original not in ok.stderr
        assert original not in report_text

    # Exception path (invalid secure dir) must also stay generic.
    bad_out = tmp_path / "bad-out"
    bad_out.mkdir()
    bad = subprocess.run(
        _script_cmd(bad_out, id_map_dir=bad_out),
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 2
    for original in ("WC-1001", "ca-9001", "ref-7001", "v28-test-only-salt"):
        assert original not in bad.stdout
        assert original not in bad.stderr


def test_id_map_deterministic_across_runs(tmp_path: Path):
    """G3: two independent runs produce byte-identical CSVs and mapping."""
    secure1 = tmp_path / "r1" / "restricted"
    secure2 = tmp_path / "r2" / "restricted"
    out1 = tmp_path / "r1" / "out"
    out2 = tmp_path / "r2" / "out"
    secure1.mkdir(parents=True)
    secure2.mkdir(parents=True)
    _run_script(id_map_dir=secure1, out_dir=out1)
    _run_script(id_map_dir=secure2, out_dir=out2)

    for csv_name in sorted(p.name for p in out1.glob("*.csv")):
        assert (out1 / csv_name).read_bytes() == (out2 / csv_name).read_bytes()
    assert (secure1 / "_id_map_pseudo.json").read_bytes() == (
        secure2 / "_id_map_pseudo.json"
    ).read_bytes()
    assert (out1 / "desensitization_report.json").read_bytes() == (
        out2 / "desensitization_report.json"
    ).read_bytes()
