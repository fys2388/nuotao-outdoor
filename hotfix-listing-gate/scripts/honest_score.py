"""Honest A++ accounting: what does the DB actually hold, and what did the payload send?"""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")

SETUP = """set -a
. /opt/nuotao/backend/.env 2>/dev/null
set +a
cd /opt/nuotao/backend
"""

PY = SETUP + r""".venv/bin/python - <<'PYEOF'
import asyncio

TARGET = "f865672b-2d98-4233-90cc-03b97aa743f6"

async def main() -> None:
    from app.core.database import async_session_factory
    from app.models.product import Product
    from app.services.listing_gate import build_wc_payload, get_english_copy, resolve_prices

    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        print("=== DB source of truth ===")
        print("  status      :", p.status)
        print("  name        :", (p.name or "")[:60])
        print("  weight_kg   :", p.weight_kg)
        print("  dimensions  :", p.dimensions)
        print("  tags        :", p.tags)
        print("  attributes  :", p.attributes)
        print("  source_url  :", p.source_url)
        print("  candidate?  :", bool(p.candidate_id) if hasattr(p, "candidate_id") else "n/a")
        meta = p.meta if isinstance(p.meta, dict) else {}
        print("  meta keys   :", sorted(meta.keys()))
        print("  meta.images :", meta.get("images"))
        print("  meta.brand  :", meta.get("brand"))
        print("  meta.sale_price :", meta.get("sale_price"))
        print("  meta.source   :", meta.get("source"))
        print("  meta.source_id:", meta.get("source_id"))
        print("  meta.source_url:", meta.get("source_url"))

        prices = resolve_prices(meta)
        print()
        print("  resolve_prices ->", prices)
        copy = get_english_copy(meta)
        payload = build_wc_payload(p, prices, copy)
        print()
        print("=== payload that gets pushed (weight/brand/images/attributes) ===")
        for k in ("weight", "dimensions", "manage_stock", "stock_quantity",
                  "stock_status", "categories", "tags", "images", "brand"):
            print(f"  {k:16s}: {payload.get(k)!r}")
        print("  keys:", sorted(payload.keys()))

        print()
        print("=== A++ rubric, scored only on data that actually exists ===")
        score = 0
        def add(label, pts, ok, note=""):
            nonlocal score
            if ok:
                score += pts
            print(f"  [{'+' if ok else ' '}] {pts:>2}  {label:<26} {note}")

        add("title", 10, bool(payload.get("name")))
        add("long desc >=600", 20, len(payload.get("description") or "") >= 600,
            f"{len(payload.get('description') or '')} chars")
        add("short desc", 10, bool(payload.get("short_description")))
        add("main image >=1", 15, bool(payload.get("images")),
            f"{len(payload.get('images') or [])} images in payload")
        add("price > 0", 10, float(payload.get("regular_price") or 0) > 0,
            repr(payload.get("regular_price")))
        add("category", 10, bool(payload.get("categories")))
        add("brand", 5, bool(payload.get("brand")), "no brand source anywhere in DB")
        add("SEO tags", 5, bool(payload.get("tags")))
        add("purchasability", 10,
            bool(payload.get("manage_stock") or payload.get("weight"))
            and bool(payload.get("dimensions")),
            f"weight={payload.get('weight')!r} dims={bool(payload.get('dimensions'))}")
        add("attributes", 5, bool(payload.get("attributes")),
            "build_wc_payload emits no attributes key at all")
        print()
        print("  honest score:", score, "/ 100")


asyncio.run(main())
PYEOF
"""


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    _, out, err = ssh.exec_command(PY, timeout=240)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print(data.rstrip(), flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:900], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
