import paramiko

# SSH连接配置
hostname = "95.217.218.178"
port = 22
username = "root"
password = "test123"

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 1. 查看.env中的默认管理员密码
    print("\n=== 1. 查看.env中的管理员配置 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -i 'admin\\|default\\|password' /opt/nuotao/backend/.env | head -20")
    print(stdout.read().decode())
    
    # 2. 查看ensure_default_admin函数
    print("\n=== 2. 查看默认管理员创建逻辑 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -A 30 'ensure_default_admin\\|DEFAULT_ADMIN' /opt/nuotao/backend/app/core/security.py 2>/dev/null | head -50")
    print(stdout.read().decode())
    
    # 3. 查看auth.py中的登录逻辑
    print("\n=== 3. 查看登录逻辑 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -A 20 'async def login' /opt/nuotao/backend/app/api/v1/endpoints/auth.py | head -30")
    print(stdout.read().decode())
    
    # 4. 重置管理员密码为admin123
    print("\n=== 4. 重置管理员密码 ===")
    stdin, stdout, stderr = ssh.exec_command("""
cd /opt/nuotao/backend
.venv/bin/python -c "
from app.core.security import get_password_hash
from app.core.database import SessionLocal
from app.models.user import User
import asyncio

async def reset_password():
    async with SessionLocal() as db:
        result = await db.execute(User.__table__.select().where(User.email == 'admin@nuotao.com'))
        user = result.fetchone()
        if user:
            hashed = get_password_hash('admin123')
            await db.execute(User.__table__.update().where(User.email == 'admin@nuotao.com').values(hashed_password=hashed))
            await db.commit()
            print('密码已重置为 admin123')
        else:
            print('用户不存在')

asyncio.run(reset_password())
"
""")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
finally:
    ssh.close()
    print("\nSSH连接已关闭")
