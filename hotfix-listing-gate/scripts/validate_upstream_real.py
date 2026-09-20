"""Validate the upstream data path with a REAL 1688 fetch (no LLM, no writes)."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")

REMOTE = r'''import asyncio, json, sys

def p(*a):
    print(*a, flush=True)

async def main():
    from app.core.database import async_session_factory
    from app.models.product import Product
    from sqlalchemy import select

    p("step1: query DB")
    TARGETS = ["NT-QINGYE-OUTDOO-09181748", "NT-HIGH-MOON-09181750",
               "NT-HIGH-MOON-09181827", "NT-WILDFU-MOON-09191408"]
    async with async_session_factory() as s:
        rows = (await s.execute(
            select(Product).where(Product.sku.in_(TARGETS))
        )).scalars().all()
    p("step2: rows found =", len(rows))

    urls = {}
    for row in rows:
        src = (row.meta or {}).get("source_url") or row.source_url
        if src:
            urls[str(row.sku)] = src
    p("step3: with source_url =", len(urls))
    for sku, u in urls.items():
        p("   ", sku, "->", str(u)[:88])
    if not urls:
        p("no source_url available; cannot validate")
        return

    sku, url = next(iter(urls.items()))
    p()
    p("=== running production 1688 extractor on", sku, "===")
    from app.services.product_pipeline_service import _fetch_1688_product
    info = await asyncio.to_thread(_fetch_1688_product, url)
    p("wrapper keys:", sorted(info.keys()))
    p("  success :", info.get("success"))
    p("  error   :", repr(info.get("error"))[:200])
    p("  data keys:", sorted((info.get("data") or {}).keys()) if isinstance(info.get("data"), dict) else type(info.get("data")).__name__)
    info = info.get("data") or {}
    if not info:
        p("extractor produced no data; upstream source is not fetchable today")
        p("DONE")
        return
    p("  import_id   :", info.get("import_id"))
    p("  product_id  :", info.get("product_id"))
    p("  data_source :", info.get("data_source"))
    p("  elapsed     :", info.get("elapsed_time_seconds"), "s")
    info = info.get("product_info") or {}
    if not info:
        p("no product_info inside data; upstream source is not fetchable today")
        p("DONE")
        return
    p("  product_info keys:", sorted(info.keys()))
    p("  name      :", str(info.get("name"))[:70])
    p("  category  :", info.get("category"))
    p("  price     :", info.get("price"))
    p("  weight    :", repr(info.get("weight")))
    p("  dimensions:", repr(info.get("dimensions")))
    p("  source_id :", repr(info.get("source_id")))
    imgs = info.get("images") or []
    p("  images    :", len(imgs), "urls")
    for item in imgs[:3]:
        p("     -", str(item)[:96])

    p()
    p("=== through the new normalisers ===")
    import app.services.listing_gate as g
    media = g.normalise_listing_images(imgs)
    p("  normalise_listing_images:", len(media), "->", media[:2])
    p("  parse_dimensions        :", g.parse_dimensions(info.get("dimensions")))
    attrs = g.collect_attributes(info)
    p("  collect_attributes      :", json.dumps(attrs, ensure_ascii=False)[:280])
    p()
    p("A++-relevant fields available from this real source:")
    p(f"  images(15)    : {'YES' if media else 'no'} ({len(media)})")
    p(f"  dimensions    : {'YES' if g.parse_dimensions(info.get('dimensions')) else 'no'}")
    p(f"  weight(10)    : {'YES' if info.get('weight') else 'no'} ({info.get('weight')!r})")
    p(f"  attributes(5) : {'YES' if attrs else 'no'}")
    p("  brand(5)      : NO - extractor never produces a brand field")
    p("DONE")

asyncio.run(main())
'''


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    with sftp.open("/tmp/validate_upstream.py", "w") as fh:
        fh.write(REMOTE.encode("utf-8"))
    sftp.close()
    script = (
        "set -a\n. /opt/nuotao/backend/.env 2>/dev/null\nset +a\n"
        "cd /opt/nuotao/backend\n.venv/bin/python -u /tmp/validate_upstream.py"
    )
    _, out, err = ssh.exec_command(script, timeout=120)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print(data.rstrip(), flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:900], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
