import paramiko
import time

host = "95.217.218.178"
port = 22
username = "root"
password = "3khgtJNvXnFN"

def run_cmd(ssh, cmd, timeout=30):
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out:
        print(out)
    if err:
        print(f"STDERR: {err}")
    return out, err

print("=" * 60)
print("连接Rescue环境...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(hostname=host, port=port, username=username, password=password, timeout=20)
print("连接成功！")

# 1. 挂载主分区
print("\n" + "=" * 60)
print("步骤1: 挂载服务器主分区 /dev/sda1")
run_cmd(ssh, "mkdir -p /mnt/system")
run_cmd(ssh, "mount /dev/sda1 /mnt/system")
run_cmd(ssh, "ls /mnt/system/")

# 2. 检查并禁用fail2ban
print("\n" + "=" * 60)
print("步骤2: 禁用fail2ban")
run_cmd(ssh, "chroot /mnt/system systemctl disable fail2ban 2>&1 || echo 'fail2ban可能未安装'")
run_cmd(ssh, "chroot /mnt/system systemctl stop fail2ban 2>&1 || echo 'fail2ban可能未运行'")

# 3. 检查并禁用ufw
print("\n" + "=" * 60)
print("步骤3: 禁用ufw防火墙")
run_cmd(ssh, "chroot /mnt/system ufw disable 2>&1 || echo 'ufw可能未安装'")
run_cmd(ssh, "chroot /mnt/system systemctl disable ufw 2>&1 || echo 'ufw可能未安装'")

# 4. 清空iptables规则
print("\n" + "=" * 60)
print("步骤4: 清空iptables规则")
run_cmd(ssh, "chroot /mnt/system iptables -F 2>&1 || echo 'iptables命令失败'")
run_cmd(ssh, "chroot /mnt/system iptables -X 2>&1 || echo 'iptables命令失败'")
run_cmd(ssh, "chroot /mnt/system iptables -P INPUT ACCEPT 2>&1 || echo '设置默认策略失败'")
run_cmd(ssh, "chroot /mnt/system iptables -P OUTPUT ACCEPT 2>&1 || echo '设置默认策略失败'")
run_cmd(ssh, "chroot /mnt/system iptables -P FORWARD ACCEPT 2>&1 || echo '设置默认策略失败'")

# 5. 确保SSH服务启用
print("\n" + "=" * 60)
print("步骤5: 确保SSH服务启用")
run_cmd(ssh, "chroot /mnt/system systemctl enable ssh 2>&1 || chroot /mnt/system systemctl enable sshd 2>&1 || echo 'SSH服务启用失败'")

# 6. 检查SSH配置
print("\n" + "=" * 60)
print("步骤6: 检查SSH配置")
run_cmd(ssh, "chroot /mnt/system grep -E '^(Port|PermitRootLogin|PasswordAuthentication|PubkeyAuthentication)' /etc/ssh/sshd_config 2>&1 || echo '读取SSH配置失败'")

# 7. 检查authorized_keys
print("\n" + "=" * 60)
print("步骤7: 检查root用户的authorized_keys")
run_cmd(ssh, "ls -la /mnt/system/root/.ssh/ 2>&1 || echo '.ssh目录不存在'")
run_cmd(ssh, "cat /mnt/system/root/.ssh/authorized_keys 2>&1 | head -5 || echo 'authorized_keys不存在'")

# 8. 卸载分区
print("\n" + "=" * 60)
print("步骤8: 卸载分区")
run_cmd(ssh, "umount /mnt/system")
run_cmd(ssh, "ls /mnt/system/")

print("\n" + "=" * 60)
print("所有修复操作完成！")
print("现在需要重启服务器回到正常系统...")

ssh.close()
print("SSH连接已关闭")
