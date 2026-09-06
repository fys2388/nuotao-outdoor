#!/usr/bin/env python3
"""更新头灯产品分类"""
import requests

WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
AUTH = ("ck_3644da6e081a9445459388cc92a82a096a35b427", "cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605")

# 更新头灯产品（ID 930）的分类
# Lighting & Power (ID=22) > Headlamps (ID=130)
product_id = 930
data = {
    "categories": [
        {"id": 22},  # Lighting & Power
        {"id": 130}  # Headlamps
    ]
}

print(f"更新产品{product_id}的分类...")
response = requests.put(f"{WC_URL}/products/{product_id}", auth=AUTH, json=data, timeout=30)

if response.status_code == 200:
    result = response.json()
    print(f"✅ 产品分类更新成功！")
    print(f"产品ID: {result.get('id')}")
    print(f"产品名称: {result.get('name')}")
    print(f"分类:")
    for cat in result.get('categories', []):
        print(f"  ID={cat['id']}, 名称={cat['name']}")
else:
    print(f"❌ 更新失败: {response.status_code} - {response.text}")
