"""Product API endpoints (CSV import + listing)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
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
