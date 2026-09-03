"""M6 extra endpoints: listing localization + customer service templates.

These are the two "补强" modules that extend existing capabilities:
- Listing localization (extends SEO/content generation)
- Customer service templates (extends customer service)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.services.customer_template_service import (
    CustomerTemplateError,
    generate_customer_response,
    get_customer_template,
    get_customer_template_status,
    list_available_templates,
)
from app.services.listing_localization_service import (
    ListingLocalizationError,
    get_listing_localization_status,
    localize_listing,
    localize_listing_batch,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/m6-extras", tags=["M6 补强模块"])

DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")


# ============================================
# Schemas
# ============================================


class LocalizeListingRequest(BaseModel):
    product_name: str = Field(..., description="Source product name")
    source_listing: dict[str, Any] = Field(..., description="Source listing data")
    target_language: str = Field("en", description="Target language code")
    target_market: str | None = Field(None, description="Target market code")
    product_category: str | None = Field(None, description="Product category")
    additional_context: dict[str, Any] | None = None


class LocalizeListingBatchRequest(BaseModel):
    product_name: str
    source_listing: dict[str, Any]
    target_languages: list[str] = Field(..., description="List of target language codes")
    product_category: str | None = None


class CustomerTemplateRequest(BaseModel):
    category: str = Field(..., description="Template category")
    language: str = Field("en", description="Target language")
    variables: dict[str, str] | None = Field(None, description="Placeholder values")


class GenerateCustomerResponseRequest(BaseModel):
    customer_name: str
    customer_message: str
    order_id: str | None = None
    product_name: str | None = None
    language: str = Field("en", description="Response language")
    tone: str = Field("empathetic", description="Response tone")
    context: dict[str, Any] | None = None


# ============================================
# Listing localization endpoints
# ============================================


@router.get("/listing-localization/status", summary="多语言Listing本地化服务状态")
async def listing_localization_status() -> dict[str, Any]:
    return {"code": 0, "message": "success", "data": get_listing_localization_status()}


@router.post("/listing-localization/localize", summary="生成多语言本地化Listing")
async def localize_listing_endpoint(
    request: LocalizeListingRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = await localize_listing(
            db,
            workspace_id=DEFAULT_WORKSPACE,
            product_name=request.product_name,
            source_listing=request.source_listing,
            target_language=request.target_language,
            target_market=request.target_market,
            product_category=request.product_category,
            additional_context=request.additional_context,
        )
        return {"code": 0, "message": "success", "data": result}
    except ListingLocalizationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.exception("listing localization failed")
        raise HTTPException(status_code=500, detail=f"Localization failed: {e!s}") from None


@router.post("/listing-localization/batch", summary="批量生成多语言本地化Listing")
async def localize_listing_batch_endpoint(
    request: LocalizeListingBatchRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = await localize_listing_batch(
            db,
            workspace_id=DEFAULT_WORKSPACE,
            product_name=request.product_name,
            source_listing=request.source_listing,
            target_languages=request.target_languages,
            product_category=request.product_category,
        )
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        logger.exception("batch listing localization failed")
        raise HTTPException(status_code=500, detail=f"Batch localization failed: {e!s}") from None


# ============================================
# Customer template endpoints
# ============================================


@router.get("/customer-templates/status", summary="客服话术模板服务状态")
async def customer_template_status() -> dict[str, Any]:
    return {"code": 0, "message": "success", "data": get_customer_template_status()}


@router.get("/customer-templates/list", summary="列出可用客服话术模板")
async def list_customer_templates(
    language: str | None = Query(None, description="Filter by language"),
) -> dict[str, Any]:
    return {"code": 0, "message": "success", "data": list_available_templates(language)}


@router.post("/customer-templates/get", summary="获取并填充客服话术模板")
async def get_customer_template_endpoint(
    request: CustomerTemplateRequest,
) -> dict[str, Any]:
    try:
        result = get_customer_template(
            category=request.category,
            language=request.language,
            variables=request.variables,
        )
        return {"code": 0, "message": "success", "data": result}
    except CustomerTemplateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/customer-templates/generate", summary="LLM生成自定义客服回复")
async def generate_customer_response_endpoint(
    request: GenerateCustomerResponseRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = await generate_customer_response(
            db,
            workspace_id=DEFAULT_WORKSPACE,
            customer_name=request.customer_name,
            customer_message=request.customer_message,
            order_id=request.order_id,
            product_name=request.product_name,
            language=request.language,
            tone=request.tone,
            context=request.context,
        )
        return {"code": 0, "message": "success", "data": result}
    except CustomerTemplateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.exception("customer response generation failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {e!s}") from None
