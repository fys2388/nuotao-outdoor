"""回填已有产品的 meta["images"] —— 从 ProductSource.raw_data 恢复 1688 图片 URL。

用法:
    cd /opt/nuotao/backend && python scripts/backfill_product_images.py [--dry-run]

说明:
    - 扫描所有 ProductSource.raw_data 中含 images / image_urls / main_image 的记录
    - 将有效 http(s) URL 写入对应 Product.meta["images"]
    - --dry-run 只打印不写库
"""

import asyncio
import sys
from pathlib import Path

# 确保 backend 目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_intelligence import ProductSource
from app.core.database import async_session_factory


async def backfill_images(dry_run: bool = True) -> dict:
    """从 ProductSource.raw_data 提取图片并回填到 Product.meta。"""
    stats = {"scanned": 0, "updated": 0, "skipped": 0, "errors": 0}

    async with async_session_factory() as session:
        async with session.begin():
            # 查出所有 Product + ProductSource 对
            sources = await session.execute(
                select(ProductSource)
                .where(ProductSource.raw_data.isnot(None))
            )
            sources_list = list(sources.scalars().all())
            stats["scanned"] = len(sources_list)

            for src in sources_list:
                raw = src.raw_data
                if not isinstance(raw, dict):
                    stats["skipped"] += 1
                    continue

                # 提取图片 URL（兼容多种字段名）
                images_raw = (
                    raw.get("images")
                    or raw.get("image_urls")
                    or raw.get("图片URL")
                    or []
                )
                if isinstance(images_raw, str):
                    images_raw = [images_raw]

                # 如果没有 images 字段，尝试从 main_image 提取
                if not images_raw and raw.get("main_image"):
                    images_raw = [raw["main_image"]]

                valid_images = [
                    str(u).strip()
                    for u in images_raw
                    if str(u).strip().startswith(("http://", "https://"))
                ]

                if not valid_images:
                    stats["skipped"] += 1
                    continue

                # 读取当前 Product.meta
                product = await session.get(Product, src.product_id)
                if product is None:
                    stats["skipped"] += 1
                    continue

                current_meta = dict(product.meta) if product.meta else {}
                current_images = current_meta.get("images", [])

                # 去重合并
                merged = list(dict.fromkeys(valid_images + current_images))
                if merged == current_images:
                    stats["skipped"] += 1
                    continue

                if not dry_run:
                    current_meta["images"] = merged
                    product.meta = current_meta
                    session.add(product)

                stats["updated"] += 1
                print(
                    f"  [{stats['updated']}] {product.sku}: "
                    f"{len(valid_images)} 新图片, 共 {len(merged)} 张"
                )

    return stats


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv or "-n" in sys.argv
    print(f"=== 回填产品图片 (dry_run={dry}) ===")
    result = asyncio.run(backfill_images(dry_run=dry))
    print(f"\n完成: 扫描 {result['scanned']} 条, 更新 {result['updated']} 条, "
          f"跳过 {result['skipped']} 条")
    if not dry:
        print("✅ 已写入数据库")
    else:
        print("ℹ️  dry-run 模式，未写库。去掉 --dry-run 参数实际执行。")
