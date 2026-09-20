"""One authoritative check: is the loop actually closed right now?"""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
SETUP = "set -a\n. /opt/nuotao/backend/.env 2>/dev/null\nset +a\ncd /opt/nuotao/backend\n"

REMOTE = r'''import json

def p(*a):
    print(*a, flush=True)

p("=== 1. DB row (Moon Chair) ===")
import asyncio
from app.core.database import async_session_factory
from app.models.product import Product

async def read():
    async with async_session_factory() as s:
        pr = await s.get(Product, "f865672b-2d98-4233-90cc-03b97aa743f6")
    m = pr.meta or {}
    return pr, m

pr, m = asyncio.run(read())
p("  woocommerce_id      :", m.get("woocommerce_id"))
p("  listing_published_by:", m.get("listing_published_by"))
p("  listing_published_price:", m.get("listing_published_price"))
p("  listing_published_at:", m.get("listing_published_at"))
p("  status              :", pr.status)
p("  candidate_status    :", pr.candidate_status)

p()
p("=== 2. WC product 2106 ===")
import requests, time
from app.services.woocommerce_sync_service import _get_wc_auth, _get_wc_headers, WC_URL
base = str(WC_URL).rstrip("/")
h, a = _get_wc_headers(), _get_wc_auth()
for i in range(5):
    try:
        r = requests.get(f"{base}/wp-json/wc/v3/products/2106", headers=h, auth=a, timeout=25)
        break
    except Exception:
        time.sleep(1.5)
if r.status_code != 200:
    p("  WC call failed:", r.status_code, r.text[:120])
else:
    w = r.json()
    p("  status        :", w.get("status"))
    p("  sku           :", w.get("sku"))
    p("  regular_price :", repr(w.get("regular_price")))
    p("  categories    :", [c["name"] for c in (w.get("categories") or [])])
    p("  tags          :", len(w.get("tags") or []))
    p("  images        :", len(w.get("images") or []))
    p("  description   :", len(w.get("description") or ""), "chars")
    p("  short_desc    :", len(w.get("short_description") or ""), "chars")
    p("  weight        :", repr(w.get("weight")))
    p("  dimensions    :", w.get("dimensions"))
    p("  permalink     :", w.get("permalink"))

p()
p("=== 3. duplicate check by SKU ===")
for i in range(5):
    try:
        r2 = requests.get(f"{base}/wp-json/wc/v3/products", headers=h, auth=a,
                          params={"sku": "NT-YUEYE-OUTDOO-09200123", "per_page": 10,
                                  "status": "any"}, timeout=25)
        break
    except Exception:
        time.sleep(1.5)
p("  x-wp-total:", r2.headers.get("x-wp-total"))

p()
p("=== 4. A++ rubric (from the real WC row) ===")
w = r.json() if r.status_code == 200 else {}
sc = 0
def add(lbl, pts, ok, note=""):
    global sc
    if ok:
        sc += pts
    p(f"  [{'+' if ok else ' '}] {pts:>2}  {lbl:<16}{note}")
add("title", 10, bool(w.get("name")))
add("long desc", 20, len(w.get("description") or "") >= 600,
    f"({len(w.get('description') or '')})")
add("short desc", 10, bool(w.get("short_description")))
add("main image", 15, len(w.get("images") or []) >= 1,
    f"({len(w.get('images') or [])})")
add("price", 10, float(w.get("regular_price") or 0) > 0)
add("category", 10, bool(w.get("categories")),
    f"({[c['name'] for c in (w.get('categories') or [])]})")
add("brand", 5, bool(w.get("brand")))
add("SEO tags", 5, bool(w.get("tags")))
add("purchasability", 10, bool(w.get("weight")) and bool(w.get("dimensions"))
    and w.get("stock_status") == "instock")
add("attributes", 5, bool(w.get("attributes")))
grade = ("A++" if sc >= 90 else "A+" if sc >= 80 else "A" if sc >= 70
         else "B+" if sc >= 60 else "B")
p()
p(f"  SCORE: {sc} / 100  ->  {grade}")
p()
p("DONE")
'''


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    with sftp.open("/tmp/loop_check.py", "w") as fh:
        fh.write(REMOTE.encode("utf-8"))
    sftp.close()
    _, out, err = ssh.exec_command(SETUP + ".venv/bin/python -u /tmp/loop_check.py",
                                   timeout=300)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print(data.rstrip(), flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:600], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
