#!/usr/bin/env python3
"""修复证书链：下载中间证书，重新生成完整的 fullchain.pem，更新 Nginx 配置"""

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
        
        # 1. 检查当前证书状态
        print("\n[1] 检查当前证书状态...")
        run_command(ssh, """
        echo '=== letsencrypt 目录结构 ==='
        ls -la /etc/letsencrypt/live/
        ls -la /etc/letsencrypt/live/admin.nuotaoutdoor.com/ 2>/dev/null || echo 'live 目录不存在'
        ls -la /etc/letsencrypt/archive/admin.nuotaoutdoor.com/ 2>/dev/null || echo 'archive 目录不存在'
        
        echo ''
        echo '=== 当前证书（从 s_client 获取）==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -noout -subject -issuer -dates 2>&1
        
        echo ''
        echo '=== s_client 显示的证书链 ==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>&1 | grep -A2 'Certificate chain' | head -10
        """)
        
        # 2. 下载 Let's Encrypt 中间证书（YE1）
        print("\n[2] 下载 Let's Encrypt 中间证书...")
        run_command(ssh, """
        echo '=== 下载 YE1 中间证书 ==='
        curl -sL -o /tmp/ye1.der "http://ye1.i.lencr.org/" 2>&1
        ls -la /tmp/ye1.der
        
        echo ''
        echo '=== 转换为 PEM 格式 ==='
        openssl x509 -inform DER -in /tmp/ye1.der -out /tmp/ye1.pem 2>&1
        ls -la /tmp/ye1.pem
        
        echo ''
        echo '=== 中间证书详情 ==='
        openssl x509 -in /tmp/ye1.pem -noout -subject -issuer -dates 2>&1
        """)
        
        # 3. 从 archive 目录获取叶子证书，重新生成完整的 fullchain.pem
        print("\n[3] 重新生成完整的证书链文件...")
        run_command(ssh, """
        echo '=== 检查 archive 目录中的证书 ==='
        ls -la /etc/letsencrypt/archive/admin.nuotaoutdoor.com/
        
        echo ''
        echo '=== 叶子证书详情 ==='
        openssl x509 -in /etc/letsencrypt/archive/admin.nuotaoutdoor.com/cert1.pem -noout -subject -issuer -dates 2>&1
        
        echo ''
        echo '=== 现有 chain.pem 详情 ==='
        openssl x509 -in /etc/letsencrypt/archive/admin.nuotaoutdoor.com/chain1.pem -noout -subject -issuer -dates 2>&1
        
        echo ''
        echo '=== 现有 fullchain.pem 中的证书数量 ==='
        grep -c 'BEGIN CERTIFICATE' /etc/letsencrypt/archive/admin.nuotaoutdoor.com/fullchain1.pem
        
        echo ''
        echo '=== 重新生成 live 目录的符号链接 ==='
        mkdir -p /etc/letsencrypt/live/admin.nuotaoutdoor.com
        cd /etc/letsencrypt/live/admin.nuotaoutdoor.com
        ln -sf ../../archive/admin.nuotaoutdoor.com/cert1.pem cert.pem
        ln -sf ../../archive/admin.nuotaoutdoor.com/chain1.pem chain.pem
        ln -sf ../../archive/admin.nuotaoutdoor.com/fullchain1.pem fullchain.pem
        ln -sf ../../archive/admin.nuotaoutdoor.com/privkey1.pem privkey.pem
        ls -la
        
        echo ''
        echo '=== 验证 fullchain.pem 中的证书数量 ==='
        grep -c 'BEGIN CERTIFICATE' fullchain.pem
        
        echo ''
        echo '=== fullchain.pem 中的每个证书 ==='
        i=0
        while read -r line; do
            if [[ "$line" == *"BEGIN CERTIFICATE"* ]]; then
                echo "--- 证书 $i ---"
                i=$((i+1))
            fi
        done < fullchain.pem
        """)
        
        # 4. 如果 fullchain.pem 只有一个证书，手动添加中间证书
        print("\n[4] 修复证书链（如果需要）...")
        run_command(ssh, """
        echo '=== 检查 fullchain.pem 证书数量 ==='
        CERT_COUNT=$(grep -c 'BEGIN CERTIFICATE' /etc/letsencrypt/live/admin.nuotaoutdoor.com/fullchain.pem)
        echo "证书数量: $CERT_COUNT"
        
        if [ "$CERT_COUNT" -lt 2 ]; then
            echo "证书链不完整，正在添加中间证书..."
            
            # 备份原文件
            cp /etc/letsencrypt/archive/admin.nuotaoutdoor.com/fullchain1.pem /etc/letsencrypt/archive/admin.nuotaoutdoor.com/fullchain1.pem.bak
            
            # 重新生成 fullchain.pem（叶子证书 + 中间证书）
            cat /etc/letsencrypt/archive/admin.nuotaoutdoor.com/cert1.pem /tmp/ye1.pem > /etc/letsencrypt/archive/admin.nuotaoutdoor.com/fullchain1.pem
            
            # 同时更新 chain.pem
            cp /tmp/ye1.pem /etc/letsencrypt/archive/admin.nuotaoutdoor.com/chain1.pem
            
            echo "证书链已修复"
        else
            echo "证书链完整"
        fi
        
        echo ''
        echo '=== 验证修复后的 fullchain.pem ==='
        grep -c 'BEGIN CERTIFICATE' /etc/letsencrypt/live/admin.nuotaoutdoor.com/fullchain.pem
        openssl crl2pkcs7 -nocrl -certfile /etc/letsencrypt/live/admin.nuotaoutdoor.com/fullchain.pem | openssl pkcs7 -print_certs -noout 2>&1 | grep -E 'subject=|issuer='
        """)
        
        # 5. 重新加载 Nginx 并验证
        print("\n[5] 重新加载 Nginx 并验证...")
        run_command(ssh, """
        echo '=== Nginx 配置测试 ==='
        nginx -t 2>&1
        
        echo ''
        echo '=== 重新加载 Nginx ==='
        systemctl reload nginx 2>&1
        echo "Nginx reloaded"
        
        echo ''
        echo '=== 等待 Nginx 启动 ==='
        sleep 2
        
        echo ''
        echo '=== 验证证书链（s_client）==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>&1 | grep -A5 'Certificate chain'
        
        echo ''
        echo '=== 验证主机名匹配 ==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com -verify_hostname admin.nuotaoutdoor.com 2>&1 | grep -E 'Verification error|Verify return code'
        
        echo ''
        echo '=== HTTPS 测试 ==='
        curl -sk -o /dev/null -w "HTTP 状态码: %{http_code}\\n" https://127.0.0.1 -H "Host: admin.nuotaoutdoor.com" 2>&1
        """)
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
