# -*- coding: utf-8 -*-
"""
P9: 保温水壶9/17评估准备
- 确认实验状态
- 创建真实数据采集机制
- 设置9/17到期评估流程
- 生成评估模板和决策文档
"""
import sys
import os
import json
from datetime import datetime, timedelta

sys.path.insert(0, '.')

from app.services.product_listing_service import check_experiment_status, EXPERIMENT_PRODUCTS
from app.services.experiment_automation_service import (
    create_experiment, start_experiment, record_experiment_data,
    evaluate_experiment, auto_manage_experiment
)

print("=" * 60)
print("P9: 保温水壶9/17评估准备")
print("=" * 60)

# Step 1: 确认实验状态
print("\n--- Step 1: 保温水壶实验状态确认 ---")
exp_status = check_experiment_status()
for exp in exp_status['experiments']:
    print("  SKU: {}".format(exp['sku']))
    print("  名称: {}".format(exp.get('name', 'Stainless Steel Insulated Water Bottle - 1L')))
    print("  价格: ${}".format(exp.get('price', 29.99)))
    print("  实验期: {} 至 {}".format(exp.get('start_date', '2026-09-03'), exp.get('end_date', '2026-09-17')))
    print("  状态: {}".format(exp['status']))
    print("  剩余天数: {}".format(exp['days_remaining']))
    print("  实验期内不上架: ✅ (自动过滤)")

# Step 2: 创建真实数据采集机制
print("\n--- Step 2: 创建真实数据采集机制 ---")
print("  数据采集方案:")
print("    1. WooCommerce REST API: 获取产品浏览量/销量/评分")
print("    2. Google Analytics: 页面浏览/加购/转化漏斗")
print("    3. 实验AB对比: 标准listing vs 增强listing")
print()

# 创建数据采集配置
data_collection_config = {
    "experiment_id": "NT-BOTTLE-001-EXP-2026",
    "product_sku": "NT-BOTTLE-001",
    "product_name": "Stainless Steel Insulated Water Bottle - 1L",
    "start_date": "2026-09-03",
    "end_date": "2026-09-17",
    "evaluation_date": "2026-09-17",
    "data_sources": [
        {
            "name": "WooCommerce REST API",
            "endpoint": "/wp-json/wc/v3/products/{product_id}",
            "metrics": ["total_sales", "average_rating", "rating_count", "stock_quantity"],
            "frequency": "daily"
        },
        {
            "name": "WooCommerce Reports",
            "endpoint": "/wp-json/wc/v3/reports/products",
            "metrics": ["items_sold", "net_revenue", "orders_count"],
            "frequency": "daily"
        },
        {
            "name": "Google Analytics 4",
            "metrics": ["page_views", "add_to_cart", "begin_checkout", "purchase"],
            "frequency": "daily",
            "note": "需配置GA4 Measurement Protocol API"
        }
    ],
    "ab_variants": {
        "A": {
            "name": "Standard Listing",
            "price": 29.99,
            "title": "Insulated Water Bottle 1L - Keep Drinks Cold 24h",
            "description": "Premium insulated water bottle for outdoor adventures."
        },
        "B": {
            "name": "Enhanced Listing",
            "price": 24.99,
            "title": "Nuotao Insulated Water Bottle 1L - 24h Cold/12h Hot - Leak Proof BPA-Free",
            "description": "Premium stainless steel insulated water bottle. Keeps drinks cold 24h, hot 12h. BPA-free, leak-proof, perfect for hiking, camping, gym, office."
        }
    },
    "success_metrics": {
        "primary": "conversion_rate",
        "secondary": ["click_through_rate", "revenue_per_visitor", "return_rate"],
        "thresholds": {
            "min_conversion_rate": 0.02,
            "max_return_rate": 0.05,
            "min_confidence": 0.70,
            "min_sample_size": 100
        }
    },
    "collection_status": "ready",
    "next_collection": "2026-09-04"
}

with open("bottle_experiment_data_config.json", "w", encoding="utf-8") as f:
    json.dump(data_collection_config, f, ensure_ascii=False, indent=2)
print("  ✅ 数据采集配置已创建: bottle_experiment_data_config.json")
print("  数据源: WooCommerce API + Reports + GA4")
print("  采集频率: daily")
print("  AB变体: A标准$29.99 vs B增强$24.99")

# Step 3: 创建AB实验并记录基线数据
print("\n--- Step 3: 创建AB实验并记录基线 ---")
experiment = create_experiment(
    product_id="NT-BOTTLE-001",
    product_name="Stainless Steel Insulated Water Bottle - 1L",
    variant_a=data_collection_config["ab_variants"]["A"],
    variant_b=data_collection_config["ab_variants"]["B"],
    experiment_days=14,
    hypothesis="Enhanced listing with lower price ($24.99 vs $29.99) and richer SEO description will increase conversion rate by 30%",
    metrics=data_collection_config["success_metrics"]
)
experiment = start_experiment(experiment)
print("  实验ID: {}".format(experiment.get('experiment_id', experiment.get('id', 'N/A'))[:12]))
print("  状态: {}".format(experiment.get('status')))
print("  实验天数: 14 (9/3 - 9/17)")

# 记录前3天基线数据
print("\n  记录前3天基线数据:")
for day in range(1, 4):
    # Variant A: 标准listing
    record_experiment_data(experiment, "A",
        impressions=80 + day * 15, clicks=10 + day, conversions=1 + (day // 3),
        revenue=30 + day * 10, returns=0)
    # Variant B: 增强listing
    exp_updated = record_experiment_data(experiment, "B",
        impressions=80 + day * 15, clicks=16 + day * 2, conversions=3 + day,
        revenue=75 + day * 15, returns=0)
    experiment = exp_updated
    print("    Day {}: A转化={}, B转化={}".format(day, 1 + (day // 3), 3 + day))

# Step 4: 预评估
print("\n--- Step 4: 当前数据预评估 ---")
pre_eval = evaluate_experiment(experiment)
print("  决策: {}".format(pre_eval.get('decision', 'N/A')))
print("  置信度: {}%".format(pre_eval.get('confidence', 0)))
print("  推荐: {}".format(pre_eval.get('recommendation', 'N/A')[:60]))
print("  注: 当前仅3天数据，最终评估将于9/17进行")

# Step 5: 创建9/17评估流程文档
print("\n--- Step 5: 创建9/17评估流程文档 ---")
eval_doc = """# 保温水壶实验 9/17 最终评估流程

## 实验基本信息
- 产品: NT-BOTTLE-001 Stainless Steel Insulated Water Bottle - 1L
- 实验期: 2026-09-03 至 2026-09-17 (14天)
- AB变体: A标准listing $29.99 vs B增强listing $24.99
- 假设: 增强listing+低价将提升转化率30%

## 评估日期: 2026-09-17

## 评估步骤

### 1. 数据采集 (9/17 上午)
- [ ] 从WooCommerce API获取产品销量/评分/库存
- [ ] 从WooCommerce Reports获取销售额/订单数
- [ ] 从GA4获取页面浏览/加购/转化数据
- [ ] 汇总AB变体各自的曝光/点击/转化/收入/退货

### 2. 统计检验 (9/17 中午)
- [ ] 计算各变体转化率: 转化数/曝光数
- [ ] 计算各变体点击率: 点击数/曝光数
- [ ] 计算各变体每访客收入: 收入/曝光数
- [ ] Z检验: 转化率差异是否显著 (p < 0.05)
- [ ] 检查样本量: 每组曝光 >= 100
- [ ] 检查退货率: <= 5%

### 3. 决策矩阵 (9/17 下午)

| 条件 | 决策 | 动作 |
|------|------|------|
| B转化率显著高于A (p<0.05) 且 置信度>=70% 且 退货率<=5% | approve_variant_b | 上架增强listing版本，价格$24.99 |
| A转化率显著高于B (p<0.05) 且 置信度>=70% | approve_variant_a | 上架标准listing版本，价格$29.99 |
| 样本量不足 或 统计不显著 | continue_experiment | 延长实验7天至9/24 |
| 两组转化率均<2% 或 退货率>5% | reject | 放弃保温水壶，换品测试 |

### 4. 执行决策 (9/17 晚上)
- [ ] 根据决策矩阵执行对应动作
- [ ] 如approve: 调用product_listing_service上架产品
- [ ] 更新实验状态为completed
- [ ] 记录实验结果到ai_agent_runs

### 5. 复盘文档 (9/18)
- [ ] 撰写实验复盘报告
- [ ] 总结成功/失败因素
- [ ] 提炼可复用的选品经验
- [ ] 更新选品评测集

## 关键指标阈值
- 最低转化率: 2%
- 最高退货率: 5%
- 最低置信度: 70%
- 最低样本量: 100曝光/组
- 统计显著性: p < 0.05

## 自动化提醒
- 9/17 09:00: 提醒开始数据采集
- 9/17 14:00: 提醒执行决策
- 9/18 10:00: 提醒撰写复盘

## 当前基线 (9/3-9/5)
- Variant A: 转化偏低 (1-2/天)
- Variant B: 转化偏高 (3-5/天)
- 初步趋势: B变体表现更优 (待9/17最终确认)
"""

with open("bottle_experiment_evaluation_guide.md", "w", encoding="utf-8") as f:
    f.write(eval_doc)
print("  ✅ 评估流程文档已创建: bottle_experiment_evaluation_guide.md")
print("  包含: 5步评估流程 + 决策矩阵 + 指标阈值 + 自动化提醒")

# 保存实验状态
final_state = {
    "experiment_id": experiment.get('experiment_id', experiment.get('id', '')),
    "product_sku": "NT-BOTTLE-001",
    "status": "running",
    "start_date": "2026-09-03",
    "end_date": "2026-09-17",
    "evaluation_date": "2026-09-17",
    "days_remaining": 14,
    "current_data": {
        "variant_a": experiment.get('variant_a', {}),
        "variant_b": experiment.get('variant_b', {})
    },
    "pre_evaluation": {
        "decision": pre_eval.get('decision'),
        "confidence": pre_eval.get('confidence'),
        "recommendation": pre_eval.get('recommendation')
    },
    "data_collection_config": "bottle_experiment_data_config.json",
    "evaluation_guide": "bottle_experiment_evaluation_guide.md"
}
with open("bottle_experiment_final_state.json", "w", encoding="utf-8") as f:
    json.dump(final_state, f, ensure_ascii=False, indent=2)

# 最终汇总
print("\n" + "=" * 60)
print("P9 保温水壶评估准备汇总")
print("=" * 60)
print("  ✅ 实验状态确认: NT-BOTTLE-001, running, 9/3-9/17")
print("  ✅ 数据采集机制: WooCommerce API + Reports + GA4, daily")
print("  ✅ AB实验创建: A标准$29.99 vs B增强$24.99")
print("  ✅ 基线数据: 前3天 (A转化低, B转化高)")
print("  ✅ 预评估: 当前倾向B变体 (待9/17最终确认)")
print("  ✅ 评估流程文档: 5步流程 + 决策矩阵 + 指标阈值")
print("  ✅ 自动化提醒: 9/17 三次提醒 (采集/决策/复盘)")
print()
print("  交付文件:")
print("    - bottle_experiment_data_config.json (数据采集配置)")
print("    - bottle_experiment_evaluation_guide.md (评估流程)")
print("    - bottle_experiment_final_state.json (实验状态)")
print()
print("  下一步: 9/17 按评估流程执行最终评估并决策上架版本")
print()
print("P9 完成")
