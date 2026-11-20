"""Decisive 1688 LOGIN_COOKIE diagnostic.

Goal: answer ONE question — does the server's LOGIN_COOKIE still let a Playwright
fetch render a real 1688 product page (bypassing the anti-bot login wall), or has
it expired so the page degrades to a generic/login shell?

Why NOT call _fetch_1688_product: it pre-checks a hardcoded _KNOWN_PRODUCTS map
and returns canned data for known IDs, so it never exercises the cookie path.
Instead we call scrape_1688_product() directly (the function that injects
LOGIN_COOKIE into Playwright) on a product ID that is NOT in _KNOWN_PRODUCTS, so
the result reflects the live cookie-driven fetch.

Verdict logic: a real page yields a specific product name; an expired cookie
yields a generic/placeholder name (or empty). We never print the cookie itself.
"""
import asyncio
import os
import traceback

# A real 1688 offer that is deliberately NOT in _KNOWN_PRODUCTS, so the fetch
# must run live through the cookie-injected browser path.
TEST_PRODUCT_ID = "994387007112"

GENERIC_NAMES = {"1688 Product", "1688产品", "Product", "商品", ""}

print("DIAG LOGIN_COOKIE len:", len(os.environ.get("LOGIN_COOKIE", "")))

from app.services.scrape_1688 import scrape_1688_product  # noqa: E402


async def main():
    try:
        scraped = await scrape_1688_product(TEST_PRODUCT_ID)
    except Exception as e:
        print("DIAG scrape RAISED:", type(e).__name__, ":", str(e)[:300])
        traceback.print_exc()
        print("DIAG VERDICT: INCONCLUSIVE (scrape raised)")
        return

    if scraped is None:
        print("DIAG VERDICT: LOGIN_COOKIE EXPIRED (scrape returned None — login wall / empty page)")
        return

    name = (getattr(scraped, "name", "") or "").strip()
    n_images = len(getattr(scraped, "images", []) or [])
    n_skus = len(getattr(scraped, "variations", []) or [])
    print("DIAG scraped name:", name[:80])
    print("DIAG scraped images:", n_images, "variations:", n_skus)

    if name in GENERIC_NAMES or len(name) < 10:
        print("DIAG VERDICT: LOGIN_COOKIE EXPIRED "
              "(generic/placeholder name — page rendered as login shell, not real product)")
    else:
        print("DIAG VERDICT: LOGIN_COOKIE VALID (real product name rendered through cookie path)")


asyncio.run(main())
