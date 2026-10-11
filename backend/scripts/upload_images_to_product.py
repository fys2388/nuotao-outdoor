#!/usr/bin/env python3
"""
上传图片到WC产品脚本

使用 image_wc_pipeline 模块上传图片到WC媒体库并关联到产品
"""

import os
import sys
import asyncio
from typing import List

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app.services.image_wc_pipeline import upload_images_to_wc


async def upload_images(product_id: int, image_urls: List[str]):
    """上传图片到WC产品"""
    print(f"Uploading {len(image_urls)} images to product {product_id}...")
    
    result = await upload_images_to_wc(
        image_urls=image_urls,
        wc_product_id=product_id,
        product_name=f"Product {product_id}",
    )
    
    print(f"Uploaded: {result.uploaded}/{result.total}")
    print(f"Failed: {result.failed}/{result.total}")
    
    if result.errors:
        print(f"Errors: {result.errors}")
    
    return result


def main():
    """主函数"""
    if len(sys.argv) < 3:
        print("Usage: python upload_images_to_product.py <product_id> <image_url1> [image_url2] ...")
        print("Example: python upload_images_to_product.py 2378 https://example.com/image1.jpg https://example.com/image2.jpg")
        sys.exit(1)
    
    product_id = int(sys.argv[1])
    image_urls = sys.argv[2:]
    
    # 运行异步任务
    result = asyncio.run(upload_images(product_id, image_urls))
    
    sys.exit(0 if result.failed == 0 else 1)


if __name__ == "__main__":
    main()
