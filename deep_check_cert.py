#!/usr/bin/env python3
"""从 s_client 获取证书并深入检查 SAN 扩展"""

import paramiko
import sys

HOST = "95.217.218.178"
PORT = 22
USERNAME = "root"
KEY_PATH = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

def run_command(ssh, command, timeout=60):
    print(f"\n{'='*60}")
    print(f"执行: {command[:120]}")
    print(f"{'='*60}")
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout, get_pty=True)
    exit_status = stdout.channel.recv_exit_status()
    output = stdout.read().decode('utf-8', errors='replace')
    error = stderr.read().decode('utf-8', errors='replace')
    if output:
        print(output[-4000:] if len(output) > 4000 else output)
    if error:
        print(f"STDERR: {error[-1000:]}")
    print(f"\n退出: {exit_status}")
    return exit_status, output, error

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        private_key = paramiko.Ed25519Key.from_private_key_file(KEY_PATH)
        ssh.connect(HOST, port=PORT, username=USERNAME, pkey=private_key, timeout=30, allow_agent=False, look_for_keys=False)
        print("连接成功！")
        
        # 1. 从 s_client 获取证书并保存
        print("\n[1] 从 s_client 获取证书...")
        run_command(ssh, """
        echo '=== 获取证书并保存 ==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -outform PEM > /tmp/current_cert.pem
        ls -la /tmp/current_cert.pem
        
        echo ''
        echo '=== 证书详情 ==='
        openssl x509 -in /tmp/current_cert.pem -noout -text 2>&1 | head -80
        """)
        
        # 2. 检查 SAN 扩展的原始字节
        print("\n[2] 检查 SAN 扩展的原始字节...")
        run_command(ssh, """
        echo '=== SAN 扩展 ==='
        openssl x509 -in /tmp/current_cert.pem -noout -ext subjectAltName 2>&1
        
        echo ''
        echo '=== 证书的 ASN.1 结构（SAN 部分）==='
        openssl asn1parse -in /tmp/current_cert.pem 2>&1 | grep -A10 -B5 'Subject Alternative Name'
        
        echo ''
        echo '=== 证书的完整 ASN.1 结构 ==='
        openssl asn1parse -in /tmp/current_cert.pem 2>&1
        """)
        
        # 3. 检查证书 CN 的原始字节
        print("\n[3] 检查证书 CN 的原始字节...")
        run_command(ssh, """
        echo '=== 证书主题 ==='
        openssl x509 -in /tmp/current_cert.pem -noout -subject -nameopt multiline,show_type,utf8 2>&1
        
        echo ''
        echo '=== 证书主题的 ASN.1 ==='
        openssl asn1parse -in /tmp/current_cert.pem -strparse 4 2>&1 | head -30
        
        echo ''
        echo '=== 证书的原始十六进制（前500字节）==='
        openssl x509 -in /tmp/current_cert.pem -outform DER 2>/dev/null | xxd | head -40
        """)
        
        # 4. 检查是否有其他证书文件
        print("\n[4] 检查所有证书文件...")
        run_command(ssh, """
        echo '=== /etc/letsencrypt/ 目录结构 ==='
        find /etc/letsencrypt -type f -name "*.pem" 2>/dev/null
        
        echo ''
        echo '=== /etc/nginx/ssl/ 目录 ==='
        ls -la /etc/nginx/ssl/ 2>/dev/null || echo '不存在'
        
        echo ''
        echo '=== 查找所有 nginx 配置中的证书引用 ==='
        grep -rn 'ssl_certificate' /etc/nginx/ 2>/dev/null
        
        echo ''
        echo '=== Nginx 进程打开的文件 ==='
        ls -la /proc/$(cat /run/nginx.pid)/fd/ 2>/dev/null | grep -i -E 'pem|cert|letsencrypt|ssl' || echo '未找到证书文件描述符'
        """)
        
        # 5. 检查 certbot 日志
        print("\n[5] 检查 certbot 日志...")
        run_command(ssh, """
        echo '=== certbot 日志（最后50行）==='
        tail -50 /var/log/letsencrypt/letsencrypt.log 2>/dev/null
        
        echo ''
        echo '=== certbot 续期配置 ==='
        ls -la /etc/letsencrypt/renewal/ 2>/dev/null
        cat /etc/letsencrypt/renewal/*.conf 2>/dev/null
        """)
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
