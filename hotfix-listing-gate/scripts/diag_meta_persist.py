"""Pin down why the DB meta was not persisted and the category stayed Lighting."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")

SETUP = """set -a
. /opt/nuotao/backend/.env 2>/dev/null
set +a
cd /opt/nuotao/backend
"""

CMDS = [
    ("A. deployed meta-persist block", r"""
grep -n 'wc_id_was_local\|new_wc_id\|listing_published_at\|Linked WooCommerce\|Adopting existing' \
  /opt/nuotao/backend/app/api/v1/endpoints/listing_publish.py
echo '--- block ---'
sed -n '262,290p' /opt/nuotao/backend/app/api/v1/endpoints/listing_publish.py
echo '--- persist block ---'
sed -n '366,400p' /opt/nuotao/backend/app/api/v1/endpoints/listing_publish.py
"""),
    ("B. full unfiltered log for that push", r"""
journalctl -u nuotao-backend --since '2026-09-20 07:42:40 UTC' --until '2026-09-20 07:44:00 UTC' \
  --no-pager 2>/dev/null | grep -vE 'UserWarning|BaseModel' | tail -40
"""),
    ("C. every WC product holding this SKU", SETUP + r""".venv/bin/python - <<'PYEOF'
import time, requests
from app.services.woocommerce_sync_service import _get_wc_auth, WC_URL, _get_wc_headers

base = str(WC_URL).rstrip("/")
h, a = _get_wc_headers(), _get_wc_auth()
for i in range(5):
    try:
        r = requests.get(f"{base}/wp-json/wc/v3/products", headers=h, auth=a,
                         params={"sku": "NT-YUEYE-OUTDOO-09200123", "per_page": 10,
                                 "status": "any"}, timeout=25)
        print("status:", r.status_code)
        if r.status_code == 200:
            print("total:", r.headers.get("x-wp-total"))
            for p in r.json():
                print("  id=%s status=%s sku=%r name=%r cat=%s" % (
                    p["id"], p["status"], p.get("sku"), p["name"][:45],
                    [c["name"] for c in (p.get("categories") or [])]))
        else:
            print(r.text[:200])
        break
    except Exception as exc:
        print("attempt", i + 1, "EXC", type(exc).__name__)
        time.sleep(1.5)
PYEOF
"""),
]


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    for label, cmd in CMDS:
        _, out, err = ssh.exec_command(cmd, timeout=240)
        data = out.read().decode("utf-8", "replace")
        et = err.read().decode("utf-8", "replace")
        print("\n" + "=" * 78, "\n### " + label, "\n" + "=" * 78, flush=True)
        print(data.rstrip()[:5500], flush=True)
        if et.strip():
            print("-- stderr --", et.rstrip()[:500], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
