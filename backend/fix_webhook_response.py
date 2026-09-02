#!/usr/bin/env python3
"""修复 Webhook 返回值符合 response_model 格式"""

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    changes = 0

    # 空请求体：返回符合 WebhookResponse 格式
    old1 = '''        logger.info("webhook received: empty body (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "empty body accepted"}'''
    new1 = '''        logger.info("webhook received: empty body (WC test), trace=%s", trace_id)
        return {"status": "created", "order_id": None, "external_order_id": None, "trace_id": str(trace_id)}'''
    if old1 in content:
        content = content.replace(old1, new1)
        changes += 1

    # 无效 JSON
    old2 = '''        logger.warning("webhook received: invalid JSON (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "invalid JSON accepted"}'''
    new2 = '''        logger.warning("webhook received: invalid JSON (WC test), trace=%s", trace_id)
        return {"status": "created", "order_id": None, "external_order_id": None, "trace_id": str(trace_id)}'''
    if old2 in content:
        content = content.replace(old2, new2)
        changes += 1

    # 非对象
    old3 = '''        logger.warning("webhook received: non-object (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "non-object accepted"}'''
    new3 = '''        logger.warning("webhook received: non-object (WC test), trace=%s", trace_id)
        return {"status": "created", "order_id": None, "external_order_id": None, "trace_id": str(trace_id)}'''
    if old3 in content:
        content = content.replace(old3, new3)
        changes += 1

    if changes > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✅ {filepath} 修复完成 ({changes} 处)")
    else:
        print(f"  ⚠️  {filepath} 未找到匹配代码")

if __name__ == "__main__":
    base = "/opt/nuotao/backend/app/api/v1/endpoints"
    print("=== 修复 webhooks.py ===")
    fix_file(f"{base}/webhooks.py")
    print("\n完成！")
