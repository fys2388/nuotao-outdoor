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

# 启用密码登录
print("\n启用SSH密码登录...")
run_cmd(ssh, "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /mnt/system/etc/ssh/sshd_config")
run_cmd(ssh, "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /mnt/system/etc/ssh/sshd_config")

# 验证配置
run_cmd(ssh, "grep -E '^(PermitRootLogin|PasswordAuthentication|PubkeyAuthentication)' /mnt/system/etc/ssh/sshd_config")

# 确保root密码正确（设置为Abkkpn9cCguX）
print("\n确保root密码正确...")
run_cmd(ssh, "chroot /mnt/system bash -c 'echo \"root:Abkkpn9cCguX\" | chpasswd'")

# 卸载分区
run_cmd(ssh, "umount /mnt/system")

print("\n完成！SSH密码登录已启用，root密码已设置为Abkkpn9cCguX")
print("现在需要重启服务器回到正常系统...")

ssh.close()
