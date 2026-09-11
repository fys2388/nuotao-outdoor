"""测试牛顿Agent创建订单能力
流程：找低价测试商品 → 确认商品信息 → 创建订单（不付款）
"""
import sys, os, json, time
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from app.services.newton_agent_service import await_result, create_agent_task, get_task_status

print("=" * 70)
print("测试1: 让牛顿Agent找一个低价测试商品")
print("=" * 70)

result1 = await_result(
    "帮我找一个1-5元的户外小用品，比如登山扣、钥匙扣、防风绳之类的，要现货，起订量1个的。只需要给我1个商品，包含：商品ID、商品名称、价格、起订量、商品链接。不要推荐多个，只要1个最便宜的。",
    max_wait=120
)

if result1.get("success"):
    print("\n牛顿Agent回复:")
    print(result1.get("content", "")[:2000])
else:
    print(f"失败: {result1.get('error')}")
    sys.exit(1)

print("\n" + "=" * 70)
print("测试2: 让牛顿Agent创建订单（不付款）")
print("=" * 70)
print("注意：创建订单后不付款，1688会在一定时间后自动关闭订单")
print()

# 等待用户确认
input("按Enter继续创建测试订单...")

result2 = await_result(
    "请帮我创建一个测试订单：购买刚才找到的那个商品，数量1个，收货地址用默认地址。创建订单后告诉我订单号和订单状态。注意：这是测试订单，不需要付款，创建后我会自己关闭。",
    max_wait=120
)

if result2.get("success"):
    print("\n牛顿Agent回复:")
    print(result2.get("content", "")[:3000])
else:
    print(f"失败: {result2.get('error')}")

print("\n" + "=" * 70)
print("测试完成")
print("=" * 70)
