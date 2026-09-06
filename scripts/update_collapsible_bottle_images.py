#!/usr/bin/env python3
import requests

WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
AUTH = ("ck_3644da6e081a9445459388cc92a82a096a35b427", "cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605")

PRODUCT_ID = 957
image_ids = [958, 959, 960, 961, 962, 963, 964, 965, 966, 967]
images = [{"id": img_id} for img_id in image_ids]

print(f"更新产品 {PRODUCT_ID} 的 {len(images)} 张图片...")
print(f"图片ID: {image_ids}")

response = requests.put(
    f"{WC_URL}/products/{PRODUCT_ID}",
    auth=AUTH,
    json={"images": images},
    timeout=30
)

if response.status_code == 200:
    result = response.json()
    print("✅ 产品图片更新成功！")
    print(f"产品ID: {result.get('id')}")
    print(f"图片数量: {len(result.get('images', []))}")
    print(f"产品链接: {result.get('permalink')}")
else:
    print(f"❌ 更新失败: {response.status_code}")
    print(f"响应: {response.text}")
