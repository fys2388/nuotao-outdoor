"""批量选品工作流处理脚本。

用法：
    # 处理所有 recalled 产品
    python -m app.scripts.process_first_batch

    # 仅处理特定品类
    python -m app.scripts.process_first_batch --category camping_lighting

    # 预览模式（不执行）
    python -m app.scripts.process_first_batch --dry-run

    # 限制处理数量
    python -m app.scripts.process_first_batch --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from uuid import UUID

from app.core.database import async_session_factory
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.services.selection_batch_service import get_batch_status, process_batch_products

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    parser = argparse.ArgumentParser(description="批量处理选品工作流")
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="品类筛选（如 camping_lighting）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="最大处理数量（默认 50）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览不执行",
    )
    args = parser.parse_args()

    workspace_id = UUID(DEFAULT_WORKSPACE_ID)

    print("=" * 60)
    print("Nuotao Outdoor 批量选品工作流处理")
    print("=" * 60)

    async with async_session_factory() as session:
        # Show current status
        print("\n📊 当前漏斗状态:")
        status = await get_batch_status(session, workspace_id=workspace_id)
        for stage, count in status.get("by_stage", {}).items():
            print(f"   {stage}: {count}")
        print(f"   总计: {status.get('total', 0)}")

        # Process products
        print(f"\n🔄 开始处理产品...")
        print(f"   品类筛选: {args.category or '全部'}")
        print(f"   最大数量: {args.limit}")
        print(f"   预览模式: {args.dry_run}")

        result = await process_batch_products(
            session,
            workspace_id=workspace_id,
            category=args.category,
            limit=args.limit,
            dry_run=args.dry_run,
        )

        await session.commit()

        # Show results
        print(f"\n{'✅' if result['status'] == 'completed' else 'ℹ️'} 处理完成:")
        print(f"   找到: {result['total_found']}")
        print(f"   成功: {result['succeeded']}")
        print(f"   失败: {result['failed']}")

        if result["results"]:
            print("\n📋 处理详情:")
            for r in result["results"]:
                icon = "✅" if r.get("status") == "completed" else "❌"
                print(f"   {icon} {r.get('sku', '?')}: {r.get('name', '?')}")
                if r.get("status") == "completed":
                    print(f"      阶段: {r.get('funnel_stage', '?')}")
                    print(f"      决策: {r.get('decision', '?')}")
                    print(f"      评分: {r.get('nuotao_score', '?')} ({r.get('nuotao_grade', '?')})")
                else:
                    print(f"      错误: {r.get('error', '?')}")

        # Show updated status
        print(f"\n📊 更新后漏斗状态:")
        status = await get_batch_status(session, workspace_id=workspace_id)
        for stage, count in status.get("by_stage", {}).items():
            print(f"   {stage}: {count}")
        print(f"   总计: {status.get('total', 0)}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n已中断")
        sys.exit(1)
    except Exception as exc:
        logger.exception("处理失败: %s", exc)
        sys.exit(1)
