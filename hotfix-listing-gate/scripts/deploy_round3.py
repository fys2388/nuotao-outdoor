"""Round 3 deploy: persist pipeline media/taxonomy + emit single-value attributes.

Anchor-asserted, backed up, compile-checked, restarted, health-checked.
Rolls back automatically if any anchor is missing or the compile fails.
"""

from __future__ import annotations

import os
import sys
import time
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
HOST = "95.217.218.178"
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
BACKUP = f"/opt/nuotao/backups/listing-gate-{STAMP}"
PATCH_DIR = "/tmp/listing-gate-patch3"
BACKEND = "/opt/nuotao/backend"

PIPELINE = f"{BACKEND}/app/services/product_pipeline_service.py"
GATE = f"{BACKEND}/app/services/listing_gate.py"

# ------------------------------------------------------------------- run -----
def run(ssh: paramiko.SSHClient, script: str, timeout: int = 900, label: str = "") -> int:
    print(f"\n{'=' * 78}\n### {label or (script.splitlines()[0][:70])}\n{'=' * 78}", flush=True)
    _, out, err = ssh.exec_command(script, timeout=timeout)
    data = out.read().decode("utf-8", "replace")
    etext = err.read().decode("utf-8", "replace")
    code = out.channel.recv_exit_status()
    print(data.rstrip(), flush=True)
    if etext.strip():
        print("-- stderr --", etext.rstrip(), flush=True)
    print(f"[exit {code}]", flush=True)
    return code


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=HOST, port=22, username="root", key_filename=KEY, timeout=20)
    print(f"connected to {HOST}", flush=True)

    run(ssh, f"mkdir -p {BACKUP} {PATCH_DIR}", label="0. prepare dirs", timeout=60)

    # upload the new gate module
    here = os.path.dirname(os.path.abspath(__file__))
    local_gate = os.path.normpath(os.path.join(here, "..", "backend", "app", "services", "listing_gate.py"))
    sftp = ssh.open_sftp()
    sftp.put(local_gate, f"{PATCH_DIR}/listing_gate.py")
    with sftp.open(f"{PATCH_DIR}/patch_pipeline.py", "w") as fh:
        fh.write(PATCH_PIPELINE_PY.encode("utf-8"))
    sftp.close()
    print("uploaded listing_gate.py + patch_pipeline.py", flush=True)

    rc = run(ssh, f"""set -e
cp -a {PIPELINE} {BACKUP}/product_pipeline_service.py
cp -a {GATE} {BACKUP}/listing_gate.py
cp {PATCH_DIR}/listing_gate.py {GATE}
echo "backed up to {BACKUP}:"
ls -la {BACKUP}""",
             label="1. backup + install listing_gate.py", timeout=120)
    if rc:
        return rc

    rc = run(ssh, f"cd {BACKEND} && .venv/bin/python {PATCH_DIR}/patch_pipeline.py",
             label="2. anchor-patch run_v3_gate", timeout=120)
    if rc:
        print("PIPELINE PATCH FAILED - restoring", flush=True)
        run(ssh, f"cp {BACKUP}/product_pipeline_service.py {PIPELINE}", label="restore pipeline")
        return rc

    rc = run(ssh, f"cd {BACKEND} && .venv/bin/python -m compileall -q "
                  f"app/services/listing_gate.py app/services/product_pipeline_service.py "
                  f"app/api/v1/endpoints/listing_publish.py && echo 'compile-ok'",
             label="3. compile backend", timeout=180)
    if rc:
        print("COMPILE FAILED - restoring both", flush=True)
        run(ssh, f"cp {BACKUP}/product_pipeline_service.py {PIPELINE}; "
                 f"cp {BACKUP}/listing_gate.py {GATE}", label="restore backend")
        return rc

    rc = run(ssh, "systemctl restart nuotao-backend && sleep 2 && systemctl is-active nuotao-backend",
             label="4. restart backend", timeout=120)
    if rc:
        return rc

    run(ssh, f"""for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:8000/api/v1/readyz || echo 000)
  echo "attempt $i readyz=$code"
  [ "$code" = "200" ] && break
  sleep 3
done""", label="5. wait for readyz", timeout=180)

    run(ssh, f"""echo '== helpers in deployed gate =='
grep -n 'def normalise_listing_images\\|def normalise_listing_tags\\|def parse_dimensions\\|def collect_attributes' {GATE}
echo '== single-value attributes enabled =='
grep -n '_MAX_ATTRIBUTES\\|_MAX_ATTRIBUTE_OPTIONS\\|_MAX_IMAGES' {GATE} | head -5
echo '== run_v3_gate patch present =='
grep -n 'BUG-13\\|listing_media\\|flag_modified' {PIPELINE} | head -12
echo '== import smoke =='
cd {BACKEND} && .venv/bin/python -c "
import app.services.listing_gate as g
import app.api.v1.endpoints.listing_publish as lp
import app.services.product_pipeline_service as pp
print('  gate helpers ok:', all(callable(getattr(g,n)) for n in
    ['normalise_listing_images','normalise_listing_tags','parse_dimensions','collect_attributes']))
print('  pipeline module ok:', callable(pp.run_v3_gate))
print('  publish budget:', lp._PUSH_BUDGET_SECONDS)
print('  chair category:', g.category_for_product(type('P',(),{'category':None})(), 'Moon Chair: Lightweight for Camping'))
"
echo ALL DONE""", label="6. verify deployment", timeout=180)

    ssh.close()
    return 0


PATCH_PIPELINE_PY = r'''
"""Anchor-asserted patch for run_v3_gate: persist pipeline media/taxonomy."""
import pathlib
import sys

TARGET = "/opt/nuotao/backend/app/services/product_pipeline_service.py"
anchor = """        session.add(product)
    await session.flush()

    evaluation = await evaluate_product("""
replacement = """        session.add(product)

    # BUG-13 (2026-09-20): listing_data already carries the media and taxonomy
    # this pipeline produced - 1688 originals + AI-generated images, tags - and
    # product_info carries the parsed weight / dimensions / attributes. None of
    # it was persisted here, so every product reached the store without a main
    # image, tags or attributes. listing_data only went back to the caller in
    # the pipeline result; it never reached the product row.
    from sqlalchemy.orm.attributes import flag_modified
    from app.services.listing_gate import (
        collect_attributes,
        normalise_listing_images,
        normalise_listing_tags,
        parse_dimensions,
    )

    listing_media = normalise_listing_images(
        listing_data.get("main_images") or listing_data.get("images")
    )
    listing_tag_names = normalise_listing_tags(listing_data.get("tags"))
    listing_attrs = collect_attributes(product_info)
    listing_dims = parse_dimensions(product_info.get("dimensions"))

    if listing_media and not (product.meta or {}).get("main_images"):
        product.meta = {**(product.meta or {}), "main_images": listing_media}
    if listing_tag_names and not product.tags:
        product.tags = listing_tag_names
    if listing_attrs and not product.attributes:
        product.attributes = listing_attrs
    if listing_dims and not product.dimensions:
        product.dimensions = listing_dims

    # The products JSON columns are plain JSON with no MutableDict, so plain
    # reassignment is not reliably flushed. Flag each column we actually touched
    # - this is the pattern that verifiably persisted in production.
    if listing_media:
        flag_modified(product, "meta")
    if listing_tag_names:
        flag_modified(product, "tags")
    if listing_attrs:
        flag_modified(product, "attributes")
    if listing_dims:
        flag_modified(product, "dimensions")
    if product.weight_kg is None:
        product.weight_kg = _parse_weight_kg(product_info.get("weight"))

    await session.flush()

    evaluation = await evaluate_product("""

path = pathlib.Path(TARGET)
src = path.read_text(encoding="utf-8")
if "BUG-13" in src:
    print("pipeline already patched; skipping")
    sys.exit(0)
count = src.count(anchor)
if count != 1:
    print(f"ANCHOR PROBLEM: {count} matches (need exactly 1)")
    sys.exit(2)
path.write_text(src.replace(anchor, replacement), encoding="utf-8")
print("pipeline patched: run_v3_gate now persists images/tags/attributes/dimensions")
'''


if __name__ == "__main__":
    raise SystemExit(main())
