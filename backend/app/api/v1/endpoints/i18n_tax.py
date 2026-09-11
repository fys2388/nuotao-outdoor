"""
国际化和税务 API 端点
支持多币种转换、多语言、美国销售税、欧盟 VAT/IOSS
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.i18n_service import (
    convert_currency,
    format_price,
    get_i18n_status,
    get_locale_for_country,
    get_supported_currencies,
    get_supported_languages,
)
from app.services.tax_service import (
    calculate_tax,
    get_tax_compliance_status,
    get_tax_rates,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/i18n-tax", tags=["i18n-tax"])


# ============================================
# 请求/响应模型
# ============================================

class CurrencyConversionRequest(BaseModel):
    """货币转换请求"""
    amount: float = Field(..., description="金额", gt=0)
    from_currency: str = Field(..., description="源货币代码（USD/EUR/GBP等）")
    to_currency: str = Field(..., description="目标货币代码")


class TaxCalculationRequest(BaseModel):
    """税务计算请求"""
    amount: float = Field(..., description="应税金额", gt=0)
    country_code: str = Field(..., description="国家代码（US/DE/FR等）")
    state_code: str | None = Field(None, description="州代码（美国必填）")
    use_reduced_rate: bool = Field(False, description="是否使用降低税率（欧盟）")
    is_import: bool = Field(False, description="是否为进口（影响 IOSS）")


# ============================================
# API 端点 - 国际化
# ============================================

@router.get(
    "/i18n/status",
    summary="获取国际化服务状态",
)
async def get_i18n_service_status() -> dict[str, Any]:
    """获取国际化服务状态和配置"""
    return get_i18n_status()


@router.get(
    "/i18n/currencies",
    summary="获取支持的货币列表",
)
async def list_currencies() -> dict[str, Any]:
    """获取所有支持的货币和汇率"""
    currencies = get_supported_currencies()
    return {
        "currencies": currencies,
        "total": len(currencies),
        "base_currency": "USD",
    }


@router.get(
    "/i18n/languages",
    summary="获取支持的语言列表",
)
async def list_languages() -> dict[str, Any]:
    """获取所有支持的语言"""
    languages = get_supported_languages()
    return {
        "languages": languages,
        "total": len(languages),
        "default_language": "en",
    }


@router.post(
    "/i18n/convert-currency",
    summary="货币转换",
)
async def convert_currency_endpoint(request: CurrencyConversionRequest) -> dict[str, Any]:
    """
    货币转换

    支持 USD、EUR、GBP、CAD、AUD 等货币之间的转换。
    汇率为静态汇率，生产环境应使用实时汇率 API。
    """
    try:
        result = convert_currency(
            amount=request.amount,
            from_currency=request.from_currency.upper(),
            to_currency=request.to_currency.upper(),
        )
        return {
            "success": True,
            "original_amount": request.amount,
            "from_currency": request.from_currency.upper(),
            "to_currency": request.to_currency.upper(),
            "converted_amount": float(result),
            "formatted_result": format_price(result, request.to_currency.upper()),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/i18n/locale/{country_code}",
    summary="获取国家默认区域设置",
)
async def get_country_locale(country_code: str) -> dict[str, Any]:
    """获取国家对应的默认货币和语言"""
    locale = get_locale_for_country(country_code)
    return {
        "country_code": country_code.upper(),
        "currency": locale["currency"],
        "language": locale["language"],
    }


# ============================================
# API 端点 - 税务
# ============================================

@router.get(
    "/tax/status",
    summary="获取税务合规服务状态",
)
async def get_tax_service_status() -> dict[str, Any]:
    """获取税务合规服务状态和配置"""
    return get_tax_compliance_status()


@router.get(
    "/tax/rates",
    summary="获取税率配置",
)
async def get_all_tax_rates() -> dict[str, Any]:
    """获取所有税率配置（美国销售税、欧盟 VAT、IOSS）"""
    return get_tax_rates()


@router.post(
    "/tax/calculate",
    summary="统一税务计算",
)
async def calculate_tax_endpoint(request: TaxCalculationRequest) -> dict[str, Any]:
    """
    统一税务计算入口

    支持：
    - 美国销售税（按州，含地方税估算）
    - 欧盟 VAT（标准税率/降低税率）
    - 欧盟 IOSS（进口订单低于 €150）
    - 其他国家/地区（默认无税）
    """
    try:
        result = calculate_tax(
            amount=request.amount,
            country_code=request.country_code,
            state_code=request.state_code,
            use_reduced_rate=request.use_reduced_rate,
            is_import=request.is_import,
        )
        return {
            "success": True,
            "request": request.model_dump(),
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/tax/us/states",
    summary="获取美国各州销售税率",
)
async def get_us_state_tax_rates(state: str | None = None) -> dict[str, Any]:
    """获取美国各州销售税率（可按州筛选）"""
    from app.services.tax_service import US_STATE_SALES_TAX, US_TAX_FREE_STATES

    if state:
        state_upper = state.upper()
        if state_upper not in US_STATE_SALES_TAX:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"State not found: {state}",
            )
        state_info = US_STATE_SALES_TAX[state_upper]
        return {
            "state": state_upper,
            "name": state_info["name"],
            "state_rate": state_info["rate"],
            "has_local_tax": state_info["has_local_tax"],
            "is_tax_free": state_upper in US_TAX_FREE_STATES,
        }

    states = [
        {
            "code": code,
            "name": info["name"],
            "state_rate": info["rate"],
            "has_local_tax": info["has_local_tax"],
            "is_tax_free": code in US_TAX_FREE_STATES,
        }
        for code, info in sorted(US_STATE_SALES_TAX.items())
    ]
    return {
        "states": states,
        "total": len(states),
        "tax_free_states": US_TAX_FREE_STATES,
    }


@router.get(
    "/tax/eu/countries",
    summary="获取欧盟各国 VAT 税率",
)
async def get_eu_vat_rates(country: str | None = None) -> dict[str, Any]:
    """获取欧盟各国 VAT 税率（可按国家筛选）"""
    from app.services.tax_service import EU_VAT_RATES

    if country:
        country_upper = country.upper()
        if country_upper not in EU_VAT_RATES:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Country not found: {country}",
            )
        country_info = EU_VAT_RATES[country_upper]
        return {
            "country": country_upper,
            "name": country_info["name"],
            "standard_rate": country_info["rate"],
            "reduced_rate": country_info["reduced_rate"],
        }

    countries = [
        {
            "code": code,
            "name": info["name"],
            "standard_rate": info["rate"],
            "reduced_rate": info["reduced_rate"],
        }
        for code, info in sorted(EU_VAT_RATES.items())
    ]
    return {
        "countries": countries,
        "total": len(countries),
    }
