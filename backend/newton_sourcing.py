# -*- coding: utf-8 -*-
"""
牛顿AI选品集成工具
结合阿里牛顿Agent自然语言找品 + 现有选品评分体系

功能:
1. 自然语言找品（牛顿Agent）
2. 商品标准化 + 选品评分（复用import_1688_products逻辑）
3. 综合选品报告输出

使用方法:
  python newton_sourcing.py "户外露营灯，10-30元，起订50个"
  python newton_sourcing.py "头灯，USB充电，轻量化" --max-wait 120
  python newton_sourcing.py "折叠椅，承重150kg" --output data/newton_results.json
"""
import sys
import os
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from app.services.newton_agent_service import (
    newton_agent_search,
    query_points,
    is_configured,
    NEWTON_APP_KEY,
)


def score_product(product: dict) -> dict:
    """
    对单个商品进行选品评分（简化版，复用选品逻辑）

    评分维度:
    - 价格竞争力（30分）
    - 起订量友好度（20分）
    - 供应商可靠性（20分）
    - 销量/热度（15分）
    - 商品信息完整度（15分）
    """
    score = 0
    reasons = []

    # 价格评分（30分）
    price = product.get("price", "")
    if isinstance(price, (int, float)) and price > 0:
        if price <= 10:
            score += 30
            reasons.append(f"价格极低({price}元)")
        elif price <= 30:
            score += 25
            reasons.append(f"价格亲民({price}元)")
        elif price <= 50:
            score += 18
            reasons.append(f"价格适中({price}元)")
        elif price <= 100:
            score += 10
            reasons.append(f"价格偏高({price}元)")
        else:
            score += 5
            reasons.append(f"价格高({price}元)")
    else:
        score += 10
        reasons.append("价格信息不明确")

    # 起订量评分（20分）
    moq = product.get("min_order_qty", 1)
    if isinstance(moq, (int, float)):
        if moq <= 10:
            score += 20
            reasons.append(f"起订量极低({moq})")
        elif moq <= 50:
            score += 16
            reasons.append(f"起订量友好({moq})")
        elif moq <= 100:
            score += 12
            reasons.append(f"起订量适中({moq})")
        elif moq <= 500:
            score += 6
            reasons.append(f"起订量偏高({moq})")
        else:
            score += 2
            reasons.append(f"起订量高({moq})")
    else:
        score += 10

    # 供应商评分（20分）
    supplier = product.get("supplier", "")
    if supplier:
        score += 15
        if "厂" in supplier or "工厂" in supplier or "实业" in supplier:
            score += 5
            reasons.append(f"源头工厂({supplier})")
        else:
            reasons.append(f"有供应商信息({supplier})")
    else:
        score += 5
        reasons.append("供应商信息缺失")

    # 商品信息完整度（15分）
    completeness = 0
    if product.get("subject"):
        completeness += 5
    if product.get("image_url"):
        completeness += 5
    if product.get("detail_url"):
        completeness += 5
    score += completeness
    reasons.append(f"信息完整度{completeness}/15")

    # 销量/热度（15分）- 牛顿返回可能没有销量，给基础分
    score += 8
    reasons.append("AI推荐热度+8")

    product["score"] = score
    product["score_reasons"] = reasons
    product["score_grade"] = (
        "S" if score >= 80 else
        "A" if score >= 65 else
        "B" if score >= 50 else
        "C"
    )
    return product


def run_newton_sourcing(query: str, max_wait: int = 180, output: str = None) -> dict:
    """
    执行牛顿AI选品完整流程

    Args:
        query: 自然语言找品需求
        max_wait: 最大等待秒数
        output: 输出文件路径（可选）

    Returns:
        选品结果报告
    """
    print("=" * 70)
    print("牛顿AI选品集成工具")
    print("=" * 70)
    print(f"找品需求: {query}")
    print(f"AppKey: {NEWTON_APP_KEY}")
    print(f"已配置: {is_configured()}")
    print()

    # 查询当前额度
    print("[1/4] 查询API额度...")
    points = query_points()
    if points.get("success"):
        print(f"  总额度: {points.get('total', 'N/A')}")
        print(f"  已使用: {points.get('used', 'N/A')}")
        print(f"  剩余: {points.get('remaining', 'N/A')}")
    else:
        print(f"  额度查询失败: {points.get('error')}")
    print()

    # 牛顿Agent找品
    print(f"[2/4] 牛顿Agent找品中（最长等待{max_wait}秒）...")
    start_time = datetime.now()
    result = newton_agent_search(query, auto=True)
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"  耗时: {elapsed:.1f}秒")
    print(f"  状态: {'成功' if result.get('success') else '失败'}")
    print(f"  来源: {result.get('source')}")
    print(f"  商品数量: {result.get('total', 0)}")
    print()

    if not result.get("success"):
        print(f"✗ 找品失败: {result.get('error')}")
        return result

    # 选品评分
    print("[3/4] 选品评分计算...")
    products = result.get("products", [])
    scored_products = []
    for i, p in enumerate(products):
        scored = score_product(p)
        scored_products.append(scored)
        print(f"  [{i+1}/{len(products)}] {scored.get('subject', '未知')[:40]}... 评分: {scored['score']} ({scored['score_grade']})")

    # 按评分排序
    scored_products.sort(key=lambda x: x["score"], reverse=True)
    print()

    # 输出报告
    print("[4/4] 生成选品报告...")
    report = {
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "source": result.get("source"),
        "task_id": result.get("task_id", ""),
        "summary": result.get("summary", ""),
        "total_found": result.get("total", 0),
        "total_scored": len(scored_products),
        "top_recommendations": scored_products[:10],
        "all_products": scored_products,
        "api_usage": {
            "total": points.get("total"),
            "used": points.get("used"),
            "remaining": points.get("remaining"),
        },
    }

    # 打印TOP推荐
    print()
    print("=" * 70)
    print("TOP 5 推荐商品")
    print("=" * 70)
    for i, p in enumerate(scored_products[:5]):
        print(f"\n【{i+1}】评分: {p['score']} ({p['score_grade']})")
        print(f"  商品: {p.get('subject', '未知')[:60]}")
        print(f"  价格: {p.get('price', 'N/A')}")
        print(f"  起订: {p.get('min_order_qty', 'N/A')}")
        print(f"  供应商: {p.get('supplier', 'N/A')[:40]}")
        print(f"  评分理由: {', '.join(p.get('score_reasons', [])[:3])}")
        if p.get("detail_url"):
            print(f"  链接: {p['detail_url'][:80]}")

    # 保存到文件
    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n✓ 报告已保存: {output}")
    else:
        default_output = f"data/newton_sourcing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs("data", exist_ok=True)
        with open(default_output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n✓ 报告已保存: {default_output}")

    print()
    print("=" * 70)
    print("选品完成")
    print("=" * 70)

    return report


def main():
    parser = argparse.ArgumentParser(description="牛顿AI选品集成工具")
    parser.add_argument("query", help="自然语言找品需求，如'户外露营灯，10-30元'")
    parser.add_argument("--max-wait", type=int, default=180, help="最大等待秒数（默认180）")
    parser.add_argument("--output", type=str, default=None, help="输出文件路径")
    args = parser.parse_args()

    run_newton_sourcing(args.query, max_wait=args.max_wait, output=args.output)


if __name__ == "__main__":
    main()
