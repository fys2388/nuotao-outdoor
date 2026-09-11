#!/usr/bin/env python3
"""获取WooCommerce产品分类列表"""
import requests

WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
AUTH = ("ck_3644da6e081a9445459388cc92a82a096a35b427", "cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605")

response = requests.get(f"{WC_URL}/products/categories", auth=AUTH, params={"per_page": 50}, timeout=30)
if response.status_code == 200:
    categories = response.json()
    print("产品分类列表:")
    for cat in categories:
        print(f"  ID={cat['id']}, 名称={cat['name']}, 父级={cat['parent']}, 商品数={cat['count']}")
else:
    print(f"获取分类失败: {response.status_code} - {response.text}")
