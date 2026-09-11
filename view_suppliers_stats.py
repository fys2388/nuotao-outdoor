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
    
    # 查看Suppliers.tsx的统计卡片部分
    print("\n=== Suppliers.tsx统计卡片部分 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n 'Statistic\\|累计采购\\|采购订单\\|供应商总数\\|value=' /opt/nuotao/frontend/src/pages/Suppliers.tsx | head -30")
    print(stdout.read().decode())
    
    # 查看useState部分
    print("\n=== useState部分 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n 'useState\\|useEffect\\|loadSuppliers\\|const load' /opt/nuotao/frontend/src/pages/Suppliers.tsx | head -20")
    print(stdout.read().decode())
    
    # 查看统计卡片的具体行
    print("\n=== 统计卡片具体内容（行50-100） ===")
    stdin, stdout, stderr = ssh.exec_command("sed -n '50,100p' /opt/nuotao/frontend/src/pages/Suppliers.tsx")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
