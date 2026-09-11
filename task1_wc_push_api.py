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
    print("=" * 60)
    print("任务1：开发推送到WooCommerce API")
    print("=" * 60)
    
    print("\n正在连接服务器...")
    ssh.connect(hostname, port, username, password, timeout=30)
    print("SSH连接成功！")
    
    # 步骤1: 在woocommerce_sync_service.py末尾添加推送函数
    print("\n" + "=" * 60)
    print("步骤1: 添加推送函数到woocommerce_sync_service.py")
    print("=" * 60)
    
    push_function = '''


# ============================================================================ #
# 推送到 WooCommerce（Nuotao AI OS → WooCommerce）
# ============================================================================ #

async def push_product_to_woocommerce(product_id: str, db_session=None) -> dict:
    """将单个产品推送到 WooCommerce（创建或更新）。

    如果产品已有 woocommerce_id，则执行更新（PUT）；
    如果没有，则执行创建（POST），并将返回的 ID 写回本地数据库。

    Args:
        product_id: 本地产品 ID
        db_session: 可选的数据库会话（用于复用连接）

    Returns:
        推送结果字典，包含 success、woocommerce_id、action、error 等字段
    """
    import sys as _sys
    if "app.core.database" not in _sys.modules:
        from app.core.database import async_session_factory
    else:
        async_session_factory = _sys.modules["app.core.database"].async_session_factory
    from app.models.product import Product
    from sqlalchemy import select
    from uuid import UUID
    import requests as _requests

    async def _get_session():
        if db_session:
            return db_session
        return async_session_factory()

    session = await _get_session()
    own_session = db_session is None

    try:
        # 查找产品
        try:
            product = await session.get(Product, UUID(str(product_id)))
        except Exception:
            product = None

        if not product:
            return {"success": False, "error": f"产品不存在: {product_id}", "action": "none"}

        # 获取 WooCommerce ID
        wc_id = None
        if product.meta and isinstance(product.meta, dict):
            wc_id = product.meta.get("woocommerce_id")

        # 构建 WooCommerce 产品数据
        wc_product = {
            "name": product.name,
            "sku": product.sku,
            "status": "publish" if product.status == "active" else "draft",
            "description": product.description or "",
            "short_description": (product.description or "")[:200] if product.description else "",
        }

        # 添加价格（从 meta 中获取）
        if product.meta and isinstance(product.meta, dict):
            if product.meta.get("regular_price"):
                wc_product["regular_price"] = str(product.meta["regular_price"])
            if product.meta.get("sale_price"):
                wc_product["sale_price"] = str(product.meta["sale_price"])
            if product.meta.get("price"):
                wc_product["price"] = str(product.meta["price"])

        # 添加标签
        if product.tags and isinstance(product.tags, list):
            wc_product["tags"] = [{"name": t} for t in product.tags if t]

        # 添加分类
        if product.category:
            wc_product["categories"] = [{"name": product.category}]

        action = "update" if wc_id else "create"

        try:
            if wc_id:
                # 更新现有产品
                wc_url = f"{WC_URL}/wp-json/wc/v3/products/{wc_id}"
                logger.info("更新产品到 WooCommerce: PUT %s, sku=%s", wc_url, product.sku)

                resp = _requests.put(
                    wc_url,
                    auth=_get_wc_auth(),
                    headers=_get_wc_headers(),
                    json=wc_product,
                    timeout=30,
                )
                resp.raise_for_status()
                wc_result = resp.json()

            else:
                # 创建新产品
                wc_url = f"{WC_URL}/wp-json/wc/v3/products"
                logger.info("创建产品到 WooCommerce: POST %s, sku=%s", wc_url, product.sku)

                resp = _requests.post(
                    wc_url,
                    auth=_get_wc_auth(),
                    headers=_get_wc_headers(),
                    json=wc_product,
                    timeout=30,
                )
                resp.raise_for_status()
                wc_result = resp.json()

                # 将 WooCommerce ID 写回本地数据库
                new_wc_id = wc_result.get("id")
                if new_wc_id:
                    meta = product.meta or {}
                    meta["woocommerce_id"] = new_wc_id
                    meta["woocommerce_slug"] = wc_result.get("slug", "")
                    product.meta = meta
                    await session.commit()
                    wc_id = new_wc_id

            # 回读验证
            verify_url = f"{WC_URL}/wp-json/wc/v3/products/{wc_id}"
            verify_resp = _requests.get(
                verify_url,
                auth=_get_wc_auth(),
                headers=_get_wc_headers(),
                timeout=30,
            )
            verify_resp.raise_for_status()
            verified = verify_resp.json()

            return {
                "success": True,
                "action": action,
                "product_id": str(product.id),
                "sku": product.sku,
                "name": product.name,
                "woocommerce_id": wc_id,
                "woocommerce_url": verified.get("permalink", ""),
                "verified": verified.get("name") == product.name,
            }

        except _requests.exceptions.RequestException as e:
            logger.error("推送到 WooCommerce 失败: %s, error=%s", product.sku, str(e))
            return {
                "success": False,
                "action": action,
                "product_id": str(product.id),
                "sku": product.sku,
                "error": f"WooCommerce API 调用失败: {str(e)}",
            }

    finally:
        if own_session:
            await session.close()


async def batch_push_products_to_woocommerce(product_ids: list[str], db_session=None) -> dict:
    """批量推送产品到 WooCommerce。

    Args:
        product_ids: 产品 ID 列表
        db_session: 可选的数据库会话

    Returns:
        批量推送结果，包含 total、success、failed、results 等字段
    """
    results = []
    success_count = 0
    failed_count = 0

    for product_id in product_ids:
        result = await push_product_to_woocommerce(product_id, db_session)
        results.append(result)
        if result.get("success"):
            success_count += 1
        else:
            failed_count += 1

    return {
        "total": len(product_ids),
        "success": success_count,
        "failed": failed_count,
        "results": results,
    }
'''
    
    # 读取文件并追加
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/backend/app/services/woocommerce_sync_service.py', 'r') as f:
        content = f.read().decode('utf-8')
    sftp.close()
    
    # 检查是否已经有推送函数
    if 'push_product_to_woocommerce' not in content:
        content += push_function
        sftp = ssh.open_sftp()
        with sftp.file('/opt/nuotao/backend/app/services/woocommerce_sync_service.py', 'w') as f:
            f.write(content.encode('utf-8'))
        sftp.close()
        print("✅ 推送函数已添加")
    else:
        print("⚠️ 推送函数已存在，跳过")
    
    # 步骤2: 在products.py API中添加推送端点
    print("\n" + "=" * 60)
    print("步骤2: 添加推送API端点")
    print("=" * 60)
    
    # 读取products.py
    sftp = ssh.open_sftp()
    with sftp.file('/opt/nuotao/backend/app/api/v1/endpoints/products.py', 'r') as f:
        products_content = f.read().decode('utf-8')
    sftp.close()
    
    # 添加推送端点（在sync-woocommerce之后）
    push_endpoints = '''


@router.post(
    "/push-woocommerce",
    status_code=status.HTTP_200_OK,
    summary="批量推送产品到 WooCommerce / Push products to WooCommerce",
)
async def push_products_to_woocommerce(
    db: DbSession,
    workspace_id: WorkspaceId,
    body: dict = Body(default={}),
) -> dict:
    """批量推送产品到 WooCommerce。

    如果请求体中包含 product_ids，则推送指定产品；
    否则推送所有 active 状态的产品。
    """
    from app.services.woocommerce_sync_service import batch_push_products_to_woocommerce
    from app.models.product import Product
    from sqlalchemy import select

    try:
        product_ids = body.get("product_ids", [])

        if not product_ids:
            # 推送所有 active 产品
            rows = (await db.execute(
                select(Product.id).where(
                    Product.workspace_id == workspace_id,
                    Product.status == "active",
                )
            )).scalars().all()
            product_ids = [str(r) for r in rows]

        if not product_ids:
            return {"success": True, "total": 0, "success": 0, "failed": 0, "message": "没有需要推送的产品"}

        result = await batch_push_products_to_woocommerce(product_ids, db)
        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"推送到 WooCommerce 失败: {str(e)}",
        ) from e


@router.post(
    "/{product_id}/push-woocommerce",
    status_code=status.HTTP_200_OK,
    summary="推送单个产品到 WooCommerce / Push single product to WooCommerce",
)
async def push_single_product_to_woocommerce(
    product_id: str,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """推送单个产品到 WooCommerce（创建或更新）。"""
    from app.services.woocommerce_sync_service import push_product_to_woocommerce

    try:
        result = await push_product_to_woocommerce(product_id, db)
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "推送失败"),
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"推送到 WooCommerce 失败: {str(e)}",
        ) from e
'''
    
    # 检查是否需要导入Body
    if 'Body' not in products_content and 'from fastapi' in products_content:
        products_content = products_content.replace(
            'from fastapi import APIRouter, Depends, HTTPException, Query, status',
            'from fastapi import APIRouter, Body, Depends, HTTPException, Query, status'
        )
        print("✅ 已添加Body导入")
    
    # 添加推送端点
    if 'push-woocommerce' not in products_content:
        # 在文件末尾添加（在最后一个端点之后）
        products_content += push_endpoints
        sftp = ssh.open_sftp()
        with sftp.file('/opt/nuotao/backend/app/api/v1/endpoints/products.py', 'w') as f:
            f.write(products_content.encode('utf-8'))
        sftp.close()
        print("✅ 推送API端点已添加")
    else:
        print("⚠️ 推送API端点已存在，跳过")
    
    # 步骤3: 重启后端服务
    print("\n" + "=" * 60)
    print("步骤3: 重启后端服务")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("systemctl restart nuotao-backend && sleep 3 && systemctl is-active nuotao-backend")
    print(f"后端服务状态: {stdout.read().decode().strip()}")
    
    # 步骤4: 测试API
    print("\n" + "=" * 60)
    print("步骤4: 测试API")
    print("=" * 60)
    stdin, stdout, stderr = ssh.exec_command("""
curl -s -X POST http://127.0.0.1:8000/api/v1/products/push-woocommerce \
  -H "Content-Type: application/json" \
  -d '{"product_ids": []}' 2>&1 | head -20
""")
    print(f"批量推送API测试: {stdout.read().decode()[:500]}")
    
    print("\n" + "=" * 60)
    print("任务1完成：推送到WooCommerce API已开发！")
    print("=" * 60)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
    print("\nSSH连接已关闭")
