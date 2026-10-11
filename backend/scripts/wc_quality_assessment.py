#!/usr/bin/env python3
"""
WC 商品上架质量评估系统

评估标准（100分制）：
- 基础信息（20分）：产品名称、SKU、状态、分类、标签
- 价格与库存（15分）：价格、库存、运费
- 内容质量（25分）：描述、简短描述、参数表、FAQ
- 图片质量（20分）：主图、补充图、图片质量
- SEO优化（20分）：SEO Title、Meta Description、Focus Keyword、robots

目标分数：≥95分
"""

import json
import os
import sys
import requests
from typing import Dict, List, Tuple

# WooCommerce API 配置
WC_URL = os.getenv("WOOCOMMERCE_URL", "https://nuotaooutdoor.com")
CK = os.getenv("WOOCOMMERCE_CONSUMER_KEY", "")
CS = os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "")
AUTH = (CK, CS)
HEADERS = {"Content-Type": "application/json"}


def get_wc_product(product_id: int) -> Dict:
    """获取WC产品数据"""
    url = f"{WC_URL}/wp-json/wc/v3/products/{product_id}"
    resp = requests.get(url, auth=AUTH, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def assess_basic_info(product: Dict) -> Tuple[float, List[str]]:
    """评估基础信息（20分）"""
    score = 0
    issues = []
    
    # 产品名称（5分）
    if product.get("name"):
        score += 5
    else:
        issues.append("缺少产品名称")
    
    # SKU（5分）
    if product.get("sku"):
        score += 5
    else:
        issues.append("缺少SKU")
    
    # 状态（5分）
    if product.get("status") == "publish":
        score += 5
    elif product.get("status") == "draft":
        issues.append(f"状态为draft，应为publish")
    else:
        issues.append(f"状态异常：{product.get('status')}")
    
    # 分类（3分）
    if product.get("categories") and len(product["categories"]) > 0:
        score += 3
    else:
        issues.append("缺少分类")
    
    # 标签（2分）
    if product.get("tags") and len(product["tags"]) >= 5:
        score += 2
    elif product.get("tags") and len(product["tags"]) > 0:
        score += 1
        issues.append(f"标签数量不足（当前{len(product['tags'])}，建议≥5）")
    else:
        issues.append("缺少标签")
    
    return score, issues


def assess_price_inventory(product: Dict) -> Tuple[float, List[str]]:
    """评估价格与库存（15分）"""
    score = 0
    issues = []
    
    # 价格（5分）
    regular_price = product.get("regular_price", "0")
    try:
        price = float(regular_price)
        if price > 0:
            score += 5
        else:
            issues.append("价格为0或缺失")
    except:
        issues.append(f"价格格式错误：{regular_price}")
    
    # 库存（5分）
    if product.get("manage_stock"):
        stock_quantity = product.get("stock_quantity", 0)
        stock_status = product.get("stock_status", "")
        if stock_status == "instock" and stock_quantity > 0:
            score += 5
        elif stock_status == "instock":
            score += 3
            issues.append("库存数量为0")
        else:
            issues.append(f"库存状态异常：{stock_status}")
    else:
        # 不管理库存也可以，但需要说明
        score += 3
        issues.append("未启用库存管理")
    
    # 运费（5分）
    if product.get("shipping_class") or product.get("weight"):
        score += 5
    else:
        issues.append("缺少运费类别或重量")
    
    return score, issues


def assess_content_quality(product: Dict) -> Tuple[float, List[str]]:
    """评估内容质量（25分）"""
    score = 0
    issues = []
    
    # 描述（10分）
    description = product.get("description", "")
    desc_len = len(description)
    if desc_len >= 1000:
        score += 10
    elif desc_len >= 600:
        score += 8
        issues.append(f"描述字数偏少（{desc_len}字符，建议≥1000）")
    elif desc_len >= 300:
        score += 5
        issues.append(f"描述字数不足（{desc_len}字符，建议≥600）")
    elif desc_len > 0:
        score += 2
        issues.append(f"描述字数严重不足（{desc_len}字符）")
    else:
        issues.append("缺少描述")
    
    # 简短描述（5分）
    short_desc = product.get("short_description", "")
    short_len = len(short_desc)
    if 100 <= short_len <= 200:
        score += 5
    elif short_len > 0:
        score += 3
        issues.append(f"简短描述长度不合适（{short_len}字符，建议100-200）")
    else:
        issues.append("缺少简短描述")
    
    # 参数表（5分）
    # 检查描述中是否包含参数表
    if "<table" in description.lower() or "规格" in description or "parameters" in description.lower():
        score += 5
    else:
        issues.append("缺少参数表")
    
    # FAQ（5分）
    if "faq" in description.lower() or "常见问题" in description:
        score += 5
    else:
        issues.append("缺少FAQ")
    
    return score, issues


def assess_images(product: Dict) -> Tuple[float, List[str]]:
    """评估图片质量（20分）"""
    score = 0
    issues = []
    
    images = product.get("images", [])
    img_count = len(images)
    
    # 主图（10分）
    if img_count >= 1:
        main_img = images[0]
        # 检查主图是否有alt和title
        if main_img.get("alt") and main_img.get("title"):
            score += 10
        elif main_img.get("alt"):
            score += 8
            issues.append("主图缺少title")
        else:
            score += 5
            issues.append("主图缺少alt和title")
    else:
        issues.append("缺少主图")
    
    # 补充图（10分）
    if img_count >= 6:
        score += 10
    elif img_count >= 4:
        score += 8
        issues.append(f"图片数量不足（当前{img_count}，建议≥6）")
    elif img_count >= 3:
        score += 5
        issues.append(f"图片数量偏少（当前{img_count}，建议≥4）")
    elif img_count >= 1:
        score += 2
        issues.append(f"图片数量严重不足（当前{img_count}，建议≥3）")
    
    # 检查图片质量（分辨率、清晰度等）
    for img in images[:3]:  # 检查前3张图片
        src = img.get("src", "")
        if "300x300" in src or "200x200" in src:
            issues.append(f"图片分辨率偏低：{img.get('id')}")
            break
    
    return score, issues


def assess_seo(product: Dict) -> Tuple[float, List[str]]:
    """评估SEO优化（20分）"""
    score = 0
    issues = []
    
    # SEO Title（5分）
    # 检查是否有自定义SEO Title（通过元数据）
    seo_title = product.get("_yoast_wpseo_title", "")
    if seo_title:
        score += 5
    else:
        issues.append("缺少SEO Title")
    
    # Meta Description（5分）
    meta_desc = product.get("_yoast_wpseo_metadesc", "")
    if meta_desc and 120 <= len(meta_desc) <= 160:
        score += 5
    elif meta_desc:
        score += 3
        issues.append(f"Meta Description长度不合适（{len(meta_desc)}字符，建议120-160）")
    else:
        issues.append("缺少Meta Description")
    
    # Focus Keyword（5分）
    focus_kw = product.get("_yoast_wpseo_focuskw", "")
    if focus_kw:
        score += 5
    else:
        issues.append("缺少Focus Keyword")
    
    # robots（5分）
    robots = product.get("_yoast_wpseo_meta-robots-noindex", "0")
    if robots == "0":
        score += 5
    else:
        issues.append("noindex已启用，应关闭")
    
    return score, issues


def assess_product(product_id: int) -> Dict:
    """评估产品质量"""
    product = get_wc_product(product_id)
    
    total_score = 0
    all_issues = []
    
    # 基础信息（20分）
    score, issues = assess_basic_info(product)
    total_score += score
    all_issues.extend([f"[基础信息] {i}" for i in issues])
    
    # 价格与库存（15分）
    score, issues = assess_price_inventory(product)
    total_score += score
    all_issues.extend([f"[价格库存] {i}" for i in issues])
    
    # 内容质量（25分）
    score, issues = assess_content_quality(product)
    total_score += score
    all_issues.extend([f"[内容质量] {i}" for i in issues])
    
    # 图片质量（20分）
    score, issues = assess_images(product)
    total_score += score
    all_issues.extend([f"[图片质量] {i}" for i in issues])
    
    # SEO优化（20分）
    score, issues = assess_seo(product)
    total_score += score
    all_issues.extend([f"[SEO优化] {i}" for i in issues])
    
    return {
        "product_id": product_id,
        "product_name": product.get("name", ""),
        "sku": product.get("sku", ""),
        "total_score": round(total_score, 1),
        "pass": total_score >= 95,
        "issues": all_issues,
        "suggestions": []  # 需要根据issues生成建议
    }


def generate_suggestions(issues: List[str]) -> List[str]:
    """根据问题生成修复建议"""
    suggestions = []
    
    for issue in issues:
        if "状态为draft" in issue:
            suggestions.append("将产品状态从draft改为publish")
        elif "缺少分类" in issue:
            suggestions.append("添加产品分类（如Outdoor, Camping等）")
        elif "缺少标签" in issue or "标签数量不足" in issue:
            suggestions.append("添加5-10个相关标签（如folding table, camping table等）")
        elif "缺少描述" in issue or "描述字数" in issue:
            suggestions.append("添加或扩展产品描述（建议≥1000字符）")
        elif "缺少简短描述" in issue or "简短描述长度" in issue:
            suggestions.append("添加简短描述（100-200字符）")
        elif "缺少参数表" in issue:
            suggestions.append("在描述中添加参数表（规格、尺寸、材质等）")
        elif "缺少FAQ" in issue:
            suggestions.append("在描述中添加FAQ部分（3-5个常见问题）")
        elif "缺少主图" in issue or "图片数量" in issue:
            suggestions.append("上传商品图片（建议6张以上，包含主图、细节图、场景图）")
        elif "缺少SEO Title" in issue:
            suggestions.append("配置SEO Title（包含核心关键词）")
        elif "缺少Meta Description" in issue or "Meta Description长度" in issue:
            suggestions.append("配置Meta Description（120-160字符）")
        elif "缺少Focus Keyword" in issue:
            suggestions.append("配置Focus Keyword（核心关键词）")
        elif "noindex已启用" in issue:
            suggestions.append("关闭noindex，启用index和follow")
        elif "缺少运费类别" in issue or "缺少重量" in issue:
            suggestions.append("配置运费类别和重量")
        elif "库存" in issue:
            suggestions.append("配置库存数量和状态")
    
    return suggestions


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python wc_quality_assessment.py <product_id>")
        print("示例: python wc_quality_assessment.py 2378")
        sys.exit(1)
    
    product_id = int(sys.argv[1])
    
    print(f"Assessing WC product {product_id}...")
    print("-" * 50)
    
    result = assess_product(product_id)
    
    # 生成修复建议
    result["suggestions"] = generate_suggestions(result["issues"])
    
    # 输出结果
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 退出码：0=通过，1=未通过
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
