"""查找 WooCommerce 实际部署位置"""
import paramiko

HOST = "95.217.218.178"
PORT = 22
USERNAME = "root"
PRIVATE_KEY = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

def ssh_run(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=HOST, port=PORT, username=USERNAME, key_filename=PRIVATE_KEY, timeout=30)
    print("SSH 连接成功!\n")
    
    # 1. 查看所有 Nginx 站点配置
    print("=" * 60)
    print("1. 所有 Nginx 站点配置")
    print("=" * 60)
    out, _ = ssh_run(client, "ls -la /etc/nginx/sites-available/; echo '==='; ls -la /etc/nginx/sites-enabled/")
    print(out)
    
    # 2. 查看主域名 nuotaooutdoor.com 的 Nginx 配置
    print("\n" + "=" * 60)
    print("2. nuotao 配置文件内容")
    print("=" * 60)
    out, _ = ssh_run(client, "cat /etc/nginx/sites-available/nuotao 2>/dev/null || cat /etc/nginx/sites-enabled/nuotao")
    print(out)
    
    # 3. 检查是否有 WordPress 相关的 Docker 容器
    print("\n" + "=" * 60)
    print("3. Docker 容器列表")
    print("=" * 60)
    out, _ = ssh_run(client, "docker ps -a 2>/dev/null || echo 'Docker 未运行或未安装'")
    print(out)
    
    # 4. 检查 /var/www/nuotao 目录内容（确认是什么）
    print("\n" + "=" * 60)
    print("4. /var/www/nuotao 目录内容")
    print("=" * 60)
    out, _ = ssh_run(client, "ls -la /var/www/nuotao/ | head -30")
    print(out)
    
    # 5. DNS 解析检查
    print("\n" + "=" * 60)
    print("5. DNS 解析")
    print("=" * 60)
    out, _ = ssh_run(client, "nslookup nuotaooutdoor.com 2>/dev/null || dig nuotaooutdoor.com +short 2>/dev/null; echo '---'; nslookup www.nuotaooutdoor.com 2>/dev/null || dig www.nuotaooutdoor.com +short 2>/dev/null; echo '---'; nslookup admin.nuotaooutdoor.com 2>/dev/null || dig admin.nuotaooutdoor.com +short 2>/dev/null")
    print(out)
    
    # 6. 检查是否有其他 Web 服务器（Apache）
    print("\n" + "=" * 60)
    print("6. Apache/其他 Web 服务")
    print("=" * 60)
    out, _ = ssh_run(client, "systemctl list-units --type=service | grep -iE 'apache|httpd|nginx|caddy|litespeed' 2>/dev/null; echo '---'; which apache2 httpd 2>/dev/null")
    print(out)
    
    # 7. 检查监听端口
    print("\n" + "=" * 60)
    print("7. 监听端口")
    print("=" * 60)
    out, _ = ssh_run(client, "ss -tlnp 2>/dev/null | grep -E ':80|:443|:8080' || netstat -tlnp 2>/dev/null | grep -E ':80|:443|:8080'")
    print(out)
    
    # 8. 检查 /opt 目录
    print("\n" + "=" * 60)
    print("8. /opt 目录")
    print("=" * 60)
    out, _ = ssh_run(client, "ls -la /opt/ 2>/dev/null")
    print(out)
    
    client.close()
    print("\n探查完成!")

if __name__ == "__main__":
    main()
