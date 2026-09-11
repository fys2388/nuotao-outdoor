#!/usr/bin/env python3
"""测试1688不同API"""
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

APP_KEY = os.getenv("ALIBABA_APP_KEY", "")
APP_SECRET = os.getenv("ALIBABA_APP_SECRET", "")
ACCESS_TOKEN = os.getenv("ALIBABA_ACCESS_TOKEN", "")
BASE_URL = "https://gw.open.1688.com/openapi"

def sign(params, secret):
    sorted_params = sorted(params.items())
    sign_str = secret + "".join(f"{k}{v}" for k, v in sorted_params) + secret
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()

def test_api(method, extra_params=None):
    """测试API调用"""
    print(f"\n=== 测试: {method} ===")
    params = {
        "method": method,
        "app_key": APP_KEY,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "2.0",
        "sign_method": "md5",
        "access_token": ACCESS_TOKEN,
    }
    if extra_params:
        params.update(extra_params)
    params["sign"] = sign(params, APP_SECRET)

    url = f"{BASE_URL}/param2/1/{method}/{APP_KEY}"
    try:
        resp = requests.post(url, data=params, timeout=30)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:300]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

# 测试不同的API
apis_to_test = [
    ("alibaba.product.search", {"keyword": "头灯", "pageNo": 1, "pageSize": 5}),
    ("alibaba.product.get", {"productId": "1072048377637"}),
    ("com.alibaba.product.search", {"keyword": "头灯", "pageNo": 1, "pageSize": 5}),
    ("com.alibaba.product.get", {"productId": "1072048377637"}),
    ("alibaba.agent.product.search", {"keyword": "头灯"}),
    ("alibaba.newton.product.search", {"keyword": "头灯"}),
]

for method, params in apis_to_test:
    test_api(method, params)
