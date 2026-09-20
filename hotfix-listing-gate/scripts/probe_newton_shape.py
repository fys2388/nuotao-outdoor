"""Probe the actual Newton product payload shape + WC measurement units."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
SETUP = "set -a\n. /opt/nuotao/backend/.env 2>/dev/null\nset +a\ncd /opt/nuotao/backend\n"

REMOTE = r'''import json, time, requests

def p(*a):
    print(*a, flush=True)

p("=== 1. Newton product payload shape (live fetch) ===")
from app.services.newton_agent_service import extract_1688_product
r = extract_1688_product("https://detail.1688.com/offer/771641344658.html",
                         "771641344658", max_wait=300)
p("  success:", r.get("success"), "status:", r.get("status"))
prod = r.get("product") or {}
p("  product type:", type(prod).__name__, "keys:", sorted(prod.keys()) if isinstance(prod, dict) else None)
if isinstance(prod, dict):
    for k in sorted(prod):
        v = prod[k]
        if isinstance(v, (list, dict)):
            p(f"    {k:16s}: {type(v).__name__} len={len(v)}")
            p(f"                   preview: {json.dumps(v, ensure_ascii=False, default=str)[:280]}")
        else:
            p(f"    {k:16s}: {str(v)[:200]}")

p()
p("=== 2. feed it through convert_1688_to_pipeline_input ===")
from app.services.product_pipeline_service import convert_1688_to_pipeline_input
try:
    info = convert_1688_to_pipeline_input(r, source_url="https://detail.1688.com/offer/771641344658.html",
                                          source_id="771641344658")
    for k in ("name", "category", "price", "description", "core_selling_points",
              "materials", "dimensions", "weight", "images", "sku", "supplier"):
        p(f"    {k:20s}: {str(info.get(k))[:170]}")
    p("    has 'attributes' key:", "attributes" in info)
except Exception as exc:
    p("  convert FAILED:", repr(exc)[:300])

p()
p("=== 3. WC store measurement units ===")
from app.services.woocommerce_sync_service import _get_wc_auth, _get_wc_headers, WC_URL
base = str(WC_URL).rstrip("/")
h, a = _get_wc_headers(), _get_wc_auth()
for path, note in (("/wp-json/wc/v3/settings", "settings"),
                   ("/wp-json/wp/v2/settings", "wp settings")):
    for i in range(4):
        try:
            rr = requests.get(base + path, headers=h, auth=a, timeout=25)
            break
        except Exception:
            time.sleep(1.5)
    p(f"  {note}: HTTP {rr.status_code}")
    if rr.status_code == 200:
        try:
            body = rr.json()
        except Exception:
            body = rr.text[:200]
        s = json.dumps(body, ensure_ascii=False, default=str)
        for needle in ("weight", "dimension", "measurement"):
            idx = s.lower().find(needle)
            while idx != -1:
                p("    ...", s[max(0, idx-40):idx+70])
                idx = s.lower().find(needle, idx+1)
                if idx > 0 and idx < 4000:
                    continue
                break
p()
p("PROBE_DONE")
'''


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    with sftp.open("/tmp/probe.py", "w") as fh:
        fh.write(REMOTE.encode("utf-8"))
    sftp.close()
    _, out, err = ssh.exec_command(SETUP + ".venv/bin/python -u /tmp/probe.py", timeout=900)
    print(out.read().decode("utf-8", "replace").rstrip(), flush=True)
    et = err.read().decode("utf-8", "replace")
    if et.strip():
        print("-- stderr --", et.rstrip()[:700], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
