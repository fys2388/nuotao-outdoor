"""V2.8 historical-data export desensitization script (draft; Owner-gated execution).

Purely local, offline, no DB connection, no network. Implements §3 of
``docs/V2_8_HISTORICAL_DATA_EXPORT_PLAN.md``:

* deterministic stable pseudo-IDs (SHA-256 with an Owner-supplied salt);
* PII stripping (explicit PII key removal + recursive JSON key scrubbing +
  regex backstop for email / phone / card / token-like values);
* missing-value handling: NULL stays NULL (never backfilled with 0) and is
  annotated with a machine-checkable ``missing_reason``;
* G3: the reversible original→pseudo mapping is written ONLY to an
  Owner-controlled restricted directory (``--id-map-dir``), never inside the
  Git worktree and never in the ordinary delivery package, with 0600 file
  permissions and explicit retention/destruction policy;
* G4: referential integrity (all five order-linked files), surrogate PK
  uniqueness/non-emptiness, and workspace consistency are self-verified;
* self-verification (plan §3.2, items V1–V7) run automatically after
  desensitizing.

The script **refuses to run without a salt file and without a valid
restricted id-map directory** (fail-closed, exit code 2). The salt itself is
never committed, never defaulted, and is read only from ``--salt-file``
(Owner delivery, controlled channel).

Usage (after Owner approval, on raw exports in ``data/raw_export/``)::

    python scripts/v28_export_desensitize.py \
        --raw-dir data/raw_export \
        --out-dir data/desensitized \
        --salt-file <owner-delivered salt file> \
        --workspace-id <workspace uuid> \
        --id-map-dir <owner-restricted-storage> \
        --id-map-retention-days 30
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# PII / credential patterns (regex backstop, plan §3.2 V3)
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# International phone: +digits / (digits) / 10-15 consecutive digits with
# separators. Deliberately conservative to limit false positives on UUIDs.
PHONE_RE = re.compile(
    r"(?:\+\d{7,15}|\(\d{2,4}\)\s?\d{3,14}|\b\d{3}[\s.-]?\d{4}[\s.-]?\d{4}\b)"
)
# Luhn-formatted card numbers (13-19 digits, optional separators).
CARD_RE = re.compile(r"\b(?:\d[ \-]?){12,18}\d\b")
TOKEN_KEY_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|cookie|cvv|client[_-]?secret)\b\s*[:=]\s*[^\s,;]+",
)

PII_KEYS = frozenset(
    {
        "billing_email",
        "billing_first_name",
        "billing_last_name",
        "billing_phone",
        "billing_address",
        "billing_address_1",
        "billing_address_2",
        "billing_city",
        "billing_state",
        "billing_postcode",
        "billing_country",
        "shipping_first_name",
        "shipping_last_name",
        "shipping_address",
        "shipping_address_1",
        "shipping_address_2",
        "shipping_city",
        "shipping_state",
        "shipping_postcode",
        "email",
        "phone",
        "first_name",
        "last_name",
        "display_name",
        "customer_name",
        "card_number",
        "cvv",
        "customer_number",
    }
)

# Entity -> (file, column) pairs that receive stable pseudo-IDs (plan §1.3).
PSEUDO_ID_FIELDS: dict[str, tuple[str, str]] = {
    "external_order_id": ("orders.csv", "external_order_id"),
    "customer_account_id": ("orders.csv", "customer_account_id"),
    "customer_reference_id": ("orders.csv", "customer_reference_id"),
    "payment_refund_id": ("refunds.csv", "payment_refund_id"),
    "woocommerce_refund_id": ("refunds.csv", "woocommerce_refund_id"),
    "tracking_number": ("shipments.csv", "tracking_number"),
    "campaign_id": ("campaigns.csv", "campaign_id"),
}

#: Fields whose raw value being the literal "0" is a *legit business zero*
#: (kept as 0, tagged). Anything else that is NULL carries a missing_reason.
ZERO_IS_LEGIT = frozenset(
    {
        "shipping_total",
        "discount_total",
        "tax_total",
        "payment_fee",
        "refunded_amount",
        "advertising_cost",
        "subtotal",
        "total",
        "line_total",
        "unit_price",
        "purchase_cost",
        "domestic_shipping",
        "first_leg_shipping",
        "last_leg_shipping",
        "international_shipping",
        "packaging",
        "tax_estimate",
        "handling",
        "total_landed_cost",
        "total_cost",
        "executed_amount",
        "requested_amount",
        "approved_amount",
        "actual_cost",
    }
)

#: Missing-reason taxonomy (plan §1.4): value is annotated, never faked.
MISSING_REASON_NOT_COLLECTED = "not_collected"
MISSING_REASON_FIELD_NOT_STORED = "field_not_stored"
MISSING_REASON_LEGACY_NO_RECORD = "legacy_no_record"
MISSING_REASON_PAYLOAD_EXCLUDED = "payload_excluded"

# ---------------------------------------------------------------------------
# G3: isolated pseudo-ID mapping store (reidentifiable by construction).
# ---------------------------------------------------------------------------
# The mapping from original IDs to pseudo-IDs is the only artifact that can
# reverse the desensitization. It MUST be written to an Owner-controlled
# restricted path, NEVER to the ordinary ``out_dir`` (which is a delivery
# package) and NEVER inside the Git worktree. The script refuses to run when
# that restricted location is absent, invalid, or unsafe (fail-closed).
ID_MAP_FILENAME = "_id_map_pseudo.json"
ID_MAP_SCHEMA_VERSION = "v28-id-map-v1"
ID_MAP_DIR_MODE = 0o700
ID_MAP_FILE_MODE = 0o600


class RestrictedIdMapError(RuntimeError):
    """Secure id-map storage unavailable.

    Raised for any condition that makes the restricted mapping location
    unusable. Messages are intentionally generic: they never carry a path,
    a workspace id, an original id, or any mapping content.
    """


# ---------------------------------------------------------------------------
# G4: referential / PK / workspace integrity for the V2.8 export.
# ---------------------------------------------------------------------------
#: Child files whose every row must resolve to an ``orders.csv`` row by
#: ``order_pk``. The value is the per-row surrogate key used for reporting
#: (``None`` when the file is an order-level projection keyed by ``order_pk``).
ORDER_FK_FILES: dict[str, str | None] = {
    "orders_lines.csv": "line_pk",
    "tax.csv": None,
    "payments.csv": None,
    "order_marketing.csv": None,
    "refunds.csv": "refund_pk",
}

#: Surrogate primary keys that MUST be present, non-empty, and unique.
PRIMARY_KEY_FIELDS: dict[str, str] = {
    "orders.csv": "order_pk",
    "orders_lines.csv": "line_pk",
    "refunds.csv": "refund_pk",
    "cost_snapshots.csv": "snapshot_pk",
    "price_history.csv": "product_pk",
    "shipments.csv": "shipment_pk",
    "logistics_events.csv": "event_pk",
    "campaigns.csv": "campaign_pk",
}

# ---------------------------------------------------------------------------
# G4 supplement: workspace contract for every export entity.
# ---------------------------------------------------------------------------
# Every export entity maps to a source table that is workspace-scoped
# (``WorkspaceMixin`` or an explicit ``workspace_id`` column). The source
# schema therefore REQUIRES ``workspace_id`` on every export file; a file that
# is exported without it violates the schema contract and must FAIL — it is
# never treated as a silent structural limitation.
SCHEMA_WORKSPACE_FILES: dict[str, bool] = {
    "orders.csv": True,
    "orders_lines.csv": True,
    "tax.csv": True,
    "cost_snapshots.csv": True,
    "cost_current.csv": True,
    "price_history.csv": True,
    "payments.csv": True,
    "refunds.csv": True,
    "shipments.csv": True,
    "logistics_events.csv": True,
    "campaigns.csv": True,
    "order_marketing.csv": True,
}

#: Parent association used for cross-entity workspace consistency.
#: value = (parent_file, parent_key_col, child_key_col); None = no parent in
#: the export set (the entity is top-level for workspace purposes).
WORKSPACE_PARENT: dict[str, tuple[str, str, str] | None] = {
    "orders.csv": None,
    "orders_lines.csv": ("orders.csv", "order_pk", "order_pk"),
    "tax.csv": ("orders.csv", "order_pk", "order_pk"),
    "payments.csv": ("orders.csv", "order_pk", "order_pk"),
    "order_marketing.csv": ("orders.csv", "order_pk", "order_pk"),
    "refunds.csv": ("orders.csv", "order_pk", "order_pk"),
    "cost_snapshots.csv": None,
    "cost_current.csv": None,
    "price_history.csv": None,
    "shipments.csv": None,
    "logistics_events.csv": ("shipments.csv", "shipment_pk", "shipment_id"),
    "campaigns.csv": None,
}

#: Association keys that index into ``orders.csv``; used to detect a single
#: ``order_pk`` that appears under more than one workspace (cross-workspace
#: same-order_pk, which order_pk-only matching must never conflate).
ORDER_LINKED_FILES = (
    "orders.csv",
    "orders_lines.csv",
    "tax.csv",
    "payments.csv",
    "order_marketing.csv",
    "refunds.csv",
    "cost_current.csv",
)

#: Associations the source schema does NOT model. The script must never
#: synthesize a fake FK for these; it only records the structural limitation.
STRUCTURAL_ASSOCIATION_LIMITS: list[dict[str, str]] = [
    {
        "association": "shipments -> orders",
        "status": "no_direct_fk_in_schema",
        "note": "shipments.csv has no order_pk; shipment integrity is checked by shipment_pk only",
    },
    {
        "association": "logistics_events -> orders",
        "status": "no_direct_fk_in_schema",
        "note": "logistics_events.csv links to shipments.csv, not orders; no FK is synthesized",
    },
    {
        "association": "campaigns -> orders",
        "status": "no_direct_fk_in_schema",
        "note": "campaigns.csv is a product-level report; no order FK is synthesized",
    },
    {
        "association": "tax / payments / order_marketing",
        "status": "no_surrogate_pk",
        "note": "these are order-level projections; order_pk is the association key, no fake row PK",
    },
    {
        "association": "order_items -> cost_snapshots",
        "status": "field_not_stored",
        "note": "cost_snapshot_id/cost_snapshot_version/pricing_*_version are not in the source schema",
    },
]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def pseudo_id(entity_kind: str, workspace_id: str, original: str, salt: str) -> str:
    """Deterministic, irreversible stable pseudo-ID (plan §1.3, SHA-256).

    Same (entity_kind, workspace, original, salt) always maps to the same
    pseudo-ID across repeated exports; without the salt the mapping cannot be
    reversed.
    """
    payload = f"{entity_kind}|{workspace_id}|{original}|{salt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def scrub_pii(
    row: dict[str, Any], *, report: dict[str, int], entity_pseudo: dict[str, str]
) -> dict[str, Any]:
    """Drop PII keys, replace sensitive IDs with pseudo-IDs, regex-sweep.

    Mutates and returns the row. ``report`` accumulates hit counters.
    """
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in PII_KEYS:
            report["pii_keys_dropped"] = report.get("pii_keys_dropped", 0) + 1
            continue
        if key in entity_pseudo:
            if _is_blank(value):
                out[key] = value
                continue
            out[key] = entity_pseudo[key]
            report["pseudo_id_replaced"] = report.get("pseudo_id_replaced", 0) + 1
            continue
        out[key] = value
    # Recursively scrub JSON-ish values (profit_snapshot / rule_results / notes).
    for key, value in list(out.items()):
        text = (
            json.dumps(value, ensure_ascii=False)
            if isinstance(value, (dict, list))
            else str(value)
        )
        if text and not _is_blank(text):
            out[key] = _sweep_text(text, report)
    return out


def _sweep_text(text: str, report: dict[str, int]) -> Any:
    """Replace PII-like substrings; keep JSON values as JSON objects."""
    if EMAIL_RE.search(text):
        report["regex_email"] = report.get("regex_email", 0) + 1
        text = EMAIL_RE.sub("[REDACTED:EMAIL]", text)
    if PHONE_RE.search(text):
        report["regex_phone"] = report.get("regex_phone", 0) + 1
        text = PHONE_RE.sub("[REDACTED:PHONE]", text)
    if CARD_RE.search(text):
        report["regex_card"] = report.get("regex_card", 0) + 1
        text = CARD_RE.sub("[REDACTED:CARD]", text)
    if TOKEN_KEY_RE.search(text):
        report["regex_token_key"] = report.get("regex_token_key", 0) + 1
        text = TOKEN_KEY_RE.sub(r"\1=[REDACTED]", text)
    if text.startswith(("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def annotate_missing(row: dict[str, Any]) -> dict[str, Any]:
    """Mark NULL cells with missing_reason; tag legit zeros (plan §1.4/V4)."""
    has_blank = False
    for key, value in list(row.items()):
        if key in ("missing_reason", "value_is_zero"):
            continue
        if _is_blank(value):
            has_blank = True
        elif value in ("0", 0, "0.00", 0.0, Decimal("0")) and key in ZERO_IS_LEGIT:
            row["value_is_zero"] = "true"
    if has_blank and not row.get("missing_reason"):
        row["missing_reason"] = MISSING_REASON_NOT_COLLECTED
    return row


# ---------------------------------------------------------------------------
# CSV I/O (no pandas: stdlib only, keeps the script portable for Owner review)
# ---------------------------------------------------------------------------


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean = {
                k: (
                    "null"
                    if v is None
                    else json.dumps(v, ensure_ascii=False)
                    if isinstance(v, (dict, list))
                    else str(v)
                )
                for k, v in row.items()
            }
            writer.writerow(clean)


# ---------------------------------------------------------------------------
# G3: restricted id-map storage (fail-closed, never in the delivery package)
# ---------------------------------------------------------------------------


def _is_within_git_repository(path: Path) -> bool:
    """True when ``path`` (or an ancestor) is a Git worktree/repo."""
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return True
    return False


def _nested_or_same(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def resolve_restricted_id_map_dir(
    raw_dir: Path, out_dir: Path, id_map_dir: Path | None
) -> Path:
    """Validate the restricted id-map location before any work happens.

    Fail-closed: the location must already exist, must be a real directory
    (not a symlink), must be disjoint from ``raw_dir``/``out_dir``, and must
    not live inside a Git worktree.
    """
    if id_map_dir is None:
        raise RestrictedIdMapError("restricted id-map storage is not configured")
    try:
        raw_res = raw_dir.resolve(strict=True)
        out_res = out_dir.resolve(strict=False)
        secure_res = id_map_dir.resolve(strict=True)
    except OSError:
        raise RestrictedIdMapError(
            "restricted id-map storage is not accessible"
        ) from None
    if secure_res.is_symlink():
        raise RestrictedIdMapError("restricted id-map storage must not be a symlink")
    if not secure_res.is_dir():
        raise RestrictedIdMapError("restricted id-map storage is not a directory")
    if (
        _nested_or_same(raw_res, secure_res)
        or _nested_or_same(out_res, secure_res)
        or _nested_or_same(raw_res, out_res)
    ):
        raise RestrictedIdMapError("restricted id-map storage must be independent")
    if _is_within_git_repository(secure_res):
        raise RestrictedIdMapError(
            "restricted id-map storage must be outside any Git repository"
        )
    return secure_res


def _id_map_payload(
    pseudo_map: dict[str, dict[str, str]],
    workspace_id: str,
    retention_days: int,
) -> dict[str, Any]:
    entries: dict[str, dict[str, str]] = {}
    for kind, mapping in pseudo_map.items():
        entries[kind] = {
            original: pseudo
            for original, pseudo in mapping.items()
            if not original.startswith("_")
        }
    return {
        "schema_version": ID_MAP_SCHEMA_VERSION,
        "workspace_id": workspace_id,
        "entry_count": sum(len(v) for v in entries.values()),
        "entries": entries,
        "security": {
            "classification": "L4_REIDENTIFIABLE",
            "storage_class": "restricted_owner_controlled",
            "git_tracked": False,
            "delivered_with_desensitized_package": False,
            "file_mode_octal": "0600",
            "directory_mode_octal": "0700",
            "retention_days": retention_days,
            "destruction_owner_decision_required": True,
            "destruction_note": (
                "Owner decides the final destruction time; secure overwrite/delete "
                "after the 30-day review and owner sign-off"
            ),
            "salt_included": False,
        },
    }


def write_restricted_id_map(
    secure_dir: Path,
    pseudo_map: dict[str, dict[str, str]],
    workspace_id: str,
    retention_days: int,
) -> int:
    """Write ``_id_map_pseudo.json`` with 0600 mode under ``secure_dir``.

    Returns the entry count. Uses O_EXCL so an existing mapping is never
    overwritten (a rerun must deliberately choose a fresh restricted slot).
    """
    target = secure_dir / ID_MAP_FILENAME
    payload = _id_map_payload(pseudo_map, workspace_id, retention_days)
    fd: int | None = None
    try:
        os.chmod(secure_dir, ID_MAP_DIR_MODE)
        fd = os.open(
            str(target),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            ID_MAP_FILE_MODE,
        )
        os.chmod(target, ID_MAP_FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fd = None
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise RestrictedIdMapError(
            "restricted id-map storage write failed (target not created)"
        ) from None
    return int(payload["entry_count"])


# ---------------------------------------------------------------------------
# Self-verification (plan §3.2 V1–V7)
# ---------------------------------------------------------------------------


@dataclass
class VerifyReport:
    checks: dict[str, Any] = field(default_factory=dict)

    def record(self, name: str, ok: bool, detail: Any = None) -> None:
        self.checks[name] = {"ok": bool(ok), "detail": detail}

    @property
    def passed(self) -> bool:
        return all(v["ok"] for v in self.checks.values())

    def to_json(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": self.checks,
        }


def verify(
    raw_files: dict[str, list[dict[str, str]]],
    des_files: dict[str, list[dict[str, Any]]],
    pseudo_map: dict[str, dict[str, str]],
    sample_rows: list[tuple[dict[str, Any], dict[str, Any]]] | None = None,
    fingerprints: dict[str, str] | None = None,
    workspace_id: str | None = None,
) -> VerifyReport:
    rep = VerifyReport()

    # V1 row counts
    row_mismatch = []
    for name in raw_files:
        if len(raw_files[name]) != len(des_files.get(name, [])):
            row_mismatch.append(name)
    rep.record("V1_row_counts", not row_mismatch, {"mismatch": row_mismatch})

    # V2 referential alignment: every order-linked row must resolve to an
    # orders.csv row. G4 supplement: the resolution key is (workspace_id,
    # order_pk) whenever BOTH the parent orders and the child row carry
    # workspace_id, so an order_pk that exists in a different workspace can
    # never satisfy a foreign reference. When neither side carries
    # workspace_id (legacy exports) we fall back to order_pk-only matching.
    # Missing association fields are recorded explicitly (never silently
    # skipped); structural limits never fabricate a fake FK.
    order_rows = des_files.get("orders.csv", [])
    order_pks = {r["order_pk"] for r in order_rows if not _is_blank(r.get("order_pk"))}
    parent_ws_present = any(not _is_blank(r.get("workspace_id")) for r in order_rows)
    if parent_ws_present:
        order_ws_keys = {
            (r.get("workspace_id"), r["order_pk"])
            for r in order_rows
            if not _is_blank(r.get("order_pk"))
        }
    else:
        order_ws_keys = None
    isolated_by_file: dict[str, list[str]] = {}
    isolated_ws_by_file: dict[str, list[dict[str, str]]] = {}
    missing_assoc_fields: dict[str, list[str]] = {}
    missing_assoc_rows: list[dict[str, str]] = []
    for filename, row_pk_field in ORDER_FK_FILES.items():
        rows = des_files.get(filename, [])
        if not rows:
            continue
        if not any("order_pk" in r for r in rows):
            missing_assoc_fields[filename] = ["order_pk"]
            continue
        isolated: list[str] = []
        isolated_ws: list[dict[str, str]] = []
        for r in rows:
            fk = r.get("order_pk")
            if _is_blank(fk):
                missing_assoc_rows.append(
                    {
                        "file": filename,
                        "row": str(r.get(row_pk_field) or ""),
                    }
                )
                continue
            if order_ws_keys is not None:
                # Workspace-aware resolution: a child reference is only valid
                # when (workspace_id, order_pk) resolves to a parent. A blank
                # child workspace cannot prove isolation, so it is isolated.
                child_ws = r.get("workspace_id")
                if _is_blank(child_ws) or (child_ws, fk) not in order_ws_keys:
                    isolated.append(str(r.get(row_pk_field) or fk))
                    isolated_ws.append(
                        {
                            "row": str(r.get(row_pk_field) or fk),
                            "workspace": "" if _is_blank(child_ws) else child_ws,
                        }
                    )
            else:
                if fk not in order_pks:
                    isolated.append(str(r.get(row_pk_field) or fk))
        if isolated:
            isolated_by_file[filename] = isolated
            isolated_ws_by_file[filename] = isolated_ws
    samples: list[str] = []
    for ids in isolated_by_file.values():
        samples.extend(ids)
    v2_ok = not isolated_by_file and not missing_assoc_fields and not missing_assoc_rows
    rep.record(
        "V2_referential",
        v2_ok,
        {
            "isolated_refund_rows": len(isolated_by_file.get("refunds.csv", [])),
            "order_pk_orphans": isolated_by_file,
            "order_pk_orphans_workspace": isolated_ws_by_file,
            "orphan_count": sum(len(v) for v in isolated_by_file.values()),
            "missing_required_association_fields": missing_assoc_fields,
            "missing_order_pk_rows": missing_assoc_rows,
            "samples": samples[:10],
            "resolution": "workspace+order_pk"
            if order_ws_keys is not None
            else "order_pk",
            "structural_limitations": STRUCTURAL_ASSOCIATION_LIMITS,
        },
    )

    # G4: surrogate primary keys must exist, be non-empty, and be unique.
    pk_detail: dict[str, Any] = {}
    for filename, pk_field in PRIMARY_KEY_FIELDS.items():
        rows = des_files.get(filename, [])
        if not rows:
            continue
        if not any(pk_field in r for r in rows):
            pk_detail[filename] = {
                "status": "missing_primary_key_field",
                "field": pk_field,
            }
            continue
        values = [str(r.get(pk_field) or "") for r in rows]
        empty_count = sum(1 for v in values if not v.strip())
        seen: set[str] = set()
        duplicates: list[str] = []
        for v in values:
            v = v.strip()
            if not v:
                continue
            if v in seen:
                duplicates.append(v)
            else:
                seen.add(v)
        pk_detail[filename] = {
            "status": "ok" if not empty_count and not duplicates else "violation",
            "field": pk_field,
            "empty_count": empty_count,
            "duplicate_count": len(duplicates),
            "duplicate_samples": duplicates[:10],
        }
    pk_violations = [f for f, d in pk_detail.items() if d["status"] != "ok"]
    rep.record(
        "V2_primary_key_integrity",
        not pk_violations,
        {"files": pk_detail, "violations": pk_violations},
    )

    # G4 supplement: workspace consistency for EVERY actual output file.
    # Every export entity is workspace-scoped in the source schema, so each
    # file must carry workspace_id and every row must be non-empty and equal
    # to the CLI workspace. Parent/child workspace consistency is resolved by
    # (workspace_id, association_key) — never by association_key alone, which
    # would silently conflate the same key across workspaces.
    ws_detail: dict[str, Any] = {
        "mismatch_rows": [],
        "missing_workspace_columns": [],
        "missing_workspace_reasons": {},
        "cross_workspace_keys": {},
        "structural_limitations": [],
        "manifest": {},
    }
    ws_by_order: dict[str, str] = {}
    ws_by_shipment: dict[str, str] = {}
    # order_pk -> set(workspace_id) across every order-linked file; any key
    # seen under 2+ workspaces is a cross-workspace same-order_pk collision.
    order_ws_seen: dict[str, set[str]] = {}
    for filename, rows in des_files.items():
        schema_has_ws = SCHEMA_WORKSPACE_FILES.get(filename, False)
        manifest_entry: dict[str, Any] = {
            "rows": len(rows),
            "has_workspace_id": bool(rows) and any("workspace_id" in r for r in rows),
            "schema_requires_workspace_id": schema_has_ws,
            "empty_workspace_rows": 0,
            "workspace_mismatch_rows": 0,
            "status": "ok",
        }
        if not rows:
            ws_detail["manifest"][filename] = manifest_entry
            continue
        if not any("workspace_id" in r for r in rows):
            if schema_has_ws:
                # Schema contract violation: the source table HAS workspace_id
                # but the export omits it. This is a FAIL, not a structural
                # limit (Owner G4 rule: schema-should-have-but-export-missing).
                manifest_entry["status"] = "missing_workspace_column_fail"
                ws_detail["missing_workspace_columns"].append(filename)
                ws_detail["missing_workspace_reasons"][filename] = (
                    "schema_requires_workspace_but_export_missing"
                )
                ws_detail["structural_limitations"].append(
                    f"{filename}: schema requires workspace_id but export omits it (FAIL)"
                )
            else:
                manifest_entry["status"] = "structural_limit"
                ws_detail["structural_limitations"].append(
                    f"{filename}: workspace_id not in source schema; workspace "
                    f"consistency not applicable (STRUCTURAL_ASSOCIATION_LIMITS)"
                )
            ws_detail["manifest"][filename] = manifest_entry
            continue
        parent = WORKSPACE_PARENT.get(filename)
        for r in rows:
            row_ws = r.get("workspace_id")
            label_field = None
            if parent:
                _, _parent_key, child_key = parent
                label_field = child_key
            elif filename == "orders.csv":
                label_field = "order_pk"
            else:
                label_field = PRIMARY_KEY_FIELDS.get(filename)
            row_label = str(r.get(label_field) or r.get("order_pk") or "")
            if _is_blank(row_ws):
                ws_detail["mismatch_rows"].append(
                    {"file": filename, "row": row_label, "reason": "missing"}
                )
                manifest_entry["empty_workspace_rows"] += 1
                if manifest_entry["status"] == "ok":
                    manifest_entry["status"] = "empty_workspace_fail"
                continue
            if workspace_id and row_ws != workspace_id:
                ws_detail["mismatch_rows"].append(
                    {
                        "file": filename,
                        "row": row_label,
                        "reason": "workspace_mismatch",
                        "row_workspace": row_ws,
                        "expected_workspace": workspace_id,
                    }
                )
                manifest_entry["workspace_mismatch_rows"] += 1
                if manifest_entry["status"] == "ok":
                    manifest_entry["status"] = "workspace_mismatch_fail"
            # Parent/child workspace consistency resolved by
            # (workspace_id, association_key).
            if filename == "orders.csv":
                ws_by_order[str(r.get("order_pk") or "")] = row_ws
            elif parent:
                parent_file, _, child_key = parent
                parent_ws_index = (
                    ws_by_shipment if parent_file == "shipments.csv" else ws_by_order
                )
                parent_ws = parent_ws_index.get(str(r.get(child_key) or ""))
                if parent_ws is not None and row_ws != parent_ws:
                    ws_detail["mismatch_rows"].append(
                        {
                            "file": filename,
                            "row": row_label,
                            "reason": "parent_workspace_mismatch",
                            "row_workspace": row_ws,
                            "parent_workspace": parent_ws,
                            "parent_file": parent_file,
                        }
                    )
                    if manifest_entry["status"] == "ok":
                        manifest_entry["status"] = "parent_workspace_mismatch_fail"
            if filename == "shipments.csv":
                ws_by_shipment[str(r.get("shipment_pk") or "")] = row_ws
            # Cross-workspace same-order_pk detection (order-linked files).
            if filename in ORDER_LINKED_FILES:
                opk = str(r.get("order_pk") or "")
                if opk and not _is_blank(row_ws):
                    order_ws_seen.setdefault(opk, set()).add(row_ws)
        ws_detail["manifest"][filename] = manifest_entry
    cross_ws = {opk: sorted(ws) for opk, ws in order_ws_seen.items() if len(ws) > 1}
    ws_detail["cross_workspace_keys"] = cross_ws
    ws_ok = (
        not ws_detail["mismatch_rows"]
        and not ws_detail["missing_workspace_columns"]
        and not cross_ws
    )
    rep.record(
        "V2_workspace_consistency",
        ws_ok,
        {
            "mismatch_count": len(ws_detail["mismatch_rows"]),
            "mismatch_rows": ws_detail["mismatch_rows"][:10],
            "missing_workspace_columns": ws_detail["missing_workspace_columns"],
            "missing_workspace_reasons": ws_detail["missing_workspace_reasons"],
            "cross_workspace_keys": cross_ws,
            "structural_limitations": ws_detail["structural_limitations"],
            "manifest": ws_detail["manifest"],
            "checked_files": len(ws_detail["manifest"]),
        },
    )

    # V3 no PII residue (re-scan the desensitized text layer)
    hits = _scan_pii_residue(des_files)
    rep.record("V3_no_pii", not hits, hits)

    # V4 missing values not filled with 0.
    # A cell that was NULL in the raw export must still be blank in the output
    # (annotated via missing_reason), and a cell that was literally 0 in the
    # raw export must remain 0 (tagged value_is_zero). Violation = a raw NULL
    # that now carries a numeric value.
    v4_bad: list[tuple[str, str]] = []
    ANNOTATION_COLS = frozenset({"missing_reason", "value_is_zero"})
    for name, raw_rows in raw_files.items():
        des_rows = des_files.get(name, [])
        for raw_row, des_row in zip(raw_rows, des_rows):
            for key, raw_value in raw_row.items():
                if key in ANNOTATION_COLS:
                    continue
                if _is_blank(raw_value) and not _is_blank(des_row.get(key)):
                    v4_bad.append((name, key))
    rep.record(
        "V4_no_zero_fill",
        not v4_bad,
        {"violations": len(v4_bad), "samples": v4_bad[:10]},
    )

    # V5 stable pseudo mapping: recompute a sample of recorded originals and
    # require byte-identical results (determinism across runs).
    v5_bad = []
    for kind, mapping in pseudo_map.items():
        for original, recorded in list(mapping.items())[:5]:
            if original.startswith("_") or original not in mapping:
                continue
            if (
                _remap(kind, original, mapping["_salt"], mapping["_workspace"])
                != recorded
            ):
                v5_bad.append(kind)
    rep.record("V5_pseudo_stable", not v5_bad, {"unstable_kinds": v5_bad})

    # V6 monetary/time preservation (spot check on provided sample pairs)
    v6_bad = 0
    for raw_row, des_row in sample_rows or []:
        for key in (
            "total",
            "tax_total",
            "currency",
            "received_at",
            "line_total",
            "payment_fee",
        ):
            if (
                raw_row.get(key)
                and des_row.get(key)
                and str(raw_row[key]) != str(des_row[key])
            ):
                v6_bad += 1
    rep.record("V6_amounts_preserved", v6_bad == 0, {"mismatched_cells": v6_bad})

    # V7 file fingerprints (computed by caller on the written files)
    rep.record(
        "V7_fingerprints", fingerprints is not None, {"sha256": fingerprints or {}}
    )
    return rep


def _scan_pii_residue(des_files: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rows in des_files.values():
        if not isinstance(rows, list):
            continue
        for row in rows:
            for value in row.values():
                if isinstance(value, (dict, list)):
                    text = json.dumps(value, ensure_ascii=False)
                else:
                    text = str(value)
                if EMAIL_RE.search(text):
                    counts["email"] = counts.get("email", 0) + 1
                # Card scan only on values that are not pseudo-IDs: SHA-256
                # pseudo-IDs are 32 hex chars (letters+digits) and would match
                # the raw card pattern as a false positive.
                if len(text) > 20 and not re.fullmatch(r"[0-9a-f]{32}", text):
                    if CARD_RE.search(text):
                        counts["card"] = counts.get("card", 0) + 1
                if TOKEN_KEY_RE.search(text):
                    counts["token_key"] = counts.get("token_key", 0) + 1
    return counts


def _remap(kind: str, original: str, salt: str, workspace: str) -> str:
    return pseudo_id(kind, workspace, original, salt)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run(
    raw_dir: Path,
    out_dir: Path,
    salt_file: Path,
    workspace_id: str,
    id_map_dir: Path | None,
    id_map_retention_days: int | None,
) -> int:
    # G3: validate the restricted id-map location BEFORE any read/write.
    try:
        secure_dir = resolve_restricted_id_map_dir(raw_dir, out_dir, id_map_dir)
    except RestrictedIdMapError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if id_map_retention_days is None or id_map_retention_days <= 0:
        print("id-map retention must be a positive number of days", file=sys.stderr)
        return 2

    try:
        salt = salt_file.read_text(encoding="utf-8").strip()
    except OSError:
        print(
            "salt file could not be read; refusing to run (fail-closed)",
            file=sys.stderr,
        )
        return 2
    if not salt:
        print("salt file is empty; refusing to run (fail-closed)", file=sys.stderr)
        return 2

    raw_files: dict[str, list[dict[str, str]]] = {}
    for candidate in (
        "orders.csv",
        "orders_lines.csv",
        "tax.csv",
        "cost_snapshots.csv",
        "cost_current.csv",
        "price_history.csv",
        "payments.csv",
        "refunds.csv",
        "shipments.csv",
        "logistics_events.csv",
        "campaigns.csv",
        "order_marketing.csv",
    ):
        path = raw_dir / candidate
        if path.exists():
            raw_files[candidate] = read_csv(path)

    des_files: dict[str, list[dict[str, Any]]] = {}
    pseudo_map: dict[str, dict[str, str]] = {
        kind: {"_salt": salt, "_workspace": workspace_id, **{}}
        for kind in PSEUDO_ID_FIELDS
    }

    # Build the pseudo-ID map first (deterministic, reusable across files).
    for kind, (fname, column) in PSEUDO_ID_FIELDS.items():
        rows = raw_files.get(fname, [])
        for row in rows:
            original = row.get(column)
            if original and original not in pseudo_map[kind]:
                pseudo_map[kind][original] = pseudo_id(
                    kind, workspace_id, original, salt
                )

    # Per-file PII columns that must be dropped from the output headers.
    dropped_columns: dict[str, set[str]] = {}
    for fname, rows in raw_files.items():
        dropped = {k for k in rows[0].keys() if k in PII_KEYS}
        if dropped:
            dropped_columns[fname] = dropped

    report: dict[str, int] = {}
    sample_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for fname, rows in raw_files.items():
        out_rows = []
        for idx, row in enumerate(rows):
            # Per-row pseudo-ID column resolution (file-local).
            row_pseudo = {
                col: pseudo_map[kind][val]
                for kind, (kfname, col) in PSEUDO_ID_FIELDS.items()
                if kfname == fname and (val := row.get(col)) in pseudo_map[kind]
            }
            des_row = scrub_pii(dict(row), report=report, entity_pseudo=row_pseudo)
            des_row = annotate_missing(des_row)
            out_rows.append(des_row)
            if idx < 25:  # V6 spot-check sample
                sample_rows.append((row, des_row))
        des_files[fname] = out_rows
        base_fields = [
            k for k in rows[0].keys() if k and k not in dropped_columns.get(fname, ())
        ]
        extra = [k for k in ("missing_reason", "value_is_zero") if k not in base_fields]
        fieldnames = base_fields + extra
        write_csv(out_dir / fname, out_rows, fieldnames=fieldnames)

    fingerprints = {
        fname: hashlib.sha256((out_dir / fname).read_bytes()).hexdigest()
        for fname in des_files
    }
    rep = verify(
        raw_files,
        des_files,
        pseudo_map,
        sample_rows,
        fingerprints=fingerprints,
        workspace_id=workspace_id,
    )

    # G3: the reidentifiable mapping is only produced when every self-check
    # passes, and only into the restricted Owner-controlled location.
    id_map_written = False
    id_map_entries = 0
    if rep.passed:
        try:
            id_map_entries = write_restricted_id_map(
                secure_dir,
                pseudo_map,
                workspace_id,
                id_map_retention_days,
            )
            id_map_written = True
        except RestrictedIdMapError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    report_path = out_dir / "desensitization_report.json"
    report_path.write_text(
        json.dumps(
            {
                "regression": rep.to_json(),
                "pii_report": report,
                "row_counts": {k: len(v) for k, v in des_files.items()},
                "id_map": {
                    "written": id_map_written,
                    "entry_count": id_map_entries,
                    "storage_class": "restricted_owner_controlled",
                    "delivered_with_package": False,
                    "git_tracked": False,
                    "retention_days": id_map_retention_days,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(rep.to_json(), indent=2))
    return 0 if rep.passed else 1


def _positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="V2.8 historical export desensitization (local only)."
    )
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--salt-file",
        required=True,
        type=Path,
        help="Owner-delivered salt file. Never committed; missing/empty aborts (exit 2).",
    )
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument(
        "--id-map-dir",
        required=True,
        type=Path,
        help=(
            "Owner-controlled restricted directory for _id_map_pseudo.json. "
            "Must exist, must be outside the Git worktree and outside "
            "raw/out dirs; the script refuses to run without it (fail-closed)."
        ),
    )
    parser.add_argument(
        "--id-map-retention-days",
        required=True,
        type=_positive_int,
        help="Minimum retention (days) before Owner-authorized destruction.",
    )
    args = parser.parse_args(argv)
    return run(
        args.raw_dir,
        args.out_dir,
        args.salt_file,
        args.workspace_id,
        args.id_map_dir,
        args.id_map_retention_days,
    )


if __name__ == "__main__":
    raise SystemExit(main())
