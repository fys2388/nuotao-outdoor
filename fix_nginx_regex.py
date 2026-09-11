#!/usr/bin/env python3
"""用正则表达式修复Nginx server_name和证书路径"""
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
        
        # 创建Python脚本来用正则表达式更新Nginx配置
        nginx_fix_script = '''
import re

# 读取Nginx配置
with open('/etc/nginx/sites-enabled/nuotao', 'r') as f:
    content = f.read()

print("更新前的关键行:")
for i, line in enumerate(content.split('\\n'), 1):
    if any(kw in line for kw in ['server_name', 'ssl_certificate', 'if ($host']):
        print(f"  行{i}: {line.strip()}")

# 1. 用正则表达式替换所有server_name（匹配错误域名admin.nuotaooutdoor.com，包括重复的）
# 错误域名是 nuotao 后面多了一个 o: nuotaoo
content = re.sub(
    r'server_name\s+admin\.nuotao+outdoor\.com(\s+admin\.nuotao+outdoor\.com)?\s*;',
    'server_name admin.nuotaoutdoor.com;',
    content
)

# 2. 替换if条件中的错误域名
content = re.sub(
    r'if\s*\(\$host\s*=\s*admin\.nuotao+outdoor\.com\)',
    'if ($host = admin.nuotaoutdoor.com)',
    content
)

# 3. 替换ssl_certificate路径
content = re.sub(
    r'ssl_certificate\s+/etc/letsencrypt/live/admin\.nuotao+outdoor\.com/fullchain\.pem\s*;',
    'ssl_certificate /etc/nginx/ssl/self-signed/admin.nuotaoutdoor.com.crt;',
    content
)

# 4. 替换ssl_certificate_key路径
content = re.sub(
    r'ssl_certificate_key\s+/etc/letsencrypt/live/admin\.nuotao+outdoor\.com/privkey\.pem\s*;',
    'ssl_certificate_key /etc/nginx/ssl/self-signed/admin.nuotaoutdoor.com.key;',
    content
)

# 写入更新后的配置
with open('/etc/nginx/sites-enabled/nuotao', 'w') as f:
    f.write(content)

print("\\n更新后的关键行:")
for i, line in enumerate(content.split('\\n'), 1):
    if any(kw in line for kw in ['server_name', 'ssl_certificate', 'if ($host']):
        print(f"  行{i}: {line.strip()}")

print("\\nNginx配置已更新")
'''
        
        # 将Python脚本写入服务器并执行
        run_command(ssh, f"cat > /tmp/fix_nginx_regex.py << 'PYEOF'\n{nginx_fix_script}\nPYEOF")
        run_command(ssh, "python3 /tmp/fix_nginx_regex.py")
        
        # 测试Nginx配置
        print("\n" + "="*60)
        print("测试Nginx配置")
        print("="*60)
        run_command(ssh, "nginx -t")
        
        # 重载Nginx
        run_command(ssh, "systemctl reload nginx")
        
        # 验证证书和访问
        print("\n" + "="*60)
        print("验证证书和访问")
        print("="*60)
        run_command(ssh, "echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -noout -subject -ext subjectAltName")
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
