import paramiko
import ssl
import socket
from cryptography import x509
from cryptography.hazmat.backends import default_backend

# SSH连接配置
hostname = '95.217.218.178'
port = 22
username = 'root'
key_path = r'C:\Users\神魂之人\.ssh\id_ed25519_nuotao'

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    # 连接
    private_key = paramiko.Ed25519Key(filename=key_path)
    ssh.connect(hostname, port, username, pkey=private_key, timeout=30)
    print("SSH连接成功！")
    
    # 读取证书文件
    print("\n=== 读取证书文件 ===")
    sftp = ssh.open_sftp()
    with sftp.file('/etc/letsencrypt/live/admin.nuotaoutdoor.com/fullchain.pem', 'r') as f:
        cert_pem = f.read()
    sftp.close()
    
    # 解析证书
    cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
    
    # 检查主题
    subject = cert.subject
    print(f"主题: {subject}")
    
    # 检查CN
    for attr in subject:
        if attr.oid._name == 'commonName':
            cn = attr.value
            print(f"CN: {cn}")
            print(f"CN长度: {len(cn)}")
            print(f"CN十六进制: {cn.encode().hex()}")
    
    # 检查SAN
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        for name in san.value.get_values_for_type(x509.DNSName):
            print(f"\nSAN: {name}")
            print(f"SAN长度: {len(name)}")
            print(f"SAN十六进制: {name.encode().hex()}")
    except Exception as e:
        print(f"SAN读取失败: {e}")
    
    # 检查有效期
    print(f"\n有效期: {cert.not_valid_before_utc} 至 {cert.not_valid_after_utc}")
    
    # 检查颁发者
    print(f"颁发者: {cert.issuer}")
    
    # 检查Nginx当前使用的证书
    print("\n=== 检查Nginx当前使用的证书 ===")
    stdin, stdout, stderr = ssh.exec_command('grep -E "ssl_certificate|server_name" /etc/nginx/sites-enabled/nuotao')
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
