#!/usr/bin/env python3
"""用 openssl 验证证书主机名，并检查证书的原始 ASN.1 结构"""

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
        print(output[-3000:] if len(output) > 3000 else output)
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
        
        # 1. 用 openssl s_client -verify_hostname 验证
        print("\n[1] openssl s_client -verify_hostname 验证...")
        run_command(ssh, """
        echo '=== 验证主机名 admin.nuotaoutdoor.com ==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com -verify_hostname admin.nuotaoutdoor.com 2>&1 | tail -30
        
        echo ''
        echo '=== 验证主机名 www.example.com（应该失败）==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com -verify_hostname www.example.com 2>&1 | tail -10
        """)
        
        # 2. 检查证书的原始 ASN.1 结构（特别是 SAN 扩展）
        print("\n[2] 检查证书 ASN.1 结构...")
        run_command(ssh, """
        echo '=== 证书的 ASN.1 结构（SAN 部分）==='
        openssl asn1parse -in /etc/letsencrypt/live/admin.nuotaoutdoor.com/cert.pem 2>&1 | grep -A5 -B5 'Subject Alternative Name'
        
        echo ''
        echo '=== 证书的完整 ASN.1 结构（前100行）==='
        openssl asn1parse -in /etc/letsencrypt/live/admin.nuotaoutdoor.com/cert.pem 2>&1 | head -100
        """)
        
        # 3. 检查证书的 SAN 扩展的原始十六进制
        print("\n[3] 检查 SAN 扩展的原始十六进制...")
        run_command(ssh, """
        echo '=== 提取 SAN 扩展 ==='
        openssl x509 -in /etc/letsencrypt/live/admin.nuotaoutdoor.com/cert.pem -noout -ext subjectAltName 2>&1
        
        echo ''
        echo '=== 证书的原始十六进制（SAN 相关）==='
        openssl x509 -in /etc/letsencrypt/live/admin.nuotaoutdoor.com/cert.pem -outform DER 2>/dev/null | xxd | grep -A2 -B2 '61646d696e' || echo '未找到'
        
        echo ''
        echo '=== 证书 CN 的原始字节 ==='
        openssl x509 -in /etc/letsencrypt/live/admin.nuotaoutdoor.com/cert.pem -noout -subject -nameopt multiline,show_type 2>&1
        """)
        
        # 4. 检查证书链
        print("\n[4] 检查证书链...")
        run_command(ssh, """
        echo '=== fullchain.pem 中的证书数量 ==='
        grep -c 'BEGIN CERTIFICATE' /etc/letsencrypt/live/admin.nuotaoutdoor.com/fullchain.pem
        
        echo ''
        echo '=== fullchain.pem 中的每个证书 ==='
        i=0
        while read -r line; do
            if [[ "$line" == *"BEGIN CERTIFICATE"* ]]; then
                echo "--- 证书 $i ---"
                i=$((i+1))
            fi
        done < /etc/letsencrypt/live/admin.nuotaoutdoor.com/fullchain.pem
        
        echo ''
        echo '=== 验证证书链 ==='
        openssl verify -CAfile /etc/letsencrypt/live/admin.nuotaoutdoor.com/chain.pem /etc/letsencrypt/live/admin.nuotaoutdoor.com/cert.pem 2>&1
        
        echo ''
        echo '=== 中间证书详情 ==='
        openssl x509 -in /etc/letsencrypt/live/admin.nuotaoutdoor.com/chain.pem -noout -subject -issuer -dates 2>&1
        """)
        
        # 5. 检查 Nginx 是否真的在使用这个证书
        print("\n[5] 检查 Nginx 使用的证书...")
        run_command(ssh, """
        echo '=== Nginx 配置中的证书路径 ==='
        grep -rn 'ssl_certificate' /etc/nginx/sites-enabled/ 2>/dev/null
        
        echo ''
        echo '=== 证书文件是否存在 ==='
        ls -la /etc/letsencrypt/live/admin.nuotaoutdoor.com/fullchain.pem
        ls -la /etc/letsencrypt/live/admin.nuotaoutdoor.com/privkey.pem
        
        echo ''
        echo '=== 符号链接指向 ==='
        readlink -f /etc/letsencrypt/live/admin.nuotaoutdoor.com/fullchain.pem
        readlink -f /etc/letsencrypt/live/admin.nuotaoutdoor.com/privkey.pem
        
        echo ''
        echo '=== 重新加载 Nginx ==='
        nginx -t 2>&1
        systemctl reload nginx 2>&1
        echo 'Nginx reloaded'
        """)
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
