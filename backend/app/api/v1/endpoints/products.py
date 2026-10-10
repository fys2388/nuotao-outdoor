"""Product API endpoints (CSV import + listing)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.product import (
    ProductBatchDeleteRequest,
    ProductBatchIdsRequest,
    ProductDeleteResult,
    ProductImportResult,
    ProductOut,
    ProductPurgeResult,
    ProductRecycleBinOut,
    ProductRestoreResult,
)
from app.schemas.user import UserResponse
from app.services import product_service
from app.services.product_lifecycle_service import (
    BatchTooLargeError,
    list_recycled_products,
    purge_products,
    restore_products,
    unpublish_products,
)

router = APIRouter(prefix="/products", tags=["products 产品管理"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]
CurrentUser = Annotated[UserResponse, Depends(get_current_user)]

MAX_IMPORT_BYTES = 5 * 1024 * 1024  # 5 MiB


@router.post(
    "/import",
    response_model=ProductImportResult,
    status_code=status.HTTP_200_OK,
    summary="导入产品 / Import products from CSV",
)
async def import_products(
    file: UploadFile,
    _current_user: CurrentUser,
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
    _current_user: CurrentUser,
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


@router.get(
    "/recycle-bin",
    response_model=ProductRecycleBinOut,
    summary="回收站列表 / List recycled products",
)
async def list_recycle_bin(
    _current_user: CurrentUser,
    db: DbSession,
    workspace_id: WorkspaceId,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ProductRecycleBinOut:
    """列出已下架（在回收站）的商品，可按 ID 恢复或彻底删除。

    本路由必须定义在 ``GET /{product_id}`` **之前**：否则 ``recycle-bin`` 会被当作
    路径参数按 UUID 解析，直接返回 422，永远到不了这里。
    """
    rows, total = await list_recycled_products(
        db, workspace_id=workspace_id, limit=limit, offset=offset,
    )
    return ProductRecycleBinOut(
        items=[ProductOut.model_validate(row) for row in rows],
        total=total,
    )


@router.get("/{product_id}", response_model=ProductOut, summary="产品详情 / Get product by ID")
async def get_product(
    product_id: UUID,
    _current_user: CurrentUser,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductOut:
    """Get a single product by ID. 404 if not found."""
    row = await product_service.get_product(
        db,
        workspace_id=workspace_id,
        product_id=product_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductOut.model_validate(row)


@router.post(
    "/batch-delete",
    response_model=ProductDeleteResult,
    status_code=status.HTTP_200_OK,
    summary="批量下架到回收站（联动 WooCommerce）/ Batch move to recycle bin",
)
async def batch_delete_products(
    body: ProductBatchDeleteRequest,
    _current_user: CurrentUser,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductDeleteResult:
    """批量把商品移入回收站，并联动下架对应的 WooCommerce 商品。

    商品可随时恢复；要真正清除请用回收站的「彻底删除」。

    先下架 WooCommerce，成功后再标记本地回收站。若某个商品下架失败，默认整体返回
    409 且**不改变任何状态**，避免产生「系统里已进回收站、店铺仍在售」的幽灵商品；
    调用方可以带 ``force_local=true`` 表示「接受店铺未下架，仅处理本地」。
    """
    try:
        result = await unpublish_products(
            db,
            workspace_id=workspace_id,
            product_ids=body.product_ids,
            force_local=body.force_local,
            trace_id=get_trace_id(),
        )
    except BatchTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if result["blocked"]:
        # 409 而不是 200：下架确实没有发生，前端必须提示运营处理，不能显示"成功"。
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result)
    return ProductDeleteResult(**result)


@router.delete(
    "/{product_id}",
    response_model=ProductDeleteResult,
    status_code=status.HTTP_200_OK,
    summary="下架到回收站（联动 WooCommerce）/ Move one product to recycle bin",
)
async def delete_product(
    product_id: UUID,
    _current_user: CurrentUser,
    db: DbSession,
    workspace_id: WorkspaceId,
    force_local: bool = Query(
        default=False,
        description="WooCommerce 下架失败时仍然把本地移入回收站",
    ),
) -> ProductDeleteResult:
    """把单个商品移入回收站（可恢复），并联动下架 WooCommerce 商品。

    下架失败时返回 409 且不改变状态（可用 ``force_local=true`` 接受店铺未下架）。
    商品不存在或已在回收站时返回 404。
    """
    try:
        result = await unpublish_products(
            db,
            workspace_id=workspace_id,
            product_ids=[product_id],
            force_local=force_local,
            trace_id=get_trace_id(),
        )
    except BatchTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if result["blocked"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result)
    if result["deleted"] == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found",
        )
    return ProductDeleteResult(**result)


@router.post(
    "/{product_id}/restore",
    response_model=ProductRestoreResult,
    status_code=status.HTTP_200_OK,
    summary="从回收站恢复 / Restore one product from recycle bin",
)
async def restore_product(
    product_id: UUID,
    _current_user: CurrentUser,
    db: DbSession,
    workspace_id: WorkspaceId,
    force_local: bool = Query(
        default=False,
        description="WooCommerce 恢复失败时仍然把本地移出回收站",
    ),
) -> ProductRestoreResult:
    """把商品从回收站恢复，并还原 WooCommerce 可见性。

    WooCommerce 回收站默认约 30 天后会被 WordPress 自动清空；若商品已被清空，
    恢复会失败——本接口**不会**自动重建店铺商品，避免意外复活一个已下线的链接。
    """
    try:
        result = await restore_products(
            db,
            workspace_id=workspace_id,
            product_ids=[product_id],
            force_local=force_local,
            trace_id=get_trace_id(),
        )
    except BatchTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if result["blocked"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result)
    if result["restored"] == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"商品 {product_id} 不在回收站中",
        )
    return ProductRestoreResult(**result)


@router.post(
    "/restore",
    response_model=ProductRestoreResult,
    status_code=status.HTTP_200_OK,
    summary="批量从回收站恢复 / Batch restore products",
)
async def batch_restore_products(
    body: ProductBatchIdsRequest,
    _current_user: CurrentUser,
    db: DbSession,
    workspace_id: WorkspaceId,
    force_local: bool = Query(default=False),
) -> ProductRestoreResult:
    """批量把商品从回收站恢复。"""
    try:
        result = await restore_products(
            db,
            workspace_id=workspace_id,
            product_ids=body.product_ids,
            force_local=force_local,
            trace_id=get_trace_id(),
        )
    except BatchTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if result["blocked"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result)
    return ProductRestoreResult(**result)


@router.delete(
    "/{product_id}/purge",
    response_model=ProductPurgeResult,
    status_code=status.HTTP_200_OK,
    summary="彻底删除（不可逆）/ Permanently delete one product",
)
async def purge_product(
    product_id: UUID,
    _current_user: CurrentUser,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductPurgeResult:
    """彻底删除商品：本地记录硬删除 + WooCommerce 商品永久删除。**不可逆。**

    被 B2B 询价单 / B2B 订单 / 履约记录引用的商品会被数据库拒绝（结果里的 ``blocked``
    会说明原因），此时本地与 WooCommerce **都不会**被改动——有交易凭证的商品不可抹除。
    """
    try:
        result = await purge_products(
            db,
            workspace_id=workspace_id,
            product_ids=[product_id],
            trace_id=get_trace_id(),
        )
    except BatchTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if result["not_found"] and not result["purged"] and not result["blocked"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found",
        )
    return ProductPurgeResult(**result)


@router.post(
    "/purge",
    response_model=ProductPurgeResult,
    status_code=status.HTTP_200_OK,
    summary="批量彻底删除（不可逆）/ Batch permanently delete products",
)
async def batch_purge_products(
    body: ProductBatchIdsRequest,
    _current_user: CurrentUser,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductPurgeResult:
    """批量彻底删除商品。**不可逆**，会同时永久删除 WooCommerce 商品。"""
    try:
        result = await purge_products(
            db,
            workspace_id=workspace_id,
            product_ids=body.product_ids,
            trace_id=get_trace_id(),
        )
    except BatchTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return ProductPurgeResult(**result)


@router.post(
    "/sync-woocommerce",
    status_code=status.HTTP_200_OK,
    summary="从 WooCommerce 同步产品 / Sync products from WooCommerce",
)
async def sync_woocommerce_products(
    _current_user: CurrentUser,
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
