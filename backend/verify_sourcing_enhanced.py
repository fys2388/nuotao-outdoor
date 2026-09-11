# -*- coding: utf-8 -*-
"""B组选品增强功能验证脚本"""
import sys, json
sys.path.insert(0, '.')

from app.services.sourcing_1688_service import search_products, get_product_detail, is_configured
from app.services.market_trend_service import analyze_market_trend, get_hot_keywords
from app.services.sourcing_evaluation_service import run_evaluation, get_evaluation_status
from app.services.experiment_automation_service import create_experiment, start_experiment, record_experiment_data, evaluate_experiment, auto_manage_experiment
from app.services.competitor_analysis_service import compare_pricing, analyze_reviews

print("=" * 60)
print("B1: 1688 API 集成（mock降级模式）")
print("=" * 60)
r = search_products("camping tent", page=1, page_size=3)
print(f"  搜索成功: {r['success']}, 来源: {r['source']}, 产品数: {len(r['products'])}, 总数: {r['total']}")
print(f"  第一个产品: {r['products'][0]['subject'][:50]}")
d = get_product_detail("test_001")
print(f"  详情获取: {d['success']}, 产品ID: {d['product']['product_id']}")

print()
print("=" * 60)
print("B2: 竞品分析")
print("=" * 60)
p = compare_pricing(79.99, [49.99, 89.99, 149.99, 29.99, 119.99])
print(f"  定价对比: 我方${p['our_price']}, 市场均价${p['market_avg']}, 定位: {p['price_position']}, 百分位: {p['percentile']}%")
rv = analyze_reviews([
    {"content": "质量很好，做工精细，非常满意", "rating": 5},
    {"content": "发货慢，有点异味", "rating": 3},
    {"content": "性价比高，推荐购买", "rating": 4},
    {"content": "用了一次就坏了，质量差", "rating": 1},
])
print(f"  评价分析: {rv['total_reviews']}条, 均分{rv['avg_rating']}, 情感: {rv['sentiment']}")
print(f"  痛点: {rv['pain_points'][:3]}")

print()
print("=" * 60)
print("B3: 市场趋势分析")
print("=" * 60)
t = analyze_market_trend("camping light", category="camping", days=30)
print(f"  趋势分析: 方向={t['metrics']['trend_direction']}, 当前指数={t['metrics']['current_index']}, 周增长={t['metrics']['growth_pct']}%")
print(f"  季节性: {t['seasonality']['pattern']}, 当前位置={t['seasonality']['current_position']}")
print(f"  30天预测增长: {t['forecast']['projected_growth_pct']}%")
hk = get_hot_keywords(limit=5)
print(f"  热门关键词TOP5: {[k['keyword'] for k in hk['keywords'][:5]]}")

print()
print("=" * 60)
print("B4: 选品评测集")
print("=" * 60)
st = get_evaluation_status()
print(f"  评测集: {st['suite_name']} v{st['version']}")
print(f"  测试用例: {st['total_test_cases']}个, 边界用例: {st['total_edge_cases']}个")
print(f"  难度分布: {st['by_difficulty']}")
print(f"  品类数: {len(st['categories'])}")
print("  运行完整评测（20用例，内置基准评分器）...")
ev = run_evaluation()
print(f"  评测结果: 通过={ev['passed']}/{ev['total']}, 通过率={ev['pass_rate']}%, 平均分={ev['avg_score']}")
print(f"  决策准确率: {ev['decision_accuracy']}%")
print(f"  整体通过: {ev['overall_pass']} (阈值{ev['pass_threshold']})")
if ev['failed_cases']:
    print(f"  失败案例: {[(f['id'], f['expected'], f['actual']) for f in ev['failed_cases'][:3]]}")

print()
print("=" * 60)
print("B5: 自动化实验")
print("=" * 60)
exp = create_experiment("prod_001", "太阳能露营灯", experiment_days=14)
print(f"  实验创建: id={exp['experiment_id'][:8]}..., 状态={exp['status']}, 天数={exp['experiment_days']}")
exp = start_experiment(exp)
print(f"  实验启动: 状态={exp['status']}")
# 记录A变体数据
exp = record_experiment_data(exp, "A", impressions=500, clicks=30, conversions=8, revenue=639.92, returns=1)
# 记录B变体数据（降价10%，转化率更高）
exp = record_experiment_data(exp, "B", impressions=500, clicks=45, conversions=14, revenue=993.86, returns=1)
print(f"  数据记录: A转化={exp['variants']['A']['data']['conversions']}, B转化={exp['variants']['B']['data']['conversions']}")
eval_r = evaluate_experiment(exp)
print(f"  实验评估: 决策={eval_r['decision']}, 置信度={eval_r['confidence']:.1%}")
print(f"  统计显著: {eval_r['significance']['significant']}, Z={eval_r['significance']['z_score']}, p={eval_r['significance']['p_value']}")
print(f"  成功指标: {eval_r['success_check']['passed_count']}/{eval_r['success_check']['total_count']}通过")
print(f"  建议: {eval_r['recommendation']}")
# 自动管理测试
auto_r = auto_manage_experiment(exp)
print(f"  自动管理: 动作={auto_r['action']}, 消息={auto_r['message'][:60]}")

print()
print("=" * 60)
print("B组全部5项功能验证完成 ✅")
print("=" * 60)
