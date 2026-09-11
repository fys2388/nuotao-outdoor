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

# 1. 把/etc/shadow的属组改回shadow
print("\n" + "=" * 60)
print("1. 把/etc/shadow的属组改回shadow")
run_cmd(ssh, "chown root:shadow /mnt/system/etc/shadow")
run_cmd(ssh, "chmod 640 /mnt/system/etc/shadow")
run_cmd(ssh, "ls -la /mnt/system/etc/shadow")

# 2. 检查AppArmor的状态
print("\n" + "=" * 60)
print("2. 检查AppArmor的状态和配置")
run_cmd(ssh, "ls -la /mnt/system/etc/apparmor.d/ 2>&1 | grep -i ssh || echo '无AppArmor SSH配置'")
run_cmd(ssh, "cat /mnt/system/etc/apparmor.d/usr.sbin.sshd 2>&1 || echo '无sshd AppArmor配置'")

# 3. 禁用AppArmor（如果有）
print("\n" + "=" * 60)
print("3. 禁用AppArmor的SSH配置")
run_cmd(ssh, "ln -sf /etc/apparmor.d/usr.sbin.sshd /mnt/system/etc/apparmor.d/disable/usr.sbin.sshd 2>&1 || echo '创建软链接失败'")
run_cmd(ssh, "ls -la /mnt/system/etc/apparmor.d/disable/ 2>&1 || echo 'disable目录不存在'")

# 4. 检查ssh.service的systemd配置中的安全设置
print("\n" + "=" * 60)
print("4. 检查ssh.service的systemd配置")
run_cmd(ssh, "cat /mnt/system/usr/lib/systemd/system/ssh.service 2>&1")

# 5. 检查是否有自定义的ssh.service覆盖
print("\n" + "=" * 60)
print("5. 检查是否有自定义的ssh.service覆盖")
run_cmd(ssh, "ls -la /mnt/system/etc/systemd/system/ssh.service.d/ 2>&1 || echo '无自定义覆盖'")
run_cmd(ssh, "cat /mnt/system/etc/systemd/system/ssh.service.d/*.conf 2>&1 || echo '无覆盖配置'")

# 6. 确保fail2ban完全禁用
print("\n" + "=" * 60)
print("6. 确保fail2ban完全禁用")
run_cmd(ssh, "rm -f /mnt/system/etc/systemd/system/multi-user.target.wants/fail2ban.service")
run_cmd(ssh, "ls -la /mnt/system/etc/systemd/system/multi-user.target.wants/ | grep -i fail || echo 'fail2ban已禁用'")

# 7. 检查PAM配置中是否有pam_systemd
print("\n" + "=" * 60)
print("7. 检查PAM配置中是否有pam_systemd")
run_cmd(ssh, "cat /mnt/system/etc/pam.d/common-session 2>&1 | grep -v '^#' | grep -v '^$'")

# 8. 临时禁用pam_systemd（可能导致问题）
print("\n" + "=" * 60)
print("8. 临时注释掉pam_systemd")
run_cmd(ssh, "sed -i 's/^session optional pam_systemd.so/#session optional pam_systemd.so/' /mnt/system/etc/pam.d/common-session")
run_cmd(ssh, "cat /mnt/system/etc/pam.d/common-session | grep -v '^#' | grep -v '^$'")

# 卸载分区
run_cmd(ssh, "umount /mnt/system")

print("\n" + "=" * 60)
print("完成！已修复/etc/shadow属组，禁用AppArmor和pam_systemd")
print("现在需要重启服务器回到正常系统，然后用密码test123登录")

ssh.close()
