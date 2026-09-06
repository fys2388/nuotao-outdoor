#!/usr/bin/env python3
"""Ensure all SQLAlchemy model tables exist in the database.

Idempotent: only creates tables that don't exist yet.
Used by GitHub Actions deploy workflow after alembic migrations.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.chdir(os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import create_engine, inspect
from app.core.config import get_settings
from app.models import Base


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

    return 0


if __name__ == "__main__":
    sys.exit(main())
