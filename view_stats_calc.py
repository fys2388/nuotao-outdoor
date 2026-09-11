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
    
    # 查看stats计算逻辑
    print("\n=== stats计算逻辑 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n 'const stats\\|stats =\\|totalSpent\\|total_orders\\|total_spent' /opt/nuotao/frontend/src/pages/Suppliers.tsx | head -20")
    print(stdout.read().decode())
    
    # 查看stats的具体计算
    print("\n=== stats具体计算（行350-380） ===")
    stdin, stdout, stderr = ssh.exec_command("sed -n '350,380p' /opt/nuotao/frontend/src/pages/Suppliers.tsx")
    print(stdout.read().decode())
    
    # 查看loadSuppliersData函数
    print("\n=== loadSuppliersData函数（行130-155） ===")
    stdin, stdout, stderr = ssh.exec_command("sed -n '130,155p' /opt/nuotao/frontend/src/pages/Suppliers.tsx")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
