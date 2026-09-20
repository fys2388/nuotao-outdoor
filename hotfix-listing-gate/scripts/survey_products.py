"""Quantify the upstream gap across all 27 draft products, and see where
listing_data ends up after the gate."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
SVC = "/opt/nuotao/backend/app/services/product_pipeline_service.py"

CMDS = [
    ("A. run_pipeline tail: what happens to listing_data after the gate", r"""
sed -n '800,930p' %s
""" % SVC),
    ("B. survey all 27 products: which fields exist at all", r"""
set -a
. /opt/nuotao/backend/.env 2>/dev/null
set +a
cd /opt/nuotao/backend
.venv/bin/python - <<'PYEOF'
import asyncio

async def main() -> None:
    from sqlalchemy import select
    from app.core.database import async_session_factory
    from app.models.product import Product

    async with async_session_factory() as s:
        rows = (await s.execute(
            select(Product).where(Product.deleted_at.is_(None))
        )).scalars().all()
        print(f"{'SKU':<32} {'src_url':<7} {'meta_imgs':<9} {'tags':<5} "
              f"{'attrs':<6} {'brand':<6} {'wt':<5} {'dims':<5} {'wc_id':<6} status")
        n_src = n_img = n_tag = n_attr = n_brand = n_wt = n_dim = n_wc = 0
        for p in rows:
            m = p.meta if isinstance(p.meta, dict) else {}
            imgs = m.get("images") or m.get("main_images") or []
            has_src = bool(m.get("source_url") or p.source_url)
            has_img = bool(imgs)
            has_tag = bool(p.tags)
            has_attr = bool(p.attributes)
            has_brand = bool(m.get("brand"))
            has_wt = p.weight_kg is not None
            has_dim = bool(p.dimensions)
            has_wc = bool(m.get("woocommerce_id"))
            n_src += has_src; n_img += has_img; n_tag += has_tag
            n_attr += has_attr; n_brand += has_brand; n_wt += has_wt
            n_dim += has_dim; n_wc += has_wc
            print(f"{str(p.sku)[:30]:<32} {str(has_src):<7} {str(has_img):<9} "
                  f"{str(has_tag):<5} {str(has_attr):<6} {str(has_brand):<6} "
                  f"{str(has_wt):<5} {str(has_dim):<5} {str(has_wc):<6} {p.status}")
        print()
        print(f"total rows           : {len(rows)}")
        print(f"have source_url      : {n_src}")
        print(f"have images in meta  : {n_img}")
        print(f"have tags            : {n_tag}")
        print(f"have attributes      : {n_attr}")
        print(f"have brand           : {n_brand}")
        print(f"have weight_kg       : {n_wt}")
        print(f"have dimensions      : {n_dim}")
        print(f"have woocommerce_id  : {n_wc}")


asyncio.run(main())
PYEOF
"""),
]


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    for label, cmd in CMDS:
        _, out, err = ssh.exec_command(cmd, timeout=300)
        data = out.read().decode("utf-8", "replace")
        et = err.read().decode("utf-8", "replace")
        print("\n" + "=" * 78, "\n### " + label, "\n" + "=" * 78, flush=True)
        print(data.rstrip()[:6500], flush=True)
        if et.strip():
            print("-- stderr --", et.rstrip()[:500], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
