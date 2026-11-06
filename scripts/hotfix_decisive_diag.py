"""Decisive diagnostic: call _fetch_1688_product directly and print the return.

Used by .github/workflows/deploy.yml hotfix step to determine whether the
None returned by asyncio.to_thread(_fetch_1688_product, ...) originates inside
that function. Runs as the nuotao user with LOGIN_COOKIE exported.
"""
import os
import sys
import traceback

print("DIAG LOGIN_COOKIE len:", len(os.environ.get("LOGIN_COOKIE", "")))
print("DIAG PLAYWRIGHT_BROWSERS_PATH:", os.environ.get("PLAYWRIGHT_BROWSERS_PATH"))

try:
    from app.services.product_pipeline_service import _fetch_1688_product

    r = _fetch_1688_product("964465929482")
    print("DIAG return type:", type(r).__name__)
    if isinstance(r, dict):
        print("DIAG success:", r.get("success"), "| error:", r.get("error"))
        pi = ((r.get("data") or {}).get("product_info") or {})
        print("DIAG name:", pi.get("name"))
        print("DIAG images:", len(pi.get("images") or []),
              "variations:", len(pi.get("variations") or []))
        print("DIAG attributes:", len(pi.get("attributes") or []))
    else:
        print("DIAG raw:", repr(r)[:300])
except Exception:
    traceback.print_exc()
    sys.exit(1)
