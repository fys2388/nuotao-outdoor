import paramiko

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
    
    # 1. 查看订单列表函数完整实现（386-420行）
    print("\n=== 1. 订单列表函数完整实现 ===")
    stdin, stdout, stderr = ssh.exec_command("sed -n '386,420p' /opt/nuotao/backend/app/api/v1/endpoints/b2b_admin.py")
    print(stdout.read().decode())
    
    # 2. 查看文件开头的导入语句
    print("\n=== 2. 文件开头的导入语句 ===")
    stdin, stdout, stderr = ssh.exec_command("sed -n '1,20p' /opt/nuotao/backend/app/api/v1/endpoints/b2b_admin.py")
    print(stdout.read().decode())
    
    # 3. 查看订单详情函数
    print("\n=== 3. 订单详情函数 ===")
    stdin, stdout, stderr = ssh.exec_command("sed -n '420,460p' /opt/nuotao/backend/app/api/v1/endpoints/b2b_admin.py")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
