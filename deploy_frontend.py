import paramiko
import os
import time

# SSH连接配置
hostname = "95.217.218.178"
port = 22
username = "root"
password = "test123"

# 本地构建目录
local_dist = r"E:\AI\nuotao-ai-os\frontend\dist"

# 服务器目标目录
remote_dir = "/var/www/nuotao"

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 1. 备份服务器上的旧文件
    print("\n=== 1. 备份服务器上的旧文件 ===")
    backup_dir = f"/root/frontend-backup-{int(time.time())}"
    stdin, stdout, stderr = ssh.exec_command(f"cp -r {remote_dir} {backup_dir} && echo '备份完成: {backup_dir}'")
    print(stdout.read().decode())
    
    # 2. 清空服务器上的旧文件
    print("\n=== 2. 清空服务器上的旧文件 ===")
    stdin, stdout, stderr = ssh.exec_command(f"rm -rf {remote_dir}/* && echo '已清空'")
    print(stdout.read().decode())
    
    # 3. 上传新构建的文件
    print("\n=== 3. 上传新构建的文件 ===")
    sftp = ssh.open_sftp()
    
    # 递归上传文件
    def upload_dir(local_path, remote_path):
        if not os.path.isdir(local_path):
            # 上传文件
            sftp.put(local_path, remote_path)
            print(f"  上传: {os.path.basename(local_path)}")
            return
        
        # 创建远程目录
        try:
            sftp.stat(remote_path)
        except:
            sftp.mkdir(remote_path)
        
        # 递归上传
        for item in os.listdir(local_path):
            local_item = os.path.join(local_path, item)
            remote_item = os.path.join(remote_path, item).replace('\\', '/')
            upload_dir(local_item, remote_item)
    
    upload_dir(local_dist, remote_dir)
    sftp.close()
    print("文件上传完成！")
    
    # 4. 设置文件权限
    print("\n=== 4. 设置文件权限 ===")
    stdin, stdout, stderr = ssh.exec_command(f"chown -R www-data:www-data {remote_dir} && chmod -R 755 {remote_dir} && echo '权限设置完成'")
    print(stdout.read().decode())
    
    # 5. 验证部署结果
    print("\n=== 5. 验证部署结果 ===")
    stdin, stdout, stderr = ssh.exec_command(f"ls -la {remote_dir}/ && echo '---' && ls -la {remote_dir}/assets/ | head -10")
    print(stdout.read().decode())
    
    # 6. 检查新的B2BAgents.js文件
    print("\n=== 6. 检查新的B2BAgents.js文件 ===")
    stdin, stdout, stderr = ssh.exec_command(f"ls -la {remote_dir}/assets/*B2B* && echo '---' && head -c 500 {remote_dir}/assets/*B2B*")
    print(stdout.read().decode())
    
    print("\n=== 部署完成！ ===")
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
