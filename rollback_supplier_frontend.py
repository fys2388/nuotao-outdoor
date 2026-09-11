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
    
    # 1. 回滚前端文件
    print("\n=== 1. 回滚前端文件 ===")
    stdin, stdout, stderr = ssh.exec_command("cp /opt/nuotao/frontend/src/pages/Suppliers.tsx.backup /opt/nuotao/frontend/src/pages/Suppliers.tsx && echo '前端文件已回滚'")
    print(stdout.read().decode())
    
    # 2. 检查修改后的文件是否有语法问题
    print("\n=== 2. 检查修改后的文件 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n 'displaySuppliers\\|realSuppliers\\|apiLoaded' /opt/nuotao/frontend/src/pages/Suppliers.tsx | head -20")
    print("修改后的文件中的关键字（应该为空，因为已回滚）:")
    print(stdout.read().decode())
    
    # 3. 重新构建前端
    print("\n=== 3. 重新构建前端（回滚版本） ===")
    stdin, stdout, stderr = ssh.exec_command("cd /opt/nuotao/frontend && npm run build 2>&1 | tail -10")
    print(stdout.read().decode())
    
    # 4. 部署前端
    print("\n=== 4. 部署前端 ===")
    stdin, stdout, stderr = ssh.exec_command("""
rm -rf /var/www/nuotao/*
cp -r /opt/nuotao/frontend/dist/* /var/www/nuotao/
chown -R www-data:www-data /var/www/nuotao/
echo '前端部署完成'
""")
    print(stdout.read().decode())
    
    print("\n=== 回滚完成，页面应该恢复正常 ===")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
