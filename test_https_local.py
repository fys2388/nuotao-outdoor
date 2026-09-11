#!/usr/bin/env python3
"""测试HTTPS访问"""
import ssl
import socket
import urllib.request
import certifi

# 测试1：直接连接IP，使用正确的server_hostname
print("="*60)
print("测试1：直接连接IP，使用正确的server_hostname")
print("="*60)

context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

try:
    with socket.create_connection(("95.217.218.178", 443), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname="admin.nuotaoutdoor.com") as ssock:
            # 获取证书
            cert = ssock.getpeercert()
            print(f"证书主题: {cert.get('subject')}")
            print(f"证书SAN: {cert.get('subjectAltName')}")
            print(f"证书有效期: {cert.get('notBefore')} - {cert.get('notAfter')}")
            
            # 发送HTTP请求
            ssock.sendall(b"GET / HTTP/1.1\r\nHost: admin.nuotaoutdoor.com\r\nConnection: close\r\n\r\n")
            response = b""
            while True:
                data = ssock.recv(4096)
                if not data:
                    break
                response += data
            
            # 解析响应
            headers = response.split(b"\r\n\r\n")[0].decode('utf-8', errors='replace')
            status_line = headers.split("\r\n")[0]
            print(f"\nHTTP响应: {status_line}")
            
except Exception as e:
    print(f"错误: {e}")

# 测试2：测试API健康检查
print("\n" + "="*60)
print("测试2：测试API健康检查")
print("="*60)

try:
    with socket.create_connection(("95.217.218.178", 443), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname="admin.nuotaoutdoor.com") as ssock:
            ssock.sendall(b"GET /api/v1/healthz HTTP/1.1\r\nHost: admin.nuotaoutdoor.com\r\nConnection: close\r\n\r\n")
            response = b""
            while True:
                data = ssock.recv(4096)
                if not data:
                    break
                response += data
            
            headers_end = response.find(b"\r\n\r\n")
            if headers_end > 0:
                headers = response[:headers_end].decode('utf-8', errors='replace')
                body = response[headers_end+4:].decode('utf-8', errors='replace')
                status_line = headers.split("\r\n")[0]
                print(f"HTTP响应: {status_line}")
                print(f"响应体: {body[:500]}")
            else:
                print(f"响应: {response[:500]}")
                
except Exception as e:
    print(f"错误: {e}")

print("\n测试完成！")
