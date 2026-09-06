#!/usr/bin/env python3
import requests
import os

image_dir = "E:/AI/nuotao-ai-os/thermos_bottle_images"
os.makedirs(image_dir, exist_ok=True)

images = [
    ("01_white_background.jpg", "https://aka.doubaocdn.com/s/NKv6na49Uz"),
    ("02_outdoor_scene.jpg", "https://aka.doubaocdn.com/s/E3RpzHP5U3"),
    ("03_promotion.jpg", "https://aka.doubaocdn.com/s/Yo0igEi8UU"),
    ("04_detail_structure.jpg", "https://aka.doubaocdn.com/s/fhSpzuZbVh"),
    ("05_multiple_colors.jpg", "https://aka.doubaocdn.com/s/Dd2WU8rlBk"),
    ("06_brand_hero.jpg", "https://aka.doubaocdn.com/s/neQZJOyiGn"),
    ("07_key_selling_points.jpg", "https://aka.doubaocdn.com/s/KM0yaivd1G"),
    ("08_function_structure.jpg", "https://aka.doubaocdn.com/s/eKEKpoLqGL"),
    ("09_usage_scenarios.jpg", "https://aka.doubaocdn.com/s/jUvaU1l2xp"),
    ("10_product_details.jpg", "https://aka.doubaocdn.com/s/SU6nObN0cf"),
    ("11_quality_assurance.jpg", "https://aka.doubaocdn.com/s/KbVPrdEYVI"),
]

for filename, url in images:
    filepath = os.path.join(image_dir, filename)
    try:
        r = requests.get(url, timeout=30)
        with open(filepath, "wb") as f:
            f.write(r.content)
        print(f"✅ {filename}: {len(r.content)} bytes")
    except Exception as e:
        print(f"❌ {filename}: {str(e)}")

print("\n11张图片下载完成！")
