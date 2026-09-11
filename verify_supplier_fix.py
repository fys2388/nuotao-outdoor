import paramiko

# SSH连接配置
hostname = "95.217.218.178"
port = 22
username = "root"
password = "4SqwD8k@vuXWYUE%!bkfyf1b"

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 1. 测试后端API
    print("\n=== 1. 测试后端API ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/suppliers")
    result = stdout.read().decode()
    print(f"API返回长度: {len(result)} 字符")
    print(f"前500字符: {result[:500]}")
    
    # 2. 检查后端日志是否有错误
    print("\n=== 2. 检查后端日志 ===")
    stdin, stdout, stderr = ssh.exec_command("journalctl -u nuotao-backend --no-pager -n 20 | grep -i 'error\\|traceback' || echo '无错误'")
    print(stdout.read().decode())
    
    # 3. 验证前端文件已部署
    print("\n=== 3. 验证前端文件 ===")
    stdin, stdout, stderr = ssh.exec_command("ls -la /var/www/nuotao/assets/ | grep -i supplier || echo '检查构建产物'")
    print(stdout.read().decode())
    
    stdin, stdout, stderr = ssh.exec_command("grep -l 'realSuppliers\\|api/v1/suppliers' /var/www/nuotao/assets/*.js 2>/dev/null | head -3")
    print(f"包含真实供应商代码的文件: {stdout.read().decode()}")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
