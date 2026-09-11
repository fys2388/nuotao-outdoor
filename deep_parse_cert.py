#!/usr/bin/env python3
"""用 cryptography 库详细解析证书，检查 SAN 扩展的原始结构"""

import ssl
import socket
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID, ExtensionOID

SERVER_IP = '95.217.218.178'
DOMAIN = 'admin.nuotaoutdoor.com'

print("="*60)
print("详细证书解析")
print("="*60)

# 1. 从服务器获取证书
print("\n[1] 从服务器获取证书...")
try:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    
    with socket.create_connection((SERVER_IP, 443), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname=DOMAIN) as ssock:
            cert_bin = ssock.getpeercert(binary_form=True)
            cert = x509.load_der_x509_certificate(cert_bin, default_backend())
            print(f"  证书长度: {len(cert_bin)} 字节")
            print(f"  序列号: {cert.serial_number}")
            print(f"  签名算法: {cert.signature_algorithm_oid}")
except Exception as e:
    print(f"  错误: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# 2. 检查主题
print("\n[2] 检查主题...")
print(f"  主题: {cert.subject}")
for attr in cert.subject:
    print(f"    {attr.oid}: '{attr.value}' (类型: {type(attr.value).__name__}, 长度: {len(attr.value)})")
    if hasattr(attr.value, 'encode'):
        print(f"      十六进制: {attr.value.encode('utf-8').hex()}")
        print(f"      字节: {[hex(b) for b in attr.value.encode('utf-8')]}")

# 3. 检查颁发者
print("\n[3] 检查颁发者...")
print(f"  颁发者: {cert.issuer}")

# 4. 检查有效期
print("\n[4] 检查有效期...")
print(f"  生效: {cert.not_valid_before_utc}")
print(f"  过期: {cert.not_valid_after_utc}")

# 5. 检查所有扩展
print("\n[5] 检查所有扩展...")
for ext in cert.extensions:
    print(f"\n  扩展: {ext.oid}")
    print(f"    Critical: {ext.critical}")
    print(f"    类型: {type(ext.value).__name__}")
    
    # 特别检查 SAN 扩展
    if ext.oid == ExtensionOID.SUBJECT_ALTERNATIVE_NAME:
        print(f"    SAN 详细内容:")
        for general_name in ext.value:
            print(f"      类型: {type(general_name).__name__}")
            print(f"      值: '{general_name.value}'")
            if hasattr(general_name.value, 'encode'):
                print(f"      十六进制: {general_name.value.encode('utf-8').hex()}")
                print(f"      长度: {len(general_name.value)}")
    
    # 检查基本约束
    if ext.oid == ExtensionOID.BASIC_CONSTRAINTS:
        print(f"    CA: {ext.value.ca}")
        print(f"    Path Length: {ext.value.path_length}")
    
    # 检查密钥用法
    if ext.oid == ExtensionOID.KEY_USAGE:
        print(f"    Digital Signature: {ext.value.digital_signature}")
        print(f"    Key Encipherment: {ext.value.key_encipherment}")

# 6. 手动检查主机名匹配
print("\n[6] 手动检查主机名匹配...")
print(f"  目标主机名: '{DOMAIN}'")
print(f"  目标主机名长度: {len(DOMAIN)}")
print(f"  目标主机名十六进制: {DOMAIN.encode('utf-8').hex()}")

# 检查 CN
cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
if cn_attrs:
    cn = cn_attrs[0].value
    print(f"\n  CN: '{cn}'")
    print(f"  CN 长度: {len(cn)}")
    print(f"  CN 十六进制: {cn.encode('utf-8').hex()}")
    print(f"  CN == 目标: {cn == DOMAIN}")
    print(f"  CN 小写 == 目标小写: {cn.lower() == DOMAIN.lower()}")

# 检查 SAN
try:
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    dns_names = san.value.get_values_for_type(x509.DNSName)
    print(f"\n  SAN DNS 名称:")
    for name in dns_names:
        print(f"    '{name}'")
        print(f"    长度: {len(name)}")
        print(f"    十六进制: {name.encode('utf-8').hex()}")
        print(f"    == 目标: {name == DOMAIN}")
        print(f"    小写 == 目标小写: {name.lower() == DOMAIN.lower()}")
        print(f"    字节比较: {name.encode('utf-8') == DOMAIN.encode('utf-8')}")
except Exception as e:
    print(f"  无 SAN: {e}")

# 7. 检查证书的原始字节
print("\n[7] 检查证书的原始字节（SAN 相关）...")
cert_hex = cert_bin.hex()
# 查找 admin 的十六进制
admin_hex = '61646d696e'
positions = []
start = 0
while True:
    pos = cert_hex.find(admin_hex, start)
    if pos == -1:
        break
    positions.append(pos)
    start = pos + 1

print(f"  找到 'admin' 在位置: {positions}")
for pos in positions:
    # 显示周围的字节
    start_byte = max(0, pos // 2 - 5)
    end_byte = min(len(cert_bin), pos // 2 + 30)
    surrounding = cert_bin[start_byte:end_byte]
    print(f"  位置 {pos} (字节 {pos//2}):")
    print(f"    十六进制: {surrounding.hex()}")
    try:
        print(f"    文本: {surrounding.decode('utf-8', errors='replace')}")
    except:
        pass

# 8. 用 ssl 模块的 dict 格式检查
print("\n[8] 用 ssl 模块的 dict 格式检查...")
cert_dict = ssock.getpeercert()
print(f"  证书 dict: {cert_dict}")
if 'subject' in cert_dict:
    print(f"  主题: {cert_dict['subject']}")
if 'subjectAltName' in cert_dict:
    print(f"  SAN: {cert_dict['subjectAltName']}")

print("\n" + "="*60)
print("检查完成")
print("="*60)
