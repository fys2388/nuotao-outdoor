import requests
import json
import os

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

# 1. 先获取服务器信息，确认API token有效
print("1. 获取服务器信息...")
try:
    response = requests.get(f"{BASE_URL}/servers/{SERVER_ID}", headers=headers, timeout=30, proxies=proxies)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        server = data.get("server", {})
        print(f"服务器名称: {server.get('name')}")
        print(f"服务器状态: {server.get('status')}")
        print(f"服务器IP: {server.get('public_net', {}).get('ipv4', {}).get('ip')}")
        print(f"救援模式: {server.get('rescue_enabled', False)}")
    else:
        print(f"错误: {response.text}")
except Exception as e:
    print(f"请求失败: {e}")

# 2. 启用Rescue环境并获取密码
print("\n2. 启用Rescue环境...")
try:
    payload = {
        "type": "linux64"
    }
    response = requests.post(
        f"{BASE_URL}/servers/{SERVER_ID}/actions/enable_rescue",
        headers=headers,
        json=payload,
        timeout=30,
        proxies=proxies
    )
    print(f"状态码: {response.status_code}")
    if response.status_code == 201:
        data = response.json()
        action = data.get("action", {})
        root_password = data.get("root_password", "")
        print(f"操作ID: {action.get('id')}")
        print(f"操作状态: {action.get('status')}")
        print(f"Root密码: {root_password}")
        
        # 保存密码到文件
        with open(r"E:\AI\nuotao-ai-os\rescue_password.txt", "w") as f:
            f.write(root_password)
        print("密码已保存到 rescue_password.txt")
    else:
        print(f"错误: {response.text}")
except Exception as e:
    print(f"请求失败: {e}")

# 3. 重启服务器
print("\n3. 重启服务器...")
try:
    response = requests.post(
        f"{BASE_URL}/servers/{SERVER_ID}/actions/reboot",
        headers=headers,
        timeout=30,
        proxies=proxies
    )
    print(f"状态码: {response.status_code}")
    if response.status_code == 201:
        data = response.json()
        action = data.get("action", {})
        print(f"操作ID: {action.get('id')}")
        print(f"操作状态: {action.get('status')}")
        print("服务器正在重启...")
    else:
        print(f"错误: {response.text}")
except Exception as e:
    print(f"请求失败: {e}")
