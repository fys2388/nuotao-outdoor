#!/usr/bin/env python3
"""检查证书目录并等待DNS生效后重试"""
import paramiko
import time
import subprocess

def check_public_dns():
    """用公共DNS验证解析"""
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['8.8.8.8', '1.1.1.1', '223.5.5.5', '114.114.114.114']
        answers = resolver.resolve('admin.nuotaoutdoor.com', 'A')
        for rdata in answers:
            print(f"公共DNS解析结果: {rdata.address}")
            return rdata.address == '95.217.218.178'
    except Exception as e:
        print(f"DNS查询失败: {e}")
        return False

def ssh_check_and_apply():
    """SSH检查并申请证书"""
    key_path = r'C:\Users\神魂之人\.ssh\id_ed25519_nuotao'
    host = '95.217.218.178'
    username = 'root'
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        private_key = paramiko.Ed25519Key.from_private_key_file(key_path)
        client.connect(hostname=host, username=username, pkey=private_key, timeout=30)
        print("SSH连接成功！")
        
        # 检查证书目录
        print("\n=== 证书目录详情 ===")
        stdin, stdout, stderr = client.exec_command('ls -la /etc/letsencrypt/live/admin.nuotaoutdoor.com/ 2>&1; echo "---"; cat /etc/letsencrypt/live/admin.nuotaoutdoor.com/cert.pem 2>/dev/null | openssl x509 -noout -subject -dates 2>&1')
        print(stdout.read().decode())
        
        # 检查archive目录
        print("\n=== Archive目录 ===")
        stdin, stdout, stderr = client.exec_command('ls -la /etc/letsencrypt/archive/admin.nuotaoutdoor.com/ 2>&1')
        print(stdout.read().decode())
        
        # 检查Nginx配置中的证书路径
        print("\n=== Nginx证书配置 ===")
        stdin, stdout, stderr = client.exec_command('grep -n "ssl_certificate\\|server_name" /etc/nginx/sites-enabled/nuotao')
        print(stdout.read().decode())
        
        # 尝试申请证书（重试）
        print("\n=== 重试申请证书 ===")
        cmd = 'certbot --nginx -d admin.nuotaoutdoor.com --non-interactive --agree-tos --email admin@nuotaooutdoor.com --redirect 2>&1'
        stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
        output = stdout.read().decode()
        print(output)
        
        if 'Successfully received certificate' in output or 'Congratulations' in output:
            print("\n=== 证书申请成功！ ===")
            
            # 验证新证书
            print("\n=== 验证新证书 ===")
            stdin, stdout, stderr = client.exec_command('certbot certificates 2>/dev/null')
            print(stdout.read().decode())
            
            # 测试Nginx配置并重载
            print("\n=== 测试并重载Nginx ===")
            stdin, stdout, stderr = client.exec_command('nginx -t 2>&1 && systemctl reload nginx 2>&1')
            print(stdout.read().decode())
            
            return True
        else:
            print("\n=== 证书申请仍失败 ===")
            return False
            
    except Exception as e:
        print(f"操作失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        client.close()

if __name__ == '__main__':
    # 等待DNS生效
    for attempt in range(6):
        print(f"\n=== 尝试 {attempt+1}/6: 检查DNS ===")
        if check_public_dns():
            print("DNS已生效！")
            break
        else:
            wait_time = 30
            print(f"DNS尚未生效，等待 {wait_time} 秒...")
            time.sleep(wait_time)
    else:
        print("DNS在3分钟内仍未生效，但继续尝试申请证书...")
    
    # SSH申请证书
    ssh_check_and_apply()
