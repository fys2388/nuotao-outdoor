#!/usr/bin/env python3
"""
获取产品930的当前状态，然后更新images数组
"""
import requests
import json

# WooCommerce API配置
WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
CONSUMER_KEY = "ck_3644da6e081a9445459388cc92a82a096a35b427"
CONSUMER_SECRET = "cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605"
AUTH = (CONSUMER_KEY, CONSUMER_SECRET)

def get_product(product_id):
    """获取产品信息"""
    url = f"{WC_URL}/products/{product_id}"
    response = requests.get(url, auth=AUTH, timeout=30)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"获取产品失败: {response.status_code} - {response.text}")
        return None

def update_product_images(product_id, images):
    """更新产品图片"""
    url = f"{WC_URL}/products/{product_id}"
    data = {"images": images}
    response = requests.put(url, auth=AUTH, json=data, timeout=30)
    if response.status_code == 200:
        print(f"产品图片更新成功！")
        return response.json()
    else:
        print(f"更新产品图片失败: {response.status_code} - {response.text}")
        return None

# 获取产品信息
print("=" * 60)
print("获取产品930信息...")
product = get_product(930)

if product:
    print(f"产品ID: {product.get('id')}")
    print(f"产品名称: {product.get('name')}")
    print(f"价格: ${product.get('price')}")
    print(f"库存: {product.get('stock_quantity')}")
    print(f"图片数量: {len(product.get('images', []))}")
    
    print("\n当前图片列表:")
    for i, img in enumerate(product.get('images', [])):
        print(f"  {i+1}. ID={img.get('id')}, 名称={img.get('name')}")
        print(f"     URL={img.get('src', '')[:100]}")
    
    # 检查是否有图片
    if len(product.get('images', [])) == 0:
        print("\n" + "=" * 60)
        print("产品没有图片！需要从媒体库获取图片ID")
        print("尝试通过WordPress REST API获取媒体库...")
        
        # 尝试通过WordPress REST API获取媒体库
        # WooCommerce Consumer Key可能没有权限，需要用Application Password
        print("\n注意：WooCommerce Consumer Key可能没有WordPress媒体库访问权限")
        print("需要通过浏览器后台手动添加图片到产品图库")
    else:
        print("\n产品已有图片，无需更新")

print("\n" + "=" * 60)
