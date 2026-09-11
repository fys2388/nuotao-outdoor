"""测试线上API是否正常工作"""
import requests
import json

# 禁用代理
proxies = {
    'http': None,
    'https': None
}

base_url = "https://admin.nuotaoutdoor.com"

print("=== 测试线上API ===\n")

# 1. 健康检查
print("1. 健康检查 /api/v1/healthz")
try:
    response = requests.get(f"{base_url}/api/v1/healthz", proxies=proxies, timeout=10, verify=False)
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.text}")
    if response.status_code == 200:
        print("   ✓ 健康检查通过")
    else:
        print("   ✗ 健康检查失败")
except Exception as e:
    print(f"   ✗ 请求失败: {e}")

print()

# 2. Dashboard summary
print("2. Dashboard summary /api/v1/dashboard/summary")
try:
    response = requests.get(f"{base_url}/api/v1/dashboard/summary", proxies=proxies, timeout=10, verify=False)
    print(f"   状态码: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   success: {data.get('success')}")
        summary = data.get('summary', {})
        this_month = summary.get('this_month', {})
        print(f"   本月订单数: {this_month.get('orders', {}).get('total_orders')}")
        print(f"   本月收入: ${this_month.get('revenue', {}).get('total_revenue')}")
        print("   ✓ Dashboard summary正常")
    else:
        print(f"   响应: {response.text[:500]}")
        print("   ✗ Dashboard summary失败")
except Exception as e:
    print(f"   ✗ 请求失败: {e}")

print()

# 3. Agent suggestions
print("3. Agent suggestions /api/v1/agent-suggestions?status=pending_approval&limit=2")
try:
    response = requests.get(f"{base_url}/api/v1/agent-suggestions", 
                           params={"status": "pending_approval", "limit": 2},
                           proxies=proxies, timeout=10, verify=False)
    print(f"   状态码: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        items = data.get('items', [])
        print(f"   返回建议数: {len(items)}")
        for item in items:
            print(f"   - ID: {item.get('id')}, Agent: {item.get('agent_id')}, 标题: {item.get('title', '')[:50]}")
        print("   ✓ Agent suggestions正常")
    else:
        print(f"   响应: {response.text[:500]}")
        print("   ✗ Agent suggestions失败")
except Exception as e:
    print(f"   ✗ 请求失败: {e}")

print()

# 4. 测试页面加载
print("4. 测试页面加载 /")
try:
    response = requests.get(f"{base_url}/", proxies=proxies, timeout=10, verify=False)
    print(f"   状态码: {response.status_code}")
    print(f"   内容长度: {len(response.content)} 字节")
    if "Nuotao" in response.text or "nuotao" in response.text:
        print("   ✓ 页面包含Nuotao品牌标识")
    if response.status_code == 200:
        print("   ✓ 页面加载正常")
    else:
        print("   ✗ 页面加载失败")
except Exception as e:
    print(f"   ✗ 请求失败: {e}")

print()
print("=== 测试完成 ===")
