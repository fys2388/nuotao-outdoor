#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nuotao AI OS → WooCommerce 反向同步服务

方向：nuotao-ai-os 内部产品库 → WooCommerce 前端商城

用法：
    # 从内部库同步所有产品到 WooCommerce
    python sync_internal_to_woocommerce.py

    # 仅同步指定产品
    python sync_internal_to_woocommerce.py --sku NUOTAO-001

    # 干跑（不实际写入）
    python sync_internal_to_woocommerce.py --dry-run

架构原则：
    选品 → nuotao-ai-os（内部产品库）→ 同步到 WooCommerce（前端商城）
    禁止直接操作 WooCommerce 数据库。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# 加载项目环境
load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.models.product import Product  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_internal_to_wc")

WC_URL = os.getenv("WOOCOMMERCE_BASE_URL", "https://nuotaooutdoor.com")
WC_KEY = os.getenv("WOOCOMMERCE_CONSUMER_KEY", "")
WC_SECRET = os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "")
DB_URL = os.getenv("DATABASE_URL", "")
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


class WooCommerceWriter:
    """WooCommerce 写入客户端（内部库 → WC 方向）"""

    def __init__(self):
        self.base = f"{WC_URL}/wp-json/wc/v3"
        self.auth = (WC_KEY, WC_SECRET)
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers.update({"Content-Type": "application/json"})

    def create_product(self, data: dict) -> dict:
        r = self.session.post(f"{self.base}/products", json=data, timeout=30)
        r.raise_for_status()
        return r.json()

    def update_product(self, wc_id: int, data: dict) -> dict:
        r = self.session.put(f"{self.base}/products/{wc_id}", json=data, timeout=30)
        r.raise_for_status()
        return r.json()

    def set_draft(self, wc_id: int) -> dict:
        r = self.session.put(
            f"{self.base}/products/{wc_id}",
            json={"status": "draft"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()


def product_to_wc_payload(product: Product) -> dict:
    """内部 Product → WooCommerce 创建/更新 payload"""
    meta = product.meta or {}
    images_meta = (meta.get("media") or {}).get("images") or []

    # 图片：WC API 接受 [{"src": url}]
    images = []
    for img_url in images_meta:
        if img_url:
            images.append({"src": img_url})

    # 价格从 meta 恢复
    regular_price = str(meta.get("regular_price") or meta.get("price") or "")

    payload = {
        "name": product.name,
        "type": "simple",
        "regular_price": regular_price,
        "description": product.description or "",
        "short_description": (product.description or "")[:200],
        "status": "publish" if product.status == "active" else "draft",
        "sku": product.sku,
        "images": images,
    }

    # 分类映射
    if product.category:
        payload["categories"] = [{"name": product.category}]

    # 标签
    if product.tags:
        payload["tags"] = [{"name": t} for t in product.tags]

    return payload


async def sync_all(dry_run: bool = False, sku_filter: str | None = None) -> dict:
    """从内部库同步产品到 WooCommerce"""
    engine = create_async_engine(DB_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    writer = WooCommerceWriter()

    created = 0
    updated = 0
    failed = 0
    errors: list[str] = []

    async with async_session() as session:
        stmt = select(Product).where(
            Product.workspace_id == WORKSPACE_ID,
            Product.source == "woocommerce",  # 只同步从WC拉来的商品
        )
        if sku_filter:
            stmt = stmt.where(Product.sku == sku_filter)
        result = await session.execute(stmt)
        products = result.scalars().all()

        logger.info(f"内部库共 {len(products)} 款产品待同步")

        for product in products:
            try:
                payload = product_to_wc_payload(product)
                wc_id = (product.meta or {}).get("woocommerce_id")

                if dry_run:
                    logger.info(f"[DRY-RUN] {product.sku} → {'UPDATE #'+str(wc_id) if wc_id else 'CREATE'} | {product.name[:50]}")
                    continue

                if wc_id:
                    # 更新已有产品
                    writer.update_product(int(wc_id), payload)
                    updated += 1
                    logger.info(f"UPDATED #{wc_id}: {product.name[:50]}")
                else:
                    # 创建新产品
                    resp = writer.create_product(payload)
                    new_id = resp.get("id")
                    # 回写 woocommerce_id 到内部库
                    product.meta = {**(product.meta or {}), "woocommerce_id": new_id}
                    created += 1
                    logger.info(f"CREATED #{new_id}: {product.name[:50]}")

            except Exception as e:
                failed += 1
                err = f"{product.sku} {product.name[:40]}: {e}"
                logger.error(f"同步失败: {err}")
                errors.append(err)

        await session.commit()

    await engine.dispose()
    return {"created": created, "updated": updated, "failed": failed, "errors": errors}


async def unpublish_all_wc() -> dict:
    """下架所有 WooCommerce 现有产品（设为 draft）"""
    writer = WooCommerceWriter()
    unpublished = 0
    page = 1
    while True:
        r = writer.session.get(
            f"{writer.base}/products",
            params={"per_page": 100, "page": page, "status": "publish"},
            timeout=30,
        )
        r.raise_for_status()
        products = r.json()
        if not products:
            break
        for p in products:
            writer.set_draft(p["id"])
            unpublished += 1
            logger.info(f"DRAFT #{p['id']}: {p['name'][:50]}")
        page += 1

    return {"unpublished": unpublished}


def main():
    parser = argparse.ArgumentParser(description="nuotao-ai-os → WooCommerce 反向同步")
    parser.add_argument("--sku", help="仅同步指定 SKU")
    parser.add_argument("--dry-run", action="store_true", help="干跑不实际写入")
    parser.add_argument("--unpublish", action="store_true", help="下架所有 WC 产品")
    args = parser.parse_args()

    if args.unpublish:
        result = asyncio.run(unpublish_all_wc())
        print(f"下架完成: {result}")
    else:
        result = asyncio.run(sync_all(dry_run=args.dry_run, sku_filter=args.sku))
        print(f"同步完成: {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
