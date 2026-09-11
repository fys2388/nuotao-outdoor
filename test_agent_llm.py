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
    
    # 1. 直接测试LLM网关
    print("\n=== 1. 测试LLM网关 ===")
    stdin, stdout, stderr = ssh.exec_command("""
cd /opt/nuotao/backend
.venv/bin/python -c "
import asyncio
from app.services.llm_gateway import complete, LLMRequest

async def test_llm():
    print('正在调用LLM...')
    req = LLMRequest(
        messages=[
            {'role': 'system', 'content': '你是一个简洁的助手，用一句话回答。'},
            {'role': 'user', 'content': '请用一句话介绍Nuotao Outdoor这个户外电商品牌。'}
        ],
        max_tokens=100,
        temperature=0.3,
    )
    try:
        resp = await complete(req)
        print(f'✅ LLM调用成功!')
        print(f'  供应商: {resp.provider}')
        print(f'  模型: {resp.model}')
        print(f'  耗时: {resp.latency_ms}ms')
        print(f'  Token: {resp.tokens.prompt}+{resp.tokens.completion}={resp.tokens.total}')
        print(f'  成本: ${resp.cost}')
        print(f'  回复: {resp.content[:200]}')
    except Exception as e:
        print(f'❌ LLM调用失败: {e}')

asyncio.run(test_llm())
"
""")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 2. 手动触发产品分析师每日任务
    print("\n=== 2. 手动触发产品分析师每日任务 ===")
    stdin, stdout, stderr = ssh.exec_command("""
cd /opt/nuotao/backend
.venv/bin/python -c "
import asyncio
from app.core.database import async_session_factory
from app.tasks.daily_agents import run_product_analyst_daily

async def run():
    print('正在运行产品分析师每日任务...')
    async with async_session_factory() as session:
        result = await run_product_analyst_daily(session)
        print(f'结果: {result}')

asyncio.run(run())
"
""")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 3. 手动触发营销经理每日任务
    print("\n=== 3. 手动触发营销经理每日任务 ===")
    stdin, stdout, stderr = ssh.exec_command("""
cd /opt/nuotao/backend
.venv/bin/python -c "
import asyncio
from app.core.database import async_session_factory
from app.tasks.daily_agents import run_marketing_manager_daily

async def run():
    print('正在运行营销经理每日任务...')
    async with async_session_factory() as session:
        result = await run_marketing_manager_daily(session)
        print(f'结果: {result}')

asyncio.run(run())
"
""")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 4. 查看最新生成的建议
    print("\n=== 4. 最新生成的建议 ===")
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT id, agent_id, suggestion_type, title, status, created_at 
FROM agent_suggestions 
ORDER BY created_at DESC 
LIMIT 10;
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
