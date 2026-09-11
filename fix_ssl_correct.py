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
    
    # 1. 恢复.env文件（去掉sslmode参数）
    print("\n=== 1. 恢复.env文件 ===")
    stdin, stdout, stderr = ssh.exec_command("""
        sed -i 's|?sslmode=disable||' /opt/nuotao/backend/.env
        grep DATABASE_URL /opt/nuotao/backend/.env
    """)
    print(stdout.read().decode())
    
    # 2. 备份并修改database.py，在connect_args中添加ssl=False
    print("\n=== 2. 修改database.py ===")
    stdin, stdout, stderr = ssh.exec_command("""
        cp /opt/nuotao/backend/app/core/database.py /opt/nuotao/backend/app/core/database.py.bak.$(date +%Y%m%d_%H%M%S)
        cat /opt/nuotao/backend/app/core/database.py
    """)
    print(stdout.read().decode())
    
    # 3. 用Python脚本修改database.py
    print("\n=== 3. 用Python修改database.py ===")
    cmd = '''
import re

with open('/opt/nuotao/backend/app/core/database.py', 'r') as f:
    content = f.read()

# 在connect_args中添加ssl=False
old_connect_args = '"connect_args": {"timeout": 5}'
new_connect_args = '"connect_args": {"timeout": 5, "ssl": False}'

if old_connect_args in content:
    content = content.replace(old_connect_args, new_connect_args)
    print("已修改connect_args，添加ssl=False")
else:
    print("未找到旧的connect_args，尝试其他方式...")
    # 尝试用正则表达式
    content = re.sub(
        r'"connect_args":\s*\{([^}]+)\}',
        r'"connect_args": {\\1, "ssl": False}',
        content
    )
    print("已用正则表达式修改")

with open('/opt/nuotao/backend/app/core/database.py', 'w') as f:
    f.write(content)

print("修改完成")
'''
    # 将Python脚本写入临时文件并执行
    stdin, stdout, stderr = ssh.exec_command(f"cat > /tmp/fix_database.py << 'PYEOF'\n{cmd}\nPYEOF\npython3 /tmp/fix_database.py")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 4. 验证修改结果
    print("\n=== 4. 验证修改结果 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -A 5 'connect_args' /opt/nuotao/backend/app/core/database.py")
    print(stdout.read().decode())
    
    # 5. 重启后端服务
    print("\n=== 5. 重启后端服务 ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl restart nuotao-backend && sleep 5 && systemctl status nuotao-backend --no-pager | head -15")
    print(stdout.read().decode())
    
    # 6. 测试API端点
    print("\n=== 6. 测试API端点 ===")
    stdin, stdout, stderr = ssh.exec_command("""
        sleep 3
        echo "健康检查:"
        curl -s http://127.0.0.1:8000/api/v1/healthz
        echo ""
        echo "Dashboard summary:"
        curl -s http://127.0.0.1:8000/api/v1/dashboard/summary | head -c 1000
        echo ""
        echo "Agent suggestions:"
        curl -s 'http://127.0.0.1:8000/api/v1/agent-suggestions?status=pending_approval&limit=1' | head -c 1000
    """)
    print(stdout.read().decode())
    
    # 7. 检查后端日志
    print("\n=== 7. 检查后端日志 ===")
    stdin, stdout, stderr = ssh.exec_command("journalctl -u nuotao-backend --no-pager -n 30 | grep -i 'error\\|permission\\|ssl' || echo '无错误日志'")
    print(stdout.read().decode())
    
    ssh.close()
    print("\n连接已关闭")
    
except Exception as e:
    print(f"连接失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
