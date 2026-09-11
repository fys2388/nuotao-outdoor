#!/usr/bin/env python3
"""
下载露营灯11张AI图片到本地
"""
import requests
import os

# 创建目录
output_dir = "E:/AI/nuotao-ai-os/camping_lantern_images"
os.makedirs(output_dir, exist_ok=True)

# 11张图片URL和文件名
images = [
    ("https://aka.doubaocdn.com/s/3qAkmUyeDw", "01_white_background.jpg"),
    ("https://aka.doubaocdn.com/s/7I84GVBMvY", "02_camping_scene.jpg"),
    ("https://aka.doubaocdn.com/s/eX0EpROped", "03_promotion.jpg"),
    ("https://aka.doubaocdn.com/s/G5Nhawy5jV", "04_detail_structure.jpg"),
    ("https://aka.doubaocdn.com/s/RLi6KB6BZu", "05_multiple_options.jpg"),
    ("https://aka.doubaocdn.com/s/eOyhaa2YhZ", "06_detail_brand_hero.jpg"),
    ("https://aka.doubaocdn.com/s/cC6cB9srcm", "07_detail_key_selling_points.jpg"),
    ("https://aka.doubaocdn.com/s/c0CsPLHSzG", "08_detail_function_structure.jpg"),
    ("https://aka.doubaocdn.com/s/q8ezZzMUJP", "09_detail_usage_scenarios.jpg"),
    ("https://aka.doubaocdn.com/s/zn61gYUeLc", "10_detail_product_details.jpg"),
    ("https://aka.doubaocdn.com/s/BQKU2V3003", "11_detail_quality_assurance.jpg"),
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

print("开始下载11张露营灯AI图片...")
success_count = 0
for url, filename in images:
    filepath = os.path.join(output_dir, filename)
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(response.content)
            print(f"  ✅ {filename}: {len(response.content)} bytes")
            success_count += 1
        else:
            print(f"  ❌ {filename}: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ❌ {filename}: {str(e)}")

print(f"\n下载完成: {success_count}/11 张图片成功")
print(f"保存目录: {output_dir}")
