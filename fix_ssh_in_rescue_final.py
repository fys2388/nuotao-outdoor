import paramiko
import time

host = "95.217.218.178"
port = 22
username = "root"
rescue_password = "em7kVxfLinCJ"

print(f"尝试用Rescue密码登录 {host}:{port}...")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    ssh.connect(
        hostname=host,
        port=port,
        username=username,
        password=rescue_password,
        timeout=30,
        allow_agent=False,
        look_for_keys=False
    )
    print("SSH密码登录成功！已进入Rescue环境")
    
    # 执行命令测试
    stdin, stdout, stderr = ssh.exec_command("hostname && whoami && uname -a")
    print("\n系统信息:")
    print(stdout.read().decode())
    
    # 挂载主分区
    print("\n创建挂载点并挂载主分区...")
    stdin, stdout, stderr = ssh.exec_command("mkdir -p /mnt/system && mount /dev/sda1 /mnt/system && ls -la /mnt/system/")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
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
    
    # 确保SSH配置允许密码登录和root登录
    print("\n确保SSH配置允许密码登录和root登录...")
    sshd_config = """Port 22
PermitRootLogin yes
PubkeyAuthentication yes
PasswordAuthentication yes
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
PrintMotd no
AcceptEnv LANG LC_*
Subsystem sftp /usr/lib/openssh/sftp-server
"""
    # 写入SSH配置
    cmd = f"cat > /mnt/system/etc/ssh/sshd_config << 'SSHEOF'\n{sshd_config}SSHEOF\ncat /mnt/system/etc/ssh/sshd_config"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 检查sshd_config.d目录
    print("\n检查sshd_config.d目录...")
    stdin, stdout, stderr = ssh.exec_command("ls -la /mnt/system/etc/ssh/sshd_config.d/ 2>/dev/null || echo '目录不存在'")
    print(stdout.read().decode())
    
    # 删除可能覆盖配置的文件
    print("\n删除可能覆盖配置的文件...")
    stdin, stdout, stderr = ssh.exec_command("rm -f /mnt/system/etc/ssh/sshd_config.d/*.conf 2>/dev/null; echo '已清理'")
    print(stdout.read().decode())
    
    # 禁用fail2ban和ufw
    print("\n禁用fail2ban和ufw...")
    stdin, stdout, stderr = ssh.exec_command("""
        chroot /mnt/system systemctl disable fail2ban 2>/dev/null || true
        chroot /mnt/system systemctl disable ufw 2>/dev/null || true
        echo 'fail2ban和ufw已禁用'
    """)
    print(stdout.read().decode())
    
    # 清空iptables规则
    print("\n清空iptables规则...")
    stdin, stdout, stderr = ssh.exec_command("""
        chroot /mnt/system iptables -F 2>/dev/null || true
        chroot /mnt/system iptables -X 2>/dev/null || true
        echo 'iptables规则已清空'
    """)
    print(stdout.read().decode())
    
    # 检查PAM配置
    print("\n检查PAM配置...")
    stdin, stdout, stderr = ssh.exec_command("cat /mnt/system/etc/pam.d/sshd")
    print(stdout.read().decode())
    
    # 卸载分区
    print("\n卸载分区...")
    stdin, stdout, stderr = ssh.exec_command("umount /mnt/system")
    print("卸载完成")
    
    ssh.close()
    print("\n连接已关闭")
    print("\n修复完成！现在需要重启服务器回到正常系统，然后用密码test123登录")
    
except paramiko.AuthenticationException as e:
    print(f"认证失败: {e}")
except Exception as e:
    print(f"连接失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
