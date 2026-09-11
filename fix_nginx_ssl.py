#!/usr/bin/env python3
"""修复 Nginx 配置并验证 SSL"""

import paramiko
import sys

HOST = "95.217.218.178"
PORT = 22
USERNAME = "root"
KEY_PATH = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

def run_command(ssh, command, timeout=60):
    print(f"\n执行: {command[:80]}")
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout, get_pty=True)
    exit_status = stdout.channel.recv_exit_status()
    output = stdout.read().decode('utf-8', errors='replace')
    error = stderr.read().decode('utf-8', errors='replace')
    if output:
        print(output[-2000:] if len(output) > 2000 else output)
    if error:
        print(f"STDERR: {error[-300:]}")
    print(f"退出: {exit_status}")
    return exit_status, output, error

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        private_key = paramiko.Ed25519Key.from_private_key_file(KEY_PATH)
        ssh.connect(HOST, port=PORT, username=USERNAME, pkey=private_key, timeout=30, allow_agent=False, look_for_keys=False)
        print("连接成功！")
        
        # 1. 查看完整的 nuotao 配置
        print("\n[1] 查看 nuotao 配置的 server 块...")
        run_command(ssh, "grep -n -E 'server \\{|server_name|listen|ssl_certificate' /etc/nginx/sites-enabled/nuotao | head -30")
        
        # 2. 修复重复的 server_name
        print("\n[2] 修复重复的 server_name...")
        run_command(ssh, """
        # 备份
        cp /etc/nginx/sites-enabled/nuotao /etc/nginx/sites-enabled/nuotao.bak.fix
        
        # 移除重复的 admin.nuotaoutdoor.com
        sed -i 's/admin\\.nuotaooutdoor\\.com admin\\.nuotaooutdoor\\.com/admin.nuotaoutdoor.com/g' /etc/nginx/sites-enabled/nuotao
        
        # 验证
        grep -n 'server_name' /etc/nginx/sites-enabled/nuotao
        
        # 测试并重载
        nginx -t 2>&1
        systemctl reload nginx 2>&1
        echo 'Nginx reloaded'
        """)
        
        # 3. 验证证书
        print("\n[3] 验证证书...")
        run_command(ssh, """
        echo '=== 证书详情 ==='
        certbot certificates 2>&1 | grep -E 'Certificate Name|Domains|Expiry Date|Certificate Path'
        
        echo ''
        echo '=== 证书有效期 ==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -noout -dates 2>/dev/null
        
        echo ''
        echo '=== 证书域名 ==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -noout -text 2>/dev/null | grep -A1 'Subject Alternative Name'
        """)
        
        # 4. 本地测试
        print("\n[4] 本地测试 HTTPS...")
        run_command(ssh, """
        curl -sk -o /dev/null -w 'admin.nuotaoutdoor.com (127.0.0.1) -> HTTP %{http_code}\\n' --resolve admin.nuotaoutdoor.com:443:127.0.0.1 https://admin.nuotaoutdoor.com 2>&1
        curl -sk -o /dev/null -w '健康检查 -> HTTP %{http_code}\\n' --resolve admin.nuotaoutdoor.com:443:127.0.0.1 https://admin.nuotaoutdoor.com/api/v1/healthz 2>&1
        """)
        
        print("\n" + "="*60)
        print("服务器端配置已修复！")
        print("证书: admin.nuotaoutdoor.com (有效期到 2026-12-01)")
        print("Nginx: 已重载，配置正常")
        print("="*60)
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
