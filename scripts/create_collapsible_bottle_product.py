#!/usr/bin/env python3
"""
创建折叠水壶产品
"""
import requests
import json

WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
AUTH = ("ck_3644da6e081a9445459388cc92a82a096a35b427", "cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605")

# 产品数据
product_data = {
    "name": "Collapsible Silicone Water Bottle - 600ml Food Grade Foldable Travel Bottle for Camping Hiking Gym",
    "slug": "collapsible-silicone-water-bottle-600ml-food-grade-foldable-travel-bottle",
    "type": "simple",
    "status": "publish",
    "sku": "NTO-COLLAPSIBLE-BOTTLE-001",
    "price": "14.99",
    "regular_price": "19.99",
    "sale_price": "14.99",
    "manage_stock": True,
    "stock_quantity": 100,
    "low_stock_amount": 10,
    "backorders": "no",
    "sold_individually": False,
    "weight": "0.175",
    "dimensions": {
        "length": "7",
        "width": "7",
        "height": "18.5"
    },
    "categories": [
        {"id": 22},   # Lighting & Power (临时，后续更新为水具分类)
    ],
    "attributes": [
        {
            "name": "Material",
            "position": 0,
            "visible": True,
            "variation": False,
            "options": ["Food Grade Silicone"]
        },
        {
            "name": "Capacity",
            "position": 1,
            "visible": True,
            "variation": False,
            "options": ["600ml"]
        },
        {
            "name": "Color",
            "position": 2,
            "visible": True,
            "variation": False,
            "options": ["Green / Blue / Pink / Gray"]
        },
        {
            "name": "Weight",
            "position": 3,
            "visible": True,
            "variation": False,
            "options": ["175g"]
        },
        {
            "name": "Features",
            "position": 4,
            "visible": True,
            "variation": False,
            "options": ["Collapsible / Leak Proof / BPA Free / Heat Resistant"]
        },
        {
            "name": "Certification",
            "position": 5,
            "visible": True,
            "variation": False,
            "options": ["FDA / LFGB"]
        }
    ],
    "short_description": "600ml collapsible silicone water bottle made from food grade silicone. Foldable design saves 70% space when empty. Leak proof screw cap, BPA free, heat resistant. Perfect for camping, hiking, gym, travel and outdoor activities. Lightweight 175g with carrying strap.",
    "description": """
<h2>Stay Hydrated Anywhere</h2>
<p>Our collapsible silicone water bottle is the perfect hydration companion for all your adventures. Made from premium food grade silicone, this 600ml bottle folds down to 70% of its size when empty, making it incredibly portable and space-saving.</p>

<h3>Key Features</h3>
<ul>
<li><strong>Food Grade Silicone</strong> - BPA free, FDA and LFGB certified, safe for hot and cold beverages</li>
<li><strong>Collapsible Design</strong> - Folds to 70% smaller when empty, perfect for travel and backpacking</li>
<li><strong>Leak Proof Screw Cap</strong> - Secure screw cap design prevents leaks and spills</li>
<li><strong>600ml Capacity</strong> - Perfect size for daily hydration and outdoor activities</li>
<li><strong>Lightweight 175g</strong> - Ultra-lightweight with integrated carrying strap</li>
<li><strong>Heat Resistant</strong> - Withstands temperatures from -40°C to 100°C</li>
<li><strong>Wide Mouth Design</strong> - Easy to fill, clean and add ice cubes</li>
</ul>

<h3>Multiple Usage Scenarios</h3>
<ul>
<li><strong>Hiking & Camping</strong> - Lightweight and collapsible, perfect for backpacking</li>
<li><strong>Gym & Fitness</strong> - Convenient carrying strap, easy to take to the gym</li>
<li><strong>Travel & Business</strong> - Folds flat for easy packing in luggage</li>
<li><strong>Daily Use</strong> - Stylish design for office, school and everyday use</li>
</ul>

<h3>Specifications</h3>
<ul>
<li>Material: Food Grade Silicone</li>
<li>Capacity: 600ml</li>
<li>Weight: 175g</li>
<li>Dimensions: 7cm x 7cm x 18.5cm (expanded)</li>
<li>Temperature Range: -40°C to 100°C</li>
<li>Colors: Green, Blue, Pink, Gray</li>
<li>Certification: FDA, LFGB</li>
<li>Care: Dishwasher safe (top rack), easy to clean</li>
</ul>

<h3>Quality Assurance</h3>
<ul>
<li>30-Day Money Back Guarantee</li>
<li>1-Year Warranty</li>
<li>Free Shipping</li>
<li>24/7 Customer Support</li>
<li>FDA & LFGB Certified Food Grade Safety</li>
</ul>
""",
    "meta_data": [
        {"key": "_1688_offer_url", "value": "https://detail.1688.com/offer/1077690601953.html"},
        {"key": "_1688_offer_id", "value": "1077690601953"},
        {"key": "_1688_supplier", "value": "义乌市汐彤贸易有限公司"},
        {"key": "_1688_supplier_rating", "value": "5.0"},
        {"key": "_1688_repeat_rate", "value": "54%"},
        {"key": "_1688_purchase_price", "value": "4.8"},
        {"key": "_1688_min_order", "value": "2"},
        {"key": "_profit_margin", "value": "65-70%"},
        {"key": "_selection_score", "value": "86"},
        {"key": "_selection_grade", "value": "A"}
    ]
}

print("创建折叠水壶产品...")
response = requests.post(f"{WC_URL}/products", auth=AUTH, json=product_data, timeout=30)

if response.status_code == 201:
    result = response.json()
    print(f"✅ 产品创建成功！")
    print(f"产品ID: {result.get('id')}")
    print(f"产品名称: {result.get('name')}")
    print(f"SKU: {result.get('sku')}")
    print(f"价格: ${result.get('price')}")
    print(f"库存: {result.get('stock_quantity')}")
    print(f"属性数量: {len(result.get('attributes', []))}")
    print(f"Meta数量: {len(result.get('meta_data', []))}")
    print(f"产品链接: {result.get('permalink')}")
else:
    print(f"❌ 创建失败: {response.status_code}")
    print(f"响应: {response.text}")
