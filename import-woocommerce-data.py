#!/usr/bin/env python3
"""
WooCommerce 数据导入脚本
将 WooCommerce 的产品、订单、客户数据导入核心业务表
支持 upsert（基于 sku / external_order_id / customer_reference_id）
"""
import os
import sys
import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

# 确保项目根目录在 path 中
sys.path.insert(0, '/opt/nuotao/backend')

# 加载 .env 配置
from dotenv import load_dotenv
load_dotenv('/opt/nuotao/backend/.env')

import requests
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.customer import CustomerProfile

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 配置
WORKSPACE_ID = UUID(os.getenv('DEFAULT_WORKSPACE_ID', '00000000-0000-0000-0000-000000000001'))
WC_URL = os.getenv('WOOCOMMERCE_URL', 'https://nuotaooutdoor.com')
WC_KEY = os.getenv('WOOCOMMERCE_CONSUMER_KEY', '')
WC_SECRET = os.getenv('WOOCOMMERCE_CONSUMER_SECRET', '')
DATABASE_URL = os.getenv('DATABASE_URL', '')
# 异步驱动替换为同步驱动（脚本使用同步 Session）
if DATABASE_URL.startswith('postgresql+asyncpg://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql+psycopg2://')

if not DATABASE_URL:
    DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'nuotao')
    DB_USER = os.getenv('DB_USER', 'nuotao')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DATABASE_URL = f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

engine = create_engine(DATABASE_URL, echo=False)


def fetch_wc_products():
    """从 WooCommerce 获取所有产品"""
    all_products = []
    page = 1
    while True:
        r = requests.get(
            f'{WC_URL}/wp-json/wc/v3/products',
            auth=(WC_KEY, WC_SECRET),
            params={'per_page': 100, 'page': page, 'status': 'publish'},
            timeout=30
        )
        r.raise_for_status()
        products = r.json()
        if not products:
            break
        all_products.extend(products)
        if len(products) < 100:
            break
        page += 1
    return all_products


def fetch_wc_orders():
    """从 WooCommerce 获取所有订单"""
    all_orders = []
    page = 1
    while True:
        r = requests.get(
            f'{WC_URL}/wp-json/wc/v3/orders',
            auth=(WC_KEY, WC_SECRET),
            params={'per_page': 100, 'page': page, 'status': 'any'},
            timeout=30
        )
        r.raise_for_status()
        orders = r.json()
        if not orders:
            break
        all_orders.extend(orders)
        if len(orders) < 100:
            break
        page += 1
    return all_orders


def import_products(session):
    """导入产品到 products 表"""
    logger.info("开始导入产品...")
    wc_products = fetch_wc_products()
    logger.info(f"从 WooCommerce 获取到 {len(wc_products)} 个产品")

    imported = 0
    updated = 0

    for wc_p in wc_products:
        sku = wc_p.get('sku') or f'WC-{wc_p["id"]}'
        name = wc_p.get('name', '')
        price = wc_p.get('price') or wc_p.get('regular_price') or '0'

        # 查找现有产品
        existing = session.execute(
            select(Product).where(
                Product.workspace_id == WORKSPACE_ID,
                Product.sku == sku
            )
        ).scalar_one_or_none()

        if existing:
            # 更新
            existing.name = name
            existing.description = (wc_p.get('description') or '')[:2000]
            existing.status = 'active' if wc_p.get('status') == 'publish' else 'draft'
            existing.source = 'woocommerce'
            existing.source_url = wc_p.get('permalink')
            existing.category = wc_p.get('categories', [{}])[0].get('name') if wc_p.get('categories') else None
            existing.tags = [t.get('name') for t in wc_p.get('tags', [])]
            existing.attributes = {
                'wc_product_id': wc_p['id'],
                'regular_price': wc_p.get('regular_price'),
                'sale_price': wc_p.get('sale_price'),
                'stock_status': wc_p.get('stock_status'),
                'stock_quantity': wc_p.get('stock_quantity'),
                'weight': wc_p.get('weight'),
                'dimensions': wc_p.get('dimensions'),
            }
            existing.meta = {'woocommerce_id': wc_p['id']}
            existing.weight_kg = Decimal(str(wc_p['weight'])) if wc_p.get('weight') else None
            updated += 1
        else:
            # 新建
            product = Product(
                workspace_id=WORKSPACE_ID,
                sku=sku,
                name=name,
                description=(wc_p.get('description') or '')[:2000],
                category=wc_p.get('categories', [{}])[0].get('name') if wc_p.get('categories') else None,
                status='active' if wc_p.get('status') == 'publish' else 'draft',
                source='woocommerce',
                source_url=wc_p.get('permalink'),
                tags=[t.get('name') for t in wc_p.get('tags', [])],
                attributes={
                    'wc_product_id': wc_p['id'],
                    'regular_price': wc_p.get('regular_price'),
                    'sale_price': wc_p.get('sale_price'),
                    'stock_status': wc_p.get('stock_status'),
                    'stock_quantity': wc_p.get('stock_quantity'),
                    'weight': wc_p.get('weight'),
                    'dimensions': wc_p.get('dimensions'),
                    'price': price,
                },
                meta={'woocommerce_id': wc_p['id']},
                weight_kg=Decimal(str(wc_p['weight'])) if wc_p.get('weight') else None,
                target_market='US',
            )
            session.add(product)
            imported += 1

    session.commit()
    logger.info(f"产品导入完成: 新增 {imported}, 更新 {updated}")
    return imported + updated


def import_customers(session, wc_orders):
    """从订单中提取客户信息导入 customer_profiles 表（PII 安全）"""
    logger.info("开始导入客户...")
    customer_map = {}  # customer_id -> order count, revenue, country

    for order in wc_orders:
        cust_id = str(order.get('customer_id', 0))
        if cust_id == '0':
            # 访客订单，使用 billing email 的 hash 作为 reference
            billing = order.get('billing', {})
            email = billing.get('email', '')
            if email:
                import hashlib
                cust_id = f'guest-{hashlib.md5(email.encode()).hexdigest()[:12]}'
            else:
                cust_id = f'guest-order-{order["id"]}'

        if cust_id not in customer_map:
            customer_map[cust_id] = {
                'orders': 0,
                'revenue': Decimal('0'),
                'country': None,
                'first_order_at': None,
            }

        customer_map[cust_id]['orders'] += 1
        customer_map[cust_id]['revenue'] += Decimal(str(order.get('total', '0')))
        billing = order.get('billing', {})
        if not customer_map[cust_id]['country'] and billing.get('country'):
            customer_map[cust_id]['country'] = billing['country']

        order_date = order.get('date_created')
        if order_date:
            try:
                dt = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
                if not customer_map[cust_id]['first_order_at'] or dt < customer_map[cust_id]['first_order_at']:
                    customer_map[cust_id]['first_order_at'] = dt
            except:
                pass

    imported = 0
    updated = 0

    for ref_id, data in customer_map.items():
        existing = session.execute(
            select(CustomerProfile).where(
                CustomerProfile.workspace_id == WORKSPACE_ID,
                CustomerProfile.customer_reference_id == ref_id
            )
        ).scalar_one_or_none()

        if existing:
            existing.total_orders = data['orders']
            existing.total_revenue = data['revenue']
            existing.country = data['country'] or existing.country
            existing.first_order_at = data['first_order_at'] or existing.first_order_at
            updated += 1
        else:
            profile = CustomerProfile(
                workspace_id=WORKSPACE_ID,
                customer_reference_id=ref_id,
                country=data['country'],
                total_orders=data['orders'],
                total_revenue=data['revenue'],
                first_order_at=data['first_order_at'],
                segment='new' if data['orders'] == 1 else 'repeat',
            )
            session.add(profile)
            imported += 1

    session.commit()
    logger.info(f"客户导入完成: 新增 {imported}, 更新 {updated}")
    return imported + updated


def import_orders(session):
    """导入订单到 orders 表和 order_items 表"""
    logger.info("开始导入订单...")
    wc_orders = fetch_wc_orders()
    logger.info(f"从 WooCommerce 获取到 {len(wc_orders)} 个订单")

    # 先导入客户
    import_customers(session, wc_orders)

    imported = 0
    updated = 0

    for wc_o in wc_orders:
        ext_id = str(wc_o['id'])
        billing = wc_o.get('billing', {})
        customer_id = str(wc_o.get('customer_id', 0))
        if customer_id == '0':
            import hashlib
            email = billing.get('email', '')
            customer_id = f'guest-{hashlib.md5(email.encode()).hexdigest()[:12]}' if email else f'guest-order-{wc_o["id"]}'

        # 查找现有订单
        existing = session.execute(
            select(Order).where(
                Order.workspace_id == WORKSPACE_ID,
                Order.external_order_id == ext_id
            )
        ).scalar_one_or_none()

        status_map = {
            'pending': 'pending',
            'processing': 'processing',
            'on-hold': 'on_hold',
            'completed': 'completed',
            'cancelled': 'cancelled',
            'refunded': 'refunded',
            'failed': 'failed',
        }
        order_status = status_map.get(wc_o.get('status'), wc_o.get('status', 'received'))

        order_data = {
            'status': order_status,
            'payment_status': 'paid' if order_status in ('completed', 'processing') else 'unpaid',
            'fulfillment_status': 'fulfilled' if order_status == 'completed' else 'unfulfilled',
            'currency': wc_o.get('currency', 'USD'),
            'country': billing.get('country'),
            'payment_method': wc_o.get('payment_method_title') or wc_o.get('payment_method'),
            'source': 'woocommerce',
            'customer_reference_id': customer_id,
            'subtotal': Decimal(str(wc_o.get('subtotal', '0'))),
            'shipping_total': Decimal(str(wc_o.get('shipping_total', '0'))),
            'discount_total': Decimal(str(wc_o.get('discount_total', '0'))),
            'tax_total': Decimal(str(wc_o.get('total_tax', '0'))),
            'total': Decimal(str(wc_o.get('total', '0'))),
        }

        try:
            received_at = datetime.fromisoformat(wc_o.get('date_created', '').replace('Z', '+00:00'))
            order_data['received_at'] = received_at
        except:
            pass

        if existing:
            for key, value in order_data.items():
                setattr(existing, key, value)
            order_id = existing.id
            updated += 1
        else:
            order = Order(
                workspace_id=WORKSPACE_ID,
                external_order_id=ext_id,
                **order_data
            )
            session.add(order)
            session.flush()
            order_id = order.id
            imported += 1

        # 处理订单项
        # 先删除旧的订单项（如果是更新）
        if existing:
            session.execute(
                OrderItem.__table__.delete().where(OrderItem.order_id == order_id)
            )

        for item in wc_o.get('line_items', []):
            # 查找对应产品
            product = session.execute(
                select(Product).where(
                    Product.workspace_id == WORKSPACE_ID,
                    Product.sku == (item.get('sku') or f'WC-{item.get("product_id")}')
                )
            ).scalar_one_or_none()

            order_item = OrderItem(
                workspace_id=WORKSPACE_ID,
                order_id=order_id,
                external_item_id=str(item.get('id')),
                product_id=product.id if product else None,
                sku=item.get('sku'),
                name=item.get('name', ''),
                quantity=int(item.get('quantity', 1)),
                unit_price=Decimal(str(item.get('price', '0'))),
                line_total=Decimal(str(item.get('total', '0'))),
            )
            session.add(order_item)

    session.commit()
    logger.info(f"订单导入完成: 新增 {imported}, 更新 {updated}")
    return imported + updated


def verify_import(session):
    """验证导入结果"""
    logger.info("=== 导入验证 ===")
    product_count = session.execute(select(Product).where(Product.workspace_id == WORKSPACE_ID)).scalars().all()
    order_count = session.execute(select(Order).where(Order.workspace_id == WORKSPACE_ID)).scalars().all()
    item_count = session.execute(select(OrderItem).where(OrderItem.workspace_id == WORKSPACE_ID)).scalars().all()
    customer_count = session.execute(select(CustomerProfile).where(CustomerProfile.workspace_id == WORKSPACE_ID)).scalars().all()

    logger.info(f"products: {len(product_count)} 条")
    logger.info(f"orders: {len(order_count)} 条")
    logger.info(f"order_items: {len(item_count)} 条")
    logger.info(f"customer_profiles: {len(customer_count)} 条")

    # 显示订单详情
    for o in order_count:
        logger.info(f"  订单 {o.external_order_id}: status={o.status}, total={o.total}, country={o.country}, items={len(o.items)}")

    return len(product_count), len(order_count), len(item_count), len(customer_count)


def main():
    logger.info("=== WooCommerce 数据导入开始 ===")
    logger.info(f"Workspace: {WORKSPACE_ID}")
    logger.info(f"WooCommerce: {WC_URL}")

    with Session(engine) as session:
        # 1. 导入产品
        product_count = import_products(session)

        # 2. 导入订单（包含客户）
        order_count = import_orders(session)

        # 3. 验证
        verify_import(session)

    logger.info("=== WooCommerce 数据导入完成 ===")


if __name__ == '__main__':
    main()
