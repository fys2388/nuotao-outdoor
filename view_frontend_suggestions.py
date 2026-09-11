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
    
    # 查看前端AgentSuggestions.tsx的关键部分
    print("\n=== 前端AgentSuggestions.tsx - 数据处理部分 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n 'filter\\|map\\|useState\\|useEffect\\|fetch\\|axios\\|items\\|data\\|setData\\|setSuggestions' /opt/nuotao/frontend/src/pages/AgentSuggestions.tsx | head -50")
    print(stdout.read().decode())
    
    # 查看文件前100行
    print("\n=== 前端AgentSuggestions.tsx - 前100行 ===")
    stdin, stdout, stderr = ssh.exec_command("head -120 /opt/nuotao/frontend/src/pages/AgentSuggestions.tsx")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
