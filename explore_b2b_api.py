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
    
    # 1. 查找B2B分销商相关的代码
    print("\n=== 1. 查找B2B分销商相关的代码文件 ===")
    stdin, stdout, stderr = ssh.exec_command("find /opt/nuotao/backend -type f -name '*.py' | xargs grep -l -i 'b2b\\|distributor\\|wholesale\\|partner' 2>/dev/null | head -20")
    print(stdout.read().decode())
    
    # 2. 查找B2B相关的API路由
    print("\n=== 2. 查找B2B相关的API路由 ===")
    stdin, stdout, stderr = ssh.exec_command("find /opt/nuotao/backend -type f -name '*.py' -path '*/api/*' | xargs grep -l -i 'b2b\\|distributor\\|wholesale\\|partner' 2>/dev/null | head -10")
    print(stdout.read().decode())
    
    # 3. 查找B2B相关的数据模型
    print("\n=== 3. 查找B2B相关的数据模型 ===")
    stdin, stdout, stderr = ssh.exec_command("find /opt/nuotao/backend -type f -name '*.py' -path '*/models/*' | xargs grep -l -i 'b2b\\|distributor\\|wholesale\\|partner' 2>/dev/null | head -10")
    print(stdout.read().decode())
    
    # 4. 查看API文档
    print("\n=== 4. 查看API文档（OpenAPI） ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/openapi.json | python3 -c \"import sys,json; d=json.load(sys.stdin); [print(f'{m.upper()} {p}') for p,methods in d.get('paths',{}).items() for m in methods if any(k in p.lower() for k in ['b2b','distributor','wholesale','partner','approval'])]\" 2>/dev/null | head -30")
    print(stdout.read().decode())
    
    # 5. 查看所有API路径（包含b2b或approval）
    print("\n=== 5. 所有包含b2b/approval的API路径 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/openapi.json | python3 -c \"import sys,json; d=json.load(sys.stdin); [print(p) for p in d.get('paths',{}).keys() if any(k in p.lower() for k in ['b2b','approval','distributor','partner'])]\" 2>/dev/null")
    print(stdout.read().decode())
    
    # 6. 查看数据库中是否有B2B相关的表
    print("\n=== 6. 数据库中B2B相关的表 ===")
    stdin, stdout, stderr = ssh.exec_command("sudo -u postgres psql -d nuotao -c \"\\dt\" 2>/dev/null | grep -i 'b2b\\|distributor\\|wholesale\\|partner\\|approval'")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
