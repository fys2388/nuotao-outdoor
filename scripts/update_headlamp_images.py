#!/usr/bin/env python3
"""
更新产品930的images数组，添加所有11张头灯图片
"""
import requests
import json

# WooCommerce API配置
WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
CONSUMER_KEY = "ck_3644da6e081a9445459388cc92a82a096a35b427"
CONSUMER_SECRET = "cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605"
AUTH = (CONSUMER_KEY, CONSUMER_SECRET)

# 11张头灯图片的ID（按顺序：主图01，然后02-11）
IMAGE_IDS = [
    931,  # 01_white_background-1.jpg（主图）
    932,  # 02_camping_scene-1.jpg
    933,  # 03_promotion-1.jpg
    934,  # 04_detail_structure.jpg
    935,  # 05_multiple_options.jpg
    936,  # 06_detail_brand_hero-1.jpg
    937,  # 07_detail_key_selling_points-1.jpg
    938,  # 08_detail_function_structure-1.jpg
    939,  # 09_detail_usage_scenarios-1.jpg
    940,  # 10_detail_product_details-1.jpg
    941,  # 11_detail_quality_assurance-1.jpg
]

def update_product_images(product_id, image_ids):
    """更新产品图片"""
    url = f"{WC_URL}/products/{product_id}"
    
    # 构建images数组
    images = [{"id": img_id} for img_id in image_ids]
    
    data = {"images": images}
    print(f"更新产品{product_id}的图片，共{len(images)}张...")
    print(f"图片ID: {image_ids}")
    
    response = requests.put(url, auth=AUTH, json=data, timeout=30)
    
    if response.status_code == 200:
        result = response.json()
        print(f"\n✅ 产品图片更新成功！")
        print(f"产品ID: {result.get('id')}")
        print(f"产品名称: {result.get('name')}")
        print(f"图片数量: {len(result.get('images', []))}")
        print("\n图片列表:")
        for i, img in enumerate(result.get('images', [])):
            print(f"  {i+1}. ID={img.get('id')}, 名称={img.get('name')}")
            print(f"     URL={img.get('src', '')[:100]}")
        return result
    else:
        print(f"\n❌ 更新产品图片失败: {response.status_code}")
        print(f"响应: {response.text}")
        return None

# 执行更新
print("=" * 60)
print("更新头灯产品（ID 930）的图片...")
print("=" * 60)

result = update_product_images(930, IMAGE_IDS)

print("\n" + "=" * 60)
if result:
    print("✅ 任务完成！产品930已成功添加11张图片")
else:
    print("❌ 任务失败")
print("=" * 60)
