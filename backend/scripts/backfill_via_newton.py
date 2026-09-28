"""通过牛顿 Agent API 从 1688 提取图片并回填 Product.meta["images"]。

用法:
    cd /opt/nuotao/backend && .venv/bin/python scripts/backfill_via_newton.py [--dry-run] [--limit 5]

说明:
    - 遍历无图片的产品
    - 从 source_url 提取 1688 商品 ID
    - 调用牛顿 Agent extract_1688_product 获取 image_urls
    - 写入 product.meta["images"]
    - 每次 API 调用约 50-114 秒，建议分批运行
"""

import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.models.product import Product
from app.core.database import async_session_factory
from app.services.newton_agent_service import extract_1688_product, is_configured

PRODUCT_ID_PATTERN = re.compile(r"/offer/(\d+)")


def extract_1688_id(url: str) -> str | None:
    """从 1688 URL 中提取商品 ID。"""
    if not url:
        return None
    m = PRODUCT_ID_PATTERN.search(url)
    return m.group(1) if m else None


async def backfill_via_newton(
    dry_run: bool = True,
    limit: int | None = None,
) -> dict:
    """通过牛顿 Agent 回填产品图片。"""
    if not is_configured():
        print("ERROR: 牛顿 Agent API 未配置 (ALI1688_APP_KEY/SECRET/TOKEN)")
        sys.exit(1)

    stats = {"scanned": 0, "fetched": 0, "updated": 0, "skipped": 0, "errors": 0}

    async with async_session_factory() as session:
        async with session.begin():
            query = select(Product).where(
                Product.source_url.isnot(None),
                Product.source_url != "",
                Product.deleted_at.is_(None),
            )
            if limit:
                query = query.limit(limit)

            products = list((await session.execute(query)).scalars().all())
            stats["scanned"] = len(products)

            for product in products:
                # 跳过已有图片的
                if (product.meta or {}).get("images"):
                    stats["skipped"] += 1
                    continue

                pid = extract_1688_id(product.source_url or "")
                if not pid:
                    stats["skipped"] += 1
                    continue

                print(f"  牛顿提取: {product.sku} (1688 id={pid})...", flush=True)

                try:
                    result = await asyncio.to_thread(
                        extract_1688_product,
                        product.source_url,
                        pid,
                        max_wait=180,
                    )

                    if not result.get("success", True):
                        stats["errors"] += 1
                        print(f"    -> API 错误: {result.get('error', 'unknown')}")
                        continue

                    # 提取图片 URL
                    images = []
                    raw = result.get("data", result)
                    img_urls = raw.get("image_urls") or raw.get("images") or []
                    if isinstance(img_urls, str):
                        img_urls = [img_urls]
                    for u in img_urls:
                        u = str(u).strip()
                        if u.startswith(("http://", "https://")):
                            images.append(u)

                    if not images:
                        stats["skipped"] += 1
                        print(f"    -> 无图片")
                        continue

                    # 写入 meta
                    meta = dict(product.meta) if product.meta else {}
                    meta["images"] = images
                    if not dry_run:
                        product.meta = meta
                        session.add(product)

                    stats["fetched"] += 1
                    stats["updated"] += 1
                    print(f"    -> {len(images)} 张图片 OK")

                except Exception as e:
                    stats["errors"] += 1
                    print(f"    -> ERROR: {e}")

                # 每条之间稍作延迟，避免触发 API 限流
                await asyncio.sleep(2)

    return stats


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv or "-n" in sys.argv
    lim = None
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            lim = int(sys.argv[i + 1])

    print(f"=== 牛顿 Agent 图片回填 (dry_run={dry}, limit={lim}) ===")
    result = asyncio.run(backfill_via_newton(dry_run=dry, limit=lim))
    print(
        f"\n完成: 扫描 {result['scanned']}, "
        f"抓取 {result['fetched']}, "
        f"更新 {result['updated']}, "
        f"跳过 {result['skipped']}, "
        f"错误 {result['errors']}"
    )
    if not dry:
        print("已写入数据库")
    else:
        print("dry-run 模式，未写库")
