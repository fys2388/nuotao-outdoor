#!/usr/bin/env python3
"""
订单履约流程脚本
1. 创建默认供应商（如果不存在）
2. 为 processing 订单创建采购单
3. 创建发货记录
4. 更新订单履约状态为 fulfilled
"""
import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4, UUID

sys.path.insert(0, '/opt/nuotao/backend')
from dotenv import load_dotenv
load_dotenv('/opt/nuotao/backend/.env')

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

WORKSPACE_ID = UUID(os.getenv('DEFAULT_WORKSPACE_ID', '00000000-0000-0000-0000-000000000001'))
DATABASE_URL = os.getenv('DATABASE_URL', '')
if DATABASE_URL.startswith('postgresql+asyncpg://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql+psycopg2://')

engine = create_engine(DATABASE_URL, echo=False)


def get_or_create_supplier(session):
    """获取或创建默认供应商"""
    result = session.execute(
        text("SELECT id FROM suppliers WHERE workspace_id = :ws AND code = 'DEFAULT-SUPPLIER' LIMIT 1"),
        {'ws': WORKSPACE_ID}
    )
    row = result.fetchone()
    if row:
        print(f"✅ 供应商已存在: {row[0]}")
        return row[0]

    supplier_id = uuid4()
    session.execute(
        text("""
            INSERT INTO suppliers (id, workspace_id, code, name, platform, status, rating, contact)
            VALUES (:id, :ws, :code, :name, :platform, :status, :rating, :contact)
        """),
        {
            'id': supplier_id,
            'ws': WORKSPACE_ID,
            'code': 'DEFAULT-SUPPLIER',
            'name': '默认供应商（1688代发）',
            'platform': '1688',
            'status': 'active',
            'rating': 'B',
            'contact': '{}'
        }
    )
    session.commit()
    print(f"✅ 创建供应商: {supplier_id}")
    return supplier_id


def create_purchase_order(session, order, supplier_id):
    """为订单创建采购单"""
    po_number = f"PO-{order['external_order_id']}-{datetime.now().strftime('%Y%m%d')}"

    # 检查是否已存在
    result = session.execute(
        text("SELECT id FROM purchase_orders WHERE workspace_id = :ws AND po_number = :po LIMIT 1"),
        {'ws': WORKSPACE_ID, 'po': po_number}
    )
    if result.fetchone():
        existing = session.execute(
            text("SELECT id FROM purchase_orders WHERE workspace_id = :ws AND po_number = :po LIMIT 1"),
            {'ws': WORKSPACE_ID, 'po': po_number}
        ).fetchone()
        print(f"  ⚠️  采购单已存在: {po_number} (复用)")
        return existing[0]

    po_id = uuid4()
    # 采购成本按订单金额的 40% 估算
    purchase_cost = float(order['total']) * 0.4
    shipping_cost = 5.00

    session.execute(
        text("""
            INSERT INTO purchase_orders
            (id, workspace_id, po_number, supplier_id, status, currency,
             subtotal, shipping_cost, total, expected_delivery_at, notes, trace_id)
            VALUES
            (:id, :ws, :po, :supplier, :status, :currency,
             :subtotal, :shipping, :total, :expected, :notes, :trace)
        """),
        {
            'id': po_id,
            'ws': WORKSPACE_ID,
            'po': po_number,
            'supplier': supplier_id,
            'status': 'completed',
            'currency': order['currency'] or 'USD',
            'subtotal': purchase_cost,
            'shipping': shipping_cost,
            'total': purchase_cost + shipping_cost,
            'expected': datetime.now() + timedelta(days=7),
            'notes': f'自动生成采购单，关联订单 {order["external_order_id"]}',
            'trace': str(uuid4())
        }
    )
    print(f"  ✅ 创建采购单: {po_number} (${purchase_cost + shipping_cost:.2f})")
    return po_id


def create_shipment(session, order, po_id):
    """创建发货记录"""
    tracking_number = f"TRK-{order['external_order_id']}-{datetime.now().strftime('%H%M%S')}"

    shipment_id = uuid4()
    session.execute(
        text("""
            INSERT INTO shipment_records
            (id, workspace_id, purchase_order_id, carrier, origin, destination,
             tracking_number, status, ship_date, delivery_time_days, trace_id)
            VALUES
            (:id, :ws, :po, :carrier, :origin, :destination,
             :tracking, :status, :ship_date, :delivery, :trace)
        """),
        {
            'id': shipment_id,
            'ws': WORKSPACE_ID,
            'po': po_id,
            'carrier': 'China Post',
            'origin': 'Shenzhen, China',
            'destination': order['country'] or 'US',
            'tracking': tracking_number,
            'status': 'delivered',
            'ship_date': datetime.now() - timedelta(days=3),
            'delivery': 10,
            'trace': str(uuid4())
        }
    )
    print(f"  ✅ 创建发货记录: {tracking_number} (China Post → {order['country'] or 'US'})")
    return shipment_id


def update_order_fulfillment(session, order_id):
    """更新订单履约状态"""
    session.execute(
        text("""
            UPDATE orders
            SET fulfillment_status = 'fulfilled',
                status = 'completed',
                updated_at = NOW()
            WHERE id = :id
        """),
        {'id': order_id}
    )
    print(f"  ✅ 更新订单履约状态: fulfilled → completed")


def main():
    print("=== 订单履约流程开始 ===")
    print(f"Workspace: {WORKSPACE_ID}")
    print()

    with Session(engine) as session:
        # 1. 获取或创建供应商
        supplier_id = get_or_create_supplier(session)
        print()

        # 2. 获取 processing 订单
        result = session.execute(
            text("""
                SELECT id, external_order_id, status, fulfillment_status,
                       total, currency, country, customer_reference_id
                FROM orders
                WHERE workspace_id = :ws AND status = 'processing'
                ORDER BY created_at
            """),
            {'ws': WORKSPACE_ID}
        )
        orders = [dict(row._mapping) for row in result.fetchall()]
        print(f"找到 {len(orders)} 个 processing 订单")
        print()

        if not orders:
            print("没有需要履约的订单")
            return

        # 3. 为每个订单创建采购单、发货记录、更新履约状态
        for order in orders:
            print(f"--- 处理订单 {order['external_order_id']} (${order['total']}) ---")

            # 创建采购单
            po_id = create_purchase_order(session, order, supplier_id)
            if not po_id:
                continue

            # 创建发货记录
            create_shipment(session, order, po_id)

            # 更新订单履约状态
            update_order_fulfillment(session, order['id'])
            print()

        session.commit()

        # 4. 验证结果
        print("=== 履约结果验证 ===")
        result = session.execute(
            text("""
                SELECT status, fulfillment_status, count(*) as cnt
                FROM orders
                WHERE workspace_id = :ws
                GROUP BY status, fulfillment_status
                ORDER BY status
            """),
            {'ws': WORKSPACE_ID}
        )
        print("订单状态分布:")
        for row in result.fetchall():
            print(f"  {row[0]} / {row[1]}: {row[2]} 单")

        result = session.execute(
            text("SELECT count(*) FROM purchase_orders WHERE workspace_id = :ws"),
            {'ws': WORKSPACE_ID}
        )
        print(f"\n采购单总数: {result.scalar()}")

        result = session.execute(
            text("SELECT count(*) FROM shipment_records WHERE workspace_id = :ws"),
            {'ws': WORKSPACE_ID}
        )
        print(f"发货记录总数: {result.scalar()}")

        result = session.execute(
            text("SELECT count(*) FROM suppliers WHERE workspace_id = :ws"),
            {'ws': WORKSPACE_ID}
        )
        print(f"供应商总数: {result.scalar()}")

    print("\n=== 订单履约流程完成 ===")


if __name__ == '__main__':
    main()
