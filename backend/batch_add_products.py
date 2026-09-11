"""
批量添加 WooCommerce 测试产品
"""
import os

import requests
from requests.auth import HTTPBasicAuth

# WooCommerce 配置
WC_BASE_URL = os.getenv("WOOCOMMERCE_BASE_URL", "https://nuotaooutdoor.com")
WC_CONSUMER_KEY = os.getenv("WOOCOMMERCE_CONSUMER_KEY", "")
WC_CONSUMER_SECRET = os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "")

API_URL = f"{WC_BASE_URL}/wp-json/wc/v3"
AUTH = HTTPBasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET)

# 产品数据
PRODUCTS = [
    {
        "name": "Premium Outdoor Sleeping Bag - 15°F",
        "type": "simple",
        "regular_price": "89.99",
        "sale_price": "69.99",
        "sku": "NT-SLEEP-001",
        "manage_stock": True,
        "stock_quantity": 50,
        "description": "High-quality 15°F sleeping bag with water-resistant outer shell, synthetic insulation, and compression sack. Perfect for camping, hiking, and backpacking in cold weather.",
        "short_description": "15°F cold weather sleeping bag with water-resistant shell and compression sack.",
        "categories": [{"id": 15}],
        "tags": [{"name": "camping"}, {"name": "sleeping bag"}, {"name": "outdoor"}],
        "weight": "1.8",
        "dimensions": {"length": "210", "width": "80", "height": "5"}
    },
    {
        "name": "Portable Folding Camping Chair",
        "type": "simple",
        "regular_price": "49.99",
        "sale_price": "39.99",
        "sku": "NT-CHAIR-001",
        "manage_stock": True,
        "stock_quantity": 100,
        "description": "Lightweight folding camping chair with aluminum frame, breathable mesh seat, and carry bag. Supports up to 150kg. Perfect for camping, fishing, picnics, and outdoor events.",
        "short_description": "Lightweight aluminum folding chair with carry bag, supports 150kg.",
        "categories": [{"id": 15}],
        "tags": [{"name": "camping"}, {"name": "chair"}, {"name": "folding"}],
        "weight": "2.5",
        "dimensions": {"length": "50", "width": "50", "height": "90"}
    },
    {
        "name": "50L Hiking Backpack with Rain Cover",
        "type": "simple",
        "regular_price": "79.99",
        "sale_price": "59.99",
        "sku": "NT-BAG-001",
        "manage_stock": True,
        "stock_quantity": 75,
        "description": "50L hiking backpack with multiple compartments, adjustable straps, water-resistant material, and included rain cover. Perfect for day hikes, overnight trips, and travel.",
        "short_description": "50L hiking backpack with rain cover, multiple compartments, adjustable straps.",
        "categories": [{"id": 15}],
        "tags": [{"name": "hiking"}, {"name": "backpack"}, {"name": "outdoor"}],
        "weight": "1.2",
        "dimensions": {"length": "30", "width": "25", "height": "60"}
    },
    {
        "name": "Rechargeable LED Headlamp - 1000 Lumens",
        "type": "simple",
        "regular_price": "34.99",
        "sale_price": "24.99",
        "sku": "NT-LIGHT-001",
        "manage_stock": True,
        "stock_quantity": 200,
        "description": "1000 lumen rechargeable LED headlamp with 5 lighting modes, IPX6 waterproof rating, adjustable headband, and USB-C charging. Perfect for camping, hiking, running, and emergencies.",
        "short_description": "1000 lumen rechargeable headlamp, 5 modes, IPX6 waterproof, USB-C.",
        "categories": [{"id": 15}],
        "tags": [{"name": "headlamp"}, {"name": "LED"}, {"name": "camping"}],
        "weight": "0.15",
        "dimensions": {"length": "8", "width": "6", "height": "4"}
    },
    {
        "name": "Stainless Steel Insulated Water Bottle - 1L",
        "type": "simple",
        "regular_price": "29.99",
        "sale_price": "19.99",
        "sku": "NT-BOTTLE-001",
        "manage_stock": True,
        "stock_quantity": 150,
        "description": "1L stainless steel insulated water bottle with double-wall vacuum insulation, keeps drinks cold for 24 hours or hot for 12 hours. BPA-free, leak-proof lid, wide mouth for ice cubes.",
        "short_description": "1L insulated stainless steel bottle, 24h cold / 12h hot, BPA-free.",
        "categories": [{"id": 15}],
        "tags": [{"name": "water bottle"}, {"name": "insulated"}, {"name": "outdoor"}],
        "weight": "0.4",
        "dimensions": {"length": "8", "width": "8", "height": "28"}
    },
    {
        "name": "Camping Cookware Set - 10 Pieces",
        "type": "simple",
        "regular_price": "59.99",
        "sale_price": "44.99",
        "sku": "NT-COOK-001",
        "manage_stock": True,
        "stock_quantity": 60,
        "description": "10-piece camping cookware set including pots, pans, cups, and utensils. Made from lightweight anodized aluminum, non-stick coating, foldable handles, and mesh carry bag. Perfect for 2-3 people camping.",
        "short_description": "10-piece aluminum camping cookware set, non-stick, foldable handles, carry bag.",
        "categories": [{"id": 15}],
        "tags": [{"name": "cookware"}, {"name": "camping"}, {"name": "outdoor"}],
        "weight": "1.5",
        "dimensions": {"length": "20", "width": "20", "height": "15"}
    },
    {
        "name": "Inflatable Camping Sleeping Pad",
        "type": "simple",
        "regular_price": "44.99",
        "sale_price": "34.99",
        "sku": "NT-PAD-001",
        "manage_stock": True,
        "stock_quantity": 80,
        "description": "Inflatable camping sleeping pad with built-in foot pump, 10cm thickness, R-value 3.5, lightweight and compact. Provides excellent insulation and comfort for camping and hiking.",
        "short_description": "Inflatable sleeping pad with foot pump, 10cm thick, R-value 3.5.",
        "categories": [{"id": 15}],
        "tags": [{"name": "sleeping pad"}, {"name": "camping"}, {"name": "inflatable"}],
        "weight": "0.6",
        "dimensions": {"length": "190", "width": "60", "height": "10"}
    },
    {
        "name": "Multi-tool Camping Knife - 15 Functions",
        "type": "simple",
        "regular_price": "39.99",
        "sale_price": "29.99",
        "sku": "NT-TOOL-001",
        "manage_stock": True,
        "stock_quantity": 120,
        "description": "15-function multi-tool camping knife including blade, pliers, screwdrivers, can opener, bottle opener, saw, file, and more. Made from stainless steel, with nylon sheath. Perfect for camping, hiking, and everyday carry.",
        "short_description": "15-function stainless steel multi-tool with nylon sheath.",
        "categories": [{"id": 15}],
        "tags": [{"name": "multi-tool"}, {"name": "knife"}, {"name": "camping"}],
        "weight": "0.3",
        "dimensions": {"length": "10", "width": "4", "height": "2"}
    }
]


def create_product(product_data):
    """创建单个产品"""
    try:
        response = requests.post(
            f"{API_URL}/products",
            auth=AUTH,
            json=product_data,
            timeout=30
        )
        if response.status_code == 201:
            product = response.json()
            print(f"  ✅ 创建成功: {product['name']} (ID: {product['id']}, SKU: {product['sku']})")
            return True
        else:
            print(f"  ❌ 创建失败: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"  ❌ 创建异常: {e}")
        return False


def main():
    print("=" * 60)
    print("WooCommerce 批量添加产品")
    print("=" * 60)
    print(f"\n店铺: {WC_BASE_URL}")
    print(f"产品数量: {len(PRODUCTS)}")
    print("\n开始创建产品...\n")

    success_count = 0
    for i, product in enumerate(PRODUCTS, 1):
        print(f"[{i}/{len(PRODUCTS)}] {product['name']}")
        if create_product(product):
            success_count += 1

    print("\n" + "=" * 60)
    print(f"创建完成: 成功 {success_count}/{len(PRODUCTS)}")
    print("=" * 60)

    # 验证产品数量
    try:
        response = requests.get(f"{API_URL}/products", auth=AUTH, params={"per_page": 100}, timeout=30)
        if response.status_code == 200:
            products = response.json()
            print(f"\n当前店铺产品总数: {len(products)}")
            print("\n产品列表:")
            for p in products:
                print(f"  - {p['name']} (${p['price']}, 库存: {p['stock_quantity']})")
    except Exception as e:
        print(f"\n验证产品列表失败: {e}")


if __name__ == "__main__":
    main()
