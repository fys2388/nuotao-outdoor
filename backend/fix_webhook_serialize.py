#!/usr/bin/env python3
"""修复 Webhook 返回值序列化问题"""

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    changes = 0

    # 替换所有包含 trace_id 的返回值为简单字符串
    old1 = '''        logger.info("webhook received: empty body (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "empty body accepted", "trace_id": trace_id}'''
    new1 = '''        logger.info("webhook received: empty body (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "empty body accepted"}'''
    if old1 in content:
        content = content.replace(old1, new1)
        changes += 1

    old2 = '''        logger.warning("webhook received: invalid JSON (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "invalid JSON accepted", "trace_id": trace_id}'''
    new2 = '''        logger.warning("webhook received: invalid JSON (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "invalid JSON accepted"}'''
    if old2 in content:
        content = content.replace(old2, new2)
        changes += 1

    old3 = '''        logger.warning("webhook received: non-object (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "non-object accepted", "trace_id": trace_id}'''
    new3 = '''        logger.warning("webhook received: non-object (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "non-object accepted"}'''
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
