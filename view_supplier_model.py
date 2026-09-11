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
    
    # 1. 查看Supplier模型
    print("\n=== 1. Supplier模型 ===")
    stdin, stdout, stderr = ssh.exec_command("cat /opt/nuotao/backend/app/models/supplier.py")
    print(stdout.read().decode())
    
    # 2. 查看supply_chain service中的supplier相关函数
    print("\n=== 2. supply_chain service中的supplier函数 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n 'supplier\\|Supplier' /opt/nuotao/backend/app/services/supply_chain.py | head -30")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
