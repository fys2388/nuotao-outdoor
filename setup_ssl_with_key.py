#!/usr/bin/env python3
"""使用 SSH 密钥登录服务器并配置 admin.nuotaoutdoor.com 的 SSL 证书"""

import paramiko
import time
import sys

# 服务器配置
HOST = "95.217.218.178"
PORT = 22
USERNAME = "root"
KEY_PATH = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

def run_command(ssh, command, timeout=180):
    """执行命令并返回输出"""
    print(f"\n{'='*60}")
    print(f"执行: {command[:120]}")
    print(f"{'='*60}")
    
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout, get_pty=True)
    
    # 等待命令完成
    exit_status = stdout.channel.recv_exit_status()
    
    # 读取输出
    output = stdout.read().decode('utf-8', errors='replace')
    error = stderr.read().decode('utf-8', errors='replace')
    
    if output:
        # 只打印最后3000字符
        if len(output) > 3000:
            print("... (输出过长，只显示最后3000字符) ...")
            print(output[-3000:])
        else:
            print(output)
    if error:
        print(f"STDERR: {error[-500:]}")
    
    print(f"\n退出状态: {exit_status}")
    return exit_status, output, error

def main():
    print("="*60)
    print("Nuotao Outdoor - SSL 证书自动配置 (SSH密钥)")
    print(f"服务器: {HOST}:{PORT}")
    print(f"用户: {USERNAME}")
    print("="*60)
    
    # 创建 SSH 客户端
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # 使用密钥连接
        print("\n[1/7] 连接服务器...")
        private_key = paramiko.Ed25519Key.from_private_key_file(KEY_PATH)
        ssh.connect(HOST, port=PORT, username=USERNAME, pkey=private_key, timeout=30, allow_agent=False, look_for_keys=False)
        print("连接成功！")
        
        # 系统信息
        run_command(ssh, "whoami && hostname && cat /etc/os-release | head -3")
        
        # 检查 Nginx 状态
        print("\n[2/7] 检查 Nginx 状态和配置...")
        run_command(ssh, "systemctl status nginx --no-pager | head -10 && echo '---' && ls -la /etc/nginx/sites-enabled/")
        
        # 查看当前 Nginx 配置
        print("\n[3/7] 查看当前 Nginx 配置...")
        run_command(ssh, "cat /etc/nginx/sites-enabled/default 2>/dev/null || cat /etc/nginx/sites-enabled/* 2>/dev/null | head -150")
        
        # 检查现有证书
        print("\n[4/7] 检查现有 SSL 证书...")
        run_command(ssh, "certbot certificates 2>&1 || echo 'certbot 未安装或无证书'")
        
        # 安装 certbot
        print("\n[5/7] 安装 certbot...")
        exit_status, output, error = run_command(ssh, 
            "apt-get update -qq 2>&1 | tail -5 && apt-get install -y -qq certbot python3-certbot-nginx 2>&1 | tail -10",
            timeout=180)
        
        # 申请证书
        print("\n[6/7] 申请包含 admin.nuotaoutdoor.com 的 SSL 证书...")
        
        # 先尝试扩展现有证书
        cert_command = (
            "certbot --nginx "
            "-d nuotaooutdoor.com -d www.nuotaoutdoor.com -d admin.nuotaoutdoor.com "
            "--email admin@nuotaooutdoor.com "
            "--agree-tos --no-eff-email "
            "--redirect --non-interactive --expand 2>&1"
        )
        
        exit_status, output, error = run_command(ssh, cert_command, timeout=180)
        
        if exit_status != 0:
            print(f"\n扩展证书失败 (exit={exit_status})，尝试单独申请 admin 证书...")
            
            admin_cert_command = (
                "certbot --nginx "
                "-d admin.nuotaoutdoor.com "
                "--email admin@nuotaooutdoor.com "
                "--agree-tos --no-eff-email "
                "--redirect --non-interactive 2>&1"
            )
            
            exit_status, output, error = run_command(ssh, admin_cert_command, timeout=180)
            
            if exit_status != 0:
                print(f"\n单独申请 admin 证书也失败 (exit={exit_status})")
                print("可能原因：DNS 解析问题或 Let's Encrypt 速率限制")
                print("将手动更新 Nginx 配置...")
        
        # 更新 Nginx 配置并验证
        print("\n[7/7] 更新 Nginx 配置并验证...")
        
        nginx_update = """
        echo "=== 更新 Nginx server_name ==="
        for conf in /etc/nginx/sites-enabled/*; do
            if [ -f "$conf" ] && grep -q "server_name.*nuotaooutdoor.com" "$conf" 2>/dev/null; then
                echo "处理: $conf"
                if ! grep -q "admin.nuotaoutdoor.com" "$conf" 2>/dev/null; then
                    sed -i 's/\\(server_name.*nuotaooutdoor.com\\)/\\1 admin.nuotaoutdoor.com/g' "$conf"
                    echo "  已添加 admin.nuotaoutdoor.com"
                else
                    echo "  admin.nuotaoutdoor.com 已存在"
                fi
            fi
        done
        
        echo ""
        echo "=== Nginx 配置测试 ==="
        nginx -t 2>&1
        
        echo ""
        echo "=== 重新加载 Nginx ==="
        systemctl reload nginx 2>&1
        echo "Nginx reload 完成"
        
        echo ""
        echo "=== 当前 server_name ==="
        grep -r "server_name" /etc/nginx/sites-enabled/ 2>/dev/null
        """
        
        run_command(ssh, nginx_update, timeout=60)
        
        # 最终验证
        print("\n" + "="*60)
        print("最终验证")
        print("="*60)
        
        verify = """
        echo "=== 证书列表 ==="
        certbot certificates 2>&1 | head -40
        
        echo ""
        echo "=== HTTPS 测试 ==="
        curl -sk -o /dev/null -w "admin.nuotaoutdoor.com -> HTTP %{http_code}\\n" https://admin.nuotaoutdoor.com 2>&1
        curl -sk -o /dev/null -w "nuotaooutdoor.com -> HTTP %{http_code}\\n" https://nuotaooutdoor.com 2>&1
        
        echo ""
        echo "=== 证书域名 ==="
        echo | openssl s_client -connect admin.nuotaoutdoor.com:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -noout -text 2>/dev/null | grep -A2 "Subject Alternative Name" | head -5
        
        echo ""
        echo "=== 完成! ==="
        """
        
        run_command(ssh, verify, timeout=60)
        
        print("\n" + "="*60)
        print("SSL 证书配置完成！")
        print("请在浏览器中访问 https://admin.nuotaoutdoor.com 验证")
        print("="*60)
        
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        ssh.close()
        print("\nSSH 连接已关闭")

if __name__ == "__main__":
    main()
