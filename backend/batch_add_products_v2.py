"""
批量添加 WooCommerce 第二批产品（10个新品类）
"""
import os
import sys

import requests
from requests.auth import HTTPBasicAuth

# WooCommerce 配置（使用读写权限密钥）
WC_BASE_URL = os.getenv("WOOCOMMERCE_BASE_URL", "https://nuotaooutdoor.com")
WC_CONSUMER_KEY = os.getenv("WOOCOMMERCE_CONSUMER_KEY", "")
WC_CONSUMER_SECRET = os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "")

API_URL = f"{WC_BASE_URL}/wp-json/wc/v3"
AUTH = HTTPBasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET)

# 第二批产品数据（10个新品类）
PRODUCTS = [
    {
        "name": "Family Camping Tent - 6 Person",
        "type": "simple",
        "regular_price": "199.99",
        "sale_price": "159.99",
        "sku": "NT-TENT-002",
        "manage_stock": True,
        "stock_quantity": 30,
        "description": "Spacious 6-person family camping tent with divided rooms, waterproof rainfly, mesh windows for ventilation, and easy setup design. Perfect for family camping trips, festivals, and outdoor adventures.",
        "short_description": "6-person family tent with divided rooms, waterproof, easy setup.",
        "categories": [{"id": 15}],
        "tags": [{"name": "tent"}, {"name": "family"}, {"name": "camping"}],
        "weight": "5.5",
        "dimensions": {"length": "430", "width": "300", "height": "180"}
    },
    {
        "name": "Carbon Fiber Trekking Poles - Pair",
        "type": "simple",
        "regular_price": "89.99",
        "sale_price": "69.99",
        "sku": "NT-POLE-001",
        "manage_stock": True,
        "stock_quantity": 60,
        "description": "Lightweight carbon fiber trekking poles with adjustable length, ergonomic cork grips, wrist straps, and tungsten carbide tips. Includes interchangeable rubber tips and snow baskets. Perfect for hiking, trekking, and mountaineering.",
        "short_description": "Carbon fiber trekking poles, adjustable, cork grips, lightweight.",
        "categories": [{"id": 15}],
        "tags": [{"name": "trekking poles"}, {"name": "hiking"}, {"name": "carbon fiber"}],
        "weight": "0.5",
        "dimensions": {"length": "65", "width": "10", "height": "5"}
    },
    {
        "name": "Portable Water Filter Purifier",
        "type": "simple",
        "regular_price": "49.99",
        "sale_price": "39.99",
        "sku": "NT-FILTER-001",
        "manage_stock": True,
        "stock_quantity": 80,
        "description": "Portable water filter purifier with 0.1 micron hollow fiber membrane, removes 99.99% of bacteria and protozoa. Filter up to 100,000 liters. Lightweight and compact, perfect for camping, hiking, travel, and emergency preparedness.",
        "short_description": "Portable water filter, 0.1 micron, 100,000L capacity, emergency ready.",
        "categories": [{"id": 15}],
        "tags": [{"name": "water filter"}, {"name": "purifier"}, {"name": "emergency"}],
        "weight": "0.2",
        "dimensions": {"length": "15", "width": "5", "height": "5"}
    },
    {
        "name": "Rechargeable Camping Lantern - 1000LM",
        "type": "simple",
        "regular_price": "44.99",
        "sale_price": "34.99",
        "sku": "NT-LANTERN-001",
        "manage_stock": True,
        "stock_quantity": 90,
        "description": "Rechargeable camping lantern with 1000 lumens, 4 lighting modes, 360-degree illumination, IPX4 waterproof, and built-in power bank for charging devices. Up to 12 hours runtime. Perfect for camping, hiking, emergencies, and power outages.",
        "short_description": "1000LM rechargeable lantern, 4 modes, power bank, IPX4 waterproof.",
        "categories": [{"id": 15}],
        "tags": [{"name": "lantern"}, {"name": "camping light"}, {"name": "rechargeable"}],
        "weight": "0.4",
        "dimensions": {"length": "10", "width": "10", "height": "18"}
    },
    {
        "name": "Outdoor Multi-tool Knife - 15 Functions",
        "type": "simple",
        "regular_price": "59.99",
        "sale_price": "44.99",
        "sku": "NT-KNIFE-002",
        "manage_stock": True,
        "stock_quantity": 70,
        "description": "Premium outdoor multi-tool knife with 15 functions including knife, saw, pliers, screwdrivers, bottle opener, can opener, wire cutter, and more. Stainless steel construction with aluminum handle and nylon sheath. Perfect for camping, hiking, fishing, and everyday carry.",
        "short_description": "15-function multi-tool knife, stainless steel, with sheath.",
        "categories": [{"id": 15}],
        "tags": [{"name": "multi-tool"}, {"name": "knife"}, {"name": "outdoor"}],
        "weight": "0.3",
        "dimensions": {"length": "12", "width": "5", "height": "3"}
    },
    {
        "name": "UV Protection Outdoor Shirt - UPF 50+",
        "type": "simple",
        "regular_price": "49.99",
        "sale_price": "39.99",
        "sku": "NT-SHIRT-001",
        "manage_stock": True,
        "stock_quantity": 100,
        "description": "UV protection outdoor shirt with UPF 50+ sun protection, moisture-wicking fabric, quick-dry technology, and breathable mesh panels. Long sleeves with thumb holes. Perfect for hiking, fishing, camping, and outdoor activities in sunny conditions.",
        "short_description": "UPF 50+ sun protection shirt, quick-dry, breathable, long sleeve.",
        "categories": [{"id": 15}],
        "tags": [{"name": "UV protection"}, {"name": "sun shirt"}, {"name": "outdoor apparel"}],
        "weight": "0.25",
        "dimensions": {"length": "30", "width": "20", "height": "2"}
    },
    {
        "name": "Insulated Outdoor Gloves - Touchscreen",
        "type": "simple",
        "regular_price": "34.99",
        "sale_price": "24.99",
        "sku": "NT-GLOVES-001",
        "manage_stock": True,
        "stock_quantity": 120,
        "description": "Insulated outdoor gloves with Thinsulate insulation, waterproof membrane, touchscreen-compatible fingertips, reinforced palm, and adjustable wrist strap. Keeps hands warm in temperatures down to -10°C. Perfect for hiking, camping, skiing, and winter outdoor activities.",
        "short_description": "Insulated waterproof gloves, touchscreen, -10°C rated, reinforced palm.",
        "categories": [{"id": 15}],
        "tags": [{"name": "gloves"}, {"name": "winter"}, {"name": "waterproof"}],
        "weight": "0.2",
        "dimensions": {"length": "25", "width": "12", "height": "3"}
    },
    {
        "name": "Waterproof Hiking Boots - Mid Ankle",
        "type": "simple",
        "regular_price": "129.99",
        "sale_price": "99.99",
        "sku": "NT-BOOTS-001",
        "manage_stock": True,
        "stock_quantity": 40,
        "description": "Waterproof mid-ankle hiking boots with genuine leather upper, breathable mesh lining, cushioned insole, and durable rubber outsole with deep lugs for excellent traction. Supports ankles on uneven terrain. Perfect for hiking, trekking, and outdoor adventures.",
        "short_description": "Waterproof leather hiking boots, mid-ankle support, durable outsole.",
        "categories": [{"id": 15}],
        "tags": [{"name": "hiking boots"}, {"name": "waterproof"}, {"name": "leather"}],
        "weight": "1.2",
        "dimensions": {"length": "32", "width": "12", "height": "18"}
    },
    {
        "name": "Inflatable Camping Sleeping Pad - Thick",
        "type": "simple",
        "regular_price": "54.99",
        "sale_price": "44.99",
        "sku": "NT-PAD-002",
        "manage_stock": True,
        "stock_quantity": 55,
        "description": "Thick inflatable camping sleeping pad with 10cm thickness for maximum comfort, built-in foot pump for easy inflation, ergonomic design, and compact carry size. R-value 3.5 for 3-season use. Perfect for camping, backpacking, and travel.",
        "short_description": "10cm thick inflatable sleeping pad, foot pump, R-value 3.5, compact.",
        "categories": [{"id": 15}],
        "tags": [{"name": "sleeping pad"}, {"name": "inflatable"}, {"name": "camping"}],
        "weight": "0.8",
        "dimensions": {"length": "190", "width": "60", "height": "10"}
    },
    {
        "name": "Portable Camping Stove - Butane",
        "type": "simple",
        "regular_price": "44.99",
        "sale_price": "34.99",
        "sku": "NT-STOVE-001",
        "manage_stock": True,
        "stock_quantity": 65,
        "description": "Portable butane camping stove with piezo ignition, adjustable flame, windproof design, and carrying case. Boils 1L water in 3 minutes. Compatible with standard butane canisters. Perfect for camping, hiking, picnics, and emergency preparedness.",
        "short_description": "Portable butane stove, piezo ignition, windproof, with carry case.",
        "categories": [{"id": 15}],
        "tags": [{"name": "camping stove"}, {"name": "butane"}, {"name": "portable"}],
        "weight": "1.0",
        "dimensions": {"length": "25", "width": "20", "height": "10"}
    }
]


def add_product(product_data):
    """添加单个产品"""
    try:
        response = requests.post(
            f"{API_URL}/products",
            auth=AUTH,
            json=product_data,
            timeout=30
        )
        if response.status_code == 201:
            product = response.json()
            print(f"✅ 成功添加: {product['name']} (ID: {product['id']}, SKU: {product['sku']})")
            return product
        else:
            print(f"❌ 添加失败: {product_data['name']} - Status: {response.status_code}")
            print(f"   错误: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"❌ 添加异常: {product_data['name']} - {e!s}")
        return None


def main():
    print("=" * 60)
    print("开始批量添加第二批 WooCommerce 产品")
    print("=" * 60)
    print(f"店铺: {WC_BASE_URL}")
    print(f"产品数量: {len(PRODUCTS)}")
    print()

    success_count = 0
    failed_count = 0
    added_products = []

    for i, product in enumerate(PRODUCTS, 1):
        print(f"\n[{i}/{len(PRODUCTS)}] 正在添加: {product['name']}")
        result = add_product(product)
        if result:
            success_count += 1
            added_products.append(result)
        else:
            failed_count += 1

    print("\n" + "=" * 60)
    print("批量添加完成")
    print("=" * 60)
    print(f"成功: {success_count}")
    print(f"失败: {failed_count}")
    print(f"总计: {len(PRODUCTS)}")

    if added_products:
        print("\n已添加产品列表:")
        for p in added_products:
            print(f"  - ID: {p['id']}, SKU: {p['sku']}, 名称: {p['name']}, 价格: ${p['price']}")

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
