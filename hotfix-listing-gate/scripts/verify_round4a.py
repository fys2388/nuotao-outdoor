"""Verify the deployed round-4a chain end to end: Newton -> convert -> product_info."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
SETUP = "set -a\n. /opt/nuotao/backend/.env 2>/dev/null\nset +a\ncd /opt/nuotao/backend\n"

REMOTE = r'''import asyncio, json, time

def p(*a):
    print(*a, flush=True)

async def main():
    from app.services.product_pipeline_service import (
        _fetch_1688_product, convert_1688_to_pipeline_input, _parse_weight_kg,
    )
    from app.services.newton_agent_service import extract_1688_product

    url = "https://detail.1688.com/offer/771641344658.html"
    pid = "771641344658"

    p("=== A. deployed max_wait default ===")
    import inspect
    p("  extract_1688_product.max_wait =",
      inspect.signature(extract_1688_product).parameters["max_wait"].default)

    p()
    p("=== B. full _fetch_1688_product (production path, deployed code) ===")
    t0 = time.monotonic()
    wrapped = await asyncio.to_thread(_fetch_1688_product, url)
    p(f"  elapsed {time.monotonic()-t0:.0f}s success={wrapped.get('success')}")
    p(f"  error={str(wrapped.get('error'))[:200]}")
    data = wrapped.get("data") or {}
    p(f"  data_source={data.get('data_source')}")
    info = data.get("product_info") or {}
    if not info:
        p("  NO product_info")
        return
    p("  product_info keys:", sorted(info.keys()))
    for k in ("name", "category", "price", "weight", "dimensions", "images",
              "materials", "sku", "supplier"):
        p(f"    {k:14s}: {str(info.get(k))[:150]}")
    p(f"    {'attributes':14s}: {json.dumps(info.get('attributes'), ensure_ascii=False)[:300]}")

    p()
    p("=== C. what A++ fields become available ===")
    import app.services.listing_gate as g
    media = g.normalise_listing_images(info.get("images"))
    dims = g.parse_dimensions(info.get("dimensions"))
    attrs = g.collect_attributes(info)
    p(f"    主图 images(15)  : {'YES' if media else 'no'} ({len(media)})")
    p(f"    weight(10)       : {'YES' if info.get('weight') else 'no'} ({info.get('weight')!r})")
    p(f"    dimensions(10)   : {'YES' if dims else 'no'} ({dims})")
    p(f"    attributes(5)    : {'YES' if attrs else 'no'} ({json.dumps(attrs, ensure_ascii=False)[:120]})")
    p()
    p("DONE")

asyncio.run(main())
'''


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    with sftp.open("/tmp/verify4a.py", "w") as fh:
        fh.write(REMOTE.encode("utf-8"))
    sftp.close()
    _, out, err = ssh.exec_command(SETUP + ".venv/bin/python -u /tmp/verify4a.py", timeout=600)
    print(out.read().decode("utf-8", "replace").rstrip(), flush=True)
    et = err.read().decode("utf-8", "replace")
    if et.strip():
        print("-- stderr --", et.rstrip()[:600], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
