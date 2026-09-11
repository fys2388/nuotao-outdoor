import paramiko
import time

# SSH连接配置
hostname = "95.217.218.178"
username = "root"
key_path = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    # 连接
    private_key = paramiko.Ed25519Key.from_private_key_file(key_path)
    ssh.connect(hostname=hostname, username=username, pkey=private_key, timeout=30)
    print("SSH连接成功！")
    
    # 1. 先验证DNS解析（从服务器端）
    print("\n=== 1. 验证DNS解析 ===")
    stdin, stdout, stderr = ssh.exec_command("nslookup admin.nuotaooutdoor.com 8.8.8.8")
    print(stdout.read().decode())
    
    # 2. 申请Let's Encrypt证书
    print("=== 2. 申请Let's Encrypt证书 ===")
    cmd = "certbot --nginx -d admin.nuotaooutdoor.com --non-interactive --agree-tos -m fys2388@gmail.com --redirect"
    print(f"执行: {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
    output = stdout.read().decode()
    error = stderr.read().decode()
    print(output)
    if error:
        print(f"STDERR: {error}")
    
    # 3. 检查证书是否申请成功
    print("\n=== 3. 检查证书状态 ===")
    stdin, stdout, stderr = ssh.exec_command("ls -la /etc/letsencrypt/live/admin.nuotaooutdoor.com/")
    print(stdout.read().decode())
    
    # 4. 验证证书内容
    print("=== 4. 验证证书内容 ===")
    stdin, stdout, stderr = ssh.exec_command("openssl x509 -in /etc/letsencrypt/live/admin.nuotaooutdoor.com/fullchain.pem -noout -subject -dates -ext subjectAltName 2>&1")
    print(stdout.read().decode())
    
    # 5. 检查Nginx配置
    print("=== 5. 检查Nginx配置 ===")
    stdin, stdout, stderr = ssh.exec_command("nginx -t 2>&1")
    print(stdout.read().decode())
    
    # 6. 重新加载Nginx
    print("=== 6. 重新加载Nginx ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl reload nginx && echo 'Nginx reloaded successfully'")
    print(stdout.read().decode())
    
    # 7. 测试HTTPS访问
    print("=== 7. 测试HTTPS访问 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s -o /dev/null -w '%{http_code}' https://admin.nuotaooutdoor.com/")
    status = stdout.read().decode().strip()
    print(f"HTTP状态码: {status}")
    
    # 8. 测试API健康检查
    print("\n=== 8. 测试API健康检查 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s https://admin.nuotaooutdoor.com/api/v1/healthz")
    print(stdout.read().decode())
    
    print("\n=== 完成！ ===")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("SSH连接已关闭")
