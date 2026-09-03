"""
AI Agent 实际运行测试脚本
直接调用 DeepSeek API，验证 5 个 Agent 的提示词和输出结构
不依赖数据库，独立运行
"""
import json
import os
import sys
import time
from datetime import datetime

import requests

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "***REMOVED_DEEPSEEK_KEY***")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"

# 系统代理（如果需要）
PROXIES = {
    "http": "http://127.0.0.1:7897",
    "https": "http://127.0.0.1:7897",
}


def call_deepseek(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict:
    """
    调用 DeepSeek API

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        temperature: 温度参数

    Returns:
        API 响应 JSON
    """
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=payload,
            timeout=60,
            proxies=PROXIES,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ProxyError:
        # 代理不可用时尝试直连
        print("  ⚠️ 代理连接失败，尝试直连...")
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  ❌ API 调用失败: {e!s}")
        raise


def extract_json_content(response: dict) -> dict:
    """从 API 响应中提取并解析 JSON 内容"""
    try:
        content = response["choices"][0]["message"]["content"]
        return json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"  ❌ JSON 解析失败: {e!s}")
        print(f"  原始内容: {response.get('choices', [{}])[0].get('message', {}).get('content', '')[:500]}")
        return {}


# ============================================
# 5 个 Agent 的测试配置
# ============================================

AGENTS_TEST_CONFIG = {
    "product_analyst": {
        "name": "产品分析师 (Product Analyst)",
        "system_prompt": (
            "You are the Product Analyst for Nuotao Outdoor, an outdoor gear DTC brand "
            "targeting European and American customers. Analyze the provided product context "
            "and respond with ONLY a JSON object matching the output schema."
        ),
        "user_prompt_template": (
            "Context: {context_json}\n\n"
            "Output schema: {output_schema}\n\n"
            "Focus on: product performance analysis, pricing recommendations, "
            "competitive positioning, inventory optimization, and actionable product insights. "
            "All recommendations must be data-driven and include confidence scores."
        ),
        "context": {
            "product": {
                "name": "Premium Outdoor Camping Tent - 4 Person",
                "sku": "NT-TENT-001",
                "price": 79.99,
                "cost": 35.00,
                "stock_quantity": 50,
                "category": "Camping Tents",
            },
            "sales_data": {
                "units_sold_30d": 120,
                "revenue_30d": 9598.80,
                "units_sold_90d": 350,
                "revenue_90d": 27996.50,
                "conversion_rate": 3.2,
                "return_rate": 5.1,
            },
            "competitors": [
                {"name": "Competitor A", "price": 89.99, "rating": 4.5},
                {"name": "Competitor B", "price": 69.99, "rating": 4.2},
                {"name": "Competitor C", "price": 99.99, "rating": 4.7},
            ],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "performance_score": {"type": "number"},
                "pricing_recommendation": {"type": "object"},
                "competitive_position": {"type": "string"},
                "inventory_advice": {"type": "string"},
                "actionable_insights": {"type": "array", "items": {"type": "string"}},
                "confidence_score": {"type": "number"},
            },
            "required": ["summary", "performance_score", "actionable_insights", "confidence_score"],
        },
    },

    "marketing_manager": {
        "name": "营销经理 (Marketing Manager)",
        "system_prompt": (
            "You are the Marketing Manager for Nuotao Outdoor, an outdoor gear DTC brand "
            "targeting European and American customers. Analyze the provided marketing context "
            "and respond with ONLY a JSON object matching the output schema."
        ),
        "user_prompt_template": (
            "Context: {context_json}\n\n"
            "Output schema: {output_schema}\n\n"
            "Focus on: campaign ROI analysis, customer segmentation, pricing strategy, "
            "competitive positioning, and actionable marketing recommendations. "
            "All recommendations must be data-driven and include confidence scores."
        ),
        "context": {
            "campaigns": [
                {"name": "Summer Sale", "spend": 5000, "revenue": 25000, "conversions": 150},
                {"name": "Email Marketing", "spend": 500, "revenue": 8000, "conversions": 80},
                {"name": "Google Ads", "spend": 3000, "revenue": 12000, "conversions": 90},
            ],
            "customer_data": {
                "total_customers": 2500,
                "new_customers_30d": 180,
                "repeat_purchase_rate": 22.5,
                "avg_order_value": 85.50,
            },
            "market_trends": {
                "camping_gear_growth": 15.2,
                "outdoor_apparel_growth": 8.7,
                "season": "Summer",
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "campaign_analysis": {"type": "object"},
                "customer_segments": {"type": "array", "items": {"type": "object"}},
                "pricing_suggestions": {"type": "array", "items": {"type": "object"}},
                "marketing_recommendations": {"type": "array", "items": {"type": "string"}},
                "confidence_score": {"type": "number"},
            },
            "required": ["summary", "campaign_analysis", "marketing_recommendations", "confidence_score"],
        },
    },

    "supply_chain_manager": {
        "name": "供应链经理 (Supply Chain Manager)",
        "system_prompt": (
            "You are the Supply Chain Manager for Nuotao Outdoor, an outdoor gear DTC brand "
            "targeting European and American customers. Analyze the provided supply chain context "
            "and respond with ONLY a JSON object matching the output schema."
        ),
        "user_prompt_template": (
            "Context: {context_json}\n\n"
            "Output schema: {output_schema}\n\n"
            "Focus on: supplier performance evaluation, inventory optimization, "
            "cost reduction opportunities, logistics efficiency, risk assessment, "
            "and actionable supply chain recommendations. "
            "All recommendations must be data-driven and include confidence scores."
        ),
        "context": {
            "suppliers": [
                {"name": "Supplier A", "on_time_delivery": 95.2, "quality_rate": 98.5, "lead_time_days": 25, "unit_cost": 35.00},
                {"name": "Supplier B", "on_time_delivery": 88.5, "quality_rate": 95.0, "lead_time_days": 18, "unit_cost": 38.50},
                {"name": "Supplier C", "on_time_delivery": 92.0, "quality_rate": 97.2, "lead_time_days": 30, "unit_cost": 32.00},
            ],
            "inventory": {
                "total_skus": 19,
                "total_units": 1850,
                "inventory_value": 45000,
                "turnover_rate": 4.5,
                "stockout_rate": 3.2,
                "overstock_skus": 3,
            },
            "logistics": {
                "avg_shipping_time_days": 7,
                "shipping_cost_per_order": 12.50,
                "warehouse_utilization": 78,
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "supplier_performance": {"type": "array", "items": {"type": "object"}},
                "inventory_optimization": {"type": "object"},
                "cost_analysis": {"type": "object"},
                "risk_assessment": {"type": "array", "items": {"type": "object"}},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "confidence_score": {"type": "number"},
            },
            "required": ["summary", "supplier_performance", "recommendations", "confidence_score"],
        },
    },

    "customer_manager": {
        "name": "客户经理 (Customer Manager)",
        "system_prompt": (
            "You are the Customer Manager for Nuotao Outdoor, an outdoor gear DTC brand "
            "targeting European and American customers. Analyze the provided customer context "
            "and respond with ONLY a JSON object matching the output schema."
        ),
        "user_prompt_template": (
            "Context: {context_json}\n\n"
            "Output schema: {output_schema}\n\n"
            "Focus on: customer sentiment analysis, support ticket prioritization, "
            "response draft generation, feedback analysis, churn risk assessment, "
            "and actionable customer experience recommendations. "
            "All recommendations must be data-driven and include confidence scores."
        ),
        "context": {
            "customer": {
                "name": "John Smith",
                "email": "john.smith@example.com",
                "total_orders": 5,
                "total_spent": 425.50,
                "last_order_date": "2026-08-15",
                "customer_since": "2025-03-10",
            },
            "recent_tickets": [
                {"id": "T-001", "subject": "Shipping delay", "status": "open", "priority": "high", "created": "2026-08-28"},
                {"id": "T-002", "subject": "Product question", "status": "resolved", "priority": "low", "created": "2026-08-20"},
            ],
            "feedback": [
                {"rating": 4, "comment": "Great product, but shipping was slow.", "date": "2026-08-25"},
                {"rating": 5, "comment": "Excellent quality, will buy again!", "date": "2026-07-10"},
            ],
            "support_metrics": {
                "avg_response_time_hours": 4.5,
                "resolution_rate": 85,
                "customer_satisfaction": 4.2,
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "sentiment_analysis": {"type": "object"},
                "ticket_prioritization": {"type": "array", "items": {"type": "object"}},
                "response_draft": {"type": "string"},
                "churn_risk": {"type": "object"},
                "feedback_insights": {"type": "array", "items": {"type": "string"}},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "confidence_score": {"type": "number"},
            },
            "required": ["summary", "sentiment_analysis", "response_draft", "recommendations", "confidence_score"],
        },
    },

    "business_analyst": {
        "name": "商业分析师 (Business Analyst)",
        "system_prompt": (
            "You are the Business Analyst for Nuotao Outdoor, an outdoor gear DTC brand "
            "targeting European and American customers. Analyze the provided business context "
            "and respond with ONLY a JSON object matching the output schema."
        ),
        "user_prompt_template": (
            "Context: {context_json}\n\n"
            "Output schema: {output_schema}\n\n"
            "Focus on: financial performance analysis, sales trends, KPI tracking, "
            "market opportunity identification, risk assessment, profitability analysis, "
            "and actionable business recommendations. "
            "All recommendations must be data-driven and include confidence scores."
        ),
        "context": {
            "financials": {
                "revenue_month": 85000,
                "revenue_last_month": 78000,
                "revenue_growth": 8.97,
                "gross_margin": 52.5,
                "net_margin": 18.3,
                "operating_expenses": 25000,
                "marketing_spend": 8500,
            },
            "sales": {
                "total_orders": 995,
                "avg_order_value": 85.43,
                "units_sold": 1850,
                "top_category": "Camping Tents",
                "top_product_revenue": 12500,
            },
            "kpis": {
                "customer_acquisition_cost": 42.50,
                "customer_lifetime_value": 285.00,
                "ltv_cac_ratio": 6.7,
                "repeat_purchase_rate": 22.5,
                "inventory_turnover": 4.5,
            },
            "market": {
                "total_market_size": 50000000,
                "market_share": 0.17,
                "industry_growth": 12.5,
                "competitors_count": 25,
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "financial_analysis": {"type": "object"},
                "sales_analysis": {"type": "object"},
                "kpi_dashboard": {"type": "object"},
                "market_opportunities": {"type": "array", "items": {"type": "object"}},
                "risk_assessment": {"type": "array", "items": {"type": "object"}},
                "profitability_analysis": {"type": "object"},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "confidence_score": {"type": "number"},
            },
            "required": ["summary", "financial_analysis", "kpi_dashboard", "recommendations", "confidence_score"],
        },
    },
}


def test_agent(agent_id: str, config: dict) -> dict:
    """测试单个 Agent"""
    print(f"\n{'='*60}")
    print(f"测试: {config['name']}")
    print(f"{'='*60}")

    # 构建用户提示词
    user_prompt = config["user_prompt_template"].format(
        context_json=json.dumps(config["context"], indent=2, ensure_ascii=False),
        output_schema=json.dumps(config["output_schema"], indent=2, ensure_ascii=False),
    )

    print(f"  上下文数据量: {len(json.dumps(config['context']))} 字符")
    print(f"  提示词长度: {len(user_prompt)} 字符")
    print(f"  正在调用 DeepSeek API ({MODEL})...")

    start_time = time.time()

    try:
        response = call_deepseek(
            system_prompt=config["system_prompt"],
            user_prompt=user_prompt,
            temperature=0.3,
        )
    except Exception as e:
        print(f"  ❌ 调用失败: {e!s}")
        return {"agent_id": agent_id, "success": False, "error": str(e)}

    elapsed = time.time() - start_time
    print(f"  ✅ API 调用成功 ({elapsed:.2f}秒)")

    # 提取并解析 JSON
    result = extract_json_content(response)

    if result:
        print(f"  ✅ JSON 解析成功")
        print(f"  输出字段: {list(result.keys())}")

        # 检查必填字段
        required_fields = config["output_schema"].get("required", [])
        missing_fields = [f for f in required_fields if f not in result]
        if missing_fields:
            print(f"  ⚠️ 缺少必填字段: {missing_fields}")
        else:
            print(f"  ✅ 所有必填字段已包含")

        # 打印摘要
        if "summary" in result:
            print(f"\n  📊 分析摘要:")
            print(f"  {result['summary'][:200]}")

        # 打印建议
        recommendations_key = None
        for key in ["recommendations", "marketing_recommendations", "actionable_insights"]:
            if key in result:
                recommendations_key = key
                break

        if recommendations_key and isinstance(result[recommendations_key], list):
            print(f"\n  💡 关键建议 ({len(result[recommendations_key])} 条):")
            for i, rec in enumerate(result[recommendations_key][:3], 1):
                if isinstance(rec, dict):
                    print(f"    {i}. {json.dumps(rec, ensure_ascii=False)[:100]}")
                else:
                    print(f"    {i}. {str(rec)[:100]}")

        # 置信度
        if "confidence_score" in result:
            print(f"\n  🎯 置信度: {result['confidence_score']}")

        # Token 使用情况
        usage = response.get("usage", {})
        if usage:
            print(f"\n  📈 Token 使用:")
            print(f"    提示词: {usage.get('prompt_tokens', 'N/A')}")
            print(f"    完成: {usage.get('completion_tokens', 'N/A')}")
            print(f"    总计: {usage.get('total_tokens', 'N/A')}")

        return {
            "agent_id": agent_id,
            "success": True,
            "elapsed_seconds": round(elapsed, 2),
            "output_fields": list(result.keys()),
            "missing_fields": missing_fields,
            "confidence_score": result.get("confidence_score"),
            "token_usage": usage,
            "result": result,
        }
    else:
        return {"agent_id": agent_id, "success": False, "error": "JSON 解析失败"}


def main():
    print("=" * 60)
    print("AI Agent 实际运行测试")
    print("=" * 60)
    print(f"模型: {MODEL}")
    print(f"API: {DEEPSEEK_API_URL}")
    print(f"测试时间: {datetime.now().isoformat()}")
    print(f"Agent 数量: {len(AGENTS_TEST_CONFIG)}")

    results = []
    for agent_id, config in AGENTS_TEST_CONFIG.items():
        result = test_agent(agent_id, config)
        results.append(result)

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count

    print(f"✅ 成功: {success_count}/{len(results)}")
    print(f"❌ 失败: {fail_count}/{len(results)}")

    print("\n详细结果:")
    print(f"{'Agent':<25} {'状态':<8} {'耗时':<10} {'字段数':<8} {'置信度':<10}")
    print("-" * 65)
    for r in results:
        name = AGENTS_TEST_CONFIG[r["agent_id"]]["name"]
        status = "✅" if r["success"] else "❌"
        elapsed = f"{r.get('elapsed_seconds', 'N/A')}s"
        fields = str(len(r.get("output_fields", [])))
        confidence = str(r.get("confidence_score", "N/A"))
        print(f"{name:<25} {status:<8} {elapsed:<10} {fields:<8} {confidence:<10}")

    # 保存完整结果
    output_file = "agent_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n📄 完整结果已保存到: {output_file}")

    if fail_count > 0:
        print(f"\n⚠️ 有 {fail_count} 个 Agent 测试失败，请检查上方错误信息")
        return 1
    else:
        print("\n🎉 所有 Agent 测试通过！")
        return 0


if __name__ == "__main__":
    sys.exit(main())
