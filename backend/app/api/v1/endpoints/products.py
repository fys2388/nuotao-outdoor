"""Product API endpoints (CSV import + listing)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.workspace import get_workspace_id
from app.schemas.product import ProductImportResult, ProductOut
from app.services import product_service

router = APIRouter(prefix="/products", tags=["products 产品管理"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]

MAX_IMPORT_BYTES = 5 * 1024 * 1024  # 5 MiB


@router.post(
    "/import",
    response_model=ProductImportResult,
    status_code=status.HTTP_200_OK,
    summary="导入产品 / Import products from CSV",
)
async def import_products(
    file: UploadFile,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductImportResult:
    """Import product base data from a UTF-8 CSV file (upsert by sku).

    Accepted columns: ``sku, name, description, category, brand, tags,
    attributes, source_url, supplier_code``. ``tags`` is semicolon-separated;
    ``attributes`` is a JSON object; ``supplier_code`` must exist in suppliers.
    """
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="CSV file exceeds the 5 MiB limit",
        )
    try:
        csv_text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must be UTF-8 encoded",
        ) from exc

    try:
        return await product_service.import_products(
            db,
            workspace_id=workspace_id,
            csv_content=csv_text,
        )
    except product_service.ProductImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[ProductOut], summary="产品列表 / List products")
async def list_products(
    db: DbSession,
    workspace_id: WorkspaceId,
    status: str | None = Query(default=None, max_length=24),
    category: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ProductOut]:
    """List products for the workspace, newest first."""
    rows, _total = await product_service.list_products(
        db,
        workspace_id=workspace_id,
        status=status,
        category=category,
        limit=limit,
        offset=offset,
    )
    return [ProductOut.model_validate(row) for row in rows]



@router.post(
    "/sync-woocommerce",
    status_code=status.HTTP_200_OK,
    summary="从 WooCommerce 同步产品 / Sync products from WooCommerce",
)
async def sync_woocommerce_products(
    db: DbSession,
    workspace_id: WorkspaceId,
    per_page: int = Query(default=100, ge=1, le=100),
    max_pages: int | None = Query(default=None, ge=1),
) -> dict:
    """从 WooCommerce 同步产品到本地数据库（upsert by workspace + sku）。"""
    from app.services.woocommerce_sync_service import sync_products_to_db

    try:
        result = await sync_products_to_db(
            db,
            workspace_id=workspace_id,
            per_page=per_page,
            max_pages=max_pages,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"WooCommerce 产品同步失败: {str(e)}",
        ) from e



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
