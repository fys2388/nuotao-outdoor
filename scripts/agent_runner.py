"""
Nuotao AI OS - 5个AI Agent角色统一运行入口
功能：
  1. 产品分析师（Product Analyst）
  2. 营销经理（Marketing Manager）
  3. 供应链经理（Supply Chain Manager）
  4. 客户经理（Customer Manager）
  5. 商业分析师（Business Analyst）

所有 Agent 严格遵循"分析+建议+审计"原则，不执行业务操作。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents import (
    analyze_product,
    analyze_marketing,
    analyze_supply_chain,
    analyze_customer,
    analyze_business,
    ProductAnalysisResult,
    MarketingAnalysisResult,
    SupplyChainAnalysisResult,
    CustomerAnalysisResult,
    BusinessAnalysisResult,
)

logger = logging.getLogger("agent_runner")

# 输出目录
OUTPUT_DIR = Path("E:/AI/nuotao-ai-os/backups/agent_reports")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class AgentRunner:
    """AI Agent 统一运行器"""

    AGENTS = {
        "product_analyst": {
            "name": "产品分析师",
            "name_en": "Product Analyst",
            "description": "产品分析与选品建议",
            "function": analyze_product,
        },
        "marketing_manager": {
            "name": "营销经理",
            "name_en": "Marketing Manager",
            "description": "营销策略与活动分析",
            "function": analyze_marketing,
        },
        "supply_chain_manager": {
            "name": "供应链经理",
            "name_en": "Supply Chain Manager",
            "description": "供应商、库存与物流优化",
            "function": analyze_supply_chain,
        },
        "customer_manager": {
            "name": "客户经理",
            "name_en": "Customer Manager",
            "description": "客户服务、体验与反馈分析",
            "function": analyze_customer,
        },
        "business_analyst": {
            "name": "商业分析师",
            "name_en": "Business Analyst",
            "description": "财务、销售与商业智能",
            "function": analyze_business,
        },
    }

    def __init__(self):
        self.results: dict[str, Any] = {}
        self.run_timestamp = datetime.now(timezone.utc).isoformat()

    def list_agents(self) -> list[dict[str, str]]:
        """列出所有可用 Agent"""
        return [
            {
                "key": key,
                "name": info["name"],
                "name_en": info["name_en"],
                "description": info["description"],
            }
            for key, info in self.AGENTS.items()
        ]

    def run_agent(self, agent_key: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """运行单个 Agent"""
        if agent_key not in self.AGENTS:
            raise ValueError(f"Unknown agent: {agent_key}. Available: {list(self.AGENTS.keys())}")

        agent_info = self.AGENTS[agent_key]
        logger.info("Running agent: %s (%s)", agent_info["name"], agent_key)

        start_time = datetime.now(timezone.utc)

        # 默认工作空间 ID
        default_workspace_id = "00000000-0000-0000-0000-000000000001"
        default_context = context or {
            "run_type": "scheduled_daily",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_source": "local_json",
        }

        try:
            # 根据 Agent 类型调用不同参数
            if agent_key == "product_analyst":
                # 产品分析师需要 product_id
                result = agent_info["function"](
                    workspace_id=default_workspace_id,
                    product_id=default_context.get("product_id", "default-product"),
                )
            else:
                # 其他 Agent 需要 workspace_id 和 context
                result = agent_info["function"](
                    workspace_id=default_workspace_id,
                    context=default_context,
                )

            # 标准化结果
            if hasattr(result, "model_dump"):
                result_dict = result.model_dump()
            elif isinstance(result, dict):
                result_dict = result
            else:
                result_dict = {"result": str(result)}

            end_time = datetime.now(timezone.utc)
            duration_ms = (end_time - start_time).total_seconds() * 1000

            agent_result = {
                "agent_key": agent_key,
                "agent_name": agent_info["name"],
                "agent_name_en": agent_info["name_en"],
                "description": agent_info["description"],
                "status": "success",
                "started_at": start_time.isoformat(),
                "completed_at": end_time.isoformat(),
                "duration_ms": round(duration_ms, 2),
                "result": result_dict,
            }

            self.results[agent_key] = agent_result
            logger.info("Agent %s completed in %.2fms", agent_key, duration_ms)

            return agent_result

        except Exception as e:
            end_time = datetime.now(timezone.utc)
            duration_ms = (end_time - start_time).total_seconds() * 1000

            agent_result = {
                "agent_key": agent_key,
                "agent_name": agent_info["name"],
                "agent_name_en": agent_info["name_en"],
                "description": agent_info["description"],
                "status": "error",
                "started_at": start_time.isoformat(),
                "completed_at": end_time.isoformat(),
                "duration_ms": round(duration_ms, 2),
                "error": str(e),
            }

            self.results[agent_key] = agent_result
            logger.error("Agent %s failed: %s", agent_key, e)

            return agent_result

    def run_all_agents(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """运行所有 5 个 Agent"""
        logger.info("=" * 60)
        logger.info("Running all 5 AI agents")
        logger.info("=" * 60)

        results = {}
        for agent_key in self.AGENTS:
            results[agent_key] = self.run_agent(agent_key, context)

        # 汇总
        success_count = sum(1 for r in results.values() if r["status"] == "success")
        error_count = sum(1 for r in results.values() if r["status"] == "error")
        total_duration = sum(r["duration_ms"] for r in results.values())

        summary = {
            "run_timestamp": self.run_timestamp,
            "total_agents": len(self.AGENTS),
            "success_count": success_count,
            "error_count": error_count,
            "total_duration_ms": round(total_duration, 2),
            "agents": results,
        }

        # 保存报告
        self.save_report(summary)

        logger.info("=" * 60)
        logger.info("All agents completed: %d success, %d error, %.2fms total",
                    success_count, error_count, total_duration)
        logger.info("=" * 60)

        return summary

    def save_report(self, summary: dict[str, Any]) -> str:
        """保存 Agent 运行报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = OUTPUT_DIR / f"agent_report_{timestamp}.json"

        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

        logger.info("Report saved: %s", report_file)
        return str(report_file)

    def print_summary(self, summary: dict[str, Any]) -> None:
        """打印运行摘要"""
        print("\n" + "=" * 70)
        print("  Nuotao AI OS - 5 AI Agents Run Summary")
        print("=" * 70)
        print(f"  运行时间: {summary['run_timestamp']}")
        print(f"  总 Agent 数: {summary['total_agents']}")
        print(f"  成功: {summary['success_count']} | 失败: {summary['error_count']}")
        print(f"  总耗时: {summary['total_duration_ms']:.2f}ms")
        print("-" * 70)

        for key, result in summary["agents"].items():
            status_icon = "✅" if result["status"] == "success" else "❌"
            print(f"  {status_icon} {result['agent_name']} ({result['agent_name_en']})")
            print(f"     耗时: {result['duration_ms']:.2f}ms")
            if result["status"] == "error":
                print(f"     错误: {result.get('error', 'Unknown')}")
            else:
                # 打印结果摘要
                result_data = result.get("result", {})
                if isinstance(result_data, dict):
                    for k, v in list(result_data.items())[:3]:
                        if v is not None:
                            v_str = str(v)[:80]
                            print(f"     {k}: {v_str}")

        print("=" * 70)
        print(f"  报告已保存到: {OUTPUT_DIR}")
        print("=" * 70 + "\n")


def main():
    """主函数：运行所有 5 个 Agent"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    runner = AgentRunner()

    # 列出可用 Agent
    print("\n可用 AI Agent:")
    for agent in runner.list_agents():
        print(f"  - {agent['name']} ({agent['name_en']}): {agent['description']}")

    # 运行所有 Agent
    context = {
        "run_type": "scheduled_daily",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    summary = runner.run_all_agents(context)
    runner.print_summary(summary)

    return summary


if __name__ == "__main__":
    main()
