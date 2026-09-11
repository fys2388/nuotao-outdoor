#!/usr/bin/env python3
"""
创建露营灯产品（WooCommerce ID待分配）
"""
import requests
import json

WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
AUTH = ("ck_3644da6e081a9445459388cc92a82a096a35b427", "cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605")

# 产品数据
product_data = {
    "name": "Solar Camping Lantern - Rechargeable LED Tent Light with Solar Panel & Type-C Charging, 3 Brightness Modes, IP55 Waterproof for Camping Hiking Emergency",
    "slug": "solar-camping-lantern-rechargeable-led-tent-light-solar-panel-type-c",
    "type": "simple",
    "status": "publish",
    "sku": "NTO-SOLAR-LANTERN-001",
    "price": "24.99",
    "regular_price": "29.99",
    "sale_price": "24.99",
    "manage_stock": True,
    "stock_quantity": 100,
    "low_stock_amount": 10,
    "backorders": "no",
    "sold_individually": False,
    "weight": "0.25",
    "dimensions": {
        "length": "10",
        "width": "10",
        "height": "7"
    },
    "categories": [
        {"id": 22},   # Lighting & Power
        {"id": 129}   # Camping Lanterns
    ],
    "attributes": [
        {
            "name": "Light Source",
            "position": 0,
            "visible": True,
            "variation": False,
            "options": ["LED"]
        },
        {
            "name": "Power",
            "position": 1,
            "visible": True,
            "variation": False,
            "options": ["50W / 100W / 150W Equivalent"]
        },
        {
            "name": "Battery Capacity",
            "position": 2,
            "visible": True,
            "variation": False,
            "options": ["1500mAh / 2400mAh / 3600mAh"]
        },
        {
            "name": "Waterproof Rating",
            "position": 3,
            "visible": True,
            "variation": False,
            "options": ["IP55"]
        },
        {
            "name": "Weight",
            "position": 4,
            "visible": True,
            "variation": False,
            "options": ["200g-250g"]
        },
        {
            "name": "Certification",
            "position": 5,
            "visible": True,
            "variation": False,
            "options": ["CE / 3C"]
        }
    ],
    "short_description": "Solar + Type-C dual charging LED camping lantern with 3 brightness modes, IP55 waterproof, 6-9 hour runtime. Perfect for camping, hiking, emergency lighting, and outdoor adventures. Lightweight 250g design with metal hook for hanging.",
    "description": """
<h2>Illuminate Your Adventure</h2>
<p>Experience reliable outdoor lighting with our Solar Camping Lantern. Featuring dual charging technology (solar + Type-C), this versatile lantern ensures you're never left in the dark. Perfect for camping, hiking, emergency preparedness, and outdoor activities.</p>

<h3>Key Features</h3>
<ul>
<li><strong>Dual Charging Technology</strong> - Solar panel + Type-C USB charging, never run out of power</li>
<li><strong>3 Brightness Modes</strong> - High/Low/Strobe modes for different scenarios</li>
<li><strong>IP55 Waterproof</strong> - Rain and splash resistant, perfect for all weather conditions</li>
<li><strong>Long Runtime</strong> - 6-9 hours continuous lighting on single charge</li>
<li><strong>Lightweight & Portable</strong> - Only 200-250g, easy to carry and hang</li>
<li><strong>Metal Hook Design</strong> - Hang anywhere: tents, branches, backpacks</li>
</ul>

<h3>Multiple Usage Scenarios</h3>
<ul>
<li><strong>Camping & Hiking</strong> - Illuminate your tent or campsite</li>
<li><strong>Emergency Lighting</strong> - Power outages and home emergencies</li>
<li><strong>Market Stall & Night Market</strong> - Bright lighting for vendors</li>
<li><strong>Fishing & Outdoor Activities</strong> - Hands-free lighting solution</li>
</ul>

<h3>Specifications</h3>
<ul>
<li>Light Source: High-brightness LED</li>
<li>Power: 50W/100W/150W equivalent (3 modes)</li>
<li>Battery: 1500mAh-3600mAh rechargeable lithium battery</li>
<li>Charging: Solar panel + Type-C USB dual charging</li>
<li>Runtime: 6-9 hours (depending on mode)</li>
<li>Waterproof: IP55</li>
<li>Weight: 200g-250g</li>
<li>Dimensions: 100mm-140mm diameter</li>
<li>Certification: CE / 3C certified</li>
</ul>

<h3>Quality Assurance</h3>
<ul>
<li>30-Day Money Back Guarantee</li>
<li>1-Year Warranty</li>
<li>Free Shipping</li>
<li>24/7 Customer Support</li>
<li>CE & 3C Certified Quality</li>
</ul>
""",
    "meta_data": [
        {"key": "_1688_offer_url", "value": "https://detail.1688.com/offer/1075485124628.html"},
        {"key": "_1688_offer_id", "value": "1075485124628"},
        {"key": "_1688_supplier", "value": "中山市成铂照明科技有限公司"},
        {"key": "_1688_supplier_rating", "value": "4.0"},
        {"key": "_1688_repeat_rate", "value": "60%"},
        {"key": "_1688_purchase_price", "value": "10.5"},
        {"key": "_1688_min_order", "value": "2"},
        {"key": "_profit_margin", "value": "60-65%"},
        {"key": "_selection_score", "value": "86"},
        {"key": "_selection_grade", "value": "A"}
    ]
}

print("创建露营灯产品...")
response = requests.post(f"{WC_URL}/products", auth=AUTH, json=product_data, timeout=30)

if response.status_code == 201:
    result = response.json()
    print(f"✅ 产品创建成功！")
    print(f"产品ID: {result.get('id')}")
    print(f"产品名称: {result.get('name')}")
    print(f"SKU: {result.get('sku')}")
    print(f"价格: ${result.get('price')}")
    print(f"库存: {result.get('stock_quantity')}")
    print(f"分类: {[cat['name'] for cat in result.get('categories', [])]}")
    print(f"属性数量: {len(result.get('attributes', []))}")
    print(f"Meta数量: {len(result.get('meta_data', []))}")
    print(f"产品链接: {result.get('permalink')}")
else:
    print(f"❌ 创建失败: {response.status_code}")
    print(f"响应: {response.text}")
