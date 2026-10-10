"""确保所有 SQLAlchemy 模型表存在，并报告 schema 漂移。

由 .github/workflows/deploy.yml 在 `alembic upgrade head` 之后调用。

这里做两件事：

1. ``create_all()`` 创建迁移尚未创建的表。有五张表（users、operation_logs、
   system_settings、product_mappings、product_nuotao_scores）**从来没有
   create_table 迁移**，是早期手动跑 backend/create_tables.py 建出来的。
   本脚本是它们与 "relation does not exist" 之间唯一的防线。
   create_all() 幂等：对已存在的表不做任何事，也不会 ALTER 已有表。

2. **漂移报告**。create_all() 不会为"表建成后模型才新增的列"补列——这正是
   ``Product.data_integrity_*`` 在生产丢失的机制：迁移里从未 add_column，
   create_all 也不会 ALTER，于是列既不在迁移历史里也不在真实表里，而任何
   SELECT 都直接 500，没有任何东西发出警报。因此我们把真实 schema 与
   Base.metadata 做 diff，把所有缺失的表/列以 WARNING 打印出来，让缺口在
   部署日志里可见，而不是在生产以 500 的形式第一次被发现。

只报告、不修复：补列需要 ALTER TABLE，而应用角色对部分表（如
product_mappings）并非属主，会抛 InsufficientPrivilegeError。修复漂移属于
人的决定（补迁移，或用表属主执行 ALTER），本脚本不越权。

始终以退出码 0 结束，保持 deploy.yml 里 "non-blocking" 的语义；只有脚本自身
异常才返回非零。
"""

from __future__ import annotations

import asyncio
import importlib
import pkgutil
import sys
import traceback
from pathlib import Path

# 脚本从 /opt/nuotao 运行，需要把 backend 放进模块搜索路径。
BACKEND = Path(__file__).resolve().parent.parent / "backend"
if BACKEND.is_dir():
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import inspect
from sqlalchemy.engine import Connection

MODELS_PACKAGE = "app.models"


def _import_all_models() -> int:
    """导入 app.models 下所有模块，把每个模型注册进 Base.metadata。

    返回成功导入的模块数。单个模块导入失败只告警、不中断：这里的目的就是
    尽量把 metadata 填全。
    """
    import app.models as models_pkg

    count = 0
    for info in pkgutil.walk_packages(models_pkg.__path__, prefix=models_pkg.__name__ + "."):
        try:
            importlib.import_module(info.name)
            count += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[tables] WARN 无法导入 {info.name}: {type(exc).__name__}: {exc}")
    return count


async def _create_missing_tables() -> None:
    """create_all()：只建不存在的表，绝不 ALTER 已有表。"""
    from app.core.database import Base, _engine

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _reflect(conn: Connection) -> tuple[set[str], dict[str, list[str]]]:
    """在同步连接内完成反射，返回 (缺失表名, {表名: [缺失列]})。"""
    from app.core.database import Base

    inspector = inspect(conn)
    live_tables = set(inspector.get_table_names())

    missing = set()
    cols: dict[str, list[str]] = {}
    for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        if table.name not in live_tables:
            missing.add(table.name)
            continue
        live_cols = {c["name"] for c in inspector.get_columns(table.name)}
        absent = sorted(c.name for c in table.columns if c.name not in live_cols)
        if absent:
            cols[table.name] = absent
    return missing, cols


async def _report_drift() -> bool:
    """比对真实 schema 与 Base.metadata，打印缺失的表与列。

    返回 True 表示没有发现漂移。
    """
    from app.core.database import Base, _engine

    # inspect() 绑定在 run_sync 的连接上，必须在该回调内用掉。
    async with _engine.connect() as conn:
        missing_tables, missing_cols = await conn.run_sync(_reflect)

    drift = bool(missing_tables) or bool(missing_cols)
    total_cols = sum(len(v) for v in missing_cols.values())

    if not drift:
        print(
            f"[tables] OK 模型 {len(Base.metadata.tables)} 张表、"
            f"{sum(len(t.columns) for t in Base.metadata.tables.values())} 列全部存在于生产库"
        )
        return True

    if missing_tables:
        print(f"[tables] WARN 生产库缺少 {len(missing_tables)} 张表:")
        for t in sorted(missing_tables):
            n = len(Base.metadata.tables[t].columns)
            print(f"[tables]   - {t} ({n} 列)")
    for tname, cols in missing_cols.items():
        print(f"[tables] WARN {tname} 缺 {len(cols)} 列:")
        for c in cols:
            print(f"[tables]   - {c}")

    print(
        f"[tables] WARN 漂移合计 {len(missing_tables)} 表 / {total_cols} 列。"
        "create_all() 无法补列（它不会 ALTER 已有表）。"
        "处理方式：为这些列补 Alembic 迁移（表需归应用角色属主），"
        "或由表属主手动 ALTER TABLE ADD COLUMN。"
    )
    return False


async def main() -> int:
    imported = _import_all_models()
    print(f"[tables] 已注册 {imported} 个模型模块")

    await _create_missing_tables()
    print("[tables] create_all() 完成（只建缺失表，幂等）")

    await _report_drift()
    return 0  # 保持 non-blocking 语义；漂移只告警不失败


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
