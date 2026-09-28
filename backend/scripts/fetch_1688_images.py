"""从 1688 商品页抓取图片 URL 并回填到 Product.meta["images"]。

用法:
    cd /opt/nuotao/backend && .venv/bin/python scripts/fetch_1688_images.py [--dry-run] [--limit 5]

说明:
    - 遍历所有有 source_url 且 meta 中没有 images 的产品
    - 请求 1688 页面提取 <img> 标签中的商品图片
    - 写入 product.meta["images"]
"""

import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.core.database import async_session_factory

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 1688 图片域名白名单（过滤掉装饰性图标/水印图）
IMG_DOMAINS = {"cbu01.alicdn.com", "img.alicdn.com", "sc04.alicdn.com"}

# 匹配 1688 商品主图 URL 模式（通常为高分辨率 jpg）
IMG_URL_PATTERN = re.compile(
    r'https?://(?:cbu01|img|sc0[1-4])\.alicdn\.com/imgextra/[^"\s<>]+\.(?:jpg|jpeg|png|webp)',
    re.IGNORECASE,
)


async def fetch_1688_images(url: str, timeout: float = 15.0) -> list[str]:
    """从 1688 商品页提取商品图片 URL 列表。"""
    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        print(f"  [WARN] fetch failed: {url} -> {e}")
        return []

    # 提取所有候选图片 URL
    urls = list(set(IMG_URL_PATTERN.findall(html)))

    # 过滤：只保留白名单域名，排除小图标（文件名太短或含 icon/logo 等）
    filtered = []
    for u in urls:
        hostname = urlparse(u).hostname or ""
        if hostname not in IMG_DOMAINS:
            continue
        path = urlparse(u).path
        # 排除明显不是商品图的文件名
        basename = path.rsplit("/", 1)[-1].lower()
        if any(kw in basename for kw in ("icon", "logo", "watermark", "avatar", "default", "placeholder")):
            continue
        filtered.append(u)

    # 去重并按 URL 排序（保证一致性）
    return list(dict.fromkeys(filtered))[:20]


async def backfill_images(
    dry_run: bool = True,
    limit: int | None = None,
) -> dict:
    """遍历无图片的产品，从 1688 源页面抓取图片并回填。"""
    stats = {"scanned": 0, "fetched": 0, "updated": 0, "skipped": 0, "errors": 0}

    async with async_session_factory() as session:
        async with session.begin():
            # 查询有 source_url 但 meta 中没有 images 的产品
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
                current_meta = product.meta or {}
                if current_meta.get("images"):
                    stats["skipped"] += 1
                    continue

                url = product.source_url
                print(f"  抓取图片: {product.sku} -> {url}")
                images = await fetch_1688_images(url)

                if not images:
                    stats["skipped"] += 1
                    continue

                # 写入 meta
                current_meta["images"] = images
                if not dry_run:
                    product.meta = current_meta
                    session.add(product)

                stats["fetched"] += 1
                stats["updated"] += 1
                print(f"  ✅ {len(images)} 张图片: {images[0][:80]}...")

    return stats


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv or "-n" in sys.argv
    lim = None
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            lim = int(sys.argv[i + 1])

    print(f"=== 从 1688 抓取产品图片 (dry_run={dry}, limit={lim}) ===")
    result = asyncio.run(backfill_images(dry_run=dry, limit=lim))
    print(
        f"\n完成: 扫描 {result['scanned']} 条, "
        f"抓取 {result['fetched']} 条, "
        f"更新 {result['updated']} 条, "
        f"跳过 {result['skipped']} 条"
    )
    if not dry:
        print("✅ 已写入数据库")
    else:
        print("ℹ️  dry-run 模式。去掉 --dry-run 实际写入。")
