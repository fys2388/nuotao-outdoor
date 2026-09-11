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
    
    # 1. 检查所有Nginx配置文件中的ssl_certificate路径
    print("\n=== 1. 检查所有配置文件中的ssl_certificate ===")
    stdin, stdout, stderr = ssh.exec_command("grep -r 'ssl_certificate' /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ /etc/nginx/nginx.conf 2>/dev/null")
    print(stdout.read().decode())
    
    # 2. 确保符号链接存在
    print("\n=== 2. 确保符号链接存在 ===")
    stdin, stdout, stderr = ssh.exec_command("ls -la /etc/nginx/ssl/admin.crt /etc/nginx/ssl/admin.key 2>&1")
    print(stdout.read().decode())
    
    # 如果符号链接不存在，创建它们
    stdin, stdout, stderr = ssh.exec_command("""
        # 先找到实际的证书文件
        CERT_FILE=$(find /etc/nginx/ssl -name '*.crt' -type f | head -1)
        KEY_FILE=$(find /etc/nginx/ssl -name '*.key' -type f | head -1)
        echo "Found cert: $CERT_FILE"
        echo "Found key: $KEY_FILE"
        
        # 创建符号链接
        ln -sf "$CERT_FILE" /etc/nginx/ssl/admin.crt
        ln -sf "$KEY_FILE" /etc/nginx/ssl/admin.key
        ls -la /etc/nginx/ssl/admin.crt /etc/nginx/ssl/admin.key
    """)
    print(stdout.read().decode())
    
    # 3. 修改所有配置文件中的ssl_certificate路径为简单路径
    print("\n=== 3. 修改所有配置文件中的证书路径 ===")
    script = '''
import os
import re

# 要修改的配置目录
config_dirs = ['/etc/nginx/sites-enabled/', '/etc/nginx/conf.d/']

# 匹配ssl_certificate和ssl_certificate_key的正则
pattern = re.compile(r'ssl_certificate(_key)?\\s+[^;]+;')

for config_dir in config_dirs:
    for filename in os.listdir(config_dir):
        filepath = os.path.join(config_dir, filename)
        if os.path.isfile(filepath) or os.path.islink(filepath):
            try:
                with open(filepath, 'r') as f:
                    content = f.read()
                
                # 替换ssl_certificate路径
                new_content = pattern.sub(lambda m: 'ssl_certificate' + ('_key' if m.group(1) else '') + ' /etc/nginx/ssl/admin' + ('.key' if m.group(1) else '.crt') + ';', content)
                
                if new_content != content:
                    with open(filepath, 'w') as f:
                        f.write(new_content)
                    print(f"Modified: {filepath}")
            except Exception as e:
                print(f"Error processing {filepath}: {e}")

print("All config files modified")
'''
    stdin, stdout, stderr = ssh.exec_command(f"cat > /tmp/fix_all_certs.py << 'PYEOF'\n{script}\nPYEOF\npython3 /tmp/fix_all_certs.py")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 4. 验证所有配置文件中的证书路径
    print("\n=== 4. 验证所有配置文件中的证书路径 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -r 'ssl_certificate' /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null")
    print(stdout.read().decode())
    
    # 5. 测试Nginx配置
    print("\n=== 5. 测试Nginx配置 ===")
    stdin, stdout, stderr = ssh.exec_command("nginx -t 2>&1")
    print(stdout.read().decode())
    
    # 6. 如果测试成功，重新加载Nginx
    print("\n=== 6. 重新加载Nginx ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl reload nginx 2>&1")
    print(stdout.read().decode())
    
    # 7. 测试本地访问
    print("\n=== 7. 测试本地访问admin.nuotaooutdoor.com ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s -k -H 'Host: admin.nuotaooutdoor.com' https://127.0.0.1/ | head -15")
    print(stdout.read().decode())
    
    # 8. 测试API
    print("\n=== 8. 测试API健康检查 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s -k -H 'Host: admin.nuotaooutdoor.com' https://127.0.0.1/api/v1/healthz")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
