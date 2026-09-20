"""Local sanity test for the listing gate module (run from repo root)."""
import sys

BACKEND = r"E:\AI\nuotao-ai-os\backend"
sys.path.insert(0, BACKEND)

from app.services.listing_gate import (  # noqa: E402
    build_wc_payload,
    evaluate_gate,
    get_english_copy,
    resolve_prices,
)


class Product:
    def __init__(self, meta, sku="S1", name="Yueye Moon Chair", status="draft"):
        self.meta = meta
        self.sku = sku
        self.name = name
        self.status = status
        self.description = ""
        self.category = None
        self.tags = []


CASES = {
    "approved+price": {
        "sale_price": "15.80",
        "source_price": "7.9",
        "localizations": {
            "en": {
                "status": "approved",
                "title": "Moon Chair",
                "description": "Great chair.",
                "bullet_points": ["Ultralight 0.9kg", "600D Oxford"],
                "seo_keywords": ["moon chair", "camping chair"],
            }
        },
    },
    "no price": {
        "localizations": {
            "en": {"status": "approved", "title": "x", "description": "y", "bullet_points": []}
        }
    },
    "unapproved copy": {
        "sale_price": "15.80",
        "localizations": {
            "en": {"status": "pending", "title": "x", "description": "y", "bullet_points": []}
        }
    },
    "no localization key": {"sale_price": "15.80"},
    "wc sale >= regular": {
        "regular_price": "20",
        "wc_sale_price": "25",
        "localizations": {"en": {"status": "approved", "title": "t", "description": "d", "bullet_points": []}},
    },
    "meta=None": None,
}

failed = 0
for label, meta in CASES.items():
    product = Product(meta or {})
    if label == "meta=None":
        product.meta = None
    prices = resolve_prices(meta)
    en = get_english_copy(meta)
    gate = evaluate_gate(product, prices, en)
    print(f"{label:20} prices={prices} gate={gate['status']:<13} reasons={[r['code'] for r in gate['reasons']]}")

    expected = {
        "approved+price": "passed",
        "no price": "needs_review",
        "unapproved copy": "needs_review",
        "no localization key": "needs_review",
        "wc sale >= regular": "passed",
        "meta=None": "needs_review",
    }[label]
    if gate["status"] != expected:
        print(f"  FAIL expected {expected}")
        failed += 1

print()
good = Product(CASES["approved+price"])
payload = build_wc_payload(good, resolve_prices(CASES["approved+price"]), get_english_copy(CASES["approved+price"]))
print("payload for approved+price:")
for key, value in payload.items():
    print(f"  {key} = {value!r}")

assert payload["regular_price"] == "15.8", payload["regular_price"]
assert "sale_price" not in payload, payload
assert payload["name"] == "Moon Chair", payload["name"]
assert payload["status"] == "draft", payload["status"]
assert payload["tags"] == [{"name": "moon chair"}, {"name": "camping chair"}], payload["tags"]
assert "Ultralight 0.9kg" in payload["short_description"], payload["short_description"]

print()
print(f"FAILED CASES: {failed}")
sys.exit(1 if failed else 0)
