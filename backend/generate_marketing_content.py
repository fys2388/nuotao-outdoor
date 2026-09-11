# -*- coding: utf-8 -*-
"""
P1: M3营销内容批量生成
为15个产品生成: SEO内容(标题/meta/关键词) + 卖点 + EDM新品邮件
同时生成 sitemap + robots.txt
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, '.')

from app.services.content_generation_service import (
    generate_seo_content, generate_selling_points, generate_edm_content,
    create_content_item, check_content_quality, get_content_generation_status
)
from app.services.seo_service import (
    generate_product_structured_data, generate_sitemap, generate_robots_txt,
    generate_keyword_strategy, get_seo_status
)
from app.services.edm_automation_service import (
    create_campaign, update_campaign_status, get_edm_automation_status
)

# 15个产品清单
PRODUCTS = [
    {"sku": "NT-SOLAR-LANTERN-100W", "name": "Nuotao LED Camping Lantern - Solar Powered", "category": "lighting", "price": 40.64},
    {"sku": "NT-SLEEP-001", "name": "Premium Outdoor Sleeping Bag - 15°F", "category": "sleeping", "price": 69.99},
    {"sku": "NT-CHAIR-001", "name": "Portable Folding Camping Chair", "category": "furniture", "price": 39.99},
    {"sku": "NT-BAG-001", "name": "50L Hiking Backpack with Rain Cover", "category": "backpacks", "price": 59.99},
    {"sku": "NT-LIGHT-001", "name": "Rechargeable LED Headlamp - 1000 Lumens", "category": "lighting", "price": 24.99},
    {"sku": "NT-COOK-001", "name": "Camping Cookware Set - 10 Pieces", "category": "cooking", "price": 44.99},
    {"sku": "NT-PAD-001", "name": "Inflatable Camping Sleeping Pad", "category": "sleeping", "price": 34.99},
    {"sku": "NT-TENT-002", "name": "Family Camping Tent - 6 Person", "category": "tents", "price": 159.99},
    {"sku": "NT-POLE-001", "name": "Carbon Fiber Trekking Poles - Pair", "category": "hiking", "price": 69.99},
    {"sku": "NT-FILTER-001", "name": "Portable Water Filter Purifier", "category": "safety", "price": 39.99},
    {"sku": "NT-LANTERN-001", "name": "Rechargeable Camping Lantern - 1000LM", "category": "lighting", "price": 34.99},
    {"sku": "NT-SHIRT-001", "name": "UV Protection Outdoor Shirt - UPF 50+", "category": "clothing", "price": 39.99},
    {"sku": "NT-GLOVES-001", "name": "Insulated Outdoor Gloves - Touchscreen", "category": "clothing", "price": 24.99},
    {"sku": "NT-BOOTS-001", "name": "Waterproof Hiking Boots - Mid Ankle", "category": "footwear", "price": 99.99},
    {"sku": "NT-PAD-002", "name": "Inflatable Camping Sleeping Pad - Thick", "category": "sleeping", "price": 44.99},
]

print("=" * 60)
print("P1: M3营销内容批量生成")
print("=" * 60)

# 结果收集
results = {"seo": [], "selling_points": [], "edm": [], "structured_data": []}

# Step 1: 为每个产品生成SEO内容 + 卖点
print("\n--- Step 1: 批量生成SEO内容 + 卖点 (15产品) ---")
for i, p in enumerate(PRODUCTS, 1):
    # SEO内容
    seo = generate_seo_content(
        product_name=p["name"],
        product_category=p["category"],
        keywords=[p["category"], "outdoor", "camping", "hiking"],
        target_audience="outdoor enthusiasts"
    )
    results["seo"].append({"sku": p["sku"], "seo": seo})

    # 卖点
    sp = generate_selling_points(
        product_name=p["name"],
        product_category=p["category"],
        key_features=[],
        target_audience="outdoor enthusiasts",
        price=p["price"]
    )
    results["selling_points"].append({"sku": p["sku"], "points": sp})

    # 结构化数据
    sd = generate_product_structured_data(
        product_name=p["name"],
        product_description="High quality {} for outdoor enthusiasts".format(p["category"]),
        price=p["price"],
        currency="USD",
        product_url="https://nuotaooutdoor.com/product/{}/".format(p["sku"].lower().replace("_", "-")),
        brand="Nuotao Outdoor",
        sku=p["sku"]
    )
    results["structured_data"].append({"sku": p["sku"], "data": sd})

    if i <= 3 or i == 15:
        print("  [{:2d}/15] {} | SEO标题: {}".format(
            i, p["sku"], seo.get("title", seo.get("seo_title", "N/A"))[:50]))

print("  ... (15个产品全部生成)")

# Step 2: 生成EDM新品上架邮件活动
print("\n--- Step 2: EDM新品上架邮件活动 ---")
edm = generate_edm_content(
    email_type="new_arrivals",
    customer_name="Outdoor Enthusiast",
    product_name="15 New Outdoor Gear",
    product_category="camping & hiking",
    discount_percent=15
)
print("  邮件类型: new_arrivals")
print("  主题: {}".format(edm.get("subject", edm.get("title", "N/A"))[:60]))
print("  折扣: 15% off")

# 创建EDM活动
campaign = create_campaign(
    campaign_type="promotional",
    name="New Arrivals - 15 Outdoor Products Launch",
    description="15 new outdoor camping & hiking products launch with 15% off",
    subject=edm.get("subject", "New Outdoor Gear Just Landed - 15% Off"),
    email_content=edm,
    target_audience="all_subscribers",
    discount_percent=15,
    created_by="system"
)
print("  活动创建: id={}, name={}, status={}".format(
    campaign.get('id', campaign.get('campaign_id', 'N/A'))[:8],
    campaign.get('name', 'N/A')[:30],
    campaign.get('status', 'N/A')))

# Step 3: 生成 sitemap 和 robots.txt
print("\n--- Step 3: SEO技术文件 ---")
sitemap = generate_sitemap(
    pages=[{"url": "/", "priority": "1.0"}, {"url": "/about/", "priority": "0.5"}, {"url": "/contact/", "priority": "0.5"}],
    products=[{"url": "/product/{}/".format(p["sku"].lower().replace("_", "-")), "lastmod": "2026-09-03"} for p in PRODUCTS],
    categories=[{"url": "/product-category/camping/"}, {"url": "/product-category/hiking/"}]
)
print("  Sitemap: {} 个URL (XML格式)".format(len(PRODUCTS)+5))

robots = generate_robots_txt(
    sitemap_url="https://nuotaooutdoor.com/sitemap.xml",
    disallow_paths=["/cart/", "/checkout/", "/my-account/", "/wp-admin/"]
)
print("  robots.txt: 已生成 (禁止爬虫访问cart/checkout/admin)")

# Step 4: 关键词策略
print("\n--- Step 4: 关键词策略 ---")
kw = generate_keyword_strategy(
    product_category="outdoor camping gear",
    target_audience="outdoor enthusiasts, campers, hikers",
    location="US"
)
print("  核心关键词数: {}".format(len(kw.get("keywords", kw.get("primary_keywords", [])))))
if kw.get("keywords"):
    for k in kw["keywords"][:5]:
        if isinstance(k, dict):
            print("    - {} (volume:{}, difficulty:{})".format(
                k.get("keyword", k.get("term", "N/A")),
                k.get("search_volume", k.get("volume", "N/A")),
                k.get("difficulty", "N/A")))
        else:
            print("    - {}".format(k))

# Step 5: 内容质量检查
print("\n--- Step 5: 内容质量检查 ---")
quality_scores = []
for r in results["seo"][:5]:
    item = {"title": r["seo"].get("title", ""), "description": r["seo"].get("meta_description", r["seo"].get("description", "")), "content_type": "seo"}
    q = check_content_quality(item)
    quality_scores.append(q.get("score", q.get("overall_score", 0)))
print("  前5个SEO内容质量分: {}".format(quality_scores))
print("  平均分: {:.1f}".format(sum(quality_scores)/len(quality_scores) if quality_scores else 0))

# 保存结果到文件
output = {
    "generated_at": datetime.now().isoformat(),
    "products_count": len(PRODUCTS),
    "seo_content": results["seo"],
    "selling_points": results["selling_points"],
    "edm_campaign": {"name": campaign.get("name"), "status": campaign.get("status"), "content": edm},
    "sitemap_xml": sitemap[:500] + "..." if len(sitemap) > 500 else sitemap,
    "sitemap_url_count": 20,
    "robots_txt": robots,
    "keyword_strategy": kw,
}
with open("marketing_content_results.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# 最终汇总
print("\n" + "=" * 60)
print("P1 M3营销内容生成汇总")
print("=" * 60)
print("  ✅ SEO内容: 15个产品 (标题+meta描述+关键词)")
print("  ✅ 卖点生成: 15个产品")
print("  ✅ 结构化数据: 15个产品 (Product Schema)")
print("  ✅ EDM活动: 新品上架15%折扣 (已创建)")
print("  ✅ Sitemap: 20个URL (XML格式)")
print("  ✅ robots.txt: 已生成")
print("  ✅ 关键词策略: 户外露营装备 niche")
print("  ✅ 内容质量检查: 前5个平均分 {:.1f}".format(sum(quality_scores)/len(quality_scores) if quality_scores else 0))
print()
print("  结果已保存: marketing_content_results.json")
print("P1 完成")
