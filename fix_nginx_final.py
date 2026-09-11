#!/usr/bin/env python3
"""用最简单的Python字符串替换修复Nginx配置"""
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
        
        # 创建Python脚本，用最简单的字符串替换
        # 错误域名: admin.nuotaooutdoor.com (nuotao后面多了一个o)
        # 正确域名: admin.nuotaoutdoor.com
        fix_script = '''
# 读取配置文件
with open('/etc/nginx/sites-enabled/nuotao', 'r') as f:
    content = f.read()

# 打印替换前的server_name行
print("替换前:")
for line in content.split('\\n'):
    if 'server_name' in line:
        print(f"  {repr(line)}")

# 用最简单的字符串替换
# 错误域名是 admin.nuotaooutdoor.com
# 正确域名是 admin.nuotaoutdoor.com
old_domain = 'admin.nuotaooutdoor.com'
new_domain = 'admin.nuotaoutdoor.com'

print(f"\\n旧域名: {repr(old_domain)}")
print(f"新域名: {repr(new_domain)}")
print(f"旧域名在配置中出现次数: {content.count(old_domain)}")

# 执行替换
content = content.replace(old_domain, new_domain)

# 打印替换后的server_name行
print("\\n替换后:")
for line in content.split('\\n'):
    if 'server_name' in line:
        print(f"  {repr(line)}")

# 写入配置文件
with open('/etc/nginx/sites-enabled/nuotao', 'w') as f:
    f.write(content)

print("\\n配置文件已更新")
'''
        
        # 将Python脚本写入服务器并执行
        run_command(ssh, f"cat > /tmp/simple_fix.py << 'PYEOF'\n{fix_script}\nPYEOF")
        run_command(ssh, "python3 /tmp/simple_fix.py")
        
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
        run_command(ssh, "grep -n 'server_name' /etc/nginx/sites-enabled/nuotao")
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
