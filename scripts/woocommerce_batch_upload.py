#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nuotao Outdoor WooCommerce 批量上架脚本 V1.0

功能：
1. 批量创建WooCommerce产品
2. 上传并关联产品图片（主图+图库）
3. 配置产品属性（颜色/材质/尺寸等）
4. 库存管理（启用库存管理+设置库存数量）
5. 采购关联meta数据（1688链接/供应商/采购价/利润率等）
6. 产品分类和标签
7. 错误处理和日志记录

使用方法：
    python woocommerce_batch_upload.py --config config.json
    python woocommerce_batch_upload.py --product product.json
    python woocommerce_batch_upload.py --batch products.json

作者：Nuotao AI OS
日期：2026-09-06
"""

import os
import sys
import json
import base64
import logging
import argparse
from typing import Dict, List, Optional, Tuple
from datetime import datetime

try:
    import requests
except ImportError:
    print("请先安装 requests 库：pip install requests")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("警告：未安装 Pillow 库，图片处理功能可能受限")
    print("安装命令：pip install Pillow")
    Image = None


# ============================================================
# 配置类
# ============================================================

class WooCommerceConfig:
    """WooCommerce API 配置"""

    def __init__(
        self,
        url: str,
        consumer_key: str,
        consumer_secret: str,
        version: str = "wc/v3",
        timeout: int = 30
    ):
        self.url = url.rstrip("/")
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.version = version
        self.timeout = timeout
        self.api_base = f"{self.url}/wp-json/{version}"

    @property
    def auth(self) -> Tuple[str, str]:
        return (self.consumer_key, self.consumer_secret)

    @classmethod
    def from_dict(cls, data: Dict) -> "WooCommerceConfig":
        return cls(
            url=data["url"],
            consumer_key=data["consumer_key"],
            consumer_secret=data["consumer_secret"],
            version=data.get("version", "wc/v3"),
            timeout=data.get("timeout", 30)
        )

    @classmethod
    def from_json_file(cls, filepath: str) -> "WooCommerceConfig":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


# ============================================================
# WooCommerce API 客户端
# ============================================================

class WooCommerceClient:
    """WooCommerce REST API 客户端"""

    def __init__(self, config: WooCommerceConfig):
        self.config = config
        self.session = requests.Session()
        self.session.auth = config.auth
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        self.logger = logging.getLogger("WooCommerceClient")

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """发送API请求"""
        url = f"{self.config.api_base}/{endpoint.lstrip('/')}"
        kwargs.setdefault("timeout", self.config.timeout)

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"HTTP错误: {e}")
            if hasattr(e, 'response') and e.response is not None:
                self.logger.error(f"响应内容: {e.response.text}")
            raise
        except requests.exceptions.RequestException as e:
            self.logger.error(f"请求错误: {e}")
            raise

    # ---- 产品操作 ----

    def create_product(self, product_data: Dict) -> Dict:
        """创建产品"""
        self.logger.info(f"创建产品: {product_data.get('name', '未命名')}")
        return self._request("POST", "products", json=product_data)

    def update_product(self, product_id: int, product_data: Dict) -> Dict:
        """更新产品"""
        self.logger.info(f"更新产品 ID={product_id}")
        return self._request("PUT", f"products/{product_id}", json=product_data)

    def get_product(self, product_id: int) -> Dict:
        """获取产品"""
        return self._request("GET", f"products/{product_id}")

    def delete_product(self, product_id: int, force: bool = True) -> Dict:
        """删除产品"""
        self.logger.info(f"删除产品 ID={product_id}")
        return self._request("DELETE", f"products/{product_id}", params={"force": force})

    def list_products(self, page: int = 1, per_page: int = 20, status: str = "any") -> List[Dict]:
        """列出产品"""
        params = {
            "page": page,
            "per_page": per_page,
            "status": status
        }
        return self._request("GET", "products", params=params)

    # ---- 媒体/图片操作 ----

    def upload_media(self, image_path: str, title: Optional[str] = None) -> Dict:
        """上传图片到WordPress媒体库"""
        self.logger.info(f"上传图片: {image_path}")

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        filename = os.path.basename(image_path)
        mime_type = self._get_mime_type(filename)

        with open(image_path, "rb") as f:
            image_data = f.read()

        # WordPress REST API 上传媒体
        wp_api_url = f"{self.config.url}/wp-json/wp/v2/media"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": mime_type
        }

        auth = (self.config.consumer_key, self.config.consumer_secret)
        response = requests.post(
            wp_api_url,
            auth=auth,
            headers=headers,
            data=image_data,
            timeout=self.config.timeout
        )
        response.raise_for_status()
        media = response.json()

        self.logger.info(f"图片上传成功，媒体ID={media.get('id')}")
        return media

    def _get_mime_type(self, filename: str) -> str:
        """获取文件MIME类型"""
        ext = os.path.splitext(filename)[1].lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        return mime_types.get(ext, "image/jpeg")

    # ---- 产品分类操作 ----

    def create_category(self, name: str, parent: Optional[int] = None) -> Dict:
        """创建产品分类"""
        data = {"name": name}
        if parent:
            data["parent"] = parent
        return self._request("POST", "products/categories", json=data)

    def get_category_by_name(self, name: str) -> Optional[Dict]:
        """根据名称获取分类"""
        categories = self._request("GET", "products/categories", params={"per_page": 100})
        for cat in categories:
            if cat["name"].lower() == name.lower():
                return cat
        return None

    def get_or_create_category(self, name: str, parent: Optional[int] = None) -> Dict:
        """获取或创建分类"""
        category = self.get_category_by_name(name)
        if category:
            return category
        return self.create_category(name, parent)


# ============================================================
# 产品数据构建器
# ============================================================

class ProductBuilder:
    """WooCommerce产品数据构建器"""

    def __init__(self):
        self.logger = logging.getLogger("ProductBuilder")

    def build_product_data(
        self,
        name: str,
        sku: str,
        regular_price: float,
        description: str = "",
        short_description: str = "",
        categories: Optional[List[Dict]] = None,
        images: Optional[List[Dict]] = None,
        attributes: Optional[List[Dict]] = None,
        manage_stock: bool = True,
        stock_quantity: int = 100,
        low_stock_threshold: int = 10,
        status: str = "publish",
        meta_data: Optional[List[Dict]] = None,
        tags: Optional[List[Dict]] = None,
        sale_price: Optional[float] = None
    ) -> Dict:
        """构建完整的产品数据"""

        product_data = {
            "name": name,
            "sku": sku,
            "regular_price": str(regular_price),
            "description": description,
            "short_description": short_description,
            "status": status,
            "manage_stock": manage_stock,
            "stock_quantity": stock_quantity,
            "low_stock_amount": low_stock_threshold,
            "stock_status": "instock" if stock_quantity > 0 else "outofstock",
            "backorders": "no",
            "sold_individually": False,
            "tax_status": "taxable",
            "tax_class": "",
            "shipping_required": True,
            "shipping_taxable": True,
            "shipping_class": "",
            "reviews_allowed": True,
            "menu_order": 0
        }

        if sale_price:
            product_data["sale_price"] = str(sale_price)

        if categories:
            product_data["categories"] = categories

        if images:
            product_data["images"] = images

        if attributes:
            product_data["attributes"] = attributes

        if meta_data:
            product_data["meta_data"] = meta_data

        if tags:
            product_data["tags"] = tags

        return product_data

    def build_image_data(self, media_id: int, alt_text: str = "") -> Dict:
        """构建图片数据（通过媒体库ID关联）"""
        return {
            "id": media_id,
            "alt": alt_text
        }

    def build_image_data_from_url(self, image_url: str, alt_text: str = "") -> Dict:
        """构建图片数据（通过URL上传）"""
        return {
            "src": image_url,
            "alt": alt_text
        }

    def build_attribute(
        self,
        name: str,
        options: List[str],
        visible: bool = True,
        variation: bool = False
    ) -> Dict:
        """构建产品属性"""
        return {
            "name": name,
            "options": options,
            "visible": visible,
            "variation": variation
        }

    def build_meta_data(self, key: str, value: str) -> Dict:
        """构建meta数据"""
        return {
            "key": key,
            "value": value
        }

    def build_purchase_meta(
        self,
        offer_url: str,
        supplier_name: str,
        cost_price_cny: float,
        cost_price_usd: float,
        profit_margin: str,
        sourcing_method: str = "1688_dropshipping",
        supplier_rating: str = "",
        offer_id: str = ""
    ) -> List[Dict]:
        """构建采购关联meta数据（标准8字段）"""
        return [
            self.build_meta_data("_1688_offer_url", offer_url),
            self.build_meta_data("_1688_offer_id", offer_id),
            self.build_meta_data("_supplier_name", supplier_name),
            self.build_meta_data("_supplier_rating", supplier_rating),
            self.build_meta_data("_cost_price_cny", str(cost_price_cny)),
            self.build_meta_data("_cost_price_usd", str(cost_price_usd)),
            self.build_meta_data("_profit_margin", profit_margin),
            self.build_meta_data("_sourcing_method", sourcing_method)
        ]


# ============================================================
# 批量上架处理器
# ============================================================

class BatchUploader:
    """批量上架处理器"""

    def __init__(self, client: WooCommerceClient):
        self.client = client
        self.builder = ProductBuilder()
        self.logger = logging.getLogger("BatchUploader")
        self.results = {
            "success": [],
            "failed": [],
            "skipped": []
        }

    def upload_single_product(self, product_config: Dict, images_dir: Optional[str] = None) -> Dict:
        """
        上架单个产品

        product_config 格式：
        {
            "name": "产品名称",
            "sku": "SKU001",
            "regular_price": 29.99,
            "sale_price": 24.99,  // 可选
            "description": "产品描述",
            "short_description": "简短描述",
            "categories": ["Camp Furniture"],  // 分类名称列表
            "attributes": [  // 属性列表
                {"name": "Color", "options": ["Black", "Khaki"]},
                {"name": "Material", "options": ["Aluminum Alloy"]}
            ],
            "stock_quantity": 100,
            "low_stock_threshold": 10,
            "images": [  // 图片列表（本地文件名或URL）
                "01_main.jpg",
                "02_scene.jpg",
                ...
            ],
            "purchase": {  // 采购关联信息
                "offer_url": "https://detail.1688.com/offer/xxx.html",
                "offer_id": "xxx",
                "supplier_name": "供应商名称",
                "supplier_rating": "供应商评级",
                "cost_price_cny": 50.0,
                "cost_price_usd": 6.85,
                "profit_margin": "83%"
            },
            "tags": ["camping", "outdoor"]  // 可选
        }
        """
        try:
            self.logger.info(f"开始处理产品: {product_config.get('name', '未命名')}")

            # 1. 处理分类
            categories = []
            for cat_name in product_config.get("categories", []):
                cat = self.client.get_or_create_category(cat_name)
                categories.append({"id": cat["id"]})

            # 2. 处理图片
            images = []
            image_files = product_config.get("images", [])

            if images_dir and image_files:
                for i, img_file in enumerate(image_files):
                    img_path = os.path.join(images_dir, img_file)
                    if os.path.exists(img_path):
                        try:
                            media = self.client.upload_media(img_path)
                            alt_text = f"{product_config.get('name', '')} - Image {i+1}"
                            images.append(self.builder.build_image_data(media["id"], alt_text))
                            self.logger.info(f"图片上传成功: {img_file} (ID={media['id']})")
                        except Exception as e:
                            self.logger.warning(f"图片上传失败: {img_file}, 错误: {e}")
                    else:
                        self.logger.warning(f"图片文件不存在: {img_path}")

            # 3. 处理属性
            attributes = []
            for attr in product_config.get("attributes", []):
                attributes.append(self.builder.build_attribute(
                    name=attr["name"],
                    options=attr["options"],
                    visible=attr.get("visible", True),
                    variation=attr.get("variation", False)
                ))

            # 4. 处理采购关联meta数据
            meta_data = []
            purchase = product_config.get("purchase")
            if purchase:
                meta_data = self.builder.build_purchase_meta(
                    offer_url=purchase.get("offer_url", ""),
                    supplier_name=purchase.get("supplier_name", ""),
                    cost_price_cny=purchase.get("cost_price_cny", 0),
                    cost_price_usd=purchase.get("cost_price_usd", 0),
                    profit_margin=purchase.get("profit_margin", ""),
                    sourcing_method=purchase.get("sourcing_method", "1688_dropshipping"),
                    supplier_rating=purchase.get("supplier_rating", ""),
                    offer_id=purchase.get("offer_id", "")
                )

            # 5. 处理标签
            tags = []
            for tag_name in product_config.get("tags", []):
                tags.append({"name": tag_name})

            # 6. 构建产品数据
            product_data = self.builder.build_product_data(
                name=product_config["name"],
                sku=product_config["sku"],
                regular_price=product_config["regular_price"],
                description=product_config.get("description", ""),
                short_description=product_config.get("short_description", ""),
                categories=categories if categories else None,
                images=images if images else None,
                attributes=attributes if attributes else None,
                manage_stock=True,
                stock_quantity=product_config.get("stock_quantity", 100),
                low_stock_threshold=product_config.get("low_stock_threshold", 10),
                status=product_config.get("status", "publish"),
                meta_data=meta_data if meta_data else None,
                tags=tags if tags else None,
                sale_price=product_config.get("sale_price")
            )

            # 7. 创建产品
            result = self.client.create_product(product_data)

            self.logger.info(f"产品创建成功: ID={result['id']}, SKU={result['sku']}")
            self.results["success"].append({
                "id": result["id"],
                "sku": result["sku"],
                "name": result["name"],
                "permalink": result.get("permalink", "")
            })

            return result

        except Exception as e:
            self.logger.error(f"产品创建失败: {product_config.get('name', '未命名')}, 错误: {e}")
            self.results["failed"].append({
                "name": product_config.get("name", "未命名"),
                "sku": product_config.get("sku", ""),
                "error": str(e)
            })
            raise

    def batch_upload(self, products_config: List[Dict], images_base_dir: Optional[str] = None) -> Dict:
        """
        批量上架产品

        products_config: 产品配置列表
        images_base_dir: 图片基础目录（每个产品一个子目录，目录名=SKU）
        """
        self.logger.info(f"开始批量上架，共 {len(products_config)} 个产品")

        for i, product_config in enumerate(products_config, 1):
            self.logger.info(f"处理第 {i}/{len(products_config)} 个产品")

            # 构建该产品的图片目录
            images_dir = None
            if images_base_dir:
                sku = product_config.get("sku", "")
                if sku:
                    images_dir = os.path.join(images_base_dir, sku)
                    if not os.path.exists(images_dir):
                        self.logger.warning(f"图片目录不存在: {images_dir}")
                        images_dir = None

            try:
                self.upload_single_product(product_config, images_dir)
            except Exception as e:
                self.logger.error(f"跳过失败产品: {e}")
                continue

        # 输出统计
        self.logger.info("=" * 50)
        self.logger.info(f"批量上架完成: 成功={len(self.results['success'])}, 失败={len(self.results['failed'])}")
        self.logger.info("=" * 50)

        return self.results


# ============================================================
# 命令行接口
# ============================================================

def setup_logging(verbose: bool = False):
    """配置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 同时输出到文件
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(file_handler)


def load_config(config_path: str) -> WooCommerceConfig:
    """加载配置"""
    if not os.path.exists(config_path):
        # 使用默认配置
        print(f"配置文件不存在: {config_path}，使用默认配置")
        return WooCommerceConfig(
            url="https://nuotaooutdoor.com",
            consumer_key="ck_3644da6e081a9445459388cc92a82a096a35b427",
            consumer_secret="cs_46d3eb06a763e8ab69a8ad1a60205938fd7df605"
        )
    return WooCommerceConfig.from_json_file(config_path)


def main():
    parser = argparse.ArgumentParser(description="Nuotao Outdoor WooCommerce 批量上架工具")
    parser.add_argument("--config", default="woocommerce_config.json", help="WooCommerce配置文件路径")
    parser.add_argument("--product", help="单个产品配置文件（JSON）")
    parser.add_argument("--batch", help="批量产品配置文件（JSON数组）")
    parser.add_argument("--images-dir", help="图片基础目录")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志输出")
    parser.add_argument("--list", action="store_true", help="列出当前所有产品")
    parser.add_argument("--delete", type=int, help="删除指定ID的产品")

    args = parser.parse_args()
    setup_logging(args.verbose)

    # 加载配置
    config = load_config(args.config)
    client = WooCommerceClient(config)

    # 列出产品
    if args.list:
        products = client.list_products(per_page=50)
        print(f"\n当前产品列表（共 {len(products)} 个）：")
        print("-" * 80)
        for p in products:
            print(f"ID={p['id']:4d} | SKU={p.get('sku', 'N/A'):20s} | "
                  f"价格=${p.get('regular_price', 'N/A'):>8s} | "
                  f"状态={p.get('status', 'N/A'):10s} | "
                  f"名称={p.get('name', 'N/A')[:40]}")
        return

    # 删除产品
    if args.delete:
        confirm = input(f"确认删除产品 ID={args.delete}？(y/N): ")
        if confirm.lower() == "y":
            result = client.delete_product(args.delete)
            print(f"产品已删除: {result}")
        else:
            print("已取消删除")
        return

    # 单个产品上架
    if args.product:
        if not os.path.exists(args.product):
            print(f"产品配置文件不存在: {args.product}")
            sys.exit(1)

        with open(args.product, "r", encoding="utf-8") as f:
            product_config = json.load(f)

        uploader = BatchUploader(client)
        images_dir = args.images_dir
        result = uploader.upload_single_product(product_config, images_dir)

        print(f"\n✅ 产品上架成功！")
        print(f"   ID: {result['id']}")
        print(f"   SKU: {result['sku']}")
        print(f"   名称: {result['name']}")
        print(f"   链接: {result.get('permalink', 'N/A')}")
        return

    # 批量产品上架
    if args.batch:
        if not os.path.exists(args.batch):
            print(f"批量配置文件不存在: {args.batch}")
            sys.exit(1)

        with open(args.batch, "r", encoding="utf-8") as f:
            products_config = json.load(f)

        uploader = BatchUploader(client)
        results = uploader.batch_upload(products_config, args.images_dir)

        print(f"\n{'='*60}")
        print(f"批量上架完成统计")
        print(f"{'='*60}")
        print(f"  成功: {len(results['success'])} 个")
        print(f"  失败: {len(results['failed'])} 个")
        print(f"{'='*60}")

        if results["success"]:
            print("\n✅ 成功产品：")
            for item in results["success"]:
                print(f"   ID={item['id']} | SKU={item['sku']} | {item['name']}")

        if results["failed"]:
            print("\n❌ 失败产品：")
            for item in results["failed"]:
                print(f"   SKU={item['sku']} | {item['name']} | 错误: {item['error']}")

        return

    # 无参数时显示帮助
    parser.print_help()
    print("\n使用示例：")
    print("  # 列出所有产品")
    print("  python woocommerce_batch_upload.py --list")
    print("\n  # 上架单个产品")
    print("  python woocommerce_batch_upload.py --product product.json --images-dir ./images")
    print("\n  # 批量上架产品")
    print("  python woocommerce_batch_upload.py --batch products.json --images-dir ./images")
    print("\n  # 删除产品")
    print("  python woocommerce_batch_upload.py --delete 123")


if __name__ == "__main__":
    main()
