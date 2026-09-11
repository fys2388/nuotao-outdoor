import paramiko
import os

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
    
    # 从服务器下载修复后的b2b_admin.py
    print("\n=== 1. 从服务器下载修复后的b2b_admin.py ===")
    sftp = ssh.open_sftp()
    remote_path = "/opt/nuotao/backend/app/api/v1/endpoints/b2b_admin.py"
    local_path = r"E:\AI\nuotao-ai-os\backend\app\api\v1\endpoints\b2b_admin.py"
    
    # 备份本地文件
    if os.path.exists(local_path):
        backup_path = local_path + ".backup"
        os.rename(local_path, backup_path)
        print(f"本地文件已备份到: {backup_path}")
    
    # 下载服务器文件
    sftp.get(remote_path, local_path)
    print(f"已下载服务器文件到: {local_path}")
    sftp.close()
    
    # 验证文件内容
    print("\n=== 2. 验证文件内容 ===")
    with open(local_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查selectinload导入
    if 'from sqlalchemy.orm import selectinload' in content:
        print("✅ selectinload导入存在")
    else:
        print("❌ selectinload导入不存在")
    
    # 检查订单列表查询
    if 'selectinload(B2BOrder.agent)' in content:
        print("✅ 订单列表查询已修复")
    else:
        print("❌ 订单列表查询未修复")
    
    print(f"\n文件大小: {len(content)} 字符")
    
    # 3. 检查git状态
    print("\n=== 3. 检查git状态 ===")
    import subprocess
    result = subprocess.run(['git', 'status', '--short'], 
                          capture_output=True, text=True, 
                          cwd=r"E:\AI\nuotao-ai-os")
    print(result.stdout)
    
    # 4. 提交git
    print("\n=== 4. 提交git ===")
    result = subprocess.run(['git', 'add', 'backend/app/api/v1/endpoints/b2b_admin.py'], 
                          capture_output=True, text=True, 
                          cwd=r"E:\AI\nuotao-ai-os")
    print(f"git add: {result.returncode}")
    
    result = subprocess.run(['git', 'commit', '-m', 
                           'fix(b2b): 修复B2B订单API MissingGreenlet错误，添加selectinload预先加载agent关系'], 
                          capture_output=True, text=True, 
                          cwd=r"E:\AI\nuotao-ai-os")
    print(f"git commit: {result.returncode}")
    print(result.stdout)
    print(result.stderr)
    
    # 5. 查看最新commit
    print("\n=== 5. 查看最新commit ===")
    result = subprocess.run(['git', 'log', '--oneline', '-5'], 
                          capture_output=True, text=True, 
                          cwd=r"E:\AI\nuotao-ai-os")
    print(result.stdout)
    
    print("\n=== 本地代码同步完成！ ===")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
