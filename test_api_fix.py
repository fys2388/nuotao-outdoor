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
    
    # 测试API端点
    print("\n=== 测试API端点 ===")
    stdin, stdout, stderr = ssh.exec_command("""
        echo "=== 健康检查 ==="
        curl -s http://127.0.0.1:8000/api/v1/healthz
        echo ""
        echo "=== Dashboard summary ==="
        curl -s http://127.0.0.1:8000/api/v1/dashboard/summary 2>&1 | head -c 2000
        echo ""
        echo "=== Agent suggestions ==="
        curl -s 'http://127.0.0.1:8000/api/v1/agent-suggestions?status=pending_approval&limit=2' 2>&1 | head -c 2000
        echo ""
    """)
    output = stdout.read().decode('utf-8', errors='replace')
    print(output)
    
    # 检查后端日志
    print("\n=== 检查后端错误日志 ===")
    stdin, stdout, stderr = ssh.exec_command("journalctl -u nuotao-backend --no-pager --since '2 minutes ago' | grep -i 'error\\|permission\\|traceback' | head -20 || echo '无错误日志'")
    output = stdout.read().decode('utf-8', errors='replace')
    print(output)
    
    # 检查启动日志
    print("\n=== 检查启动日志 ===")
    stdin, stdout, stderr = ssh.exec_command("journalctl -u nuotao-backend --no-pager --since '2 minutes ago' | grep -i 'startup\\|admin\\|ensure' | head -10 || echo '无相关日志'")
    output = stdout.read().decode('utf-8', errors='replace')
    print(output)
    
    ssh.close()
    print("\n连接已关闭")
    
except Exception as e:
    print(f"连接失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
