#!/usr/bin/env python3
"""诊断 admin.nuotaoutdoor.com HTTPS 连接问题"""

import paramiko
import sys

HOST = "95.217.218.178"
PORT = 22
USERNAME = "root"
KEY_PATH = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

def run_command(ssh, command, timeout=60):
    """执行命令并返回输出"""
    print(f"\n{'='*60}")
    print(f"执行: {command[:100]}")
    print(f"{'='*60}")
    
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout, get_pty=True)
    exit_status = stdout.channel.recv_exit_status()
    output = stdout.read().decode('utf-8', errors='replace')
    error = stderr.read().decode('utf-8', errors='replace')
    
    if output:
        print(output[-3000:] if len(output) > 3000 else output)
    if error:
        print(f"STDERR: {error[-500:]}")
    
    print(f"\n退出状态: {exit_status}")
    return exit_status, output, error

def main():
    print("="*60)
    print("诊断 admin.nuotaoutdoor.com HTTPS 问题")
    print("="*60)
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        private_key = paramiko.Ed25519Key.from_private_key_file(KEY_PATH)
        ssh.connect(HOST, port=PORT, username=USERNAME, pkey=private_key, timeout=30, allow_agent=False, look_for_keys=False)
        print("连接成功！")
        
        # 1. 检查端口监听
        print("\n[1] 检查 443 端口监听...")
        run_command(ssh, "ss -tlnp | grep -E ':(80|443)' && echo '---' && netstat -tlnp 2>/dev/null | grep -E ':(80|443)'")
        
        # 2. 检查所有 Nginx 配置文件
        print("\n[2] 查看所有 Nginx 配置文件...")
        run_command(ssh, "ls -la /etc/nginx/sites-available/ && echo '---' && ls -la /etc/nginx/sites-enabled/")
        
        # 3. 查看 nuotao-console 配置
        print("\n[3] 查看 nuotao-console 配置...")
        run_command(ssh, "cat /etc/nginx/sites-available/nuotao-console 2>/dev/null | head -100")
        
        # 4. 查看 nuotao 配置的 server_name 和 SSL 部分
        print("\n[4] 查看 nuotao 配置的 server_name 和 SSL...")
        run_command(ssh, "grep -n -E 'server_name|ssl_certificate|listen' /etc/nginx/sites-available/nuotao 2>/dev/null | head -30")
        
        # 5. 检查本地 DNS 解析
        print("\n[5] 检查服务器本地 DNS 解析...")
        run_command(ssh, "cat /etc/resolv.conf && echo '---' && nslookup admin.nuotaoutdoor.com 2>&1 | head -20 && echo '---' && getent hosts admin.nuotaoutdoor.com")
        
        # 6. 检查 hosts 文件
        print("\n[6] 检查 /etc/hosts...")
        run_command(ssh, "cat /etc/hosts")
        
        # 7. 直接用 IP 测试 443
        print("\n[7] 用 IP 直接测试 443...")
        run_command(ssh, "curl -sk -o /dev/null -w 'HTTP %{http_code}\\n' --resolve admin.nuotaoutdoor.com:443:127.0.0.1 https://admin.nuotaoutdoor.com 2>&1")
        
        # 8. 检查 Nginx 错误日志
        print("\n[8] 检查 Nginx 错误日志...")
        run_command(ssh, "tail -30 /var/log/nginx/error.log 2>/dev/null")
        
        # 9. 修复重复的 server_name
        print("\n[9] 修复重复的 server_name...")
        run_command(ssh, """
        for conf in /etc/nginx/sites-enabled/*; do
            if [ -f "$conf" ]; then
                # 移除重复的 admin.nuotaoutdoor.com
                sed -i 's/admin\\.nuotaooutdoor\\.com admin\\.nuotaooutdoor\\.com/admin.nuotaoutdoor.com/g' "$conf"
            fi
        done
        grep -n 'server_name' /etc/nginx/sites-enabled/* 2>/dev/null
        echo '---'
        nginx -t 2>&1
        systemctl reload nginx 2>&1
        echo 'Nginx reloaded'
        """)
        
        # 10. 最终测试
        print("\n[10] 最终测试...")
        run_command(ssh, """
        echo '=== 用 --resolve 测试 ==='
        curl -sk -o /dev/null -w 'admin.nuotaoutdoor.com (127.0.0.1) -> HTTP %{http_code}\\n' --resolve admin.nuotaoutdoor.com:443:127.0.0.1 https://admin.nuotaoutdoor.com 2>&1
        
        echo ''
        echo '=== 证书信息 ==='
        echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -noout -text 2>/dev/null | grep -E 'Subject:|DNS:|Not After' | head -5
        
        echo ''
        echo '=== Nginx 配置中的 server_name ==='
        grep -rn 'server_name' /etc/nginx/sites-enabled/ 2>/dev/null
        """)
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()
        print("\nSSH 连接已关闭")

if __name__ == "__main__":
    main()
