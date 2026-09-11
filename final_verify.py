import paramiko

# SSH连接配置
hostname = "95.217.218.178"
port = 22
username = "root"
password = "test123"

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 1. 删除sites-enabled中的备份文件
    print("\n=== 1. 删除sites-enabled中的备份文件 ===")
    stdin, stdout, stderr = ssh.exec_command("rm -f /etc/nginx/sites-enabled/nuotao.bak.* && ls -la /etc/nginx/sites-enabled/")
    print(stdout.read().decode())
    
    # 2. 再次测试Nginx配置
    print("\n=== 2. 再次测试Nginx配置 ===")
    stdin, stdout, stderr = ssh.exec_command("nginx -t 2>&1")
    print(stdout.read().decode())
    
    # 3. 重新加载Nginx
    print("\n=== 3. 重新加载Nginx ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl reload nginx && systemctl status nginx --no-pager | head -5")
    print(stdout.read().decode())
    
    # 4. 测试所有站点
    print("\n=== 4. 测试admin站点 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s -k -H 'Host: admin.nuotaooutdoor.com' https://127.0.0.1/ | grep '<title>'")
    print(stdout.read().decode())
    
    print("\n=== 测试b2b站点 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s -k -H 'Host: b2b.nuotaooutdoor.com' https://127.0.0.1/ | grep '<title>'")
    print(stdout.read().decode())
    
    # 5. 测试API端点
    print("\n=== 5. 测试API端点 ===")
    print("健康检查:")
    stdin, stdout, stderr = ssh.exec_command("curl -s -k -H 'Host: admin.nuotaooutdoor.com' https://127.0.0.1/api/v1/healthz")
    print(stdout.read().decode())
    
    print("\nDashboard summary:")
    stdin, stdout, stderr = ssh.exec_command("curl -s -k -H 'Host: admin.nuotaooutdoor.com' https://127.0.0.1/api/v1/dashboard/summary | head -c 200")
    print(stdout.read().decode())
    
    print("\nAgent suggestions:")
    stdin, stdout, stderr = ssh.exec_command("curl -s -k -H 'Host: admin.nuotaooutdoor.com' 'https://127.0.0.1/api/v1/agent-suggestions?status=pending_approval&limit=1' | head -c 200")
    print(stdout.read().decode())
    
    print("\n=== 所有测试完成！ ===")
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
