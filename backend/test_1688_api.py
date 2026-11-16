#!/usr/bin/env python3
"""
1688 商品上架脚本 - 通过 Open API 获取数据并创建产品
目标：上架 (加厚充棉三档调节月亮椅) 卡其色/黑色/白色 三款SKU
"""
import os
import sys
import json
import time
import hashlib
import hmac
import requests

# 加载环境变量
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

# 配置
APP_KEY = os.getenv("ALI1688_APP_KEY", "")
APP_SECRET = os.getenv("ALI1688_APP_SECRET", "")
ACCESS_TOKEN = os.getenv("ALI1688_ACCESS_TOKEN", "")
BASE_URL = "https://gw.open.1688.com/openapi"

print("=" * 60)
print("1688 Open API 商品上架")
print("=" * 60)
print(f"APP_KEY: {APP_KEY[:6]}...")
print(f"APP_SECRET: {'configured' if APP_SECRET else 'EMPTY'}")
print(f"ACCESS_TOKEN: {'configured' if ACCESS_TOKEN else 'EMPTY'}")

def sign_api(url_path, params, secret):
    """1688 API 签名"""
    sign_params = {k: v for k, v in params.items() if k != "_aop_signature"}
    sorted_params = sorted(sign_params.items())
    param_str = "".join(f"{k}{v}" for k, v in sorted_params)
    sign_str = url_path + param_str
    return hmac.new(
        secret.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest().upper()

def call_api(method, biz_params):
    """调用 1688 Open API"""
    if not APP_KEY or not APP_SECRET:
        return {"success": False, "error": "API credentials not configured"}
    
    url_path = f"param2/1/com.alibaba.product/{method}/{APP_KEY}"
    params = {
        **biz_params,
        "access_token": ACCESS_TOKEN,
        "_aop_timestamp": str(int(time.time() * 1000)),
    }
    params["_aop_signature"] = sign_api(url_path, params, APP_SECRET)
    
    try:
        response = requests.get(
            f"{BASE_URL}/{url_path}",
            params=params,
            timeout=30,
            proxies={"http": None, "https": None},
        )
        data = response.json()
        
        error_code = data.get("error_code") or data.get("errorCode")
        if response.status_code >= 400 or error_code:
            error_msg = data.get("error_message") or data.get("errorMsg") or f"HTTP {response.status_code}"
            return {"success": False, "error": f"{error_code}: {error_msg}"}
        
        return data
    except Exception as e:
        return {"success": False, "error": str(e)}

# 测试获取商品详情
product_id = "844058953087"
print(f"\n📦 获取商品详情: {product_id}")

# 先尝试 simple.get
result = call_api("simple.get", {"productID": product_id, "webSite": "1688"})
print(f"API调用结果: {json.dumps(result, ensure_ascii=False, indent=2)[:800]}")

if result.get("success") or "productInfo" in result or "product" in result:
    print("\n✅ 成功获取商品数据")
else:
    # 尝试 alibaba.product.get
    print("\n尝试备用接口 alibaba.product.get...")
    result = call_api("alibaba.product.get", {"productID": product_id})
    print(f"API调用结果: {json.dumps(result, ensure_ascii=False, indent=2)[:800]}")

# 输出完整结果
print("\n" + "=" * 60)
print("完整 API 响应:")
print("=" * 60)
print(json.dumps(result, ensure_ascii=False, indent=2))

# 保存结果到文件
output_path = os.path.join(os.path.dirname(__file__), "1688_product_result.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\n💾 结果已保存到: {output_path}")
