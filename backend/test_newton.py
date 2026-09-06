#!/usr/bin/env python3
"""使用牛顿云API真实创建选品任务"""
import sys
import os
sys.path.insert(0, '/opt/nuotao/backend')

# 手动加载.env文件
env_path = '/opt/nuotao/backend/.env'
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

from app.services.newton_agent_service import (
    is_configured, create_agent_task, get_task_status,
    fetch_task_result, await_result, newton_agent_search
)
import json
import time

print(f"牛顿云API已配置: {is_configured()}")

# 使用newton_agent_search高层封装
print("\n=== 牛顿AI智能找品 ===")
print("查询: 户外头灯，价格5-20元，起订量1-100件")

try:
    result = newton_agent_search(
        query="户外头灯",
        min_price=5,
        max_price=20,
        min_order_qty=1,
        category="照明电筒",
        auto=True
    )

    print(f"\n任务完成!")
    print(f"任务ID: {result.get('task_id')}")
    print(f"状态: {result.get('status')}")

    # 打印结果摘要
    data = result.get('data', {})
    if isinstance(data, str):
        print(f"结果摘要: {data[:500]}")
    elif isinstance(data, dict):
        print(f"结果keys: {list(data.keys())}")
        # 尝试提取产品列表
        products = data.get('products', data.get('items', data.get('result', [])))
        if products:
            print(f"\n找到 {len(products)} 个产品:")
            for i, p in enumerate(products[:5]):
                if isinstance(p, dict):
                    title = p.get('title', p.get('subject', p.get('name', 'N/A')))
                    price = p.get('price', p.get('priceRange', 'N/A'))
                    print(f"  {i+1}. {title[:60]} - 价格: {price}")
                else:
                    print(f"  {i+1}. {str(p)[:100]}")

    # 保存完整结果到文件
    with open('/opt/nuotao/backend/newton_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n完整结果已保存到: /opt/nuotao/backend/newton_result.json")

except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
