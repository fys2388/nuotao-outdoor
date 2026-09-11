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
    
    # 1. 备份Nginx配置
    print("\n=== 1. 备份Nginx配置 ===")
    stdin, stdout, stderr = ssh.exec_command("cp /etc/nginx/sites-enabled/nuotao /etc/nginx/sites-enabled/nuotao.bak.$(date +%Y%m%d%H%M%S)")
    print(stdout.read().decode())
    
    # 2. 修复server_name拼写错误
    print("\n=== 2. 修复server_name拼写错误 ===")
    # 使用sed替换所有的admin.nuotaoutdoor.com为admin.nuotaooutdoor.com
    stdin, stdout, stderr = ssh.exec_command("sed -i 's/admin\\.nuotaoutdoor\\.com/admin.nuotaooutdoor.com/g' /etc/nginx/sites-enabled/nuotao")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 3. 验证修改
    print("\n=== 3. 验证修改 ===")
    stdin, stdout, stderr = ssh.exec_command("grep 'server_name' /etc/nginx/sites-enabled/nuotao")
    print(stdout.read().decode())
    
    # 4. 测试Nginx配置
    print("\n=== 4. 测试Nginx配置 ===")
    stdin, stdout, stderr = ssh.exec_command("nginx -t")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 5. 重新加载Nginx
    print("\n=== 5. 重新加载Nginx ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl reload nginx")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 6. 测试本地访问
    print("\n=== 6. 测试本地访问admin.nuotaooutdoor.com ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s -k -H 'Host: admin.nuotaooutdoor.com' https://127.0.0.1/ | head -20")
    print(stdout.read().decode())
    
    # 7. 测试API
    print("\n=== 7. 测试API健康检查 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s -k -H 'Host: admin.nuotaooutdoor.com' https://127.0.0.1/api/v1/healthz")
    print(stdout.read().decode())
    
    print("\n=== 修复完成！ ===")
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
