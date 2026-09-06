#!/usr/bin/env python3
"""测试1688 API调用"""
import sys
sys.path.insert(0, '/opt/nuotao/backend')

from app.services.sourcing_1688_service import (
    is_configured, ALI1688_APP_KEY, ALI1688_ACCESS_TOKEN,
    ALI1688_APP_SECRET, get_product_detail, _build_common_params, _sign
)

print(f"AppKey configured: {bool(ALI1688_APP_KEY)}")
print(f"AppSecret configured: {bool(ALI1688_APP_SECRET)}")
print(f"AccessToken configured: {bool(ALI1688_ACCESS_TOKEN)}")
print(f"is_configured: {is_configured()}")

# 测试参数构建
params = _build_common_params("alibaba.product.get")
params["productId"] = "1072048377637"
print(f"\nParams keys: {list(params.keys())}")
print(f"Has access_token: {'access_token' in params}")

# 测试API调用
print("\n=== 调用1688 API ===")
result = get_product_detail("1072048377637")
print(f"Success: {result.get('success')}")
print(f"Source: {result.get('source')}")
print(f"Error: {result.get('error')}")
if result.get('product'):
    p = result['product']
    print(f"\nProduct ID: {p.get('product_id')}")
    print(f"Title: {p.get('subject', 'N/A')[:80]}")
    print(f"Price: {p.get('price', 'N/A')}")
    print(f"Images count: {len(p.get('images', []))}")
    print(f"SKU count: {len(p.get('sku_list', []))}")
