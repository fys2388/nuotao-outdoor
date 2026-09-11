# -*- coding: utf-8 -*-
"""
P5: 营销内容实际部署到WooCommerce
批量更新15个产品的SEO标题/描述/关键词
"""
import sys
import os
import json
import requests

sys.path.insert(0, '.')

WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
WC_KEY = os.environ.get("WOOCOMMERCE_CONSUMER_KEY")
WC_SECRET = os.environ.get("WOOCOMMERCE_CONSUMER_SECRET")
if not WC_KEY or not WC_SECRET:
    print("ERROR: WOOCOMMERCE_CONSUMER_KEY and WOOCOMMERCE_CONSUMER_SECRET environment variables must be set.")
    print("Set them before running this script (do NOT hardcode credentials in source files).")
    sys.exit(1)
WC_AUTH = (WC_KEY, WC_SECRET)

# 读取营销内容
with open("marketing_content_results.json", "r", encoding="utf-8") as f:
    marketing = json.load(f)

seo_contents = {item["sku"]: item["seo"] for item in marketing["seo_content"]}
selling_points = {item["sku"]: item["points"] for item in marketing["selling_points"]}

print("=" * 60)
print("P5: 营销内容部署到WooCommerce")
print("=" * 60)

# 获取当前产品列表
print("\n--- 获取当前WooCommerce产品列表 ---")
resp = requests.get(f"{WC_URL}/products?per_page=100", auth=WC_AUTH, timeout=30)
products = resp.json()
print("  产品总数: {}".format(len(products)))

# SKU到产品ID的映射
sku_to_id = {}
for p in products:
    sku = p.get("sku", "")
    if sku:
        sku_to_id[sku] = p["id"]
print("  有SKU的产品: {} 个".format(len(sku_to_id)))

# 批量更新
print("\n--- 批量更新SEO内容 ---")
success_count = 0
fail_count = 0
results = []

for sku, seo in seo_contents.items():
    if sku not in sku_to_id:
        print("  ⚠️ {}: 产品不存在，跳过".format(sku))
        fail_count += 1
        continue

    product_id = sku_to_id[sku]
    seo_title = seo.get("seo_title", "")
    meta_desc = seo.get("meta_description", "")
    keywords = seo.get("keywords", [])
    paragraphs = seo.get("paragraphs", [])

    # 构建产品描述（用paragraphs或article_outline）
    if isinstance(paragraphs, list) and paragraphs:
        description = "\n\n".join(paragraphs[:5])
    elif isinstance(paragraphs, str):
        description = paragraphs[:2000]
    else:
        description = meta_desc

    # 构建卖点HTML
    sp = selling_points.get(sku, {})
    selling_points_html = ""
    if isinstance(sp, dict):
        points_list = sp.get("selling_points", sp.get("points", []))
        if isinstance(points_list, list) and points_list:
            selling_points_html = "<h3>Key Features</h3><ul>" + "".join(
                "<li>{}</li>".format(str(p)[:100]) for p in points_list[:5]
            ) + "</ul>"

    full_description = description + "\n\n" + selling_points_html

    # 构建更新数据
    update_data = {
        "description": full_description[:3000],
        "meta_data": [
            {"key": "_yoast_wpseo_metadesc", "value": meta_desc[:300]},
            {"key": "_yoast_wpseo_focuskw", "value": ", ".join(keywords[:5]) if isinstance(keywords, list) else str(keywords)},
            {"key": "_yoast_wpseo_title", "value": seo_title[:80]},
        ]
    }

    # 调用API更新
    try:
        resp = requests.put(
            f"{WC_URL}/products/{product_id}",
            json=update_data,
            auth=WC_AUTH,
            timeout=30
        )
        if resp.status_code == 200:
            updated = resp.json()
            print("  ✅ {} (ID={}): SEO标题已更新".format(sku, product_id))
            print("     标题: {}".format(seo_title[:55]))
            print("     Meta描述: {}...".format(meta_desc[:60]))
            success_count += 1
            results.append({"sku": sku, "id": product_id, "status": "success"})
        else:
            print("  ❌ {} (ID={}): HTTP {} - {}".format(sku, product_id, resp.status_code, resp.text[:100]))
            fail_count += 1
            results.append({"sku": sku, "id": product_id, "status": "failed", "error": resp.text[:100]})
    except Exception as e:
        print("  ❌ {} (ID={}): 异常 - {}".format(sku, product_id, str(e)[:100]))
        fail_count += 1
        results.append({"sku": sku, "id": product_id, "status": "error", "error": str(e)[:100]})

# 验证更新
print("\n--- 验证更新结果 ---")
verify_count = 0
for sku in list(seo_contents.keys())[:5]:
    if sku not in sku_to_id:
        continue
    product_id = sku_to_id[sku]
    resp = requests.get(f"{WC_URL}/products/{product_id}", auth=WC_AUTH, timeout=30)
    if resp.status_code == 200:
        p = resp.json()
        desc_len = len(p.get("description", ""))
        meta_count = len(p.get("meta_data", []))
        print("  {} (ID={}): 描述长度={}, meta_data={} 项".format(sku, product_id, desc_len, meta_count))
        if desc_len > 100:
            verify_count += 1

# 最终汇总
print("\n" + "=" * 60)
print("P5 营销内容部署汇总")
print("=" * 60)
print("  待更新产品: {} 个".format(len(seo_contents)))
print("  成功更新: {} 个".format(success_count))
print("  失败: {} 个".format(fail_count))
print("  验证通过: {} / 5 (前5个产品描述长度>100)".format(verify_count))
print()
print("  更新内容:")
print("    - 产品描述: SEO文章段落 + 卖点HTML")
print("    - Meta描述: _yoast_wpseo_metadesc")
print("    - 焦点关键词: _yoast_wpseo_focuskw")
print("    - SEO标题: _yoast_wpseo_title")
print()
print("P5 完成")
