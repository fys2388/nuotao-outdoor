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
    
    # 1. 检查证书目录
    print("\n=== 1. 检查证书目录 ===")
    stdin, stdout, stderr = ssh.exec_command("ls -la /etc/nginx/ssl/self-signed/")
    print(stdout.read().decode())
    
    # 2. 检查当前Nginx配置中的ssl_certificate路径
    print("\n=== 2. 检查当前Nginx配置中的ssl_certificate路径 ===")
    stdin, stdout, stderr = ssh.exec_command("grep 'ssl_certificate' /etc/nginx/sites-enabled/nuotao")
    print(stdout.read().decode())
    
    # 3. 恢复Nginx配置（从备份）
    print("\n=== 3. 恢复Nginx配置（从备份） ===")
    stdin, stdout, stderr = ssh.exec_command("ls -la /etc/nginx/sites-enabled/nuotao.bak.*")
    print(stdout.read().decode())
    
    # 找到最新的备份文件
    stdin, stdout, stderr = ssh.exec_command("ls -t /etc/nginx/sites-enabled/nuotao.bak.* | head -1")
    backup_file = stdout.read().decode().strip()
    print(f"最新备份文件: {backup_file}")
    
    if backup_file:
        stdin, stdout, stderr = ssh.exec_command(f"cp {backup_file} /etc/nginx/sites-enabled/nuotao")
        print("已恢复Nginx配置")
    
    # 4. 检查恢复后的配置
    print("\n=== 4. 检查恢复后的配置 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -E 'server_name|ssl_certificate' /etc/nginx/sites-enabled/nuotao")
    print(stdout.read().decode())
    
    # 5. 测试Nginx配置
    print("\n=== 5. 测试Nginx配置 ===")
    stdin, stdout, stderr = ssh.exec_command("nginx -t")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 6. 重新加载Nginx
    print("\n=== 6. 重新加载Nginx ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl reload nginx")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
