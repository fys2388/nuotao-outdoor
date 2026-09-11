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
    
    # 1. 查看B2B门户申请的schema
    print("\n=== 1. B2B门户申请Schema ===")
    stdin, stdout, stderr = ssh.exec_command("cat /opt/nuotao/backend/app/schemas/b2b_portal.py")
    print(stdout.read().decode())
    
    # 2. 查看B2B管理API的实现
    print("\n=== 2. B2B管理API实现（前100行） ===")
    stdin, stdout, stderr = ssh.exec_command("head -150 /opt/nuotao/backend/app/api/v1/endpoints/b2b_admin.py")
    print(stdout.read().decode())
    
    # 3. 查看b2b_agents表结构
    print("\n=== 3. b2b_agents表结构 ===")
    stdin, stdout, stderr = ssh.exec_command("sudo -u postgres psql -d nuotao -c '\\d b2b_agents' 2>/dev/null")
    print(stdout.read().decode())
    
    # 4. 查看现有的B2B代理商
    print("\n=== 4. 现有的B2B代理商 ===")
    stdin, stdout, stderr = ssh.exec_command("sudo -u postgres psql -d nuotao -c 'SELECT id, company_name, contact_name, email, status, created_at FROM b2b_agents ORDER BY created_at DESC LIMIT 10;' 2>/dev/null")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
