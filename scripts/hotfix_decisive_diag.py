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
    # _fetch_1688_product is a coroutine function; await it directly. Wrapping it
    # in asyncio.to_thread returns an unawaited coroutine object and never runs
    # the fetch (the RuntimeWarning 'coroutine was never awaited' proves it).
    try:
        result = await m._fetch_1688_product("964465929482")
        print("DIAG await result type:", type(result).__name__)
        print("DIAG await raw:", repr(result)[:300])
    except Exception as e:
        print("DIAG await RAISED:", type(e).__name__, ":", str(e)[:300])
        traceback.print_exc()
        return

    if result is None:
        print("DIAG VERDICT: fetch returned None — likely blocked by login wall / captcha / empty page")
        return

    if isinstance(result, dict):
        keys = sorted(result.keys())
        print("DIAG VERDICT: got dict with keys:", keys[:20])
        title = str(result.get("title") or result.get("name") or "")[:80]
        print("DIAG VERDICT: title field:", title or "(empty)")
        # A live login wall yields an empty/None title; a real product has one.
        if title:
            print("DIAG VERDICT: LOGIN_COOKIE VALID (real product data returned)")
        else:
            print("DIAG VERDICT: LOGIN_COOKIE LIKELY EXPIRED (dict but no product title — probable login/captcha page)")


asyncio.run(main())
