#!/usr/bin/env python3
"""测试 HTTPS 连接（禁用所有代理）"""

import os
import ssl
import socket
import requests
import urllib3

urllib3.disable_warnings()

# 清除代理环境变量
for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(key, None)

# 设置 NO_PROXY 包含所有地址
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

SERVER_IP = '95.217.218.178'
DOMAIN = 'admin.nuotaoutdoor.com'

print("="*60)
print("测试 HTTPS 连接（禁用代理）")
print(f"服务器IP: {SERVER_IP}")
print(f"域名: {DOMAIN}")
print("="*60)

# 1. 用 requests 测试（验证证书）
print("\n[1] requests 测试（验证证书）...")
try:
    session = requests.Session()
    session.trust_env = False  # 不使用环境变量代理
    r = session.get(f'https://{DOMAIN}', verify=True, timeout=15)
    print(f"  状态码: {r.status_code}")
    print(f"  证书验证: 成功！")
except requests.exceptions.SSLError as e:
    print(f"  SSL 错误: {e}")
except Exception as e:
    print(f"  错误: {e}")

# 2. 用 requests 测试（跳过证书验证）
print("\n[2] requests 测试（跳过证书验证）...")
try:
    session = requests.Session()
    session.trust_env = False
    r = session.get(f'https://{DOMAIN}', verify=False, timeout=15)
    print(f"  状态码: {r.status_code}")
    title_start = r.text.find('<title>')
    title_end = r.text.find('</title>')
    if title_start != -1 and title_end != -1:
        print(f"  页面标题: {r.text[title_start+7:title_end]}")
except Exception as e:
    print(f"  错误: {e}")

# 3. 用 ssl 模块测试（验证证书）
print("\n[3] ssl 模块测试（验证证书）...")
try:
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    
    with socket.create_connection((SERVER_IP, 443), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname=DOMAIN) as ssock:
            cert = ssock.getpeercert()
            print(f"  证书验证: 成功！")
            print(f"  主题: {cert.get('subject', 'N/A')}")
            print(f"  有效期到: {cert.get('notAfter', 'N/A')}")
except ssl.SSLCertVerificationError as e:
    print(f"  证书验证错误: {e}")
    print(f"  错误码: {e.verify_code}")
    print(f"  错误信息: {e.verify_message}")
except Exception as e:
    print(f"  错误: {e}")

# 4. 用 ssl 模块测试（不验证证书，获取详情）
print("\n[4] ssl 模块测试（不验证证书，获取详情）...")
try:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    
    with socket.create_connection((SERVER_IP, 443), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname=DOMAIN) as ssock:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            
            cert_bin = ssock.getpeercert(binary_form=True)
            cert = x509.load_der_x509_certificate(cert_bin, default_backend())
            
            print(f"  主题: {cert.subject}")
            print(f"  颁发者: {cert.issuer}")
            print(f"  有效期: {cert.not_valid_before_utc} 到 {cert.not_valid_after_utc}")
            
            try:
                san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                print(f"  SAN: {san.value.get_values_for_type(x509.DNSName)}")
            except:
                print("  无 SAN")
                
            # 检查主机名匹配
            print(f"\n  主机名匹配检查:")
            print(f"    连接主机名: {DOMAIN}")
            print(f"    证书 CN: {cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value if cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME) else 'N/A'}")
except Exception as e:
    print(f"  错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("测试完成")
print("="*60)
