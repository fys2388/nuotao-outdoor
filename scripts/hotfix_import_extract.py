"""Hotfix helper: print structured fields from a 1688 import JSON response.

Used by .github/workflows/deploy.yml hotfix step to dump the parsed
product_info from /tmp/import_<id>.json without embedding Python in YAML.
"""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/import_964465929482.json"

try:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
except Exception as e:  # noqa: BLE001
    print(f"[hotfix] import JSON parse failed ({path}): {e}")
    sys.exit(0)

print("[hotfix] success:", d.get("success"), "error:", d.get("error"))
p = (d.get("data") or {}).get("product_info") or {}
print("[hotfix] name:", p.get("name"))
print("[hotfix] price:", p.get("price"))
print("[hotfix] category:", p.get("category"))
print("[hotfix] dimensions:", p.get("dimensions"))
print("[hotfix] weight:", p.get("weight"))
print("[hotfix] materials:", p.get("materials"))
print("[hotfix] sku:", p.get("sku"))

images = p.get("images") or []
print("[hotfix] images:", len(images))
for i, u in enumerate(images[:10]):
    print("  img%d: %s" % (i + 1, str(u)[:120]))

v = p.get("variations") or []
print("[hotfix] variations:", len(v))
for x in v:
    print("  sku: %s | name: %s | price: %s | stock: %s" % (
        x.get("sku"), x.get("name"), x.get("price"), x.get("stock_quantity")))

attrs = p.get("attributes") or []
print("[hotfix] attributes:", len(attrs))
for a in attrs[:20]:
    if isinstance(a, dict):
        print("   %s = %s" % (a.get("name") or a.get("attributeName"), a.get("value")))

sup = p.get("supplier") or {}
print("[hotfix] supplier:", sup.get("company_name"))
print("[hotfix] selling_points:", p.get("core_selling_points"))
