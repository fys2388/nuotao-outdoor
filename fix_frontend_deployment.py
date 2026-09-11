import paramiko
import time

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
    
    # 1. 备份当前的/var/www/nuotao目录
    print("\n=== 1. 备份当前的/var/www/nuotao目录 ===")
    stdin, stdout, stderr = ssh.exec_command("cp -r /var/www/nuotao /var/www/nuotao.bak.b2b-$(date +%Y%m%d%H%M%S)")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 2. 清空/var/www/nuotao目录
    print("\n=== 2. 清空/var/www/nuotao目录 ===")
    stdin, stdout, stderr = ssh.exec_command("rm -rf /var/www/nuotao/*")
    print(stdout.read().decode())
    
    # 3. 复制AI管理控制台的前端文件到/var/www/nuotao
    print("\n=== 3. 复制AI管理控制台的前端文件 ===")
    stdin, stdout, stderr = ssh.exec_command("cp -r /opt/nuotao/frontend/dist/* /var/www/nuotao/")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 4. 设置正确的权限
    print("\n=== 4. 设置正确的权限 ===")
    stdin, stdout, stderr = ssh.exec_command("chown -R www-data:www-data /var/www/nuotao/")
    print(stdout.read().decode())
    
    # 5. 验证文件
    print("\n=== 5. 验证文件 ===")
    stdin, stdout, stderr = ssh.exec_command("ls -la /var/www/nuotao/")
    print(stdout.read().decode())
    
    # 6. 检查index.html的标题
    print("\n=== 6. 检查index.html的标题 ===")
    stdin, stdout, stderr = ssh.exec_command("head -20 /var/www/nuotao/index.html")
    print(stdout.read().decode())
    
    # 7. 测试Nginx配置
    print("\n=== 7. 测试Nginx配置 ===")
    stdin, stdout, stderr = ssh.exec_command("nginx -t")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 8. 重新加载Nginx
    print("\n=== 8. 重新加载Nginx ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl reload nginx")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 9. 测试本地访问
    print("\n=== 9. 测试本地访问admin.nuotaooutdoor.com ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s -k -H 'Host: admin.nuotaooutdoor.com' https://127.0.0.1/ | head -20")
    print(stdout.read().decode())
    
    print("\n=== 修复完成！ ===")
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
