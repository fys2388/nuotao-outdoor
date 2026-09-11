import paramiko
import time

# SSH连接配置
hostname = "95.217.218.178"
port = 22
username = "root"
password = "test123"

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 等待服务启动
    print("\n等待服务启动...")
    time.sleep(5)
    
    # 测试健康检查
    print("\n=== 1. 测试健康检查 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/healthz")
    print(stdout.read().decode())
    
    # 测试B2B订单API
    print("\n=== 2. 测试B2B订单API ===")
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3ODkwMzY1NDYsInN1YiI6ImM2ZmU2YjE4LTk4NGQtNDE4NC04MDk1LWY2OGE4NmVkN2QxZiIsInR5cGUiOiJhY2Nlc3MiLCJpYXQiOjE3ODg5NTAxNDYsInJvbGUiOiJhZG1pbiIsInVzZXJuYW1lIjoiYWRtaW4iLCJlbWFpbCI6ImFkbWluQG51b3Rhby5jb20ifQ.yMgcFVqX8lMKF2ax-OpIYOELFgx6CRH-cx7EgXI4mPo"
    stdin, stdout, stderr = ssh.exec_command(f"""
curl -s -w "\\nHTTP Status: %{{http_code}}\\n" \\
  -H "Authorization: Bearer {token}" \\
  "http://127.0.0.1:8000/api/v1/admin/b2b/orders?page=1&page_size=3"
""")
    response = stdout.read().decode()
    print(response[:2000])
    
    # 检查后端日志
    print("\n=== 3. 检查后端日志 ===")
    stdin, stdout, stderr = ssh.exec_command("journalctl -u nuotao-backend --no-pager -n 20 --since '1 minute ago' | grep -i 'error\\|traceback' | head -10")
    logs = stdout.read().decode()
    if logs:
        print(logs)
    else:
        print("无错误日志")
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
