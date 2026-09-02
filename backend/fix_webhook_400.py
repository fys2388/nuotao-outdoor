#!/usr/bin/env python3
"""修复 Webhook 端点的 400 错误，使空/无效请求体返回 200"""
import sys

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    changes = 0

    # 1. 空请求体：400 -> 200
    old1 = '''    body = await request.body()
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty request body")'''
    new1 = '''    body = await request.body()
    if not body:
        logger.info("webhook received: empty body (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "empty body accepted", "trace_id": trace_id}'''
    if old1 in content:
        content = content.replace(old1, new1)
        changes += 1
        print(f"  - 空请求体处理已修改")

    # 2. JSON 解析失败：400 -> 200
    old2 = '''    try:
        raw = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning("webhook rejected: invalid JSON trace=%s", trace_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="payload must be valid JSON"
        ) from exc'''
    new2 = '''    try:
        raw = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning("webhook received: invalid JSON (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "invalid JSON accepted", "trace_id": trace_id}'''
    if old2 in content:
        content = content.replace(old2, new2)
        changes += 1
        print(f"  - JSON解析失败处理已修改")

    # 3. 非 dict 检查：400 -> 200（仅 webhooks.py）
    old3 = '''    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload must be a JSON object",
        )'''
    new3 = '''    if not isinstance(raw, dict):
        logger.warning("webhook received: non-object (WC test), trace=%s", trace_id)
        return {"status": "accepted", "message": "non-object accepted", "trace_id": trace_id}'''
    if old3 in content:
        content = content.replace(old3, new3)
        changes += 1
        print(f"  - 非对象检查已修改")

    if changes > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✅ {filepath} 修改完成 ({changes} 处)")
    else:
        print(f"  ⚠️  {filepath} 未找到匹配的代码（可能已修改）")

if __name__ == "__main__":
    base = "/opt/nuotao/backend/app/api/v1/endpoints"
    print("=== 修改 webhooks.py ===")
    fix_file(f"{base}/webhooks.py")
    print("\n=== 修改 webhooks_generic.py ===")
    fix_file(f"{base}/webhooks_generic.py")
    print("\n完成！")
