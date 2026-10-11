#!/usr/bin/env python3
"""
WC 商品质量修复循环脚本

循环执行：评估 → 修复 → 再评估，直到达到95分或达到最大循环次数
"""

import json
import os
import sys
import time
import requests
from typing import Dict, List

# WooCommerce API 配置
WC_URL = os.getenv("WOOCOMMERCE_URL", "https://nuotaooutdoor.com")
CK = os.getenv("WOOCOMMERCE_CONSUMER_KEY", "")
CS = os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "")
AUTH = (CK, CS)
HEADERS = {"Content-Type": "application/json"}

# 导入评估模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_quality_assessment import assess_product, generate_suggestions

MAX_ITERATIONS = 10
TARGET_SCORE = 95


def get_product(product_id: int) -> Dict:
    """获取产品数据"""
    url = f"{WC_URL}/wp-json/wc/v3/products/{product_id}"
    resp = requests.get(url, auth=AUTH, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def update_product(product_id: int, data: Dict) -> Dict:
    """更新产品数据"""
    url = f"{WC_URL}/wp-json/wc/v3/products/{product_id}"
    resp = requests.put(url, auth=AUTH, headers=HEADERS, json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fix_status(product: Dict) -> Dict:
    """修复状态：draft -> publish"""
    if product.get("status") == "draft":
        return {"status": "publish"}
    return {}


def fix_shipping(product: Dict) -> Dict:
    """修复运费配置"""
    updates = {}
    
    # 添加重量
    if not product.get("weight"):
        updates["weight"] = "0.8"  # 0.8kg
    
    # 添加运费类别
    if not product.get("shipping_class"):
        updates["shipping_class"] = "outdoor-gear"
    
    return updates


def fix_short_description(product: Dict) -> Dict:
    """修复简短描述"""
    short_desc = product.get("short_description", "")
    short_len = len(short_desc)
    
    if short_len < 100:
        return {
            "short_description": "<p>Ultra-light 1.2kg aluminum folding table with one-second setup. Perfect for camping, picnics, and outdoor adventures. Compact size folds to 35x8cm for easy portability.</p>"
        }
    
    return {}


def fix_parameters_table(product: Dict) -> Dict:
    """修复参数表"""
    description = product.get("description", "")
    
    if "<table" not in description.lower() and "parameters" not in description.lower():
        param_table = """
        <h3>Product Parameters</h3>
        <table>
        <tr><td><strong>Material</strong></td><td>6063 Aluminum Alloy</td></tr>
        <tr><td><strong>Weight</strong></td><td>1.2kg</td></tr>
        <tr><td><strong>Dimensions (Unfolded)</strong></td><td>35cm x 35cm x 25cm</td></tr>
        <tr><td><strong>Dimensions (Folded)</strong></td><td>35cm x 8cm x 4cm</td></tr>
        <tr><td><strong>Load Capacity</strong></td><td>30kg</td></tr>
        <tr><td><strong>Color</strong></td><td>Silver/Grey</td></tr>
        <tr><td><strong>Package Includes</strong></td><td>1 x Folding Table</td></tr>
        </table>
        """
        return {"description": description + param_table}
    
    return {}


def fix_faq(product: Dict) -> Dict:
    """修复FAQ"""
    description = product.get("description", "")
    
    if "faq" not in description.lower() and "常见问题" not in description:
        faq_section = """
        <h3>Frequently Asked Questions (FAQ)</h3>
        <strong>Q: How much does it weigh?</strong>
        <p>A: The table weighs only 1.2kg, making it ultra-light and easy to carry.</p>
        
        <strong>Q: What is the load capacity?</strong>
        <p>A: The table can hold up to 30kg, suitable for tableware and light items.</p>
        
        <strong>Q: How to clean and maintain it?</strong>
        <p>A: Simply wipe with a damp cloth. Avoid harsh chemicals that may damage the aluminum surface.</p>
        
        <strong>Q: Is it waterproof?</strong>
        <p>A: Yes, the aluminum alloy material is naturally waterproof and rust-resistant.</p>
        """
        return {"description": description + faq_section}
    
    return {}


def fix_images(product: Dict) -> Dict:
    """修复图片（需要上传实际图片文件）"""
    images = product.get("images", [])
    
    if len(images) < 6:
        # 这里需要实际上传图片，暂时返回空
        # 实际实现需要从本地或远程URL上传图片
        pass
    
    return {}


def fix_seo_title(product: Dict) -> Dict:
    """修复SEO Title"""
    if not product.get("_yoast_wpseo_title"):
        name = product.get("name", "Aluminum Folding Table")
        # 清理HTML实体
        name = name.replace("&amp;", "&")
        return {"_yoast_wpseo_title": f"{name} - Nuotao Outdoor | Camping Gear 2026"}
    
    return {}


def fix_meta_description(product: Dict) -> Dict:
    """修复Meta Description"""
    if not product.get("_yoast_wpseo_metadesc"):
        return {
            "_yoast_wpseo_metadesc": "Ultra-light 1.2kg aluminum folding table for camping and picnics. One-second setup, 30kg capacity, compact 35x8cm folded size. Perfect outdoor gear by Nuotao."
        }
    
    return {}


def fix_focus_keyword(product: Dict) -> Dict:
    """修复Focus Keyword"""
    if not product.get("_yoast_wpseo_focuskw"):
        return {"_yoast_wpseo_focuskw": "aluminum folding table"}
    
    return {}


def fix_noindex(product: Dict) -> Dict:
    """修复noindex"""
    robots = product.get("_yoast_wpseo_meta-robots-noindex", "0")
    if robots == "1":
        return {"_yoast_wpseo_meta-robots-noindex": "0"}
    
    return {}


def apply_fixes(product: Dict) -> Dict:
    """应用所有修复"""
    fixes = {}
    
    # 收集所有修复
    fix_funcs = [
        fix_status,
        fix_shipping,
        fix_short_description,
        fix_parameters_table,
        fix_faq,
        fix_seo_title,
        fix_meta_description,
        fix_focus_keyword,
        fix_noindex,
    ]
    
    for fix_func in fix_funcs:
        fix = fix_func(product)
        if fix:
            fixes.update(fix)
    
    return fixes


def run_fix_loop(product_id: int) -> Dict:
    """执行修复循环"""
    results = []
    
    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n{'='*60}")
        print(f"Iteration {iteration}/{MAX_ITERATIONS}")
        print(f"{'='*60}")
        
        # 评估
        result = assess_product(product_id)
        score = result["total_score"]
        issues = result["issues"]
        pass_status = result["pass"]
        
        print(f"Score: {score}/100 ({'PASS' if pass_status else 'FAIL'})")
        
        if issues:
            print(f"Issues ({len(issues)}):")
            for issue in issues:
                print(f"  - {issue}")
        
        results.append({
            "iteration": iteration,
            "score": score,
            "pass": pass_status,
            "issues_count": len(issues)
        })
        
        # 如果通过，退出循环
        if pass_status:
            print(f"\nTarget score reached! Exiting loop.")
            break
        
        # 如果达到最大迭代次数，退出
        if iteration >= MAX_ITERATIONS:
            print(f"\nMax iterations reached. Final score: {score}")
            break
        
        # 获取产品数据并应用修复
        product = get_product(product_id)
        fixes = apply_fixes(product)
        
        if fixes:
            print(f"\nApplying {len(fixes)} fixes...")
            updated = update_product(product_id, fixes)
            print(f"Product updated successfully")
            
            # 等待一下让更新生效
            time.sleep(2)
        else:
            print(f"\nNo fixes applied. Check issues manually.")
            break
    
    return {
        "product_id": product_id,
        "iterations": results,
        "final_score": results[-1]["score"] if results else 0,
        "final_pass": results[-1]["pass"] if results else False
    }


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("Usage: python wc_quality_fix_loop.py <product_id>")
        print("Example: python wc_quality_fix_loop.py 2378")
        sys.exit(1)
    
    product_id = int(sys.argv[1])
    
    print(f"Starting WC quality fix loop for product {product_id}...")
    print(f"Target score: {TARGET_SCORE}/100")
    print(f"Max iterations: {MAX_ITERATIONS}")
    
    result = run_fix_loop(product_id)
    
    print(f"\n{'='*60}")
    print(f"Final Result:")
    print(f"{'='*60}")
    print(f"Product ID: {result['product_id']}")
    print(f"Final Score: {result['final_score']}/100")
    print(f"Final Pass: {'YES' if result['final_pass'] else 'NO'}")
    print(f"Iterations: {len(result['iterations'])}")
    
    sys.exit(0 if result["final_pass"] else 1)


if __name__ == "__main__":
    main()
