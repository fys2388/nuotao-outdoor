"""检查数据库表结构"""
from sqlalchemy import inspect

from app.core.database import _engine as engine

inspector = inspect(engine)
tables = inspector.get_table_names()

print("数据库表列表:")
for t in sorted(tables):
    print(f"  - {t}")

print(f"\n总表数: {len(tables)}")
print(f"orders 表存在: {'orders' in tables}")
print(f"order_items 表存在: {'order_items' in tables}")

if "orders" in tables:
    columns = inspector.get_columns("orders")
    print(f"\norders 表字段 ({len(columns)}个):")
    for col in columns:
        print(f"  - {col['name']}: {col['type']}")
