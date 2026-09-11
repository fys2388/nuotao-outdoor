import paramiko
import os

host = "95.217.218.178"
port = 22
username = "root"
key_path = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"

print(f"尝试用SSH密钥登录 {host}:{port}...")
print(f"密钥路径: {key_path}")
print(f"密钥文件存在: {os.path.exists(key_path)}")

try:
    # 加载SSH密钥
    key = paramiko.Ed25519Key.from_private_key_file(key_path)
    print("SSH密钥加载成功")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    ssh.connect(
        hostname=host,
        port=port,
        username=username,
        pkey=key,
        timeout=20,
        allow_agent=False,
        look_for_keys=False
    )
    print("SSH密钥登录成功！已进入Rescue环境")
    
    # 执行命令测试
    stdin, stdout, stderr = ssh.exec_command("hostname && whoami && uname -a")
    print("\n系统信息:")
    print(stdout.read().decode())
    
    # 挂载主分区
    print("\n挂载主分区...")
    stdin, stdout, stderr = ssh.exec_command("mount /dev/sda1 /mnt/system && ls -la /mnt/system/")
    print(stdout.read().decode())
    
    # 检查正常系统的SSH配置
    print("\n检查正常系统的SSH配置...")
    stdin, stdout, stderr = ssh.exec_command("cat /mnt/system/etc/ssh/sshd_config | grep -v '^#' | grep -v '^$'")
    print(stdout.read().decode())
    
    # 检查正常系统的root密码
    print("\n检查正常系统的root密码哈希...")
    stdin, stdout, stderr = ssh.exec_command("grep '^root:' /mnt/system/etc/shadow")
    print(stdout.read().decode())
    
    # 重新设置正常系统的root密码为test123
    print("\n重新设置正常系统的root密码为test123...")
    stdin, stdout, stderr = ssh.exec_command('HASH=$(openssl passwd -6 "test123"); sed -i "s|^root:[^:]*:|root:$HASH:|" /mnt/system/etc/shadow && grep "^root:" /mnt/system/etc/shadow')
    print(stdout.read().decode())
    
    # 确保root账户未被锁定
    print("\n确保root账户未被锁定...")
    stdin, stdout, stderr = ssh.exec_command("sed -i 's/^root:!/root:/' /mnt/system/etc/shadow && grep '^root:' /mnt/system/etc/shadow")
    print(stdout.read().decode())
    
    # 修复/etc/shadow权限
    print("\n修复/etc/shadow权限...")
    stdin, stdout, stderr = ssh.exec_command("chown root:shadow /mnt/system/etc/shadow && chmod 640 /mnt/system/etc/shadow && ls -la /mnt/system/etc/shadow")
    print(stdout.read().decode())
    
    # 确保SSH配置允许密码登录
    print("\n确保SSH配置允许密码登录...")
    stdin, stdout, stderr = ssh.exec_command("""cat > /mnt/system/etc/ssh/sshd_config << 'EOF'
Port 22
PermitRootLogin yes
PubkeyAuthentication yes
PasswordAuthentication yes
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
PrintMotd no
AcceptEnv LANG LC_*
Subsystem sftp /usr/lib/openssh/sftp-server
EOF
cat /mnt/system/etc/ssh/sshd_config""")
    print(stdout.read().decode())
    
    # 卸载分区
    print("\n卸载分区...")
    stdin, stdout, stderr = ssh.exec_command("umount /mnt/system")
    print("卸载完成")
    
    ssh.close()
    print("\n连接已关闭")
    print("\n现在需要重启服务器回到正常系统，然后用密码test123登录")
    
except paramiko.AuthenticationException as e:
    print(f"认证失败: {e}")
except Exception as e:
    print(f"连接失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
