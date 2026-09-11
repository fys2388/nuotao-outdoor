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

# 1. 检查/etc/passwd和/etc/shadow文件权限
print("\n" + "=" * 60)
print("1. 检查/etc/passwd和/etc/shadow文件权限")
run_cmd(ssh, "ls -la /mnt/system/etc/passwd /mnt/system/etc/shadow")

# 2. 用SHA-512格式重新设置密码
print("\n" + "=" * 60)
print("2. 用SHA-512格式重新设置密码")
run_cmd(ssh, 'HASH=$(openssl passwd -6 "test123"); echo "生成的哈希: $HASH"; sed -i "s|^root:[^:]*:|root:$HASH:|" /mnt/system/etc/shadow')
run_cmd(ssh, "grep '^root:' /mnt/system/etc/shadow")

# 3. 确保root账户未被锁定
print("\n" + "=" * 60)
print("3. 确保root账户未被锁定")
run_cmd(ssh, "sed -i 's/^root:!/root:/' /mnt/system/etc/shadow")
run_cmd(ssh, "grep '^root:' /mnt/system/etc/shadow")

# 4. 检查PAM配置中是否有其他模块
print("\n" + "=" * 60)
print("4. 检查PAM配置中是否有其他模块")
run_cmd(ssh, "cat /mnt/system/etc/pam.d/sshd | grep -v '^#' | grep -v '^$'")
run_cmd(ssh, "cat /mnt/system/etc/pam.d/common-auth | grep -v '^#' | grep -v '^$'")

# 5. 检查/etc/security/access.conf
print("\n" + "=" * 60)
print("5. 检查/etc/security/access.conf")
run_cmd(ssh, "cat /mnt/system/etc/security/access.conf 2>&1 | grep -v '^#' | grep -v '^$' || echo '无特殊配置'")

# 6. 检查sshd的配置测试
print("\n" + "=" * 60)
print("6. 检查sshd配置")
run_cmd(ssh, "cat /mnt/system/etc/ssh/sshd_config")

# 7. 检查是否有sshguard或其他安全软件
print("\n" + "=" * 60)
print("7. 检查是否有其他安全软件")
run_cmd(ssh, "dpkg --root=/mnt/system -l 2>&1 | grep -i 'sshguard\\|denyhosts\\|pam_abl\\|libpam' || echo '无其他安全软件'")

# 8. 检查/var/log/auth.log中的详细错误
print("\n" + "=" * 60)
print("8. 检查auth.log中我们IP的详细错误")
run_cmd(ssh, "grep '77.42.80.164' /mnt/system/var/log/auth.log 2>&1 | tail -20 || echo '无记录'")

# 9. 修复文件权限
print("\n" + "=" * 60)
print("9. 修复文件权限")
run_cmd(ssh, "chmod 644 /mnt/system/etc/passwd")
run_cmd(ssh, "chmod 640 /mnt/system/etc/shadow")
run_cmd(ssh, "chown root:root /mnt/system/etc/passwd /mnt/system/etc/shadow")
run_cmd(ssh, "ls -la /mnt/system/etc/passwd /mnt/system/etc/shadow")

# 10. 检查root用户的家目录权限
print("\n" + "=" * 60)
print("10. 检查root用户的家目录权限")
run_cmd(ssh, "ls -la /mnt/system/root/ | head -10")
run_cmd(ssh, "ls -la /mnt/system/root/.ssh/ 2>&1 || echo '无.ssh目录'")

# 卸载分区
run_cmd(ssh, "umount /mnt/system")

print("\n" + "=" * 60)
print("完成！已用SHA-512格式重新设置密码，修复文件权限")
print("现在需要重启服务器回到正常系统，然后用密码test123登录")

ssh.close()
