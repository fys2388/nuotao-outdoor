"""
Nuotao AI OS - 5个AI Agent异步运行器
使用数据库会话运行所有 Agent
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, "E:/AI/nuotao-ai-os/backend")

from app.core.database import async_session_factory
from app.agents import (
    analyze_product,
    analyze_marketing,
    analyze_supply_chain,
    analyze_customer,
    analyze_business,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agent_async_runner")

OUTPUT_DIR = Path("E:/AI/nuotao-ai-os/backups/agent_reports")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


AGENTS = [
    {
        "key": "product_analyst",
        "name": "产品分析师",
        "name_en": "Product Analyst",
        "description": "产品分析与选品建议",
        "function": analyze_product,
        "needs_product_id": True,
    },
    {
        "key": "marketing_manager",
        "name": "营销经理",
        "name_en": "Marketing Manager",
        "description": "营销策略与活动分析",
        "function": analyze_marketing,
        "needs_product_id": False,
    },
    {
        "key": "supply_chain_manager",
        "name": "供应链经理",
        "name_en": "Supply Chain Manager",
        "description": "供应商、库存与物流优化",
        "function": analyze_supply_chain,
        "needs_product_id": False,
    },
    {
        "key": "customer_manager",
        "name": "客户经理",
        "name_en": "Customer Manager",
        "description": "客户服务、体验与反馈分析",
        "function": analyze_customer,
        "needs_product_id": False,
    },
    {
        "key": "business_analyst",
        "name": "商业分析师",
        "name_en": "Business Analyst",
        "description": "财务、销售与商业智能",
        "function": analyze_business,
        "needs_product_id": False,
    },
]


async def run_agent(session, agent_info: dict, context: dict) -> dict:
    """运行单个 Agent"""
    start_time = datetime.now(timezone.utc)
    logger.info("Running: %s", agent_info["name"])

    try:
        if agent_info["needs_product_id"]:
            result = await agent_info["function"](
                session=session,
                workspace_id=DEFAULT_WORKSPACE_ID,
                product_id=context.get("product_id", "demo-product-001"),
            )
        else:
            result = await agent_info["function"](
                session=session,
                workspace_id=DEFAULT_WORKSPACE_ID,
                context=context,
            )

        end_time = datetime.now(timezone.utc)
        duration_ms = (end_time - start_time).total_seconds() * 1000

        # 标准化结果
        if hasattr(result, "model_dump"):
            result_dict = result.model_dump()
        elif isinstance(result, dict):
            result_dict = result
        else:
            result_dict = {"result": str(result)}

        return {
            "agent_key": agent_info["key"],
            "agent_name": agent_info["name"],
            "agent_name_en": agent_info["name_en"],
            "description": agent_info["description"],
            "status": "success",
            "duration_ms": round(duration_ms, 2),
            "result": result_dict,
        }

    except Exception as e:
        end_time = datetime.now(timezone.utc)
        duration_ms = (end_time - start_time).total_seconds() * 1000
        logger.error("Agent %s failed: %s", agent_info["name"], str(e))

        return {
            "agent_key": agent_info["key"],
            "agent_name": agent_info["name"],
            "agent_name_en": agent_info["name_en"],
            "description": agent_info["description"],
            "status": "error",
            "duration_ms": round(duration_ms, 2),
            "error": str(e),
        }


async def run_all_agents():
    """运行所有 5 个 Agent"""
    print("\n" + "=" * 70)
    print("  Nuotao AI OS - 5 AI Agents Async Runner")
    print("=" * 70)

    context = {
        "run_type": "demo",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "product_id": "demo-product-001",
    }

    results = {}
    async with async_session_factory() as session:
        for agent_info in AGENTS:
            result = await run_agent(session, agent_info, context)
            results[agent_info["key"]] = result

    # 汇总
    success_count = sum(1 for r in results.values() if r["status"] == "success")
    error_count = sum(1 for r in results.values() if r["status"] == "error")
    total_duration = sum(r["duration_ms"] for r in results.values())

    summary = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_agents": len(AGENTS),
        "success_count": success_count,
        "error_count": error_count,
        "total_duration_ms": round(total_duration, 2),
        "agents": results,
    }

    # 保存报告
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = OUTPUT_DIR / f"agent_report_{timestamp}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    # 打印摘要
    print("\n" + "-" * 70)
    print(f"  总 Agent: {len(AGENTS)} | 成功: {success_count} | 失败: {error_count}")
    print(f"  总耗时: {total_duration:.2f}ms")
    print("-" * 70)

    for key, result in results.items():
        icon = "✅" if result["status"] == "success" else "❌"
        print(f"  {icon} {result['agent_name']} ({result['agent_name_en']}) - {result['duration_ms']:.2f}ms")
        if result["status"] == "error":
            print(f"     错误: {result.get('error', 'Unknown')[:100]}")

    print("=" * 70)
    print(f"  报告已保存: {report_file}")
    print("=" * 70 + "\n")

    return summary


if __name__ == "__main__":
    asyncio.run(run_all_agents())
