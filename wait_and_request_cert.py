import paramiko
import time
import subprocess
import sys

def check_dns():
    """检查公共DNS是否已传播"""
    try:
        result = subprocess.run(
            ['nslookup', 'admin.nuotaoutdoor.com', '8.8.8.8'],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout + result.stderr
        if '95.217.218.178' in output:
            return True
        return False
    except Exception as e:
        print(f"DNS检查失败: {e}")
        return False

def request_cert():
    """在服务器上申请Let's Encrypt证书"""
    hostname = '95.217.218.178'
    port = 22
    username = 'root'
    key_path = r'C:\Users\神魂之人\.ssh\id_ed25519_nuotao'
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        private_key = paramiko.Ed25519Key(filename=key_path)
        ssh.connect(hostname, port, username, pkey=private_key, timeout=30)
        print("SSH连接成功！")
        
        # 申请证书
        print("\n=== 申请Let's Encrypt证书 ===")
        stdin, stdout, stderr = ssh.exec_command(
            'certbot --nginx -d admin.nuotaoutdoor.com --non-interactive --agree-tos --email admin@nuotaoutdoor.com --redirect 2>&1',
            timeout=180
        )
        print(stdout.read().decode())
        print(stderr.read().decode())
        
        # 验证证书
        print("\n=== 验证证书 ===")
        stdin, stdout, stderr = ssh.exec_command(
            'certbot certificates && '
            'openssl x509 -in /etc/letsencrypt/live/admin.nuotaoutdoor.com/fullchain.pem -noout -subject -ext subjectAltName -dates'
        )
        print(stdout.read().decode())
        
        # 验证Nginx配置
        print("\n=== 验证Nginx配置 ===")
        stdin, stdout, stderr = ssh.exec_command('nginx -t 2>&1 && systemctl reload nginx && echo "Nginx已重新加载"')
        print(stdout.read().decode())
        
        # 测试HTTPS访问
        print("\n=== 测试HTTPS访问 ===")
        stdin, stdout, stderr = ssh.exec_command(
            'curl -sI https://admin.nuotaoutdoor.com/ | head -5 && '
            'curl -s https://admin.nuotaoutdoor.com/api/v1/healthz'
        )
        print(stdout.read().decode())
        
        return True
        
    except Exception as e:
        print(f"申请证书失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        ssh.close()

# 主循环：等待DNS传播后申请证书
print("开始等待DNS传播...")
max_attempts = 60  # 最多等待60次（每次30秒，共30分钟）
attempt = 0

while attempt < max_attempts:
    attempt += 1
    print(f"\n[{attempt}/{max_attempts}] 检查DNS状态...")
    
    if check_dns():
        print("✅ DNS已传播！开始申请证书...")
        if request_cert():
            print("\n🎉 证书申请成功！")
            sys.exit(0)
        else:
            print("\n❌ 证书申请失败，将在30秒后重试...")
    else:
        print("⏳ DNS尚未传播，将在30秒后重试...")
    
    time.sleep(30)

print(f"\n⚠️ 已等待{max_attempts * 30}秒，DNS仍未传播。请稍后手动运行此脚本。")
sys.exit(1)
