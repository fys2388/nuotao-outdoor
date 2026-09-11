import paramiko
import sys

key_path = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"
host = "95.217.218.178"
port = 22
username = "root"

print(f"尝试SSH连接 {host}:{port} ...")
print(f"使用密钥: {key_path}")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    private_key = paramiko.Ed25519Key.from_private_key_file(key_path)
    print("密钥加载成功")
    
    ssh.connect(hostname=host, port=port, username=username, pkey=private_key, timeout=15)
    print("SSH连接成功！")
    
    # 执行命令测试
    stdin, stdout, stderr = ssh.exec_command("hostname && whoami && uptime")
    print("\n命令输出:")
    print(stdout.read().decode())
    
    ssh.close()
    print("\n连接已关闭")
    
except paramiko.AuthenticationException as e:
    print(f"认证失败: {e}")
except paramiko.SSHException as e:
    print(f"SSH异常: {e}")
except Exception as e:
    print(f"连接失败: {type(e).__name__}: {e}")
