# -*- coding: utf-8 -*-
"""第 3 批上架：6 图上传 + 6 商品创建（nuotaooutdoor.com）"""
import base64, json, os, requests

USER = "fys2388@gmail.com"
APP_PW = "7g7r yV5N GeUs x7Cu EljL NPjf"
BASE = "https://nuotaooutdoor.com"
AUTH = base64.b64encode(f"{USER}:{APP_PW}".encode()).decode()

# 根目录 .env consumer key（wc/v3 写权限）
with open(r"E:\AI\nuotao-ai-os\.env", encoding="utf-8") as f:
    env = dict(l.split("=", 1) for l in f.read().splitlines() if "=" in l)
CK, CS = env["WOOCOMMERCE_CONSUMER_KEY"].strip().strip('"'), env["WOOCOMMERCE_CONSUMER_SECRET"].strip().strip('"')

IMGS = {
    "c1.jpg": "rechargeable-led-headlamp",
    "c2.jpg": "portable-water-filter-bottle",
    "c3.jpg": "high-back-reclining-camping-chair",
    "c4.jpg": "foldable-camping-cutlery-set",
    "c5.jpg": "outdoor-pop-up-mosquito-net",
    "c6.jpg": "waterproof-wet-dry-swim-bag",
}

# 1) 上传图片
media_ids = {}
for fn, slug in IMGS.items():
    path = os.path.join(r"C:\temp\shop_images3", fn)
    with open(path, "rb") as f:
        r = requests.post(
            f"{BASE}/wp-json/wp/v2/media",
            headers={"Authorization": f"Basic {AUTH}", "Content-Disposition": f'attachment; filename="{slug}.jpg"', "Content-Type": "image/jpeg"},
            data=f.read(),
            timeout=120,
        )
    if r.status_code not in (200, 201):
        print("MEDIA FAIL", fn, r.status_code, r.text[:300]); raise SystemExit(1)
    mid = r.json()["id"]
    media_ids[slug] = mid
    print("media", slug, mid)

# 2) 创建商品
PRODUCTS = [
    dict(name="Rechargeable LED Headlamp - USB-C Motion Sensor with Adjustable Strap",
         slug="rechargeable-led-headlamp-usb-c-motion-sensor",
         type="simple", status="publish", regular_price="19.99", categories=[{"id": 130}],
         short_description="<p>USB-C rechargeable headlamp with motion sensor, COB floodlight & side spotlight. Hands-free lighting for camping, hiking, fishing & night runs.</p>",
         description="<h2>Hands-Free Light for Any Adventure</h2><ul><li>USB-C rechargeable - no batteries needed</li><li>Motion sensor wave control - turn on/off without touching</li><li>COB floodlight + long-range spotlight dual beam</li><li>Adjustable head strap, comfortable for all-day wear</li><li>IPX4 water resistant for light rain</li></ul>",
         meta_data=[{"key": "_sku_override", "value": "NT-HEAD-03"}]),
    dict(name="Portable Water Filter Bottle - Outdoor Filtration Drinking Cup",
         slug="portable-water-filter-bottle-outdoor",
         type="simple", status="publish", regular_price="29.99", categories=[{"id": 94}],
         short_description="<p>Lightweight portable filter bottle with replaceable filter cartridge. Fill from streams, lakes or taps - squeeze and drink. Perfect for hiking, camping & travel.</p>",
         description="<h2>Clean Drinking Water, Wherever You Roam</h2><ul><li>Built-in filtration cartridge with activated carbon + ultrafiltration membrane</li><li>One-hand squeeze drinking design with flip cap</li><li>Lightweight BPA-free body, leak-proof carry loop</li><li>Replaceable filter - long service life</li><li>Great for hiking, trekking, camping & travel</li></ul>",
         meta_data=[{"key": "_sku_override", "value": "NT-BTL-03"}]),
    dict(name="High-Back Reclining Camping Chair - Foldable Moon Chair with Footrest",
         slug="high-back-reclining-camping-chair-footrest",
         type="simple", status="publish", regular_price="39.99", categories=[{"id": 119}],
         short_description="<p>Reclining high-back moon chair with adjustable footrest. 3-position recline, breathable Oxford fabric & sturdy steel frame. Supports up to 120kg.</p>",
         description="<h2>Recline, Relax, Repeat</h2><ul><li>3-position adjustable recline + detachable footrest</li><li>High-back design with headrest zone for full-body support</li><li>600D water-repellent Oxford fabric, breathable & tear-resistant</li><li>Reinforced steel frame, 120kg weight capacity</li><li>Folds compact with carry bag - 3.2kg</li></ul>",
         meta_data=[{"key": "_sku_override", "value": "NT-CHR-03"}]),
    dict(name="Foldable Camping Cutlery Set - 304 Stainless Steel Fork & Spoon with Pouch",
         slug="foldable-camping-cutlery-set-304",
         type="simple", status="publish", regular_price="12.99", categories=[{"id": 56}],
         short_description="<p>Foldable 304 stainless steel fork & spoon set with carry pouch. Folds flat for your pocket - ideal for camping, hiking, picnics & travel.</p>",
         description="<h2>Compact Cutlery for the Trail</h2><ul><li>Fork & spoon, both foldable to fit any pocket</li><li>Premium 304 stainless steel - rust resistant</li><li>Lightweight carry pouch with hanging loop</li><li>Easy to clean - dishwasher friendly</li><li>Perfect for camping, hiking, backpacking & office lunches</li></ul>",
         meta_data=[{"key": "_sku_override", "value": "NT-COOK-03"}]),
    dict(name="Large Pop-Up Mosquito Net Canopy - Outdoor Insect Screen for Camping & Patio",
         slug="large-pop-up-mosquito-net-canopy",
         type="simple", status="publish", regular_price="19.99", categories=[{"id": 53}],
         short_description="<p>Extra-large pop-up mosquito net canopy. No-pole setup in seconds - protect your patio, campsite or picnic table from insects day and night.</p>",
         description="<h2>Instant Insect-Free Zone</h2><ul><li>Extra-large size covers dining table & seating area (up to 6-8 people)</li><li>No assembly - pops open in seconds, folds flat for storage</li><li>Fine mesh keeps mosquitoes & bugs out while staying breathable</li><li>Lightweight with carry bag included</li><li>Use at campsites, patios, gardens, balconies & beach picnics</li></ul>",
         meta_data=[{"key": "_sku_override", "value": "NT-TENT-03"}]),
    dict(name="Waterproof Wet & Dry Swim Bag - PVC Beach & Gym Bag with Shoulder Strap",
         slug="waterproof-wet-dry-swim-bag",
         type="simple", status="publish", regular_price="12.99", categories=[{"id": 121}],
         short_description="<p>Waterproof PVC wet/dry bag with shoulder strap. Roll-top seal keeps wet swimwear, towels & gear separated from dry items. Ideal for beach, pool & gym.</p>",
         description="<h2>Keep Wet Gear in Its Place</h2><ul><li>Waterproof PVC shell - roll-top seal keeps water inside</li><li>Two-layer design separates wet & dry items</li><li>Adjustable shoulder strap & carry handle</li><li>Large capacity for swimwear, towels & toiletries</li><li>Perfect for swimming, beach days, gym & travel</li></ul>",
         meta_data=[{"key": "_sku_override", "value": "NT-STO-03"}]),
]

created = []
for p in PRODUCTS:
    img = media_ids.get(p["slug"].split("-")[0] if False else None)
    # 匹配主图：slug 前缀映射
    key = None
    for s, mid in media_ids.items():
        if s in p["slug"]:
            key = mid; break
    if key:
        p["images"] = [{"id": key}]
    r = requests.post(f"{BASE}/wp-json/wc/v3/products", auth=(CK, CS), json=p, timeout=120)
    if r.status_code not in (200, 201):
        print("PRODUCT FAIL", p["slug"], r.status_code, r.text[:400]); raise SystemExit(1)
    j = r.json()
    created.append((j["id"], j["name"], j["price"]))
    print("created", j["id"], j["name"], j["price"], "img:", key)

print("DONE", len(created))
