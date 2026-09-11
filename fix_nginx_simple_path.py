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
    
    # 1. 查看Nginx配置中ssl_certificate行的十六进制
    print("\n=== 1. 查看ssl_certificate行的十六进制 ===")
    stdin, stdout, stderr = ssh.exec_command("grep 'ssl_certificate' /etc/nginx/sites-enabled/nuotao | xxd")
    print(stdout.read().decode())
    
    # 2. 直接用Nginx测试配置并显示详细错误
    print("\n=== 2. Nginx测试配置（详细） ===")
    stdin, stdout, stderr = ssh.exec_command("nginx -t 2>&1")
    print(stdout.read().decode())
    
    # 3. 检查Nginx进程的权限
    print("\n=== 3. 检查Nginx进程的用户 ===")
    stdin, stdout, stderr = ssh.exec_command("ps aux | grep nginx | grep -v grep")
    print(stdout.read().decode())
    
    # 4. 检查证书目录的权限
    print("\n=== 4. 检查证书目录的权限 ===")
    stdin, stdout, stderr = ssh.exec_command("namei -l /etc/nginx/ssl/self-signed/admin.nuotaooutdoor.com.crt")
    print(stdout.read().decode())
    
    # 5. 尝试用Nginx用户读取证书文件
    print("\n=== 5. 尝试用www-data用户读取证书文件 ===")
    stdin, stdout, stderr = ssh.exec_command("sudo -u www-data cat /etc/nginx/ssl/self-signed/admin.nuotaooutdoor.com.crt | head -1")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 6. 直接修改Nginx配置，使用简单的证书路径
    print("\n=== 6. 创建符号链接到简单路径 ===")
    stdin, stdout, stderr = ssh.exec_command("ln -sf /etc/nginx/ssl/self-signed/admin.nuotaooutdoor.com.crt /etc/nginx/ssl/admin.crt && ln -sf /etc/nginx/ssl/self-signed/admin.nuotaooutdoor.com.key /etc/nginx/ssl/admin.key")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 7. 修改Nginx配置使用简单路径
    print("\n=== 7. 修改Nginx配置使用简单路径 ===")
    script = '''
with open('/etc/nginx/sites-enabled/nuotao', 'r') as f:
    content = f.read()

content = content.replace('ssl_certificate /etc/nginx/ssl/self-signed/admin.nuotaooutdoor.com.crt;', 
                          'ssl_certificate /etc/nginx/ssl/admin.crt;')
content = content.replace('ssl_certificate_key /etc/nginx/ssl/self-signed/admin.nuotaooutdoor.com.key;', 
                          'ssl_certificate_key /etc/nginx/ssl/admin.key;')

with open('/etc/nginx/sites-enabled/nuotao', 'w') as f:
    f.write(content)

print("Nginx配置已修改为简单路径")
'''
    stdin, stdout, stderr = ssh.exec_command(f"cat > /tmp/fix_nginx2.py << 'PYEOF'\n{script}\nPYEOF\npython3 /tmp/fix_nginx2.py")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 8. 验证修改
    print("\n=== 8. 验证修改 ===")
    stdin, stdout, stderr = ssh.exec_command("grep 'ssl_certificate' /etc/nginx/sites-enabled/nuotao")
    print(stdout.read().decode())
    
    # 9. 测试Nginx配置
    print("\n=== 9. 测试Nginx配置 ===")
    stdin, stdout, stderr = ssh.exec_command("nginx -t 2>&1")
    print(stdout.read().decode())
    
    # 10. 重新加载Nginx
    print("\n=== 10. 重新加载Nginx ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl reload nginx 2>&1")
    print(stdout.read().decode())
    
    # 11. 测试本地访问
    print("\n=== 11. 测试本地访问admin.nuotaooutdoor.com ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s -k -H 'Host: admin.nuotaooutdoor.com' https://127.0.0.1/ | head -15")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
