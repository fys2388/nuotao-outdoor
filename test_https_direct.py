#!/usr/bin/env python3
"""测试 admin.nuotaoutdoor.com HTTPS 连接（禁用代理，直连IP）"""

import requests
import urllib3
import ssl
import socket

urllib3.disable_warnings()

# 禁用代理
proxies = {
    'http': None,
    'https': None,
}

SERVER_IP = '95.217.218.178'
DOMAIN = 'admin.nuotaoutdoor.com'

print("="*60)
print("测试 admin.nuotaoutdoor.com HTTPS 连接（直连IP）")
print(f"服务器IP: {SERVER_IP}")
print(f"域名: {DOMAIN}")
print("="*60)

# 1. 测试 HTTPS 连接（跳过证书验证，直连IP）
print("\n[1] 测试 HTTPS 连接（跳过证书验证，直连IP）...")
try:
    # 使用自定义 Host 头
    headers = {'Host': DOMAIN}
    r = requests.get(f'https://{SERVER_IP}', verify=False, timeout=15, proxies=proxies, headers=headers)
    print(f"  状态码: {r.status_code}")
    title_start = r.text.find('<title>')
    title_end = r.text.find('</title>')
    if title_start != -1 and title_end != -1:
        print(f"  页面标题: {r.text[title_start+7:title_end]}")
    print(f"  内容长度: {len(r.text)} 字节")
except Exception as e:
    print(f"  错误: {e}")

# 2. 检查证书详情（直连IP，设置 server_hostname）
print("\n[2] 检查 SSL 证书详情（直连IP）...")
try:
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    
    with socket.create_connection((SERVER_IP, 443), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname=DOMAIN) as ssock:
            cert = ssock.getpeercert()
            print(f"  证书验证: 成功！")
            print(f"  主题: {cert.get('subject', 'N/A')}")
            print(f"  颁发者: {cert.get('issuer', 'N/A')}")
            print(f"  有效期从: {cert.get('notBefore', 'N/A')}")
            print(f"  有效期到: {cert.get('notAfter', 'N/A')}")
            print(f"  主题备用名称: {cert.get('subjectAltName', 'N/A')}")
except ssl.SSLCertVerificationError as e:
    print(f"  证书验证错误: {e}")
except Exception as e:
    print(f"  错误: {e}")

# 3. 检查证书详情（不验证主机名）
print("\n[3] 检查 SSL 证书详情（不验证主机名）...")
try:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    
    with socket.create_connection((SERVER_IP, 443), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname=DOMAIN) as ssock:
            cert = ssock.getpeercert()
            print(f"  主题: {cert.get('subject', 'N/A')}")
            print(f"  颁发者: {cert.get('issuer', 'N/A')}")
            print(f"  有效期从: {cert.get('notBefore', 'N/A')}")
            print(f"  有效期到: {cert.get('notAfter', 'N/A')}")
            print(f"  主题备用名称: {cert.get('subjectAltName', 'N/A')}")
except Exception as e:
    print(f"  错误: {e}")

# 4. 测试健康检查 API
print("\n[4] 测试健康检查 API...")
try:
    headers = {'Host': DOMAIN}
    r = requests.get(f'https://{SERVER_IP}/api/v1/healthz', verify=False, timeout=15, proxies=proxies, headers=headers)
    print(f"  状态码: {r.status_code}")
    print(f"  响应: {r.text[:200]}")
except Exception as e:
    print(f"  错误: {e}")

# 5. 检查本地 DNS 解析
print("\n[5] 检查本地 DNS 解析...")
try:
    import subprocess
    result = subprocess.run(['ping', '-n', '1', DOMAIN], capture_output=True, text=True, timeout=10)
    print(f"  ping 输出: {result.stdout[:300]}")
except Exception as e:
    print(f"  错误: {e}")

# 6. 检查 hosts 文件
print("\n[6] 检查 hosts 文件...")
try:
    with open(r'C:\Windows\System32\drivers\etc\hosts', 'r', encoding='utf-8') as f:
        for line in f:
            if DOMAIN in line or 'nuotao' in line.lower():
                print(f"  {line.strip()}")
except Exception as e:
    print(f"  错误: {e}")

print("\n" + "="*60)
print("测试完成")
print("="*60)
