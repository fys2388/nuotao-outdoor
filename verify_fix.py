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
    
    # 1. 验证通过Nginx代理的API访问
    print("\n=== 1. 验证通过Nginx代理的API访问 ===")
    stdin, stdout, stderr = ssh.exec_command("""
        echo "=== 健康检查（通过Nginx） ==="
        curl -sk https://127.0.0.1/api/v1/healthz -H 'Host: admin.nuotaoutdoor.com'
        echo ""
        echo "=== Dashboard summary（通过Nginx） ==="
        curl -sk https://127.0.0.1/api/v1/dashboard/summary -H 'Host: admin.nuotaoutdoor.com' | head -c 500
        echo ""
        echo "=== Agent suggestions（通过Nginx） ==="
        curl -sk 'https://127.0.0.1/api/v1/agent-suggestions?status=pending_approval&limit=1' -H 'Host: admin.nuotaoutdoor.com' | head -c 500
    """)
    output = stdout.read().decode('utf-8', errors='replace')
    print(output)
    
    # 2. 检查后端服务状态
    print("\n=== 2. 检查后端服务状态 ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl status nuotao-backend --no-pager | head -10")
    output = stdout.read().decode('utf-8', errors='replace')
    print(output)
    
    # 3. 检查最近的错误日志
    print("\n=== 3. 检查最近5分钟的错误日志 ===")
    stdin, stdout, stderr = ssh.exec_command("journalctl -u nuotao-backend --no-pager --since '5 minutes ago' | grep -i 'error\\|exception\\|traceback' | head -10 || echo '无错误日志'")
    output = stdout.read().decode('utf-8', errors='replace')
    print(output)
    
    # 4. 显示修改后的database.py内容
    print("\n=== 4. 修改后的database.py ===")
    stdin, stdout, stderr = ssh.exec_command("cat /opt/nuotao/backend/app/core/database.py")
    output = stdout.read().decode('utf-8', errors='replace')
    print(output)
    
    ssh.close()
    print("\n连接已关闭")
    
except Exception as e:
    print(f"连接失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
