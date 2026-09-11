# -*- coding: utf-8 -*-
"""第 4 批上架：3 图上传 + 3 商品创建（补足 30 SKU）"""
import base64, os, requests

USER = "fys2388@gmail.com"
APP_PW = "7g7r yV5N GeUs x7Cu EljL NPjf"
BASE = "https://nuotaooutdoor.com"
AUTH = base64.b64encode(f"{USER}:{APP_PW}".encode()).decode()

with open(r"E:\AI\nuotao-ai-os\.env", encoding="utf-8") as f:
    env = dict(l.split("=", 1) for l in f.read().splitlines() if "=" in l)
CK = env["WOOCOMMERCE_CONSUMER_KEY"].strip().strip('"')
CS = env["WOOCOMMERCE_CONSUMER_SECRET"].strip().strip('"')

IMGS = {
    "d1.jpg": "camping-inflatable-pillow",
    "d2.jpg": "rechargeable-led-flashlight",
    "d3.jpg": "aluminum-folding-camping-cot",
}

media_ids = {}
for fn, slug in IMGS.items():
    path = os.path.join(r"C:\temp\shop_images4", fn)
    with open(path, "rb") as f:
        r = requests.post(
            f"{BASE}/wp-json/wp/v2/media",
            headers={"Authorization": f"Basic {AUTH}",
                     "Content-Disposition": f'attachment; filename="{slug}.jpg"',
                     "Content-Type": "image/jpeg"},
            data=f.read(), timeout=120,
        )
    if r.status_code not in (200, 201):
        print("MEDIA FAIL", fn, r.status_code, r.text[:300]); raise SystemExit(1)
    mid = r.json()["id"]
    media_ids[slug] = mid
    print("media", slug, mid)

PRODUCTS = [
    dict(name="Camping Inflatable Pillow - 3D Memory Foam Auto-Inflating Travel Pillow",
         slug="camping-inflatable-pillow-3d-memory-foam",
         type="simple", status="publish", regular_price="19.99", categories=[{"id": 118}],
         short_description="<p>3D memory foam auto-inflating pillow - high-elastic sponge, silent and comfortable. Packs tiny, supports your neck and head on any camp night.</p>",
         description="<h2>Sleep Well Anywhere</h2><ul><li>High-elastic 3D sponge - soft yet supportive</li><li>Auto-inflating: open the valve and it fills itself</li><li>Quiet fabric - no crinkle noise while sleeping</li><li>Compact stuff sack - fits in any pack</li><li>Great for camping, travel, car naps & office rest</li></ul>",
         meta_data=[{"key": "_sku_override", "value": "NT-SLEEP-03"}]),
    dict(name="Rechargeable LED Flashlight - USB-C Zoomable Camping Torch",
         slug="rechargeable-led-flashlight-usb-c-zoomable",
         type="simple", status="publish", regular_price="19.99", categories=[{"id": 22}],
         short_description="<p>USB-C rechargeable LED flashlight with zoomable beam & side COB light. Bright, compact and water-resistant - built for camping, hiking and emergencies.</p>",
         description="<h2>Light Up the Dark</h2><ul><li>Zoomable focus - spot or flood with a push</li><li>Side COB light for wide-area lantern mode</li><li>USB-C rechargeable, long runtime</li><li>Aluminum body, IPX4 water resistant</li><li>Belt clip & lanyard included</li></ul>",
         meta_data=[{"key": "_sku_override", "value": "NT-LIGHT-03"}]),
    dict(name="Aluminum Folding Camping Cot - Ultralight Portable Cot for Camping & Hiking",
         slug="aluminum-folding-camping-cot-ultralight",
         type="simple", status="publish", regular_price="69.99", categories=[{"id": 55}],
         short_description="<p>Ultralight aluminum folding cot - two height levels, high-strength aluminum frame & tear-resistant fabric. Sleep above the ground for a better night outdoors.</p>",
         description="<h2>Your Bed, Anywhere</h2><ul><li>High-strength aluminum alloy frame - ultralight yet sturdy</li><li>Two height levels: low camp mode & high cot mode</li><li>600D tear-resistant Oxford fabric</li><li>Supports up to 120kg</li><li>Folds into compact carry bag - easy transport</li></ul>",
         meta_data=[{"key": "_sku_override", "value": "NT-FURN-03"}]),
]

for p in PRODUCTS:
    img = None
    for s, mid in media_ids.items():
        if s in p["slug"]:
            img = mid; break
    if img:
        p["images"] = [{"id": img}]
    r = requests.post(f"{BASE}/wp-json/wc/v3/products", auth=(CK, CS), json=p, timeout=120)
    if r.status_code not in (200, 201):
        print("PRODUCT FAIL", p["slug"], r.status_code, r.text[:400]); raise SystemExit(1)
    j = r.json()
    print("created", j["id"], j["name"], j["price"], "img:", img)

print("DONE")
