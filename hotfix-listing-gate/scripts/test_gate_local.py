"""Local sanity test for the listing gate module (run from repo root)."""
import sys

BACKEND = r"E:\AI\nuotao-ai-os\backend"
sys.path.insert(0, BACKEND)

from app.services.listing_gate import (  # noqa: E402
    build_wc_payload,
    evaluate_gate,
    get_english_copy,
    has_cjk,
    resolve_prices,
)

ENGLISH_OK = {
    "status": "approved",
    "title": "Yueye Moon Chair Ultralight",
    "description": "D" * 700,
    "bullet_points": ["Ultralight 0.9kg", "600D Oxford fabric"],
    "seo_keywords": ["moon chair", "camping chair"],
    "short_description": "Ultralight foldable moon chair.",
}
ENGLISH_THIN = dict(ENGLISH_OK, description="Short.", bullet_points=[])
ENGLISH_PENDING = dict(ENGLISH_OK, status="pending")
CHINESE_TITLE = dict(ENGLISH_OK, title="月亮椅 户外折叠椅")


class Product:
    def __init__(self, meta, sku="NT-YUEYE-001", candidate_status=None, status="draft",
                 name="月亮椅 户外折叠躺椅", description="月亮椅描述"):
        self.meta = meta
        self.sku = sku
        self.name = name
        self.status = status
        self.description = description
        self.category = "露营"
        self.brand = "Yueye"
        self.candidate_status = candidate_status
        self.source = "pipeline"
        self.source_url = None
        self.tags = ["camping"]
        self.attributes = {"Color": ["Black", "Grey"], "Size": "L"}
        self.weight_kg = 0.9
        self.dimensions = {"length": 32, "width": 44, "height": 85}
        self.target_market = "US"


def meta_with(copy, sale_price="15.80", images=None, stock=None):
    meta = {"sale_price": sale_price, "source_price": "7.9"}
    if copy is not None:
        meta["localizations"] = {"en": copy}
    if images:
        meta["images"] = images
    if stock:
        meta.update(stock)
    return meta


CASES = [
    # (label, product kwargs, meta, expected gate status)
    ("commerce product, ok", dict(), meta_with(ENGLISH_OK), "passed"),
    ("candidate not approved", dict(candidate_status="candidate"),
     meta_with(ENGLISH_OK), "needs_review"),
    ("candidate rejected", dict(candidate_status="rejected"),
     meta_with(ENGLISH_OK), "needs_review"),
    ("no price", dict(), meta_with(ENGLISH_OK, sale_price=None), "needs_review"),
    ("unapproved copy", dict(), meta_with(ENGLISH_PENDING), "needs_review"),
    ("no localization key",
     dict(name="Foldable Moon Chair", description="A foldable moon chair."),
     meta_with(None), "needs_review"),
    ("cjk without localization", dict(), meta_with(None), "blocked"),
    ("cjk inside approved copy", dict(), meta_with(CHINESE_TITLE), "needs_review"),
    ("thin approved copy", dict(), meta_with(ENGLISH_THIN), "needs_review"),
    ("missing sku", dict(sku=""), meta_with(ENGLISH_OK), "blocked"),
    ("meta None", dict(name="Foldable Moon Chair", description="A foldable moon chair."),
     None, "needs_review"),
]

failed = 0
for label, kwargs, meta, expected in CASES:
    product = Product(meta or {}, **kwargs)
    if meta is None:
        product.meta = None
    prices = resolve_prices(meta)
    gate = evaluate_gate(product, prices, get_english_copy(meta))
    codes = [reason["code"] for reason in gate["reasons"]]
    ok = gate["status"] == expected
    if not ok:
        failed += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {label:26} status={gate['status']:<13} "
          f"expected={expected:<13} codes={codes}")

print()
print("cjk detector:", has_cjk("月亮椅"), has_cjk("Moon Chair"))

print()
good = Product(meta_with(
    ENGLISH_OK, images=["https://cdn.example.com/a.jpg", "https://cdn.example.com/b.jpg"],
    stock={"stock_quantity": 50, "stock_status": "instock"},
))
prices = resolve_prices(good.meta)
payload = build_wc_payload(good, prices, get_english_copy(good.meta))
print("payload for a complete commerce product:")
for key, value in payload.items():
    print(f"  {key} = {value!r}")

EXPECTED_KEYS = {
    "name", "sku", "type", "status", "regular_price", "description",
    "short_description", "categories", "brand", "images", "weight",
    "dimensions", "manage_stock", "stock_quantity", "stock_status",
    "tags", "attributes",
}
missing = sorted(EXPECTED_KEYS - set(payload))
print()
print("missing payload keys:", missing)
assert not missing, missing
assert payload["regular_price"] == "15.8", payload["regular_price"]
assert "sale_price" not in payload, payload
assert payload["type"] == "simple"
assert payload["categories"] == [{"name": "Camping"}], payload["categories"]
assert payload["images"] == [
    {"src": "https://cdn.example.com/a.jpg"},
    {"src": "https://cdn.example.com/b.jpg"},
], payload["images"]
assert payload["weight"] == "0.900", payload["weight"]
assert payload["dimensions"] == {"length": "32", "width": "44", "height": "85"}
assert payload["stock_quantity"] == 50
assert payload["stock_status"] == "instock"
assert payload["tags"] == [{"name": "moon chair"}, {"name": "camping chair"}]

# multi-option attributes ship; scalar/single-option ones are not variants
attribute_names = [a["name"] for a in payload.get("attributes", [])]
assert attribute_names == ["Color"], attribute_names
assert payload["attributes"][0]["options"] == ["Black", "Grey"]

print()
print(f"FAILED CASES: {failed}")
sys.exit(1 if failed or missing else 0)
