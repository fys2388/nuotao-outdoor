"""Clear the diagnostic residue (weight / dimensions) from WC 2106.

Only those two fields. stock_quantity / manage_stock / stock_status come from the
deployed build_wc_payload defaults, not from a diagnostic PUT, so they are left
untouched and reported separately.
"""

from __future__ import annotations

import json
import os
import time
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")

SETUP = """set -a
. /opt/nuotao/backend/.env 2>/dev/null
set +a
cd /opt/nuotao/backend
"""

PY = SETUP + r""".venv/bin/python - <<'PYEOF'
import json, time, requests
from app.services.woocommerce_sync_service import _get_wc_auth, WC_URL, _get_wc_headers

base = str(WC_URL).rstrip("/")
h, a = _get_wc_headers(), _get_wc_auth()

def call(method, url, **kw):
    for i in range(6):
        try:
            return requests.request(method, url, headers=h, auth=a, timeout=30, **kw)
        except Exception as exc:
            print("  attempt", i + 1, "transport error", type(exc).__name__)
            time.sleep(1.5)
    raise SystemExit("gave up")

r = call("GET", f"{base}/wp-json/wc/v3/products/2106")
assert r.status_code == 200, r.text[:200]
before = r.json()
print("BEFORE  weight =", repr(before.get("weight")), " dims =", before.get("dimensions"))

patch_variants = [
    ("nested empty strings", {
        "weight": "",
        "dimensions": {"length": "", "width": "", "height": ""},
    }),
    ("nested nulls", {
        "weight": None,
        "dimensions": {"length": None, "width": None, "height": None},
    }),
]

for label, patch in patch_variants:
    r2 = call("PUT", f"{base}/wp-json/wc/v3/products/2106", json=patch)
    print(f"PUT [{label}] -> {r2.status_code}")
    if r2.status_code != 200:
        print("  body:", r2.text[:400])
    time.sleep(1)
    r3 = call("GET", f"{base}/wp-json/wc/v3/products/2106")
    after = r3.json()
    print("  now weight =", repr(after.get("weight")),
          " dims =", after.get("dimensions"))
    if after.get("weight") == "" and not any(after.get("dimensions") or {}):
        print(f"  -> cleared by [{label}]")
        break

r3 = call("GET", f"{base}/wp-json/wc/v3/products/2106")
after = r3.json()
print()
print("FINAL weight =", repr(after.get("weight")), " dims =", after.get("dimensions"))
print()
print("untouched fields left as-is (from build_wc_payload defaults):")
print("  manage_stock   =", after.get("manage_stock"))
print("  stock_quantity =", after.get("stock_quantity"))
print("  stock_status   =", after.get("stock_status"))
print("  categories     =", [c["name"] for c in (after.get("categories") or [])])
print("  regular_price  =", repr(after.get("regular_price")))
print("  status         =", after.get("status"))
print()
print("residue cleared:", after.get("weight") == "" and not any(after.get("dimensions") or {}))
PYEOF
"""


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    _, out, err = ssh.exec_command(PY, timeout=300)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print(data.rstrip(), flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:700], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
