"""Decisive diagnostic: 1688 Open API path for product 964465929482.

Verifies that the official 1688 Open API (alibaba.product.get / .simple.get)
returns REAL data for this offer, which would let the import bypass the
anti-bot login wall entirely (no browser cookie needed).

Prints: configured / success / error / subject / price / sku_count / attr_count
"""
import os
import traceback

print("OAPI APP_KEY:", os.environ.get("ALI1688_APP_KEY", "")[:6] + "..." or "(none)")
print("OAPI ACCESS_TOKEN:", (os.environ.get("ALI1688_ACCESS_TOKEN", "") or "(none)")[:8] + "...")

from app.services.sourcing_1688_service import (
    get_product_detail,
    is_configured,
)

print("OAPI is_configured:", is_configured())

try:
    r = get_product_detail("964465929482")
    print("OAPI success:", r.get("success"))
    print("OAPI source:", r.get("source"))
    print("OAPI api_method:", r.get("api_method"))
    print("OAPI error:", r.get("error"))
    prod = r.get("product") or {}
    print("OAPI subject:", str(prod.get("subject"))[:120])
    print("OAPI price:", prod.get("price"))
    skus = prod.get("sku_list") or []
    print("OAPI sku_count:", len(skus))
    for s in skus[:5]:
        print("  sku:", str(s)[:160])
    attrs = prod.get("attributes") or []
    print("OAPI attr_count:", len(attrs))
    print("OAPI images:", len(prod.get("images") or []))
except Exception as e:
    print("OAPI RAISED:", type(e).__name__, ":", str(e)[:200])
    traceback.print_exc()
