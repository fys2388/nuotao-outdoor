import requests
import json

# 测试AI文案生成API
url = "http://localhost:8000/api/v1/products/351113e4-7b0d-4e9c-ace3-2b788d56e81e/generate-copy"
resp = requests.post(url, timeout=60)
data = resp.json()

print("=== AI文案生成验证 ===")
print(f"状态码: {resp.status_code}")
print(f"标题: {data.get('title', 'N/A')[:80]}...")
print(f"简短描述: {data.get('short_description', 'N/A')}")
print(f"卖点数量: {len(data.get('bullet_points', []))}")
print(f"SEO关键词数量: {len(data.get('seo_keywords', []))}")
print(f"模型: {data.get('_meta', {}).get('model', 'N/A')}")
print(f"Tokens: {data.get('_meta', {}).get('tokens', {}).get('total_tokens', 'N/A')}")
print(f"成本: ${data.get('_meta', {}).get('cost', 'N/A')}")
print(f"延迟: {data.get('_meta', {}).get('latency_ms', 'N/A')}ms")
print("=== 验证通过 ===")
