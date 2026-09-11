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
    
    # 1. 重命名证书文件为正确的域名
    print("\n=== 1. 重命名证书文件为正确的域名 ===")
    stdin, stdout, stderr = ssh.exec_command("cd /etc/nginx/ssl/self-signed/ && mv admin.nuotaoutdoor.com.crt admin.nuotaooutdoor.com.crt && mv admin.nuotaoutdoor.com.key admin.nuotaooutdoor.com.key")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 验证证书文件
    stdin, stdout, stderr = ssh.exec_command("ls -la /etc/nginx/ssl/self-signed/")
    print(stdout.read().decode())
    
    # 2. 修改Nginx配置中的server_name和ssl_certificate路径
    print("\n=== 2. 修改Nginx配置 ===")
    # 使用Python脚本来精确替换，避免sed的转义问题
    script = '''
import re

with open('/etc/nginx/sites-enabled/nuotao', 'r') as f:
    content = f.read()

# 替换server_name
content = content.replace('server_name admin.nuotaoutdoor.com;', 'server_name admin.nuotaooutdoor.com;')

# 替换ssl_certificate路径
content = content.replace('ssl_certificate /etc/nginx/ssl/self-signed/admin.nuotaoutdoor.com.crt;', 
                          'ssl_certificate /etc/nginx/ssl/self-signed/admin.nuotaooutdoor.com.crt;')
content = content.replace('ssl_certificate_key /etc/nginx/ssl/self-signed/admin.nuotaoutdoor.com.key;', 
                          'ssl_certificate_key /etc/nginx/ssl/self-signed/admin.nuotaooutdoor.com.key;')

with open('/etc/nginx/sites-enabled/nuotao', 'w') as f:
    f.write(content)

print("Nginx配置已修改")
'''
    # 将脚本写入临时文件并执行
    stdin, stdout, stderr = ssh.exec_command(f"cat > /tmp/fix_nginx.py << 'PYEOF'\n{script}\nPYEOF\npython3 /tmp/fix_nginx.py")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 3. 验证修改
    print("\n=== 3. 验证修改 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -E 'server_name|ssl_certificate' /etc/nginx/sites-enabled/nuotao")
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
