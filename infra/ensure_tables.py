#!/usr/bin/env python3
"""Ensure all SQLAlchemy model tables exist in the database.

Idempotent: only creates tables that don't exist yet.
Also checks for missing columns on existing tables and adds them.
Used by GitHub Actions deploy workflow after alembic migrations.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.chdir(os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import create_engine, inspect, text
from app.core.config import get_settings
from app.core.database import Base
import app.models  # noqa: F401 - 导入所有模型，注册到 Base.metadata


def ensure_missing_columns(engine):
    """检查已存在的表是否有缺失的字段，如果有则自动添加。"""
    insp = inspect(engine)
    added_columns = []

    # 硬编码检查：确保 agent_suggestions 表有 feishu_message_id 列
    if insp.has_table("agent_suggestions"):
        existing_cols = {col["name"] for col in insp.get_columns("agent_suggestions")}
        if "feishu_message_id" not in existing_cols:
            print("[db] 硬编码添加 feishu_message_id 列到 agent_suggestions 表")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE agent_suggestions ADD COLUMN feishu_message_id VARCHAR(128)"))
            added_columns.append("agent_suggestions.feishu_message_id")
            print("[db] feishu_message_id 列添加成功")

    for table_name, table in Base.metadata.tables.items():
        if not insp.has_table(table_name):
            continue  # 表不存在，由 create_all 处理

        existing_columns = {col["name"] for col in insp.get_columns(table_name)}

        for column in table.columns:
            if column.name not in existing_columns:
                # 构建 ALTER TABLE 语句
                col_type = column.type.compile(dialect=engine.dialect)
                nullable = "NULL" if column.nullable else "NOT NULL"
                default = ""
                if column.default is not None and column.default.arg is not None:
                    default_val = column.default.arg
                    if isinstance(default_val, str):
                        default = f" DEFAULT '{default_val}'"
                    else:
                        default = f" DEFAULT {default_val}"

                alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type} {nullable}{default}"
                print(f"[db] adding missing column: {table_name}.{column.name} ({col_type})")
                try:
                    with engine.begin() as conn:
                        conn.execute(text(alter_sql))
                    added_columns.append(f"{table_name}.{column.name}")
                except Exception as e:
                    print(f"[db] WARNING: 添加列失败 {table_name}.{column.name}: {e}")

    if added_columns:
        print(f"[db] added {len(added_columns)} missing columns: {added_columns}")
    else:
        print("[db] all columns exist, nothing to add")


def main():
    settings = get_settings()
    sync_url = settings.database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    needed = set(Base.metadata.tables.keys())
    missing = needed - existing

    if missing:
        print(f"[db] creating missing tables: {sorted(missing)}")
        Base.metadata.create_all(bind=engine)
        print("[db] missing tables created successfully")
    else:
        print("[db] all tables exist, nothing to create")

    # 检查并添加缺失的字段
    ensure_missing_columns(engine)

    return 0


if __name__ == "__main__":
    sys.exit(main())
