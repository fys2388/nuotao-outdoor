#!/usr/bin/env python3
"""详细调试1688 API调用"""
import sys
import os
sys.path.insert(0, '/opt/nuotao/backend')

# 手动加载.env文件
env_path = '/opt/nuotao/backend/.env'
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

import hashlib
from datetime import datetime
import requests

# 配置
APP_KEY = os.getenv("ALIBABA_APP_KEY", "")
APP_SECRET = os.getenv("ALIBABA_APP_SECRET", "")
ACCESS_TOKEN = os.getenv("ALIBABA_ACCESS_TOKEN", "")
BASE_URL = "https://gw.open.1688.com/openapi"

print(f"APP_KEY: {APP_KEY[:6]}..." if APP_KEY else "APP_KEY: EMPTY")
print(f"APP_SECRET: {'configured' if APP_SECRET else 'EMPTY'}")
print(f"ACCESS_TOKEN: {ACCESS_TOKEN[:8]}..." if ACCESS_TOKEN else "ACCESS_TOKEN: EMPTY")

def sign(params, secret):
    """1688 API 签名"""
    sorted_params = sorted(params.items())
    sign_str = secret + "".join(f"{k}{v}" for k, v in sorted_params) + secret
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()

# 测试1: alibaba.product.get
print("\n=== 测试1: alibaba.product.get ===")
method = "alibaba.product.get"
params = {
    "method": method,
    "app_key": APP_KEY,
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "format": "json",
    "v": "2.0",
    "sign_method": "md5",
    "access_token": ACCESS_TOKEN,
    "productId": "1072048377637",
}
params["sign"] = sign(params, APP_SECRET)

print(f"Params: {list(params.keys())}")
print(f"Sign: {params['sign'][:8]}...")

url = f"{BASE_URL}/param2/1/{method}/{APP_KEY}"
print(f"URL: {url}")

try:
    resp = requests.post(url, data=params, timeout=30)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# 测试2: 尝试GET请求
print("\n=== 测试2: GET请求 ===")
try:
    resp = requests.get(url, params=params, timeout=30)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# 测试3: 不带access_token
print("\n=== 测试3: 不带access_token ===")
params2 = {k: v for k, v in params.items() if k != "access_token"}
params2["sign"] = sign(params2, APP_SECRET)
try:
    resp = requests.post(url, data=params2, timeout=30)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
