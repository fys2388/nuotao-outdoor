# -*- coding: utf-8 -*-
"""
P2: 真实选品流程跑通
流程: 市场趋势分析 -> 热门关键词 -> 竞品分析 -> 选品评测 -> 自动化实验
"""
import sys
import os
import json
import asyncio
from datetime import datetime, timedelta

sys.path.insert(0, '.')

from app.services.market_trend_service import (
    analyze_market_trend, get_hot_keywords, compare_category_trends
)
from app.services.competitor_analysis_service import compare_pricing, analyze_reviews
from app.services.sourcing_evaluation_service import run_evaluation, get_evaluation_status
from app.services.experiment_automation_service import (
    create_experiment, start_experiment, record_experiment_data,
    evaluate_experiment, auto_manage_experiment
)

print("=" * 60)
print("P2: 真实选品流程跑通")
print("=" * 60)

# 候选品类
CANDIDATE_CATEGORIES = ["camping tents", "hiking backpacks", "outdoor lighting", "sleeping bags", "cooking gear"]

# Step 1: 多品类趋势对比
print("\n--- Step 1: 多品类市场趋势对比 ---")
trend_comparison = compare_category_trends(CANDIDATE_CATEGORIES, days=90)
print("  分析品类: {} 个".format(len(CANDIDATE_CATEGORIES)))

# 提取各品类趋势指标
category_scores = []
for cat in CANDIDATE_CATEGORIES:
    trend = analyze_market_trend(cat, category=cat, days=90, region="US")
    metrics = trend.get("metrics", trend.get("trend_metrics", {}))
    growth = metrics.get("growth_rate", metrics.get("trend_direction", "unknown"))
    volume = metrics.get("current_volume", metrics.get("average_volume", 0))
    category_scores.append({
        "category": cat,
        "growth": growth,
        "volume": volume,
        "raw_metrics": metrics
    })
    print("  {:25s} 增长={}, 搜索量={}".format(cat, growth, volume))

# 按增长潜力排序（简单规则：有增长趋势的优先）
def growth_priority(score):
    g = str(score["growth"]).lower()
    if "rising" in g or "up" in g or "positive" in g:
        return 3
    if "stable" in g or "flat" in g:
        return 2
    return 1

category_scores.sort(key=growth_priority, reverse=True)
top_categories = [s["category"] for s in category_scores[:3]]
print("\n  TOP3 候选品类: {}".format(", ".join(top_categories)))

# Step 2: 热门关键词
print("\n--- Step 2: 户外品类热门关键词 ---")
hot_kw = get_hot_keywords(category="outdoor", limit=20)
keywords = hot_kw.get("keywords", hot_kw.get("hot_keywords", []))
print("  热门关键词数: {}".format(len(keywords)))
for i, kw in enumerate(keywords[:10], 1):
    if isinstance(kw, dict):
        print("    {:2d}. {} (volume:{}, trend:{})".format(
            i, kw.get("keyword", kw.get("term", "N/A")),
            kw.get("search_volume", kw.get("volume", "N/A")),
            kw.get("trend", "N/A")))
    else:
        print("    {:2d}. {}".format(i, kw))

# Step 3: 竞品定价分析
print("\n--- Step 3: 竞品定价分析 (TOP3品类) ---")
# 模拟各品类竞品价格（基于市场调研的典型价格区间）
MOCK_COMPETITOR_PRICES = {
    "camping tents": [89.99, 129.99, 159.99, 199.99, 249.99, 299.99, 349.99],
    "hiking backpacks": [39.99, 49.99, 59.99, 79.99, 99.99, 129.99, 159.99],
    "outdoor lighting": [19.99, 24.99, 34.99, 44.99, 54.99, 69.99, 89.99],
}
OUR_PRICES = {"camping tents": 159.99, "hiking backpacks": 59.99, "outdoor lighting": 34.99}

competitor_results = {}
for cat in top_categories:
    our_price = OUR_PRICES.get(cat, 49.99)
    comp_prices = MOCK_COMPETITOR_PRICES.get(cat, [29.99, 39.99, 49.99, 59.99, 69.99])
    pricing = compare_pricing(our_price=our_price, competitor_prices=comp_prices)
    competitor_results[cat] = pricing
    percentile = pricing.get("percentile", "N/A")
    avg_price = pricing.get("market_avg", "N/A")
    print("  {:25s} 我方=${}, 均价=${}, 百分位={}%, 定位={}".format(
        cat, our_price, avg_price, percentile,
        pricing.get("price_position", "N/A")))

# Step 4: 选品评测
print("\n--- Step 4: 选品评测 (基于评测集) ---")
eval_result = run_evaluation(path="tests/sourcing_evaluation_suite.json")
print("  评测用例: {} 个".format(eval_result.get("total_cases", eval_result.get("total", 20))))
print("  通过: {} 个".format(eval_result.get("passed", eval_result.get("pass_count", 0))))
print("  通过率: {}%".format(eval_result.get("pass_rate", eval_result.get("pass_percentage", 0))))
print("  平均分: {}".format(eval_result.get("average_score", eval_result.get("mean_score", 0))))
print("  决策准确率: {}%".format(eval_result.get("decision_accuracy", 0)))

# Step 5: 自动化实验 - 为TOP1品类创建AB实验
print("\n--- Step 5: 自动化选品实验 ---")
top_cat = top_categories[0]
experiment = create_experiment(
    product_id="EXP-{}".format(top_cat.replace(" ", "-").upper()),
    product_name="Test Product - {}".format(top_cat.title()),
    variant_a={"name": "Standard Listing", "price": 49.99, "description": "Basic product description"},
    variant_b={"name": "Enhanced Listing", "price": 44.99, "description": "Enhanced SEO description with keywords"},
    experiment_days=14,
    hypothesis="Enhanced listing with lower price will increase conversion rate by 20%",
    metrics={"primary": "conversion_rate", "secondary": ["click_through_rate", "revenue_per_visitor"]}
)
print("  实验创建: id={}, product={}".format(
    experiment.get("experiment_id", experiment.get("id", "N/A"))[:12],
    experiment.get("product_name", "N/A")))
print("  实验天数: 14, 假设: {}".format(experiment.get("hypothesis", "N/A")[:50]))

# 启动实验
experiment = start_experiment(experiment)
print("  实验状态: {}".format(experiment.get("status", "N/A")))

# 模拟14天实验数据（A: 标准listing, B: 增强listing）
print("\n  模拟实验数据 (14天):")
for day in range(1, 15):
    # Variant A: 标准
    exp_a = record_experiment_data(experiment, "A",
        impressions=50 + day * 5, clicks=8 + day, conversions=2 + (day // 3),
        revenue=100 + day * 15, returns=0)
    # Variant B: 增强（转化率更高）
    exp_b = record_experiment_data(experiment, "B",
        impressions=50 + day * 5, clicks=12 + day * 2, conversions=4 + (day // 2),
        revenue=180 + day * 20, returns=0)
    experiment = exp_b  # 更新实验状态

print("    Variant A: 曝光={}, 点击={}, 转化={}".format(
    experiment.get("variant_a", {}).get("impressions", "N/A"),
    experiment.get("variant_a", {}).get("clicks", "N/A"),
    experiment.get("variant_a", {}).get("conversions", "N/A")))
print("    Variant B: 曝光={}, 点击={}, 转化={}".format(
    experiment.get("variant_b", {}).get("impressions", "N/A"),
    experiment.get("variant_b", {}).get("clicks", "N/A"),
    experiment.get("variant_b", {}).get("conversions", "N/A")))

# 评估实验
eval_exp = evaluate_experiment(experiment)
print("\n  实验评估:")
print("    决策: {}".format(eval_exp.get("decision", "N/A")))
print("    置信度: {}%".format(eval_exp.get("confidence", 0)))
print("    Z值: {}".format(eval_exp.get("z_score", eval_exp.get("z_statistic", "N/A"))))
print("    P值: {}".format(eval_exp.get("p_value", "N/A")))
print("    推荐: {}".format(eval_exp.get("recommendation", "N/A")[:60]))

# 自动管理
managed = auto_manage_experiment(experiment)
print("    自动管理: {}".format(managed.get("action", managed.get("decision", "N/A"))))

# 保存选品报告
report = {
    "generated_at": datetime.now().isoformat(),
    "candidate_categories": CANDIDATE_CATEGORIES,
    "top_categories": top_categories,
    "category_trends": category_scores,
    "hot_keywords": keywords[:10],
    "competitor_analysis": {k: {kk: vv for kk, vv in v.items() if kk != "competitors"} for k, v in competitor_results.items()},
    "evaluation": {
        "total_cases": eval_result.get("total_cases", 20),
        "passed": eval_result.get("passed", 0),
        "pass_rate": eval_result.get("pass_rate", 0),
        "average_score": eval_result.get("average_score", 0),
    },
    "experiment": {
        "product": experiment.get("product_name"),
        "decision": eval_exp.get("decision"),
        "confidence": eval_exp.get("confidence"),
        "recommendation": eval_exp.get("recommendation"),
    }
}
with open("sourcing_report.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

# 最终汇总
print("\n" + "=" * 60)
print("P2 真实选品流程汇总")
print("=" * 60)
print("  ✅ 市场趋势分析: {} 个品类对比".format(len(CANDIDATE_CATEGORIES)))
print("  ✅ 热门关键词: {} 个 (户外品类)".format(len(keywords)))
print("  ✅ 竞品分析: TOP3 品类定价/竞争度分析")
print("  ✅ 选品评测: {} 用例, 通过率{}%, 均分{}".format(
    eval_result.get("total_cases", 20),
    eval_result.get("pass_rate", 0),
    eval_result.get("average_score", 0)))
print("  ✅ 自动化实验: AB实验创建->启动->14天数据->评估->自动管理")
print("     决策: {}, 置信度: {}%".format(eval_exp.get("decision"), eval_exp.get("confidence")))
print("     推荐: {}".format(eval_exp.get("recommendation", "N/A")[:50]))
print()
print("  选品报告已保存: sourcing_report.json")
print("P2 完成")
