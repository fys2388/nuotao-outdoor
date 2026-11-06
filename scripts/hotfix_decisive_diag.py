"""Decisive diagnostic v3: reproduce the API channel exactly.

The API path is: import_from_1688 -> _cached_fetch_1688_product (async)
  -> asyncio.to_thread(_fetch_1688_product, url)   # worker thread
  -> _fetch_1688_product internally calls _asyncio.run(scrape_1688_product(...))

diag v1/v2 called _fetch_1688_product SYNCHRONOUSLY (main thread) and got a
dict. The API channel calls it via asyncio.to_thread (worker thread) and got
None. This script reproduces the worker-thread call and prints what comes back,
plus catches the actual exception if the Future carries one.
"""
import asyncio
import os
import traceback

print("DIAG LOGIN_COOKIE len:", len(os.environ.get("LOGIN_COOKIE", "")))

import app.services.product_pipeline_service as m  # noqa: E402


async def main():
    # Reproduce exactly what _cached_fetch_1688_product does at line ~2447
    try:
        result = await asyncio.to_thread(m._fetch_1688_product, "964465929482")
        print("DIAG to_thread result type:", type(result).__name__)
        print("DIAG to_thread raw:", repr(result)[:300])
    except Exception as e:
        print("DIAG to_thread RAISED:", type(e).__name__, ":", str(e)[:300])
        traceback.print_exc()
        return

    # Also reproduce the None-guard branch
    if result is None:
        print("DIAG >>> _cached_fetch would set: Fetch returned None <<<")


asyncio.run(main())
