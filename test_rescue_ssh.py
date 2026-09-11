import paramiko
import sys

host = "95.217.218.178"
port = 22
username = "root"
password = "3khgtJNvXnFN"

print(f"尝试SSH连接Rescue环境 {host}:{port} ...")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    ssh.connect(hostname=host, port=port, username=username, password=password, timeout=20)
    print("SSH连接成功！已进入Rescue环境")
    
    # 执行命令测试
    stdin, stdout, stderr = ssh.exec_command("hostname && whoami && uname -a")
    print("\n系统信息:")
    print(stdout.read().decode())
    
    # 查看磁盘分区
    stdin, stdout, stderr = ssh.exec_command("lsblk && fdisk -l")
    print("\n磁盘分区:")
    print(stdout.read().decode())
    
    ssh.close()
    print("\n连接已关闭")
    
except paramiko.AuthenticationException as e:
    print(f"认证失败: {e}")
except paramiko.SSHException as e:
    print(f"SSH异常: {e}")
except Exception as e:
    print(f"连接失败: {type(e).__name__}: {e}")
