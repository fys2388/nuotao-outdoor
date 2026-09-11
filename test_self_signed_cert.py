#!/usr/bin/env python3
"""生成自签名证书测试，确认是证书问题还是Nginx配置问题"""

import paramiko
import sys

HOST = "95.217.218.178"
PORT = 22
USERNAME = "root"
KEY_PATH = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

def run_command(ssh, command, timeout=120):
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
        
        # 1. 生成自签名证书（RSA，CN 和 SAN 都是 admin.nuotaoutdoor.com）
        print("\n[1] 生成自签名证书...")
        run_command(ssh, """
        echo '=== 生成自签名证书 ==='
        mkdir -p /tmp/test-cert
        cd /tmp/test-cert
        
        # 生成私钥
        openssl genrsa -out test.key 2048 2>&1
        
        # 生成证书签名请求
        openssl req -new -key test.key -out test.csr -subj "/CN=admin.nuotaoutdoor.com" 2>&1
        
        # 生成扩展文件（包含 SAN）
        cat > test.ext << 'EOF'
        authorityKeyIdentifier=keyid,issuer
        basicConstraints=CA:FALSE
        keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
        subjectAltName = @alt_names
        [alt_names]
        DNS.1 = admin.nuotaoutdoor.com
        EOF
        
        # 生成自签名证书
        openssl x509 -req -in test.csr -signkey test.key -out test.crt -days 365 -extfile test.ext 2>&1
        
        echo ''
        echo '=== 证书详情 ==='
        openssl x509 -in test.crt -noout -text 2>&1 | head -40
        
        echo ''
        echo '=== 验证主机名匹配（自签名证书）==='
        openssl verify -CAfile test.crt -verify_hostname admin.nuotaoutdoor.com test.crt 2>&1
        """)
        
        # 2. 临时配置 Nginx 使用自签名证书
        print("\n[2] 临时配置 Nginx 使用自签名证书...")
        run_command(ssh, """
        echo '=== 备份当前 Nginx 配置 ==='
        cp /etc/nginx/sites-enabled/nuotao /etc/nginx/sites-enabled/nuotao.bak.testcert
        
        echo ''
        echo '=== 修改 Nginx 配置使用自签名证书 ==='
        sed -i 's|ssl_certificate /etc/letsencrypt/live/admin.nuotaoutdoor.com/fullchain.pem|ssl_certificate /tmp/test-cert/test.crt|' /etc/nginx/sites-enabled/nuotao
        sed -i 's|ssl_certificate_key /etc/letsencrypt/live/admin.nuotaoutdoor.com/privkey.pem|ssl_certificate_key /tmp/test-cert/test.key|' /etc/nginx/sites-enabled/nuotao
        
        echo ''
        echo '=== 验证修改 ==='
        grep -n 'ssl_certificate' /etc/nginx/sites-enabled/nuotao
        
        echo ''
        echo '=== Nginx 配置测试 ==='
        nginx -t 2>&1
        
        echo ''
        echo '=== 重新加载 Nginx ==='
        systemctl reload nginx 2>&1
        sleep 2
        echo "Nginx reloaded"
        """)
        
        # 3. 验证自签名证书的主机名匹配
        print("\n[3] 验证自签名证书的主机名匹配...")
        run_command(ssh, """
        echo '=== 从 s_client 获取证书 ==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -noout -subject -issuer -dates 2>&1
        
        echo ''
        echo '=== 验证主机名匹配（通过 s_client）==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com -verify_hostname admin.nuotaoutdoor.com 2>&1 | grep -E 'Verification error|Verify return code|subject='
        
        echo ''
        echo '=== 证书链 ==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>&1 | grep -A5 'Certificate chain'
        """)
        
        # 4. 恢复原来的 Nginx 配置
        print("\n[4] 恢复原来的 Nginx 配置...")
        run_command(ssh, """
        echo '=== 恢复 Nginx 配置 ==='
        cp /etc/nginx/sites-enabled/nuotao.bak.testcert /etc/nginx/sites-enabled/nuotao
        
        echo ''
        echo '=== 验证恢复 ==='
        grep -n 'ssl_certificate' /etc/nginx/sites-enabled/nuotao
        
        echo ''
        echo '=== Nginx 配置测试 ==='
        nginx -t 2>&1
        
        echo ''
        echo '=== 重新加载 Nginx ==='
        systemctl reload nginx 2>&1
        sleep 2
        echo "Nginx reloaded"
        
        echo ''
        echo '=== 验证恢复后的证书 ==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -noout -subject -issuer 2>&1
        """)
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
