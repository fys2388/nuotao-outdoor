#!/usr/bin/env python3
"""Apply the listing-gate hotfix on the Nuotao production server.

Design goals (server-side code may carry uncommitted changes, so):
  * ADD new modules, never overwrite an existing production file.
  * Every modification to an existing file is an anchor-asserted insertion /
    replacement; a missing or duplicated anchor aborts before writing.
  * Full rollback backup is written to /opt/nuotao/backups/ first.
  * Backend syntax + import smoke check runs before anything is restarted.

Usage: apply_patch.py --patch-dir DIR [--backend /opt/nuotao/backend]
                            [--frontend /opt/nuotao/frontend] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import subprocess
import sys
from pathlib import Path

BACKUP_ROOT = "/opt/nuotao/backups"

NEW_FILES = [
    ("backend/app/services/listing_gate.py", "app/services/listing_gate.py"),
    ("backend/app/api/v1/endpoints/listing_publish.py",
     "app/api/v1/endpoints/listing_publish.py"),
]

ROUTER_ANCHOR = "api_router.include_router(products.router)"
ROUTER_INSERT = (
    "# [listing-gate hotfix] Gate-controlled publish route. Registered before\n"
    "# products.router so POST /products/{id}/push-woocommerce is served by the\n"
    "# gated endpoint; all other products.py routes stay intact.\n"
    "import importlib as _listing_gate_il\n"
    "api_router.include_router(\n"
    "    _listing_gate_il.import_module("
    "'app.api.v1.endpoints.listing_publish').router\n"
    ")\n"
)


def sh(cmd: list[str], cwd: str | None = None) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=cwd)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patch-dir", required=True)
    parser.add_argument("--backend", default="/opt/nuotao/backend")
    parser.add_argument("--frontend", default="/opt/nuotao/frontend")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    patch_dir = Path(args.patch_dir)
    backend = Path(args.backend)
    frontend = Path(args.frontend)
    stamp = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup_dir = Path(BACKUP_ROOT) / f"listing-gate-{stamp}"

    print(f"patch_dir   = {patch_dir}", flush=True)
    print(f"backend     = {backend}", flush=True)
    print(f"frontend    = {frontend}", flush=True)
    print(f"backup_dir  = {backup_dir}", flush=True)

    # ---- 0. preflight ---------------------------------------------------
    failures: list[str] = []
    for label, path in (("patch", patch_dir), ("backend", backend), ("frontend", frontend)):
        if not path.is_dir():
            failures.append(f"{label} dir missing: {path}")
    for rel, _ in NEW_FILES:
        if not (patch_dir / rel).is_file():
            failures.append(f"patch file missing: {patch_dir / rel}")
    if failures:
        print("PREFLIGHT FAILED:", flush=True)
        for item in failures:
            print(f"  - {item}", flush=True)
        return 2

    print("\n[0/6] preflight OK", flush=True)

    # ---- 1. backup ------------------------------------------------------
    if not args.dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)

    targets_to_backup = [
        (backend / "app/api/v1/router.py", "router.py"),
        (frontend / "src/pages/ProductPublish.tsx", "ProductPublish.tsx"),
    ]
    print("\n[1/6] backing up files that will be touched", flush=True)
    for src, name in targets_to_backup:
        if src.is_file():
            if not args.dry_run:
                shutil.copy2(src, backup_dir / name)
            print(f"  backup {src} -> {backup_dir / name}", flush=True)
        else:
            failures.append(f"target file missing (cannot patch safely): {src}")
            print(f"  MISSING {src}", flush=True)
    for rel, target_rel in NEW_FILES:
        target = backend / target_rel
        if target.is_file():
            dest = backup_dir / (target_rel.replace("/", "__"))
            if not args.dry_run:
                shutil.copy2(target, dest)
            print(f"  backup existing {target} -> {dest}", flush=True)
        else:
            print(f"  (no pre-existing {target}; new file)", flush=True)

    if failures:
        print("\nPREFLIGHT FAILED, nothing written:", flush=True)
        for item in failures:
            print(f"  - {item}", flush=True)
        return 2

    # ---- 2. new modules -------------------------------------------------
    print("\n[2/6] installing new modules", flush=True)
    for rel, target_rel in NEW_FILES:
        src = patch_dir / rel
        target = backend / target_rel
        if not args.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        print(f"  {src} -> {target}", flush=True)

    # ---- 3. router.py ---------------------------------------------------
    print("\n[3/6] registering the gate-controlled publish route", flush=True)
    router_path = backend / "app/api/v1/router.py"
    router_src = read_text(router_path)
    count = router_src.count(ROUTER_ANCHOR)
    print(f"  anchor '{ROUTER_ANCHOR}' occurrences = {count}", flush=True)
    if count != 1:
        print("  ABORT: router anchor count is not exactly 1", flush=True)
        return 3
    if "listing_publish" in router_src:
        print("  router already references listing_publish; skipping", flush=True)
    elif not args.dry_run:
        write_text(router_path, router_src.replace(ROUTER_ANCHOR, ROUTER_INSERT + ROUTER_ANCHOR, 1))
        print(f"  patched {router_path}", flush=True)
    else:
        print("  (dry-run) would insert registration above the products router", flush=True)

    # ---- 4. frontend field name ----------------------------------------
    print("\n[4/6] aligning frontend copy field name", flush=True)
    tsx_path = frontend / "src/pages/ProductPublish.tsx"
    tsx_src = read_text(tsx_path)
    occurrences = tsx_src.count(".bullets")
    print(f"  '.bullets' occurrences = {occurrences}", flush=True)
    if occurrences:
        if "bullet_points" in tsx_src:
            print("  already uses .bullet_points somewhere; replacing .bullets only", flush=True)
        if not args.dry_run:
            write_text(tsx_path, tsx_src.replace(".bullets", ".bullet_points"))
            print(f"  patched {tsx_path} ({occurrences} site(s))", flush=True)
        else:
            print("  (dry-run) would replace .bullets -> .bullet_points", flush=True)
    else:
        print("  '.bullets' not found - frontend may already be correct; skipping", flush=True)

    # ---- 5. verify ------------------------------------------------------
    print("\n[5/6] backend syntax check", flush=True)
    python_bin = backend / ".venv/bin/python"
    if not python_bin.is_file():
        python_bin = Path(sys.executable)
    syntax_status = sh([str(python_bin), "-m", "compileall", "-q", "app"], cwd=str(backend))
    if syntax_status != 0:
        print("SYNTAX CHECK FAILED - restore backup and abort", flush=True)
        return 4

    print("\n[6/6] import smoke check (new modules + router registration)", flush=True)
    smoke = (
        "import app.api.v1.router as r\n"
        "import app.services.listing_gate as g\n"
        "print('gate module ok:', sorted(getattr(g, 'HARD_BLOCK', [])))\n"
        "print('total routes:', len(r.api_router.routes))\n"
        "for route in r.api_router.routes:\n"
        "    path = getattr(route, 'path', '')\n"
        "    methods = getattr(route, 'methods', None)\n"
        "    if 'push-woocommerce' in path:\n"
        "        print('  push-woocommerce route:', sorted(methods), path)\n"
    )
    smoke_status = sh([str(python_bin), "-c", smoke], cwd=str(backend))
    if smoke_status != 0:
        print("IMPORT SMOKE FAILED - restore backup and abort", flush=True)
        return 5

    print("\nPATCH APPLIED OK" + (" (dry-run)" if args.dry_run else ""), flush=True)
    if not args.dry_run:
        print(f"rollback backup: {backup_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
