import paramiko

host = "95.217.218.178"
port = 22
username = "root"
password = "test123"

print(f"登录服务器 {host}...")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    ssh.connect(
        hostname=host,
        port=port,
        username=username,
        password=password,
        timeout=30,
        allow_agent=False,
        look_for_keys=False
    )
    print("登录成功！")
    
    # 1. 查看pg_hba.conf配置
    print("\n=== 1. 查看pg_hba.conf配置 ===")
    stdin, stdout, stderr = ssh.exec_command("cat /etc/postgresql/*/main/pg_hba.conf | grep -v '^#' | grep -v '^$'")
    print(stdout.read().decode())
    
    # 2. 检查环境变量中的PGSSL设置
    print("\n=== 2. 检查环境变量 ===")
    stdin, stdout, stderr = ssh.exec_command("env | grep -i pgssl || echo '无PGSSL环境变量'")
    print(stdout.read().decode())
    
    # 3. 检查systemd服务的环境变量
    print("\n=== 3. 检查systemd服务环境变量 ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl show nuotao-backend --property=Environment")
    print(stdout.read().decode())
    
    # 4. 检查是否有客户端证书文件
    print("\n=== 4. 检查客户端证书文件 ===")
    stdin, stdout, stderr = ssh.exec_command("""
        find /root /home /opt/nuotao -name '*.crt' -o -name '*.key' -o -name '*.pem' 2>/dev/null | head -20
        echo "---"
        ls -la /root/.postgresql/ 2>/dev/null || echo '/root/.postgresql/不存在'
        echo "---"
        ls -la /home/nuotao/.postgresql/ 2>/dev/null || echo '/home/nuotao/.postgresql/不存在'
    """)
    print(stdout.read().decode())
    
    # 5. 测试数据库连接（不使用SSL）
    print("\n=== 5. 测试数据库连接 ===")
    stdin, stdout, stderr = ssh.exec_command("""
        sudo -u nuotao PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -p 5432 -U nuotao -d nuotao -c 'SELECT 1;' 2>&1
    """)
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 6. 检查asyncpg版本和默认SSL行为
    print("\n=== 6. 检查asyncpg版本 ===")
    stdin, stdout, stderr = ssh.exec_command("/opt/nuotao/backend/.venv/bin/pip show asyncpg | head -5")
    print(stdout.read().decode())
    
    # 7. 修复方案：在数据库连接字符串中添加sslmode=disable
    print("\n=== 7. 修复方案 ===")
    print("在DATABASE_URL中添加?sslmode=disable，因为本地连接不需要SSL")
    
    # 8. 备份并修改.env文件
    print("\n=== 8. 修改.env文件 ===")
    stdin, stdout, stderr = ssh.exec_command("""
        cp /opt/nuotao/backend/.env /opt/nuotao/backend/.env.bak.$(date +%Y%m%d_%H%M%S)
        sed -i 's|DATABASE_URL=postgresql+asyncpg://nuotao:s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09@127.0.0.1:5432/nuotao|DATABASE_URL=postgresql+asyncpg://nuotao:s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09@127.0.0.1:5432/nuotao?sslmode=disable|' /opt/nuotao/backend/.env
        grep DATABASE_URL /opt/nuotao/backend/.env
    """)
    print(stdout.read().decode())
    
    # 9. 重启后端服务
    print("\n=== 9. 重启后端服务 ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl restart nuotao-backend && sleep 3 && systemctl status nuotao-backend --no-pager | head -15")
    print(stdout.read().decode())
    
    # 10. 测试API端点
    print("\n=== 10. 测试API端点 ===")
    stdin, stdout, stderr = ssh.exec_command("""
        sleep 5
        echo "健康检查:"
        curl -s http://127.0.0.1:8000/api/v1/healthz
        echo ""
        echo "Dashboard summary:"
        curl -s http://127.0.0.1:8000/api/v1/dashboard/summary | head -c 500
        echo ""
        echo "Agent suggestions:"
        curl -s 'http://127.0.0.1:8000/api/v1/agent-suggestions?status=pending_approval&limit=1' | head -c 500
    """)
    print(stdout.read().decode())
    
    ssh.close()
    print("\n连接已关闭")
    
except Exception as e:
    print(f"连接失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
