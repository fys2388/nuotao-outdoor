#!/usr/bin/env python3
"""
头灯产品上架脚本
- 上传11张图片到WordPress媒体库
- 创建WooCommerce产品
- 配置属性、库存、采购关联meta
"""

import requests
import base64
import json
import os
import time

# 配置
WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
WP_URL = "https://nuotaooutdoor.com/wp-json/wp/v2"
CONSUMER_KEY = "ck_3644da6e081a9445459388cc92a82a096a35b427"
CONSUMER_SECRET = "cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605"
IMAGE_DIR = r"E:\AI\nuotao-ai-os\headlamp_images"

# 认证
auth = (CONSUMER_KEY, CONSUMER_SECRET)
wp_auth = base64.b64encode(f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode()).decode()
wp_headers = {"Authorization": f"Basic {wp_auth}"}

def upload_image(filepath, filename):
    """上传图片到WordPress媒体库"""
    url = f"{WP_URL}/media"
    headers = {
        "Authorization": f"Basic {wp_auth}",
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    with open(filepath, "rb") as f:
        files = {"file": (filename, f, "image/jpeg")}
        response = requests.post(url, headers=headers, files=files, timeout=30)
    if response.status_code == 201:
        data = response.json()
        print(f"  上传成功: {filename} -> ID {data['id']}")
        return data["id"], data["source_url"]
    else:
        print(f"  上传失败: {filename} -> {response.status_code} {response.text[:200]}")
        return None, None

def create_product(image_ids):
    """创建WooCommerce产品"""
    url = f"{WC_URL}/products"
    
    # 构建图片数组
    images = []
    for i, img_id in enumerate(image_ids):
        images.append({"id": img_id})
    
    # 产品数据
    product_data = {
        "name": "Ultra-Bright LED Headlamp - Motion Sensor, IPX4 Waterproof, 1200mAh Rechargeable for Camping Fishing Running",
        "slug": "ultra-bright-led-headlamp-motion-sensor-ipx4-waterproof-rechargeable",
        "type": "simple",
        "status": "publish",
        "sku": "NTO-HEADLAMP-001",
        "price": "19.99",
        "regular_price": "24.99",
        "sale_price": "19.99",
        "description": """
<h2>Illuminate Your Adventure</h2>
<p>Experience hands-free lighting with our Ultra-Bright LED Headlamp. Perfect for camping, fishing, running, and any outdoor activity where you need both hands free.</p>

<h3>Key Features</h3>
<ul>
<li><strong>Motion Sensor Control</strong> - Wave your hand to turn on/off, completely hands-free operation</li>
<li><strong>Ultra-Bright LED</strong> - 500 lumens output, illuminates up to 200-500 meters</li>
<li><strong>IPX4 Waterproof</strong> - Rain and sweat resistant, perfect for all weather conditions</li>
<li><strong>1200mAh Rechargeable Battery</strong> - Up to 8 hours runtime, USB-C fast charging</li>
<li><strong>Lightweight & Comfortable</strong> - Only 300g, adjustable elastic headband for all head sizes</li>
<li><strong>Multiple Light Modes</strong> - High/Low/Strobe/SOS modes for different scenarios</li>
</ul>

<h3>Multiple Options Available</h3>
<p>Choose from Single LED, Dual LED, or Tri-LED configurations to match your needs.</p>

<h3>Quality Assurance</h3>
<ul>
<li>CE / ROHS / FCC / MSDS certified</li>
<li>30-day money back guarantee</li>
<li>1-year warranty</li>
<li>24/7 customer support</li>
</ul>
        """,
        "short_description": "Ultra-bright 500 lumen LED headlamp with motion sensor control, IPX4 waterproof, 1200mAh rechargeable battery. Perfect for camping, fishing, running, and outdoor activities. Lightweight 300g design with adjustable headband.",
        "categories": [
            {"id": 15},  # Outdoor Lighting (需要确认分类ID)
        ],
        "tags": [
            {"name": "headlamp"},
            {"name": "LED headlamp"},
            {"name": "camping light"},
            {"name": "fishing headlamp"},
            {"name": "running light"},
            {"name": "motion sensor"},
            {"name": "waterproof"},
            {"name": "rechargeable"},
            {"name": "outdoor gear"},
        ],
        "images": images,
        "attributes": [
            {
                "name": "Light Configuration",
                "position": 0,
                "visible": True,
                "variation": False,
                "options": ["Single LED", "Dual LED", "Tri-LED (White+Red+Yellow)"]
            },
            {
                "name": "Brightness",
                "position": 1,
                "visible": True,
                "variation": False,
                "options": ["500 Lumens"]
            },
            {
                "name": "Battery Capacity",
                "position": 2,
                "visible": True,
                "variation": False,
                "options": ["1200mAh"]
            },
            {
                "name": "Waterproof Rating",
                "position": 3,
                "visible": True,
                "variation": False,
                "options": ["IPX4"]
            },
            {
                "name": "Weight",
                "position": 4,
                "visible": True,
                "variation": False,
                "options": ["300g"]
            },
            {
                "name": "Certification",
                "position": 5,
                "visible": True,
                "variation": False,
                "options": ["CE", "ROHS", "FCC", "MSDS"]
            },
        ],
        "manage_stock": True,
        "stock_quantity": 100,
        "low_stock_amount": 10,
        "stock_status": "instock",
        "weight": "0.3",
        "dimensions": {
            "length": "10",
            "width": "8",
            "height": "5"
        },
        "shipping_class": "standard",
        "meta_data": [
            {"key": "_1688_product_url", "value": "https://detail.1688.com/offer/1037363321650.html"},
            {"key": "_1688_offer_id", "value": "1037363321650"},
            {"key": "_supplier_name", "value": "义乌市松兴户外用品有限公司"},
            {"key": "_supplier_rating", "value": "入驻7年, 回头率44%, 好评率99.6%, 准时发货率99%"},
            {"key": "_purchase_price_cny", "value": "6.50"},
            {"key": "_purchase_price_usd", "value": "0.90"},
            {"key": "_profit_margin", "value": "85%"},
            {"key": "_purchase_method", "value": "1688一件代发"},
            {"key": "_selection_score", "value": "87.5"},
            {"key": "_selection_grade", "value": "A"},
        ],
    }
    
    response = requests.post(url, auth=auth, json=product_data, timeout=30)
    if response.status_code == 201:
        data = response.json()
        print(f"\n产品创建成功! ID: {data['id']}, SKU: {data['sku']}")
        print(f"产品链接: {data['permalink']}")
        return data
    else:
        print(f"\n产品创建失败: {response.status_code}")
        print(response.text[:500])
        return None

def main():
    print("=" * 60)
    print("头灯产品上架流程")
    print("=" * 60)
    
    # 1. 上传图片
    print("\n[1/2] 上传11张图片到WordPress媒体库...")
    image_files = sorted([f for f in os.listdir(IMAGE_DIR) if f.endswith('.jpg')])
    image_ids = []
    
    for filename in image_files:
        filepath = os.path.join(IMAGE_DIR, filename)
        img_id, img_url = upload_image(filepath, filename)
        if img_id:
            image_ids.append(img_id)
        time.sleep(1)  # 避免请求过快
    
    print(f"\n成功上传 {len(image_ids)}/11 张图片")
    
    if len(image_ids) < 5:
        print("警告: 图片数量不足，可能影响产品展示")
    
    # 2. 创建产品
    print("\n[2/2] 创建WooCommerce产品...")
    product = create_product(image_ids)
    
    if product:
        print("\n" + "=" * 60)
        print("上架完成!")
        print(f"产品ID: {product['id']}")
        print(f"产品名称: {product['name']}")
        print(f"SKU: {product['sku']}")
        print(f"价格: ${product['price']}")
        print(f"图片数量: {len(product['images'])}")
        print(f"产品链接: {product['permalink']}")
        print("=" * 60)
    else:
        print("\n产品创建失败，请检查错误信息")

if __name__ == "__main__":
    main()
