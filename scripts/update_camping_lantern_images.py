#!/usr/bin/env python3
"""
更新露营灯产品（ID=942）的11张图片
"""
import requests
import json

WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
AUTH = ("ck_3644da6e081a9445459388cc92a82a096a35b427", "cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605")

PRODUCT_ID = 942

# 11张图片ID（按顺序）
image_ids = [
    943,  # 01_white_background
    953,  # 02_camping_scene_v2
    944,  # 03_promotion
    954,  # 04_detail_structure_v2
    946,  # 05_multiple_options
    947,  # 06_detail_brand_hero
    955,  # 07_detail_key_selling_points_v2
    949,  # 08_detail_function_structure
    950,  # 09_detail_usage_scenarios
    951,  # 10_detail_product_details
    956,  # 11_detail_quality_assurance_v2
]

# 构建images数组
images = [{"id": img_id} for img_id in image_ids]

print(f"更新产品 {PRODUCT_ID} 的 {len(images)} 张图片...")
print(f"图片ID: {image_ids}")

# 更新产品
update_data = {
    "images": images
}

response = requests.put(
    f"{WC_URL}/products/{PRODUCT_ID}",
    auth=AUTH,
    json=update_data,
    timeout=30
)

if response.status_code == 200:
    result = response.json()
    print(f"\n✅ 产品图片更新成功！")
    print(f"产品ID: {result.get('id')}")
    print(f"产品名称: {result.get('name')}")
    print(f"图片数量: {len(result.get('images', []))}")
    print(f"\n图片列表:")
    for i, img in enumerate(result.get('images', [])):
        print(f"  {i+1}. ID={img.get('id')}, {img.get('name', 'N/A')}")
    print(f"\n产品链接: {result.get('permalink')}")
else:
    print(f"\n❌ 更新失败: {response.status_code}")
    print(f"响应: {response.text}")
