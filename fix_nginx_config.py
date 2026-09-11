#!/usr/bin/env python3
"""修复Nginx配置：删除备份文件、更新server_name和证书路径"""
import paramiko
import sys

# SSH配置
HOST = "95.217.218.178"
USER = "root"
KEY_PATH = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

def run_command(ssh, cmd, timeout=30):
    """执行命令并返回输出"""
    print(f"\n$ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out:
        print(out)
    if err:
        print(f"STDERR: {err}")
    return out, err

def main():
    # 创建SSH客户端
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # 使用密钥登录
        private_key = paramiko.Ed25519Key.from_private_key_file(KEY_PATH)
        ssh.connect(HOST, username=USER, pkey=private_key, timeout=30)
        print(f"成功登录 {USER}@{HOST}")
        
        # 1. 检查nuotao-console配置文件
        print("\n" + "="*60)
        print("1. 检查nuotao-console配置文件")
        print("="*60)
        run_command(ssh, "cat /etc/nginx/sites-available/nuotao-console")
        
        # 2. 移动备份文件到备份目录
        print("\n" + "="*60)
        print("2. 移动备份文件到备份目录")
        print("="*60)
        run_command(ssh, "mkdir -p /etc/nginx/backups")
        run_command(ssh, "mv /etc/nginx/sites-enabled/nuotao.backup.* /etc/nginx/backups/ 2>/dev/null || echo '没有备份文件需要移动'")
        run_command(ssh, "ls -la /etc/nginx/sites-enabled/")
        
        # 3. 创建Python脚本来正确更新Nginx配置
        print("\n" + "="*60)
        print("3. 更新Nginx配置")
        print("="*60)
        
        nginx_update_script = '''
# 读取Nginx配置
with open('/etc/nginx/sites-enabled/nuotao', 'r') as f:
    content = f.read()

print("更新前的server_name行:")
for i, line in enumerate(content.split('\\n'), 1):
    if 'server_name' in line:
        print(f"  行{i}: {line.strip()}")

# 1. 替换所有错误域名的server_name（包括重复的）
# 错误域名是 admin.nuotaooutdoor.com (多了一个o)
content = content.replace(
    'server_name admin.nuotaooutdoor.com admin.nuotaooutdoor.com;',
    'server_name admin.nuotaoutdoor.com;'
)
content = content.replace(
    'server_name admin.nuotaooutdoor.com;',
    'server_name admin.nuotaoutdoor.com;'
)

# 2. 替换if条件中的错误域名
content = content.replace(
    'if ($host = admin.nuotaooutdoor.com) {',
    'if ($host = admin.nuotaoutdoor.com) {'
)

# 3. 替换ssl_certificate路径（错误域名的证书路径）
content = content.replace(
    'ssl_certificate /etc/letsencrypt/live/admin.nuotaooutdoor.com/fullchain.pem;',
    'ssl_certificate /etc/nginx/ssl/self-signed/admin.nuotaoutdoor.com.crt;'
)

# 4. 替换ssl_certificate_key路径
content = content.replace(
    'ssl_certificate_key /etc/letsencrypt/live/admin.nuotaooutdoor.com/privkey.pem;',
    'ssl_certificate_key /etc/nginx/ssl/self-signed/admin.nuotaoutdoor.com.key;'
)

# 写入更新后的配置
with open('/etc/nginx/sites-enabled/nuotao', 'w') as f:
    f.write(content)

print("\\n更新后的server_name行:")
for i, line in enumerate(content.split('\\n'), 1):
    if 'server_name' in line:
        print(f"  行{i}: {line.strip()}")

print("\\nNginx配置已更新")
'''
        
        # 将Python脚本写入服务器并执行
        run_command(ssh, f"cat > /tmp/fix_nginx.py << 'PYEOF'\n{nginx_update_script}\nPYEOF")
        run_command(ssh, "python3 /tmp/fix_nginx.py")
        
        # 4. 测试Nginx配置
        print("\n" + "="*60)
        print("4. 测试Nginx配置")
        print("="*60)
        run_command(ssh, "nginx -t")
        
        # 5. 重载Nginx
        print("\n" + "="*60)
        print("5. 重载Nginx")
        print("="*60)
        run_command(ssh, "systemctl reload nginx")
        
        # 6. 验证证书
        print("\n" + "="*60)
        print("6. 验证证书")
        print("="*60)
        run_command(ssh, "echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -noout -subject -ext subjectAltName")
        
        # 7. 测试HTTP访问
        print("\n" + "="*60)
        print("7. 测试HTTP访问")
        print("="*60)
        run_command(ssh, "curl -k -s -o /dev/null -w 'HTTP状态码: %{http_code}\\n' https://127.0.0.1/ -H 'Host: admin.nuotaoutdoor.com'")
        run_command(ssh, "curl -k -s https://127.0.0.1/api/v1/healthz -H 'Host: admin.nuotaoutdoor.com'")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()
        print("\nSSH连接已关闭")

if __name__ == "__main__":
    main()
