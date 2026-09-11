#!/usr/bin/env python3
"""测试 admin.nuotaoutdoor.com HTTPS 连接和证书"""

import requests
import urllib3
import ssl
import socket

urllib3.disable_warnings()

print("="*60)
print("测试 admin.nuotaoutdoor.com HTTPS 连接")
print("="*60)

# 1. 测试 HTTPS 连接（跳过证书验证）
print("\n[1] 测试 HTTPS 连接（跳过证书验证）...")
try:
    r = requests.get('https://admin.nuotaoutdoor.com', verify=False, timeout=15)
    print(f"  状态码: {r.status_code}")
    title_start = r.text.find('<title>')
    title_end = r.text.find('</title>')
    if title_start != -1 and title_end != -1:
        print(f"  页面标题: {r.text[title_start+7:title_end]}")
    print(f"  内容长度: {len(r.text)} 字节")
except Exception as e:
    print(f"  错误: {e}")

# 2. 测试 HTTPS 连接（验证证书）
print("\n[2] 测试 HTTPS 连接（验证证书）...")
try:
    r = requests.get('https://admin.nuotaoutdoor.com', verify=True, timeout=15)
    print(f"  状态码: {r.status_code}")
    print(f"  证书验证: 成功！")
except requests.exceptions.SSLError as e:
    print(f"  SSL 错误: {e}")
except Exception as e:
    print(f"  错误: {e}")

# 3. 检查证书详情
print("\n[3] 检查 SSL 证书详情...")
try:
    context = ssl.create_default_context()
    with socket.create_connection(('admin.nuotaoutdoor.com', 443), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname='admin.nuotaoutdoor.com') as ssock:
            cert = ssock.getpeercert()
            print(f"  主题: {cert.get('subject', 'N/A')}")
            print(f"  颁发者: {cert.get('issuer', 'N/A')}")
            print(f"  有效期从: {cert.get('notBefore', 'N/A')}")
            print(f"  有效期到: {cert.get('notAfter', 'N/A')}")
            print(f"  主题备用名称: {cert.get('subjectAltName', 'N/A')}")
except ssl.SSLCertVerificationError as e:
    print(f"  证书验证错误: {e}")
except Exception as e:
    print(f"  错误: {e}")

# 4. 测试健康检查 API
print("\n[4] 测试健康检查 API...")
try:
    r = requests.get('https://admin.nuotaoutdoor.com/api/v1/healthz', verify=False, timeout=15)
    print(f"  状态码: {r.status_code}")
    print(f"  响应: {r.text[:200]}")
except Exception as e:
    print(f"  错误: {e}")

print("\n" + "="*60)
print("测试完成")
print("="*60)
