import paramiko
import secrets
import string

# SSH连接配置
hostname = "95.217.218.178"
port = 22
username = "root"
password = "test123"

# 生成强密码
def generate_strong_password(length=24):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 1. 生成新的强密码
    print("\n=== 1. 生成新的强密码 ===")
    new_root_password = generate_strong_password()
    new_admin_password = generate_strong_password()
    print(f"新root密码: {new_root_password}")
    print(f"新管理员密码: {new_admin_password}")
    
    # 保存密码到文件
    with open(r'E:\AI\nuotao-ai-os\server_credentials.txt', 'w') as f:
        f.write(f"服务器IP: {hostname}\n")
        f.write(f"root密码: {new_root_password}\n")
        f.write(f"管理员账号: admin\n")
        f.write(f"管理员密码: {new_admin_password}\n")
        f.write(f"SSH密钥: C:\\Users\\神魂之人\\.ssh\\id_ed25519_nuotao\n")
    print("密码已保存到 server_credentials.txt")
    
    # 2. 修改root密码
    print("\n=== 2. 修改root密码 ===")
    stdin, stdout, stderr = ssh.exec_command(f"echo 'root:{new_root_password}' | chpasswd && echo 'root密码修改成功'")
    print(stdout.read().decode())
    
    # 3. 修改管理员密码
    print("\n=== 3. 修改管理员密码 ===")
    stdin, stdout, stderr = ssh.exec_command(f"""
cd /opt/nuotao/backend
.venv/bin/python -c "
import asyncio
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.user import User
from sqlalchemy import select, update

async def reset_password():
    async for db in get_db():
        hashed = get_password_hash('{new_admin_password}')
        await db.execute(update(User).where(User.email == 'admin@nuotao.com').values(hashed_password=hashed))
        await db.commit()
        print('管理员密码修改成功')
        break

asyncio.run(reset_password())
"
""")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 4. 启用fail2ban
    print("\n=== 4. 启用fail2ban ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl enable fail2ban && systemctl start fail2ban && systemctl status fail2ban --no-pager | head -10")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 5. 配置fail2ban SSH保护
    print("\n=== 5. 配置fail2ban SSH保护 ===")
    stdin, stdout, stderr = ssh.exec_command("""
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = 22
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 86400
EOF
systemctl restart fail2ban && echo 'fail2ban配置完成'
""")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 6. 验证SSH密钥认证仍然可用
    print("\n=== 6. 验证SSH密钥认证 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -E 'PubkeyAuthentication|PasswordAuthentication' /etc/ssh/sshd_config | grep -v '^#'")
    print(stdout.read().decode())
    
    # 7. 检查authorized_keys
    print("\n=== 7. 检查authorized_keys ===")
    stdin, stdout, stderr = ssh.exec_command("ls -la /root/.ssh/authorized_keys && wc -l /root/.ssh/authorized_keys")
    print(stdout.read().decode())
    
    # 8. 重启后端服务以应用新密码
    print("\n=== 8. 重启后端服务 ===")
    stdin, stdout, stderr = ssh.exec_command("systemctl restart nuotao-backend && sleep 2 && systemctl status nuotao-backend --no-pager | head -5")
    print(stdout.read().decode())
    
    # 9. 验证服务状态
    print("\n=== 9. 验证服务状态 ===")
    stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/v1/healthz")
    print(f"健康检查: {stdout.read().decode()}")
    
    print("\n=== 安全加固完成！ ===")
    print(f"新root密码: {new_root_password}")
    print(f"新管理员密码: {new_admin_password}")
    print("密码已保存到 server_credentials.txt")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
