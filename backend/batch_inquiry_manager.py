# -*- coding: utf-8 -*-
"""
批量询盘管理工具
对接牛顿Agent批量询盘能力，实现供应商询价流程管理

功能:
1. 发起批量询盘（对多个1688商品ID）
2. 查询询盘状态和结果
3. 询盘策略配置（现货类/定制类）
4. 询盘记录管理（保存/查询/导出）

使用方法:
  python batch_inquiry_manager.py create --ids 123456,789012 --message "请问批发价和交期"
  python batch_inquiry_manager.py status --task-id xxx
  python batch_inquiry_manager.py list
  python batch_inquiry_manager.py strategy --type spot
"""
import sys
import os
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from app.services.newton_agent_service import (
    batch_inquiry,
    create_agent_task,
    get_task_status,
    await_result,
    is_configured,
)

# 询盘记录文件
INQUIRY_RECORDS_FILE = "data/inquiry_records.json"

# 询盘策略模板
INQUIRY_STRATEGIES = {
    "spot": {
        "name": "现货类策略",
        "questions": [
            "库存有多少？能否当天发货？",
            "裸价是多少？阶梯报价？",
            "支持哪些物流方式？运费多少？",
            "是否支持7天无理由退换？",
        ],
        "description": "先问库存和发货，再问价格，适合现货采购",
    },
    "custom": {
        "name": "定制类策略",
        "questions": [
            "打样周期多久？打样费多少？",
            "最小起订量(MOQ)是多少？",
            "支持哪些定制方式（LOGO/包装/颜色）？",
            "大货生产周期多久？阶梯报价？",
        ],
        "description": "先问打样和起订量，再谈阶梯价，适合OEM/ODM定制",
    },
    "standard": {
        "name": "标准策略",
        "questions": [
            "批发价是多少？阶梯报价？",
            "最小起订量(MOQ)是多少？",
            "交货周期多久？",
            "是否支持OEM/ODM定制？",
        ],
        "description": "标准四问：价格、起订量、交期、定制",
    },
}


def load_records() -> list[dict]:
    """加载询盘记录"""
    if os.path.exists(INQUIRY_RECORDS_FILE):
        with open(INQUIRY_RECORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_records(records: list[dict]):
    """保存询盘记录"""
    os.makedirs(os.path.dirname(INQUIRY_RECORDS_FILE), exist_ok=True)
    with open(INQUIRY_RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def create_inquiry(product_ids: list[str], message: str, strategy: str = "standard") -> dict:
    """
    发起批量询盘

    Args:
        product_ids: 1688商品ID列表
        message: 询盘内容
        strategy: 询盘策略类型（spot/custom/standard）

    Returns:
        询盘结果
    """
    print(f"发起批量询盘...")
    print(f"  商品数量: {len(product_ids)}")
    print(f"  商品ID: {', '.join(product_ids)}")
    print(f"  策略: {INQUIRY_STRATEGIES.get(strategy, {}).get('name', strategy)}")
    print(f"  询盘内容: {message}")
    print()

    # 如果选择了策略，追加策略问题
    if strategy in INQUIRY_STRATEGIES:
        strategy_questions = INQUIRY_STRATEGIES[strategy]["questions"]
        full_message = message + "\n\n请按以下问题逐一询问：\n"
        for i, q in enumerate(strategy_questions, 1):
            full_message += f"{i}. {q}\n"
    else:
        full_message = message

    # 调用批量询盘
    result = batch_inquiry(product_ids, full_message)

    # 保存记录
    records = load_records()
    record = {
        "id": f"inquiry_{int(datetime.now().timestamp())}",
        "created_at": datetime.now().isoformat(),
        "product_ids": product_ids,
        "message": message,
        "strategy": strategy,
        "task_id": result.get("result", {}).get("task_id", ""),
        "status": result.get("result", {}).get("status", "created"),
        "result": result,
    }
    records.append(record)
    save_records(records)

    print(f"询盘发起结果:")
    print(f"  成功: {result.get('success')}")
    print(f"  询盘数量: {result.get('inquiry_count')}")
    if result.get("result"):
        r = result["result"]
        print(f"  状态: {r.get('status')}")
        print(f"  任务ID: {r.get('task_id')}")
        content = r.get("content", "")
        if content:
            print(f"  返回内容: {content[:300]}")

    print(f"\n询盘记录ID: {record['id']}")
    print(f"提示: 商家回复一般需要时间，可用 'python batch_inquiry_manager.py status --record-id {record['id']}' 查询结果")

    return result


def query_inquiry_status(record_id: str = None, task_id: str = None) -> dict:
    """查询询盘状态和结果"""
    records = load_records()

    if record_id:
        record = next((r for r in records if r["id"] == record_id), None)
        if not record:
            print(f"未找到询盘记录: {record_id}")
            return {}
        task_id = record.get("task_id")

    if not task_id:
        print("请提供 --record-id 或 --task-id")
        return {}

    print(f"查询询盘状态...")
    print(f"  任务ID: {task_id}")

    # 查询任务状态
    status = get_task_status(task_id)
    print(f"  状态: {status.get('status')}")

    raw = status.get("raw", {})
    content = raw.get("content", "")
    if content:
        print(f"  内容长度: {len(content)}")
        print(f"  内容预览: {content[:500]}")

    # 更新记录
    if record_id:
        for r in records:
            if r["id"] == record_id:
                r["status"] = status.get("status")
                r["last_updated"] = datetime.now().isoformat()
                save_records(records)
                break

    return status


def list_inquiries(limit: int = 10) -> list[dict]:
    """列出询盘记录"""
    records = load_records()
    print(f"询盘记录（共{len(records)}条，显示最近{limit}条）:")
    print("-" * 80)
    for r in records[-limit:][::-1]:
        print(f"ID: {r['id']}")
        print(f"  时间: {r['created_at'][:19]}")
        print(f"  商品: {len(r['product_ids'])}个 - {', '.join(r['product_ids'][:3])}")
        print(f"  策略: {r.get('strategy', 'N/A')}")
        print(f"  状态: {r.get('status', 'N/A')}")
        print(f"  任务ID: {r.get('task_id', 'N/A')}")
        print()
    return records


def show_strategy(strategy_type: str = None):
    """显示询盘策略"""
    if strategy_type:
        if strategy_type in INQUIRY_STRATEGIES:
            s = INQUIRY_STRATEGIES[strategy_type]
            print(f"策略: {s['name']}")
            print(f"描述: {s['description']}")
            print("问题列表:")
            for i, q in enumerate(s["questions"], 1):
                print(f"  {i}. {q}")
        else:
            print(f"未找到策略: {strategy_type}")
            print(f"可用策略: {', '.join(INQUIRY_STRATEGIES.keys())}")
    else:
        print("可用询盘策略:")
        print("-" * 60)
        for key, s in INQUIRY_STRATEGIES.items():
            print(f"[{key}] {s['name']}")
            print(f"  描述: {s['description']}")
            print(f"  问题数: {len(s['questions'])}")
            print()


def main():
    parser = argparse.ArgumentParser(description="批量询盘管理工具")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # create命令
    create_parser = subparsers.add_parser("create", help="发起批量询盘")
    create_parser.add_argument("--ids", required=True, help="商品ID列表，逗号分隔")
    create_parser.add_argument("--message", default="请问批发价、起订量、交货周期是多少？", help="询盘内容")
    create_parser.add_argument("--strategy", default="standard", choices=["spot", "custom", "standard"], help="询盘策略")

    # status命令
    status_parser = subparsers.add_parser("status", help="查询询盘状态")
    status_parser.add_argument("--record-id", help="询盘记录ID")
    status_parser.add_argument("--task-id", help="任务ID")

    # list命令
    list_parser = subparsers.add_parser("list", help="列出询盘记录")
    list_parser.add_argument("--limit", type=int, default=10, help="显示数量")

    # strategy命令
    strategy_parser = subparsers.add_parser("strategy", help="查看询盘策略")
    strategy_parser.add_argument("--type", help="策略类型（spot/custom/standard）")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "create":
        product_ids = [x.strip() for x in args.ids.split(",") if x.strip()]
        create_inquiry(product_ids, args.message, args.strategy)
    elif args.command == "status":
        query_inquiry_status(args.record_id, args.task_id)
    elif args.command == "list":
        list_inquiries(args.limit)
    elif args.command == "strategy":
        show_strategy(args.type)


if __name__ == "__main__":
    main()
