"""
竞品分析服务
支持竞品价格对比、销量估算、评价分析、差异化定位
数据来源：WooCommerce 产品 + 1688 供应商 + 手动录入竞品
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


async def analyze_competitors(
    session: AsyncSession,
    product_id: str | None = None,
    keyword: str | None = None,
    competitors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    竞品分析

    Args:
        session: 数据库会话
        product_id: 我方产品 ID（可选，用于对比基准）
        keyword: 关键词（用于搜索相关竞品）
        competitors: 手动录入的竞品列表（可选）

    Returns:
        竞品分析报告
    """
    # 获取我方产品作为基准
    our_product = None
    if product_id:
        try:
            result = await session.execute(
                select(Product).where(Product.id == UUID(product_id))
            )
            our_product = result.scalar_one_or_none()
        except Exception as e:
            logger.warning("Failed to fetch our product: %s", str(e))

    # 合并竞品数据
    all_competitors = []
    if competitors:
        all_competitors.extend(competitors)

    # 从数据库获取同类产品作为竞品参考
    if keyword or our_product:
        try:
            search_kw = keyword or (our_product.category if our_product else None)
            if search_kw:
                result = await session.execute(
                    select(Product).where(
                        Product.category.ilike(f"%{search_kw}%")
                    ).limit(10)
                )
                db_products = result.scalars().all()
                for p in db_products:
                    if our_product and str(p.id) == str(our_product.id):
                        continue
                    all_competitors.append({
                        "name": p.name,
                        "price": float(p.retail_price) if p.retail_price else 0,
                        "source": "internal_db",
                        "category": p.category,
                    })
        except Exception as e:
            logger.warning("Failed to fetch competitor products: %s", str(e))

    # 如果没有竞品数据，生成示例
    if not all_competitors:
        all_competitors = _generate_sample_competitors(keyword or our_product.name if our_product else "户外用品")

    # 计算分析指标
    our_price = float(our_product.retail_price) if our_product and our_product.retail_price else None
    analysis = _calculate_analysis(all_competitors, our_price)

    return {
        "success": True,
        "analyzed_at": datetime.utcnow().isoformat(),
        "our_product": {
            "id": str(our_product.id) if our_product else None,
            "name": our_product.name if our_product else None,
            "price": our_price,
        } if our_product else None,
        "competitors_count": len(all_competitors),
        "competitors": all_competitors[:20],
        "analysis": analysis,
        "recommendations": _generate_recommendations(analysis, our_price),
    }


def compare_pricing(
    our_price: float,
    competitor_prices: list[float],
) -> dict[str, Any]:
    """
    定价对比分析

    Args:
        our_price: 我方价格
        competitor_prices: 竞品价格列表

    Returns:
        定价分析
    """
    if not competitor_prices:
        return {"success": False, "error": "无竞品价格数据"}

    sorted_prices = sorted(competitor_prices)
    avg_price = sum(sorted_prices) / len(sorted_prices)
    median_price = sorted_prices[len(sorted_prices) // 2]
    min_price = sorted_prices[0]
    max_price = sorted_prices[-1]

    price_position = "mid"
    if our_price < avg_price * 0.8:
        price_position = "low"
    elif our_price > avg_price * 1.2:
        price_position = "high"

    return {
        "success": True,
        "our_price": our_price,
        "market_avg": round(avg_price, 2),
        "market_median": round(median_price, 2),
        "market_min": round(min_price, 2),
        "market_max": round(max_price, 2),
        "price_position": price_position,
        "vs_avg_pct": round((our_price - avg_price) / avg_price * 100, 1) if avg_price else 0,
        "percentile": round(sum(1 for p in sorted_prices if p <= our_price) / len(sorted_prices) * 100, 1),
    }


def analyze_reviews(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """
    评价分析（关键词提取、情感倾向、痛点识别）

    Args:
        reviews: 评价列表，每项包含 content/rating

    Returns:
        评价分析
    """
    if not reviews:
        return {"success": False, "error": "无评价数据"}

    # 评分统计
    ratings = [r.get("rating", 0) for r in reviews if r.get("rating")]
    avg_rating = sum(ratings) / len(ratings) if ratings else 0

    # 关键词提取（简单分词）
    all_text = " ".join(r.get("content", "") for r in reviews)
    keywords = _extract_keywords(all_text)

    # 痛点识别（负面评价关键词）
    negative_reviews = [r for r in reviews if r.get("rating", 5) <= 3]
    pain_points = _extract_pain_points(negative_reviews)

    # 正面卖点
    positive_reviews = [r for r in reviews if r.get("rating", 0) >= 4]
    strengths = _extract_keywords(" ".join(r.get("content", "") for r in positive_reviews))[:5]

    return {
        "success": True,
        "total_reviews": len(reviews),
        "avg_rating": round(avg_rating, 2),
        "rating_distribution": {
            "5_star": sum(1 for r in ratings if r == 5),
            "4_star": sum(1 for r in ratings if r == 4),
            "3_star": sum(1 for r in ratings if r == 3),
            "2_star": sum(1 for r in ratings if r == 2),
            "1_star": sum(1 for r in ratings if r == 1),
        },
        "top_keywords": keywords[:10],
        "strengths": strengths,
        "pain_points": pain_points,
        "sentiment": "positive" if avg_rating >= 4 else "neutral" if avg_rating >= 3 else "negative",
    }


# ============================================
# 内部工具函数
# ============================================

def _calculate_analysis(competitors: list[dict[str, Any]], our_price: float | None) -> dict[str, Any]:
    """计算竞品分析指标"""
    prices = [float(c.get("price", 0)) for c in competitors if c.get("price")]
    if not prices:
        return {"error": "无有效价格数据"}

    sorted_prices = sorted(prices)
    avg = sum(prices) / len(prices)

    return {
        "total_competitors": len(competitors),
        "price_range": {
            "min": round(min(prices), 2),
            "max": round(max(prices), 2),
            "avg": round(avg, 2),
            "median": round(sorted_prices[len(sorted_prices) // 2], 2),
        },
        "price_quartiles": {
            "q1": round(sorted_prices[len(sorted_prices) // 4], 2),
            "q2": round(sorted_prices[len(sorted_prices) // 2], 2),
            "q3": round(sorted_prices[3 * len(sorted_prices) // 4], 2),
        },
        "our_vs_market": compare_pricing(our_price, prices) if our_price else None,
        "market_concentration": _calculate_concentration(competitors),
    }


def _calculate_concentration(competitors: list[dict[str, Any]]) -> str:
    """估算市场集中度"""
    suppliers = set(c.get("supplier_login_id", c.get("company_name", "")) for c in competitors)
    unique_suppliers = len([s for s in suppliers if s])
    if unique_suppliers <= 3:
        return "highly_concentrated"
    elif unique_suppliers <= 8:
        return "moderately_concentrated"
    else:
        return "fragmented"


def _generate_recommendations(analysis: dict[str, Any], our_price: float | None) -> list[str]:
    """生成差异化建议"""
    recs = []
    if our_price and analysis.get("our_vs_market"):
        pos = analysis["our_vs_market"].get("price_position")
        if pos == "high":
            recs.append("当前定价高于市场均价 20%+，建议强化高端价值主张（材质/工艺/品牌）或考虑促销")
        elif pos == "low":
            recs.append("当前定价低于市场均价 20%+，存在利润空间，可考虑小幅提价或增加增值服务")
        else:
            recs.append("定价处于市场中位区间，建议通过差异化功能/设计/包装提升竞争力")

    conc = analysis.get("market_concentration")
    if conc == "highly_concentrated":
        recs.append("市场集中度高，头部供应商占主导，建议寻找细分差异化机会或长尾品类")
    elif conc == "fragmented":
        recs.append("市场分散，存在整合机会，建议建立供应链优势和品牌认知")

    if not recs:
        recs.append("建议持续监控竞品价格变动，每周更新竞品分析数据")

    return recs


def _extract_keywords(text: str) -> list[dict[str, Any]]:
    """简单关键词提取"""
    # 中文分词简化版：按常见词频
    stop_words = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这", "那", "这个", "那个", "还", "可以", "就是", "但是", "因为", "所以", "如果", "虽然", "而且", "或者", "以及", "的话", "一下", "一点", "一些", "一样", "一直", "已经", "可能", "应该", "需要", "觉得", "知道", "时候", "东西", "比较", "非常", "真的", "确实", "其实", "不过", "然后", "后来", "现在", "以前", "以后", "今天", "昨天", "明天"}

    # 提取 2-4 字词组
    words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
    freq: dict[str, int] = {}
    for w in words:
        if w not in stop_words and len(w) >= 2:
            freq[w] = freq.get(w, 0) + 1

    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [{"keyword": w, "count": c} for w, c in sorted_words[:15]]


def _extract_pain_points(negative_reviews: list[dict[str, Any]]) -> list[str]:
    """提取痛点关键词"""
    pain_keywords = ["质量", "做工", "破损", "坏", "差", "异味", "褪色", "变形", "漏水", "漏气", "不结实", "太薄", "太小", "太大", "不合适", "发货慢", "物流", "客服", "售后", "退货", "假货", "虚假", "描述不符", "色差", "气味", "过敏", "不舒服", "难用", "复杂", "麻烦"]

    all_text = " ".join(r.get("content", "") for r in negative_reviews)
    found = []
    for kw in pain_keywords:
        if kw in all_text:
            count = all_text.count(kw)
            found.append({"keyword": kw, "count": count})

    found.sort(key=lambda x: x["count"], reverse=True)
    return [f["keyword"] for f in found[:8]] or ["数据不足，建议收集更多评价"]


def _generate_sample_competitors(keyword: str) -> list[dict[str, Any]]:
    """生成示例竞品数据"""
    return [
        {"name": f"{keyword} - 品牌A 旗舰款", "price": 89.99, "rating": 4.5, "reviews": 1250, "source": "sample", "supplier": "品牌A"},
        {"name": f"{keyword} - 品牌B 性价比款", "price": 49.99, "rating": 4.2, "reviews": 3400, "source": "sample", "supplier": "品牌B"},
        {"name": f"{keyword} - 品牌C 高端款", "price": 149.99, "rating": 4.8, "reviews": 560, "source": "sample", "supplier": "品牌C"},
        {"name": f"{keyword} - 白牌基础款", "price": 29.99, "rating": 3.8, "reviews": 8900, "source": "sample", "supplier": "白牌工厂"},
        {"name": f"{keyword} - 品牌D 专业款", "price": 119.99, "rating": 4.6, "reviews": 780, "source": "sample", "supplier": "品牌D"},
    ]
