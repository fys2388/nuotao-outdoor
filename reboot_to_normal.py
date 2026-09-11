import requests
import os
import time

# 禁用代理
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

# Hetzner API配置
API_TOKEN = "xd2lNU9GevqmRc6y4JItkpEeJOLCzdhq859cxgAWV97optuzZ1OZ6vt7w3W2682S"
SERVER_ID = "164324723"
BASE_URL = "https://api.hetzner.cloud/v1"

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

proxies = {
    "http": None,
    "https": None
}

# 禁用Rescue环境（这样重启后会从本地磁盘启动）
print("1. 禁用Rescue环境...")
try:
    response = requests.post(
        f"{BASE_URL}/servers/{SERVER_ID}/actions/disable_rescue",
        headers=headers,
        timeout=30,
        proxies=proxies
    )
    print(f"状态码: {response.status_code}")
    if response.status_code in [200, 201]:
        data = response.json()
        action = data.get("action", {})
        print(f"操作ID: {action.get('id')}")
        print(f"操作状态: {action.get('status')}")
        print("Rescue环境已禁用")
    else:
        print(f"响应: {response.text}")
except Exception as e:
    print(f"请求失败: {e}")

# 重启服务器
print("\n2. 重启服务器...")
try:
    response = requests.post(
        f"{BASE_URL}/servers/{SERVER_ID}/actions/reboot",
        headers=headers,
        timeout=30,
        proxies=proxies
    )
    print(f"状态码: {response.status_code}")
    if response.status_code in [200, 201]:
        data = response.json()
        action = data.get("action", {})
        print(f"操作ID: {action.get('id')}")
        print(f"操作状态: {action.get('status')}")
        print("服务器正在重启...")
    else:
        print(f"响应: {response.text}")
except Exception as e:
    print(f"请求失败: {e}")

print("\n等待服务器重启完成（90秒）...")
