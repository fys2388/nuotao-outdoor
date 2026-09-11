#!/usr/bin/env python3
"""在服务器上生成正确域名的自签名证书并更新Nginx配置"""
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
        
        # 1. 生成正确域名的自签名证书
        print("\n" + "="*60)
        print("1. 生成正确域名的自签名证书")
        print("="*60)
        
        # 创建证书目录
        run_command(ssh, "mkdir -p /etc/nginx/ssl/self-signed")
        
        # 生成自签名证书（有效期365天）
        cert_cmd = """openssl req -x509 -nodes -days 365 -newkey rsa:2048 \\
            -keyout /etc/nginx/ssl/self-signed/admin.nuotaoutdoor.com.key \\
            -out /etc/nginx/ssl/self-signed/admin.nuotaoutdoor.com.crt \\
            -subj "/C=CN/ST=Beijing/L=Beijing/O=Nuotao Outdoor/OU=IT/CN=admin.nuotaoutdoor.com" \\
            -addext "subjectAltName=DNS:admin.nuotaoutdoor.com,DNS:nuotaooutdoor.com" """
        run_command(ssh, cert_cmd)
        
        # 验证证书
        run_command(ssh, "openssl x509 -in /etc/nginx/ssl/self-signed/admin.nuotaoutdoor.com.crt -noout -subject -dates -ext subjectAltName")
        
        # 2. 备份当前Nginx配置
        print("\n" + "="*60)
        print("2. 备份当前Nginx配置")
        print("="*60)
        run_command(ssh, "cp /etc/nginx/sites-enabled/nuotao /etc/nginx/sites-enabled/nuotao.backup.$(date +%Y%m%d%H%M%S)")
        
        # 3. 更新Nginx配置 - 使用Python脚本精确替换
        print("\n" + "="*60)
        print("3. 更新Nginx配置")
        print("="*60)
        
        # 创建Python脚本来更新Nginx配置
        nginx_update_script = '''
import re

# 读取Nginx配置
with open('/etc/nginx/sites-enabled/nuotao', 'r') as f:
    content = f.read()

# 1. 替换server_name（443块）
content = content.replace(
    'server_name admin.nuotaooutdoor.com admin.nuotaooutdoor.com;',
    'server_name admin.nuotaoutdoor.com;'
)

# 2. 替换ssl_certificate路径
content = content.replace(
    'ssl_certificate /etc/letsencrypt/live/admin.nuotaooutdoor.com/fullchain.pem;',
    'ssl_certificate /etc/nginx/ssl/self-signed/admin.nuotaoutdoor.com.crt;'
)

# 3. 替换ssl_certificate_key路径
content = content.replace(
    'ssl_certificate_key /etc/letsencrypt/live/admin.nuotaooutdoor.com/privkey.pem;',
    'ssl_certificate_key /etc/nginx/ssl/self-signed/admin.nuotaoutdoor.com.key;'
)

# 4. 替换80块的server_name
content = content.replace(
    'server_name admin.nuotaooutdoor.com admin.nuotaooutdoor.com;',
    'server_name admin.nuotaoutdoor.com;'
)

# 5. 替换80块的if条件
content = content.replace(
    'if ($host = admin.nuotaooutdoor.com) {',
    'if ($host = admin.nuotaoutdoor.com) {'
)

# 写入更新后的配置
with open('/etc/nginx/sites-enabled/nuotao', 'w') as f:
    f.write(content)

print("Nginx配置已更新")
'''
        
        # 将Python脚本写入服务器并执行
        run_command(ssh, f"cat > /tmp/update_nginx.py << 'PYEOF'\n{nginx_update_script}\nPYEOF")
        run_command(ssh, "python3 /tmp/update_nginx.py")
        
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
        
        # 6. 验证新证书
        print("\n" + "="*60)
        print("6. 验证新证书")
        print("="*60)
        run_command(ssh, "echo | openssl s_client -connect 127.0.0.1:443 -servername admin.nuotaoutdoor.com 2>/dev/null | openssl x509 -noout -subject -dates -ext subjectAltName")
        
        # 7. 测试HTTP访问
        print("\n" + "="*60)
        print("7. 测试HTTP访问")
        print("="*60)
        run_command(ssh, "curl -k -s -o /dev/null -w '%{http_code}' https://127.0.0.1/ -H 'Host: admin.nuotaoutdoor.com'")
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
