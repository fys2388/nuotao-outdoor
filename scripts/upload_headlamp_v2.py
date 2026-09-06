#!/usr/bin/env python3
"""
头灯产品上架脚本 V2
- 使用WooCommerce API直接传入图片URL，让WooCommerce自动下载
- 创建产品并配置属性、库存、采购关联meta
"""

import requests
import json
import time

# 配置
WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
CONSUMER_KEY = "ck_3644da6e081a9445459388cc92a82a096a35b427"
CONSUMER_SECRET = "cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605"
auth = (CONSUMER_KEY, CONSUMER_SECRET)

# 11张图片URL
IMAGE_URLS = [
    "https://aka.doubaocdn.com/s/u2Qyb5WA9u",  # 01 白底主图
    "https://aka.doubaocdn.com/s/9IVnAkNsMV",  # 02 露营场景
    "https://aka.doubaocdn.com/s/P4ynNMyVMP",  # 03 促销转化
    "https://aka.doubaocdn.com/s/AaVaGnsoyS",  # 04 结构细节
    "https://aka.doubaocdn.com/s/MHxtPJqcrF",  # 05 多规格展示
    "https://aka.doubaocdn.com/s/wKS6gqybup",  # 06 品牌主视觉
    "https://aka.doubaocdn.com/s/ze5DnehlNz",  # 07 核心卖点
    "https://aka.doubaocdn.com/s/mKEU6hYmiK",  # 08 功能结构
    "https://aka.doubaocdn.com/s/QEj3kLhC7Q",  # 09 使用场景
    "https://aka.doubaocdn.com/s/xH86cUVGSn",  # 10 产品细节
    "https://aka.doubaocdn.com/s/OV1UB4UYkD",  # 11 品质保障
]

def create_product():
    """创建WooCommerce产品"""
    url = f"{WC_URL}/products"
    
    # 构建图片数组（使用URL，WooCommerce会自动下载）
    images = []
    for i, img_url in enumerate(IMAGE_URLS):
        images.append({
            "src": img_url,
            "name": f"headlamp_{i+1:02d}.jpg",
            "alt": "Ultra-Bright LED Headlamp"
        })
    
    # 产品数据
    product_data = {
        "name": "Ultra-Bright LED Headlamp - Motion Sensor, IPX4 Waterproof, 1200mAh Rechargeable for Camping Fishing Running",
        "slug": "ultra-bright-led-headlamp-motion-sensor-waterproof-rechargeable",
        "type": "simple",
        "status": "publish",
        "sku": "NTO-LED-HEADLAMP-001",
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
            {"id": 15},
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
    
    print("正在创建产品（含11张图片下载）...")
    print("WooCommerce需要从URL下载图片，这可能需要1-2分钟...")
    
    response = requests.post(url, auth=auth, json=product_data, timeout=180)
    
    if response.status_code == 201:
        data = response.json()
        print(f"\n产品创建成功!")
        print(f"  ID: {data['id']}")
        print(f"  SKU: {data['sku']}")
        print(f"  名称: {data['name']}")
        print(f"  价格: ${data['price']}")
        print(f"  图片数量: {len(data['images'])}")
        print(f"  产品链接: {data['permalink']}")
        return data
    else:
        print(f"\n产品创建失败: {response.status_code}")
        print(response.text[:1000])
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("头灯产品上架 V2 - 使用图片URL直接导入")
    print("=" * 60)
    create_product()
