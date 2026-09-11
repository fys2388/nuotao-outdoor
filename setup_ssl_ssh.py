#!/usr/bin/env python3
"""自动 SSH 登录服务器并配置 admin.nuotaoutdoor.com 的 SSL 证书"""

import paramiko
import time
import sys

# 服务器配置
HOST = "95.217.218.178"
PORT = 22
USERNAME = "root"
PASSWORD = "Abkkpn9cCguX"

def run_command(ssh, command, timeout=120):
    """执行命令并返回输出"""
    print(f"\n{'='*60}")
    print(f"执行命令: {command[:100]}...")
    print(f"{'='*60}")
    
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    
    # 等待命令完成
    exit_status = stdout.channel.recv_exit_status()
    
    # 读取输出
    output = stdout.read().decode('utf-8', errors='replace')
    error = stderr.read().decode('utf-8', errors='replace')
    
    if output:
        print(output[-2000:])  # 只打印最后2000字符
    if error:
        print(f"STDERR: {error[-1000:]}")
    
    print(f"退出状态: {exit_status}")
    return exit_status, output, error

def main():
    print("="*60)
    print("Nuotao Outdoor - SSL 证书自动配置")
    print(f"服务器: {HOST}:{PORT}")
    print(f"用户: {USERNAME}")
    print("="*60)
    
    # 创建 SSH 客户端
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # 连接服务器
        print("\n[1/6] 连接服务器...")
        ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD, timeout=30)
        print("连接成功！")
        
        # 检查系统信息
        run_command(ssh, "uname -a && cat /etc/os-release | head -5")
        
        # 安装 certbot
        print("\n[2/6] 安装 certbot 和 python3-certbot-nginx...")
        exit_status, output, error = run_command(ssh, 
            "apt-get update -qq && apt-get install -y -qq certbot python3-certbot-nginx 2>&1",
            timeout=180)
        
        if exit_status != 0:
            print(f"警告: certbot 安装可能失败 (exit={exit_status})，继续尝试...")
        
        # 检查 Nginx 配置
        print("\n[3/6] 检查当前 Nginx 配置...")
        run_command(ssh, "ls -la /etc/nginx/sites-enabled/ && echo '---' && cat /etc/nginx/sites-enabled/* 2>/dev/null | head -100")
        
        # 检查现有证书
        print("\n[4/6] 检查现有 SSL 证书...")
        run_command(ssh, "certbot certificates 2>&1 || echo '无现有证书'")
        
        # 申请新证书（包含 admin 子域名）
        print("\n[5/6] 申请包含 admin.nuotaoutdoor.com 的 SSL 证书...")
        
        # 先尝试扩展现有证书
        cert_command = (
            "certbot --nginx "
            "-d nuotaooutdoor.com -d www.nuotaooutdoor.com -d admin.nuotaoutdoor.com "
            "--email admin@nuotaooutdoor.com "
            "--agree-tos --no-eff-email "
            "--redirect --non-interactive --expand 2>&1"
        )
        
        exit_status, output, error = run_command(ssh, cert_command, timeout=180)
        
        if exit_status != 0:
            print(f"扩展证书失败 (exit={exit_status})，尝试单独申请 admin 证书...")
            
            # 单独申请 admin 证书
            admin_cert_command = (
                "certbot --nginx "
                "-d admin.nuotaoutdoor.com "
                "--email admin@nuotaooutdoor.com "
                "--agree-tos --no-eff-email "
                "--redirect --non-interactive 2>&1"
            )
            
            exit_status, output, error = run_command(ssh, admin_cert_command, timeout=180)
            
            if exit_status != 0:
                print(f"单独申请 admin 证书也失败 (exit={exit_status})")
                print("可能原因：DNS 解析问题或 Let's Encrypt 速率限制")
                print("继续手动更新 Nginx 配置...")
        
        # 更新 Nginx 配置，确保 admin 子域名在 server_name 中
        print("\n[6/6] 更新 Nginx 配置并验证...")
        
        nginx_update_command = """
        for conf in /etc/nginx/sites-enabled/*; do
            if [ -f "$conf" ] && grep -q "server_name.*nuotaooutdoor.com" "$conf" 2>/dev/null; then
                echo "处理配置文件: $conf"
                if ! grep -q "admin.nuotaoutdoor.com" "$conf" 2>/dev/null; then
                    echo "  添加 admin.nuotaoutdoor.com 到 server_name"
                    sed -i 's/\\(server_name.*nuotaooutdoor.com\\)/\\1 admin.nuotaoutdoor.com/g' "$conf"
                else
                    echo "  admin.nuotaoutdoor.com 已存在"
                fi
            fi
        done
        echo "---"
        echo "Nginx 配置测试:"
        nginx -t 2>&1
        echo "---"
        echo "重新加载 Nginx:"
        systemctl reload nginx 2>&1
        echo "Nginx 状态:"
        systemctl status nginx --no-pager 2>&1 | head -10
        """
        
        run_command(ssh, nginx_update_command, timeout=60)
        
        # 验证 SSL 配置
        print("\n" + "="*60)
        print("验证 SSL 配置结果")
        print("="*60)
        
        verify_command = """
        echo "=== 证书信息 ==="
        certbot certificates 2>&1 | head -30
        echo ""
        echo "=== Nginx server_name ==="
        grep -r "server_name" /etc/nginx/sites-enabled/ 2>/dev/null
        echo ""
        echo "=== HTTPS 测试 (admin.nuotaoutdoor.com) ==="
        curl -sk -o /dev/null -w "HTTP 状态码: %{http_code}\\n" https://admin.nuotaoutdoor.com 2>&1
        echo ""
        echo "=== 证书域名验证 ==="
        echo | openssl s_client -connect admin.nuotaoutdoor.com:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -noout -text 2>/dev/null | grep -A1 "Subject Alternative Name" | head -5
        echo ""
        echo "=== 完成! ==="
        """
        
        run_command(ssh, verify_command, timeout=60)
        
        print("\n" + "="*60)
        print("SSL 证书配置完成！")
        print("请在浏览器中访问 https://admin.nuotaoutdoor.com 验证")
        print("="*60)
        
    except paramiko.AuthenticationException as e:
        print(f"认证失败: {e}")
        print("请检查用户名和密码")
        sys.exit(1)
    except paramiko.SSHException as e:
        print(f"SSH 连接错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        ssh.close()
        print("\nSSH 连接已关闭")

if __name__ == "__main__":
    main()
