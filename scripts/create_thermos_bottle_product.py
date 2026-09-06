#!/usr/bin/env python3
import requests

WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
AUTH = ("ck_3644da6e081a9445459388cc92a82a096a35b427", "cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605")

product_data = {
    "name": "Stainless Steel Vacuum Insulated Water Bottle - 600ml 304 Food Grade Leak Proof Travel Thermos for Outdoor Hiking Camping Gym",
    "slug": "stainless-steel-vacuum-insulated-water-bottle-600ml-304-food-grade-leak-proof-travel-thermos",
    "type": "simple",
    "status": "publish",
    "sku": "NTO-THERMOS-BOTTLE-001",
    "regular_price": "34.99",
    "sale_price": "29.99",
    "manage_stock": True,
    "stock_quantity": 100,
    "stock_status": "instock",
    "categories": [{"id": 22}],
    "description": """
<h2>Stay Hydrated Anywhere with Premium Insulation</h2>
<p>Our 600ml Stainless Steel Vacuum Insulated Water Bottle keeps your drinks hot for up to 24 hours and cold for up to 24 hours. Made with food-grade 304 stainless steel inner wall and durable 201 stainless steel outer wall, this bottle is built to last through all your adventures.</p>

<h3>Key Features</h3>
<ul>
<li><strong>24-Hour Insulation:</strong> Double-wall vacuum technology maintains temperature for hot and cold drinks</li>
<li><strong>304 Food Grade Stainless:</strong> Safe, BPA-free inner wall ensures pure taste with no metallic flavor</li>
<li><strong>100% Leak Proof:</strong> Silicone sealing ring prevents spills, perfect for bags and backpacks</li>
<li><strong>Wide Mouth Design:</strong> Easy to fill with ice cubes and clean thoroughly</li>
<li><strong>Portable Carry Loop:</strong> Convenient handle for hiking, camping, gym, and daily use</li>
<li><strong>Multiple Colors:</strong> Available in Green, Black, Navy Blue, Silver, Red, and more</li>
</ul>

<h3>Specifications</h3>
<ul>
<li>Capacity: 600ml (20oz)</li>
<li>Material: 304 Stainless Steel Inner / 201 Stainless Steel Outer</li>
<li>Insulation: Double-wall vacuum, 24h hot / 24h cold</li>
<li>Weight: 280g (empty)</li>
<li>Dimensions: 7.5cm diameter x 23cm height</li>
<li>Certifications: CE, FDA, RoHS</li>
</ul>

<h3>Perfect for Every Occasion</h3>
<p>Whether you're hiking mountain trails, camping under the stars, hitting the gym, or just need a reliable bottle for the office, this insulated thermos delivers. The matte finish provides a secure grip, and the compact size fits most cup holders and backpack pockets.</p>
""",
    "short_description": "600ml Stainless Steel Vacuum Insulated Water Bottle - 24H Hot & Cold, 304 Food Grade, 100% Leak Proof, Portable Carry Loop for Hiking Camping Gym Office",
    "attributes": [
        {"name": "Material", "position": 0, "visible": True, "variation": False, "options": ["304 Stainless Steel Inner / 201 Stainless Steel Outer"]},
        {"name": "Capacity", "position": 1, "visible": True, "variation": False, "options": ["600ml (20oz)"]},
        {"name": "Color", "position": 2, "visible": True, "variation": False, "options": ["Green", "Black", "Navy Blue", "Silver", "Red"]},
        {"name": "Weight", "position": 3, "visible": True, "variation": False, "options": ["280g"]},
        {"name": "Insulation Time", "position": 4, "visible": True, "variation": False, "options": ["24h Hot / 24h Cold"]},
        {"name": "Features", "position": 5, "visible": True, "variation": False, "options": ["Leak Proof", "BPA Free", "Wide Mouth", "Carry Loop", "Double Wall Vacuum"]},
    ],
    "meta_data": [
        {"key": "_1688_offer_id", "value": "531322518970"},
        {"key": "_1688_supplier", "value": "永康市江南优汇杯厂"},
        {"key": "_1688_supplier_years", "value": "11"},
        {"key": "_1688_purchase_price", "value": "26.00"},
        {"key": "_1688_shipping_fee", "value": "5.00"},
        {"key": "_1688_moq", "value": "1"},
        {"key": "_1688_return_rate", "value": "60%"},
        {"key": "_1688_review_rate", "value": "99.9%"},
        {"key": "_1688_sales_volume", "value": "7300+"},
        {"key": "_product_weight_g", "value": "280"},
        {"key": "_selection_score_v2", "value": "84"},
    ],
}

print("创建不锈钢保温瓶产品...")
response = requests.post(f"{WC_URL}/products", auth=AUTH, json=product_data, timeout=30)

if response.status_code == 201:
    result = response.json()
    print("✅ 产品创建成功！")
    print(f"产品ID: {result.get('id')}")
    print(f"产品名称: {result.get('name')[:60]}")
    print(f"SKU: {result.get('sku')}")
    print(f"价格: ${result.get('sale_price')} (原价 ${result.get('regular_price')})")
    print(f"库存: {result.get('stock_quantity')}")
    print(f"产品链接: {result.get('permalink')}")
else:
    print(f"❌ 创建失败: {response.status_code}")
    print(f"响应: {response.text}")
