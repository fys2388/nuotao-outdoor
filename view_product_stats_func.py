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
    
    # 查看_get_product_stats函数完整代码（346-380行）
    print("\n=== _get_product_stats函数完整代码 ===")
    stdin, stdout, stderr = ssh.exec_command("sed -n '346,380p' /opt/nuotao/backend/app/tasks/daily_agents.py")
    print(stdout.read().decode())
    
    # 查看文件末尾
    print("\n=== 文件末尾 ===")
    stdin, stdout, stderr = ssh.exec_command("wc -l /opt/nuotao/backend/app/tasks/daily_agents.py")
    print(stdout.read().decode())
    
    stdin, stdout, stderr = ssh.exec_command("tail -30 /opt/nuotao/backend/app/tasks/daily_agents.py")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
