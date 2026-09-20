"""End-to-end data flow proof: Newton -> product_info -> listing_data -> WC payload."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
SETUP = "set -a\n. /opt/nuotao/backend/.env 2>/dev/null\nset +a\ncd /opt/nuotao/backend\n"

REMOTE = r'''import asyncio, json, time

def p(*a):
    print(*a, flush=True)

async def main():
    from app.core.database import async_session_factory
    from app.models.product import Product
    from sqlalchemy import select
    import app.services.product_pipeline_service as pp
    import app.services.listing_gate as g

    p("=== 1. pick a product that has a source_url ===")
    async with async_session_factory() as s:
        rows = (await s.execute(
            select(Product).where(Product.source_url.isnot(None),
                                  Product.deleted_at.is_(None))
        )).scalars().all()
    targets = [(str(r.sku), r.source_url) for r in rows if r.source_url]
    p(f"  products with source_url: {len(targets)}")
    if not targets:
        p("  none available"); return
    sku, url = targets[0]
    p(f"  testing: {sku}")
    p(f"  source   : {url[:90]}")

    p()
    p("=== 2. fetch via production path (Newton) ===")
    t0 = time.monotonic()
    wrapped = await asyncio.to_thread(pp._fetch_1688_product, url)
    p(f"  elapsed {time.monotonic()-t0:.0f}s success={wrapped.get('success')} "
      f"source={((wrapped.get('data') or {}).get('data_source'))}")
    info = (wrapped.get("data") or {}).get("product_info") or {}
    if not info:
        p("  fetch failed:", str(wrapped.get("error"))[:200]); return

    p()
    p("=== 3. what the pipeline now yields ===")
    for k in ("name", "category", "price", "weight", "dimensions", "images",
              "materials", "description"):
        p(f"  {k:14s}: {str(info.get(k))[:110]}")
    p(f"  {'attributes':14s}: {len(info.get('attributes') or [])} entries")
    p(f"  {'supplier':14s}: {str(info.get('supplier'))[:80]}")

    p()
    p("=== 4. build WC payload as the gate would ===")
    listing = pp._generate_listing_data(info, None, None)
    p("  listing keys:", sorted(listing.keys()))
    p(f"  listing.images    : {len(listing.get('images') or [])}")
    p(f"  listing.main_images: {len(listing.get('main_images') or [])}")
    p(f"  listing.tags      : {len(listing.get('tags') or [])}")

    fake = type("P", (), {
        "sku": info.get("sku") or "TEST",
        "name": info.get("name") or "test",
        "description": info.get("description") or "test",
        "status": "draft",
        "tags": listing.get("tags") or [],
        "attributes": g.collect_attributes(info),
        "weight_kg": pp._parse_weight_kg(info.get("weight")),
        "dimensions": g.parse_dimensions(info.get("dimensions")),
        "brand": None,
        "meta": {"main_images": listing.get("main_images") or listing.get("images")},
    })()
    prices = g.resolve_prices({"sale_price": None, "price": info.get("price")})
    loc = {"title": info.get("name"), "description": info.get("description"),
           "short_description": (info.get("description") or "")[:200]}
    payload = g.build_wc_payload(fake, prices, loc)

    p()
    p("=== 5. A++ rubric on the resulting payload ===")
    score = 0
    def add(lbl, pts, ok, note=""):
        nonlocal score
        if ok: score += pts
        p(f"  [{'+' if ok else ' '}] {pts:>2}  {lbl:<14}{note}")
    add("title", 10, bool(payload.get("name")))
    add("long desc", 20, len(payload.get("description") or "") >= 600,
        f"({len(payload.get('description') or '')})")
    add("short desc", 10, bool(payload.get("short_description")))
    add("main image", 15, len(payload.get("images") or []) >= 1,
        f"({len(payload.get('images') or [])})")
    add("price", 10, float(payload.get("regular_price") or 0) > 0,
        f"({payload.get('regular_price')})")
    add("category", 10, bool(payload.get("categories")),
        f"({payload.get('categories')})")
    add("brand", 5, bool(payload.get("brand")))
    add("SEO tags", 5, bool(payload.get("tags")), f"({len(payload.get('tags') or [])})")
    add("purchasability", 10, bool(payload.get("weight")) and bool(payload.get("dimensions"))
        and payload.get("stock_status") == "instock",
        f"(w={payload.get('weight')} d={payload.get('dimensions')} s={payload.get('stock_status')})")
    add("attributes", 5, bool(payload.get("attributes")),
        f"({len(payload.get('attributes') or [])} groups)")
    grade = ("A++" if score >= 90 else "A+" if score >= 80 else "A" if score >= 70
             else "B+" if score >= 60 else "B")
    p()
    p(f"  >>> SCORE: {score}/100  ->  {grade}")
    p()
    p("DONE")

asyncio.run(main())
'''


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    with sftp.open("/tmp/e2e_flow.py", "w") as fh:
        fh.write(REMOTE.encode("utf-8"))
    sftp.close()
    _, out, err = ssh.exec_command(SETUP + ".venv/bin/python -u /tmp/e2e_flow.py", timeout=600)
    print(out.read().decode("utf-8", "replace").rstrip(), flush=True)
    et = err.read().decode("utf-8", "replace")
    if et.strip():
        print("-- stderr --", et.rstrip()[:700], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
