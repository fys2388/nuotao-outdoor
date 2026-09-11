import paramiko

# SSH连接配置
hostname = "95.217.218.178"
port = 22
username = "root"
password = "4SqwD8k@vuXWYUE%!bkfyf1b"

# 创建SSH客户端
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 1. 创建测试脚本
    print("\n=== 1. 创建测试脚本 ===")
    test_script = '''
import asyncio
from app.core.database import async_session_factory
from app.tasks.daily_agents import run_product_analyst_daily, run_supply_chain_manager_daily

async def run():
    print("=" * 60)
    print("运行产品分析师每日任务...")
    print("=" * 60)
    async with async_session_factory() as session:
        result = await run_product_analyst_daily(session)
        print(f"结果: {result}")
    
    print()
    print("=" * 60)
    print("运行供应链经理每日任务...")
    print("=" * 60)
    async with async_session_factory() as session:
        result = await run_supply_chain_manager_daily(session)
        print(f"结果: {result}")

asyncio.run(run())
'''
    sftp = ssh.open_sftp()
    with sftp.file('/tmp/test_agents.py', 'w') as f:
        f.write(test_script)
    sftp.close()
    print("测试脚本已创建")
    
    # 2. 执行测试
    print("\n=== 2. 执行测试 ===")
    stdin, stdout, stderr = ssh.exec_command("cd /opt/nuotao/backend && .venv/bin/python /tmp/test_agents.py")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 3. 查看最新生成的建议
    print("\n=== 3. 最新生成的建议 ===")
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT id, agent_id, suggestion_type, title, status, priority, created_at 
FROM agent_suggestions 
ORDER BY created_at DESC 
LIMIT 15;
"
""")
    print(stdout.read().decode())
    
    # 4. 按Agent统计建议数量
    print("\n=== 4. 按Agent统计建议数量 ===")
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT agent_id, COUNT(*) as count, status 
FROM agent_suggestions 
GROUP BY agent_id, status 
ORDER BY agent_id, status;
"
""")
    print(stdout.read().decode())
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
