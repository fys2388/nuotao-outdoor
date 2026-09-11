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

print("连接Rescue环境...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(hostname=host, port=port, username=username, password=password, timeout=20)
print("连接成功！")

# 挂载主分区
run_cmd(ssh, "mount /dev/sda1 /mnt/system")

# 检查root用户的shadow状态
print("\n检查root用户密码状态:")
run_cmd(ssh, "grep '^root:' /mnt/system/etc/shadow")

# 直接用openssl生成密码哈希并替换
print("\n生成密码哈希并设置root密码...")
run_cmd(ssh, 'HASH=$(openssl passwd -6 "Abkkpn9cCguX"); sed -i "s|^root:[^:]*:|root:$HASH:|" /mnt/system/etc/shadow')

# 验证密码已设置
print("\n验证root密码已设置:")
run_cmd(ssh, "grep '^root:' /mnt/system/etc/shadow")

# 确保root账户未被锁定
print("\n确保root账户未被锁定:")
run_cmd(ssh, "sed -i 's/^root:!/root:/' /mnt/system/etc/shadow")
run_cmd(ssh, "grep '^root:' /mnt/system/etc/shadow")

# 再次验证SSH配置
print("\n验证SSH配置:")
run_cmd(ssh, "grep -E '^(PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|UsePAM)' /mnt/system/etc/ssh/sshd_config")

# 检查PAM配置
print("\n检查PAM配置:")
run_cmd(ssh, "cat /mnt/system/etc/pam.d/sshd 2>&1 | head -20")

# 卸载分区
run_cmd(ssh, "umount /mnt/system")

print("\n完成！root密码已重新设置，账户已解锁")
ssh.close()
