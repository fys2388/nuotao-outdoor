#!/usr/bin/env python3
"""直接读取并修复Nginx配置"""
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
        
        # 1. 先查看配置文件的前10行的原始内容（包括不可见字符）
        print("\n" + "="*60)
        print("1. 查看配置文件前10行的原始内容")
        print("="*60)
        run_command(ssh, "head -10 /etc/nginx/sites-enabled/nuotao | cat -A")
        
        # 2. 查看server_name行的原始内容
        print("\n" + "="*60)
        print("2. 查看server_name行的原始内容")
        print("="*60)
        run_command(ssh, "grep -n 'server_name' /etc/nginx/sites-enabled/nuotao | cat -A")
        
        # 3. 用sed直接替换（使用简单的字符串替换）
        print("\n" + "="*60)
        print("3. 用sed替换server_name")
        print("="*60)
        # 错误域名是 admin.nuotaooutdoor.com (nuotao后面多了一个o)
        # 正确域名是 admin.nuotaoutdoor.com
        run_command(ssh, "sed -i 's/admin\\.nuotaoo\\?outdoor\\.com/admin.nuotaoutdoor.com/g' /etc/nginx/sites-enabled/nuotao")
        
        # 4. 验证替换结果
        print("\n" + "="*60)
        print("4. 验证替换结果")
        print("="*60)
        run_command(ssh, "grep -n 'server_name' /etc/nginx/sites-enabled/nuotao")
        run_command(ssh, "grep -n 'ssl_certificate' /etc/nginx/sites-enabled/nuotao")
        run_command(ssh, "grep -n 'if ($host' /etc/nginx/sites-enabled/nuotao")
        
        # 5. 测试Nginx配置
        print("\n" + "="*60)
        print("5. 测试Nginx配置")
        print("="*60)
        run_command(ssh, "nginx -t")
        
        # 6. 重载Nginx
        run_command(ssh, "systemctl reload nginx")
        
        # 7. 验证证书和访问
        print("\n" + "="*60)
        print("7. 验证证书和访问")
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
