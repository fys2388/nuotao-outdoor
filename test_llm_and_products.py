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
    
    # 1. 创建LLM测试脚本
    print("\n=== 1. 创建LLM测试脚本 ===")
    test_script = '''
import asyncio
from app.services.llm_gateway import complete, LLMRequest

async def test_llm():
    print("正在调用LLM...")
    req = LLMRequest(
        messages=[
            {"role": "system", "content": "你是一个简洁的助手，用一句话回答。"},
            {"role": "user", "content": "请用一句话介绍Nuotao Outdoor这个户外电商品牌。"}
        ],
        max_tokens=100,
        temperature=0.3,
    )
    try:
        resp = await complete(req)
        print("✅ LLM调用成功!")
        print(f"  供应商: {resp.provider}")
        print(f"  模型: {resp.model}")
        print(f"  耗时: {resp.latency_ms}ms")
        print(f"  Token: {resp.tokens.prompt}+{resp.tokens.completion}={resp.tokens.total}")
        print(f"  成本: ${resp.cost}")
        print(f"  回复: {resp.content[:200]}")
    except Exception as e:
        print(f"❌ LLM调用失败: {e}")

asyncio.run(test_llm())
'''
    sftp = ssh.open_sftp()
    with sftp.file('/tmp/test_llm.py', 'w') as f:
        f.write(test_script)
    sftp.close()
    print("测试脚本已创建")
    
    # 2. 执行LLM测试
    print("\n=== 2. 执行LLM测试 ===")
    stdin, stdout, stderr = ssh.exec_command("cd /opt/nuotao/backend && .venv/bin/python /tmp/test_llm.py")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    # 3. 检查产品分析师使用的数据表
    print("\n=== 3. 检查产品分析师数据来源 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -n 'products\\|product\\|Product' /opt/nuotao/backend/app/tasks/daily_agents.py | head -30")
    print(stdout.read().decode())
    
    # 4. 检查_get_product_stats函数
    print("\n=== 4. 检查_get_product_stats函数 ===")
    stdin, stdout, stderr = ssh.exec_command("grep -A 50 '_get_product_stats' /opt/nuotao/backend/app/tasks/daily_agents.py | head -60")
    print(stdout.read().decode())
    
    # 5. 检查数据库中的产品相关表
    print("\n=== 5. 数据库产品相关表数据量 ===")
    stdin, stdout, stderr = ssh.exec_command("""
PGPASSWORD=s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09 psql -h 127.0.0.1 -U nuotao -d nuotao -c "
SELECT table_name, n_live_tup 
FROM pg_stat_user_tables 
WHERE table_name LIKE '%product%' 
ORDER BY table_name;
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
