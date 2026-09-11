import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

print("=" * 60)
print("Nuotao AI OS 完整功能验证报告")
print("=" * 60)

# 1. 健康检查
print("\n[1] 健康检查")
resp = requests.get(f"{BASE_URL}/../healthz")
print(f"  状态码: {resp.status_code} {'✓' if resp.status_code == 200 else '✗'}")

# 2. 产品列表API
print("\n[2] 产品列表API (P0-3)")
resp = requests.get(f"{BASE_URL}/products?limit=3")
data = resp.json()
print(f"  状态码: {resp.status_code} {'✓' if resp.status_code == 200 else '✗'}")
print(f"  产品数量: {len(data)}")
if data:
    p = data[0]
    print(f"  首个产品: {p['sku']} - {p['name'][:40]}...")
    print(f"  source_url: {p.get('source_url', 'N/A')} {'✓' if p.get('source_url') else '✗ (P0-2)'}")
    print(f"  中文名称: {'✓ 正常' if '?' not in p['name'] else '✗ 编码问题 (P0-1)'}")

# 3. AI文案生成API
print("\n[3] AI文案生成API (P1-2)")
if data:
    pid = data[0]['id']
    resp = requests.post(f"{BASE_URL}/products/{pid}/generate-copy", timeout=60)
    if resp.status_code == 200:
        copy = resp.json()
        print(f"  状态码: {resp.status_code} ✓")
        print(f"  标题: {copy.get('title', 'N/A')[:60]}...")
        print(f"  卖点数量: {len(copy.get('bullet_points', []))}")
        print(f"  SEO关键词: {len(copy.get('seo_keywords', []))}")
        print(f"  模型: {copy.get('_meta', {}).get('model', 'N/A')}")
        print(f"  成本: ${copy.get('_meta', {}).get('cost', 'N/A')}")
    else:
        print(f"  状态码: {resp.status_code} ✗")
        print(f"  错误: {resp.text[:100]}")

# 4. 采购建议API
print("\n[4] 采购建议API (P1-3)")
resp = requests.get(f"{BASE_URL}/products/procurement-suggestions?limit=3")
if resp.status_code == 200:
    data = resp.json()
    print(f"  状态码: {resp.status_code} ✓")
    print(f"  建议数量: {data['summary']['total_products']}")
    print(f"  高优先级: {data['summary']['high_priority']}")
    print(f"  中优先级: {data['summary']['medium_priority']}")
    print(f"  低优先级: {data['summary']['low_priority']}")
    print(f"  建议总数量: {data['summary']['total_units']}件")
    if data['suggestions']:
        s = data['suggestions'][0]
        print(f"  首个建议: {s['sku']} - 优先级:{s['priority']} - 建议:{s['suggested_quantity']}件")
        print(f"  原因: {s['reason']}")
else:
    print(f"  状态码: {resp.status_code} ✗")

# 5. 低库存API
print("\n[5] 低库存API (P2-1)")
resp = requests.get(f"{BASE_URL}/products/low-stock?threshold=50")
print(f"  状态码: {resp.status_code} {'✓' if resp.status_code == 200 else '✗ (待修复)'}")
if resp.status_code == 200:
    data = resp.json()
    print(f"  低库存产品: {data['total_low_stock']}个")

# 6. 库存同步API
print("\n[6] 库存同步API (P2-1)")
resp = requests.post(f"{BASE_URL}/products/sync-inventory", timeout=30)
print(f"  状态码: {resp.status_code} {'✓' if resp.status_code == 200 else '✗'}")

# 7. 批量更新API
print("\n[7] 批量更新API (P2-2)")
resp = requests.post(f"{BASE_URL}/products/batch-update", json={
    "product_ids": [],
    "updates": {"stock": 100}
})
print(f"  状态码: {resp.status_code} {'✓' if resp.status_code == 200 else '✗'}")

print("\n" + "=" * 60)
print("验证完成")
print("=" * 60)
