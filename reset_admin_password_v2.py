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
    
    # 1. 查看database.py的导出
    print("\n=== 1. 查看database.py的导出 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -E '^def |^class |^[a-zA-Z_]+ =' /opt/nuotao/backend/app/core/database.py | head -20")
    print(stdout.read().decode())
    
    # 2. 查看用户表结构
    print("\n=== 2. 查看用户表 ===")
    stdin, stdout, stderr = ssh.exec_command("sudo -u postgres psql -d nuotao -c \"SELECT id, username, email, role, is_active FROM users;\" 2>/dev/null")
    print(stdout.read().decode())
    
    # 3. 用正确的方式重置密码
    print("\n=== 3. 重置管理员密码 ===")
    stdin, stdout, stderr = ssh.exec_command("""
cd /opt/nuotao/backend
.venv/bin/python -c "
import asyncio
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.user import User
from sqlalchemy import select, update

async def reset_password():
    async for db in get_db():
        result = await db.execute(select(User).where(User.email == 'admin@nuotao.com'))
        user = result.scalar_one_or_none()
        if user:
            hashed = get_password_hash('admin123')
            await db.execute(update(User).where(User.email == 'admin@nuotao.com').values(hashed_password=hashed))
            await db.commit()
            print(f'密码已重置为 admin123, 用户ID: {user.id}, 用户名: {user.username}')
        else:
            print('用户不存在')
        break

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
