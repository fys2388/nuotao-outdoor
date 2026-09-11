"""
税务合规服务
支持美国销售税计算、欧盟 IOSS、增值税计算
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

logger = logging.getLogger(__name__)

# 美国各州销售税率（简化版，实际包含州税+地方税）
# 基准日期：2026-09-01
US_STATE_SALES_TAX = {
    "AL": {"rate": 0.0400, "name": "Alabama", "has_local_tax": True},
    "AK": {"rate": 0.0000, "name": "Alaska", "has_local_tax": True},
    "AZ": {"rate": 0.0560, "name": "Arizona", "has_local_tax": True},
    "AR": {"rate": 0.0650, "name": "Arkansas", "has_local_tax": True},
    "CA": {"rate": 0.0725, "name": "California", "has_local_tax": True},
    "CO": {"rate": 0.0290, "name": "Colorado", "has_local_tax": True},
    "CT": {"rate": 0.0635, "name": "Connecticut", "has_local_tax": False},
    "DE": {"rate": 0.0000, "name": "Delaware", "has_local_tax": False},
    "FL": {"rate": 0.0600, "name": "Florida", "has_local_tax": True},
    "GA": {"rate": 0.0400, "name": "Georgia", "has_local_tax": True},
    "HI": {"rate": 0.0400, "name": "Hawaii", "has_local_tax": True},
    "ID": {"rate": 0.0600, "name": "Idaho", "has_local_tax": True},
    "IL": {"rate": 0.0625, "name": "Illinois", "has_local_tax": True},
    "IN": {"rate": 0.0700, "name": "Indiana", "has_local_tax": False},
    "IA": {"rate": 0.0600, "name": "Iowa", "has_local_tax": True},
    "KS": {"rate": 0.0650, "name": "Kansas", "has_local_tax": True},
    "KY": {"rate": 0.0600, "name": "Kentucky", "has_local_tax": False},
    "LA": {"rate": 0.0445, "name": "Louisiana", "has_local_tax": True},
    "ME": {"rate": 0.0550, "name": "Maine", "has_local_tax": False},
    "MD": {"rate": 0.0600, "name": "Maryland", "has_local_tax": False},
    "MA": {"rate": 0.0625, "name": "Massachusetts", "has_local_tax": False},
    "MI": {"rate": 0.0600, "name": "Michigan", "has_local_tax": False},
    "MN": {"rate": 0.0688, "name": "Minnesota", "has_local_tax": True},
    "MS": {"rate": 0.0700, "name": "Mississippi", "has_local_tax": True},
    "MO": {"rate": 0.0423, "name": "Missouri", "has_local_tax": True},
    "MT": {"rate": 0.0000, "name": "Montana", "has_local_tax": True},
    "NE": {"rate": 0.0550, "name": "Nebraska", "has_local_tax": True},
    "NV": {"rate": 0.0685, "name": "Nevada", "has_local_tax": True},
    "NH": {"rate": 0.0000, "name": "New Hampshire", "has_local_tax": True},
    "NJ": {"rate": 0.0663, "name": "New Jersey", "has_local_tax": False},
    "NM": {"rate": 0.0513, "name": "New Mexico", "has_local_tax": True},
    "NY": {"rate": 0.0400, "name": "New York", "has_local_tax": True},
    "NC": {"rate": 0.0475, "name": "North Carolina", "has_local_tax": True},
    "ND": {"rate": 0.0500, "name": "North Dakota", "has_local_tax": True},
    "OH": {"rate": 0.0575, "name": "Ohio", "has_local_tax": True},
    "OK": {"rate": 0.0450, "name": "Oklahoma", "has_local_tax": True},
    "OR": {"rate": 0.0000, "name": "Oregon", "has_local_tax": False},
    "PA": {"rate": 0.0600, "name": "Pennsylvania", "has_local_tax": True},
    "RI": {"rate": 0.0700, "name": "Rhode Island", "has_local_tax": False},
    "SC": {"rate": 0.0600, "name": "South Carolina", "has_local_tax": True},
    "SD": {"rate": 0.0450, "name": "South Dakota", "has_local_tax": True},
    "TN": {"rate": 0.0700, "name": "Tennessee", "has_local_tax": True},
    "TX": {"rate": 0.0625, "name": "Texas", "has_local_tax": True},
    "UT": {"rate": 0.0610, "name": "Utah", "has_local_tax": True},
    "VT": {"rate": 0.0600, "name": "Vermont", "has_local_tax": True},
    "VA": {"rate": 0.0530, "name": "Virginia", "has_local_tax": True},
    "WA": {"rate": 0.0650, "name": "Washington", "has_local_tax": True},
    "WV": {"rate": 0.0600, "name": "West Virginia", "has_local_tax": True},
    "WI": {"rate": 0.0500, "name": "Wisconsin", "has_local_tax": True},
    "WY": {"rate": 0.0400, "name": "Wyoming", "has_local_tax": True},
    "DC": {"rate": 0.0600, "name": "District of Columbia", "has_local_tax": False},
}

# 欧盟国家增值税率（VAT）
# 基准日期：2026-09-01
EU_VAT_RATES = {
    "DE": {"rate": 0.19, "name": "Germany", "reduced_rate": 0.07},
    "FR": {"rate": 0.20, "name": "France", "reduced_rate": 0.055},
    "IT": {"rate": 0.22, "name": "Italy", "reduced_rate": 0.05},
    "ES": {"rate": 0.21, "name": "Spain", "reduced_rate": 0.10},
    "NL": {"rate": 0.21, "name": "Netherlands", "reduced_rate": 0.09},
    "BE": {"rate": 0.21, "name": "Belgium", "reduced_rate": 0.06},
    "AT": {"rate": 0.20, "name": "Austria", "reduced_rate": 0.10},
    "PT": {"rate": 0.23, "name": "Portugal", "reduced_rate": 0.06},
    "GR": {"rate": 0.24, "name": "Greece", "reduced_rate": 0.06},
    "IE": {"rate": 0.23, "name": "Ireland", "reduced_rate": 0.09},
    "FI": {"rate": 0.255, "name": "Finland", "reduced_rate": 0.10},
    "SE": {"rate": 0.25, "name": "Sweden", "reduced_rate": 0.06},
    "DK": {"rate": 0.25, "name": "Denmark", "reduced_rate": 0.0},
    "PL": {"rate": 0.23, "name": "Poland", "reduced_rate": 0.05},
    "CZ": {"rate": 0.21, "name": "Czech Republic", "reduced_rate": 0.10},
    "HU": {"rate": 0.27, "name": "Hungary", "reduced_rate": 0.05},
    "RO": {"rate": 0.19, "name": "Romania", "reduced_rate": 0.05},
    "BG": {"rate": 0.20, "name": "Bulgaria", "reduced_rate": 0.09},
    "HR": {"rate": 0.25, "name": "Croatia", "reduced_rate": 0.05},
    "SK": {"rate": 0.23, "name": "Slovakia", "reduced_rate": 0.10},
    "SI": {"rate": 0.22, "name": "Slovenia", "reduced_rate": 0.095},
    "LT": {"rate": 0.21, "name": "Lithuania", "reduced_rate": 0.05},
    "LV": {"rate": 0.21, "name": "Latvia", "reduced_rate": 0.05},
    "EE": {"rate": 0.22, "name": "Estonia", "reduced_rate": 0.09},
    "LU": {"rate": 0.17, "name": "Luxembourg", "reduced_rate": 0.08},
    "MT": {"rate": 0.18, "name": "Malta", "reduced_rate": 0.05},
    "CY": {"rate": 0.19, "name": "Cyprus", "reduced_rate": 0.05},
}

# IOSS（进口一站式服务）配置
IOSS_CONFIG = {
    "enabled": True,
    "threshold_eur": 150.0,  # 低于 150 欧元的订单使用 IOSS
    "ioss_number": "IM1234567890",  # 示例 IOSS 号码
    "description": "EU Import One-Stop Shop (IOSS) for orders under €150",
}

# 免税州（美国）
US_TAX_FREE_STATES = ["AK", "DE", "MT", "NH", "OR"]


def calculate_us_sales_tax(
    amount: Decimal | float | str,
    state_code: str,
    include_local_tax_estimate: bool = True,
) -> dict[str, Any]:
    """
    计算美国销售税

    Args:
        amount: 应税金额
        state_code: 州代码（如 CA、NY）
        include_local_tax_estimate: 是否包含地方税估算

    Returns:
        包含税额、税率、明细的字典
    """
    state_upper = state_code.upper()
    if state_upper not in US_STATE_SALES_TAX:
        raise ValueError(f"Unsupported US state: {state_code}")

    state_info = US_STATE_SALES_TAX[state_upper]
    state_rate = Decimal(str(state_info["rate"]))

    # 地方税估算（平均 1.5%，实际因城市而异）
    local_rate = Decimal("0.015") if include_local_tax_estimate and state_info["has_local_tax"] else Decimal("0")
    total_rate = state_rate + local_rate

    amount_decimal = Decimal(str(amount))
    tax_amount = (amount_decimal * total_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_amount = amount_decimal + tax_amount

    return {
        "country": "US",
        "state": state_upper,
        "state_name": state_info["name"],
        "tax_type": "sales_tax",
        "taxable_amount": str(amount_decimal),
        "state_rate": str(state_rate),
        "local_rate_estimate": str(local_rate),
        "total_rate": str(total_rate),
        "tax_amount": str(tax_amount),
        "total_amount": str(total_amount),
        "is_tax_free": state_upper in US_TAX_FREE_STATES,
        "note": "Local tax is estimated. Actual rate may vary by city/county.",
    }


def calculate_eu_vat(
    amount: Decimal | float | str,
    country_code: str,
    use_reduced_rate: bool = False,
    is_import: bool = False,
) -> dict[str, Any]:
    """
    计算欧盟增值税（VAT）

    Args:
        amount: 应税金额（不含税）
        country_code: 国家代码（如 DE、FR）
        use_reduced_rate: 是否使用降低税率
        is_import: 是否为进口（影响 IOSS）

    Returns:
        包含税额、税率、明细的字典
    """
    country_upper = country_code.upper()
    if country_upper not in EU_VAT_RATES:
        raise ValueError(f"Unsupported EU country: {country_code}")

    country_info = EU_VAT_RATES[country_upper]
    vat_rate = Decimal(str(country_info["reduced_rate"] if use_reduced_rate else country_info["rate"]))

    amount_decimal = Decimal(str(amount))
    vat_amount = (amount_decimal * vat_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_amount = amount_decimal + vat_amount

    # IOSS 检查
    use_ioss = False
    if is_import and IOSS_CONFIG["enabled"]:
        threshold = Decimal(str(IOSS_CONFIG["threshold_eur"]))
        if amount_decimal <= threshold:
            use_ioss = True

    return {
        "country": country_upper,
        "country_name": country_info["name"],
        "tax_type": "vat",
        "taxable_amount": str(amount_decimal),
        "vat_rate": str(vat_rate),
        "is_reduced_rate": use_reduced_rate,
        "vat_amount": str(vat_amount),
        "total_amount": str(total_amount),
        "ioss": {
            "applicable": use_ioss,
            "ioss_number": IOSS_CONFIG["ioss_number"] if use_ioss else None,
            "threshold_eur": IOSS_CONFIG["threshold_eur"],
        },
    }


def calculate_tax(
    amount: Decimal | float | str,
    country_code: str,
    state_code: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    统一税务计算入口

    Args:
        amount: 应税金额
        country_code: 国家代码
        state_code: 州代码（美国必填）
        **kwargs: 其他参数

    Returns:
        税务计算结果
    """
    country_upper = country_code.upper()

    if country_upper == "US":
        if not state_code:
            raise ValueError("state_code is required for US tax calculation")
        include_local_tax_estimate = kwargs.get("include_local_tax_estimate", True)
        return calculate_us_sales_tax(amount, state_code, include_local_tax_estimate)
    elif country_upper in EU_VAT_RATES:
        use_reduced_rate = kwargs.get("use_reduced_rate", False)
        is_import = kwargs.get("is_import", False)
        return calculate_eu_vat(amount, country_code, use_reduced_rate, is_import)
    else:
        # 其他国家/地区：默认无税
        amount_decimal = Decimal(str(amount))
        return {
            "country": country_upper,
            "tax_type": "none",
            "taxable_amount": str(amount_decimal),
            "tax_rate": "0",
            "tax_amount": "0.00",
            "total_amount": str(amount_decimal),
            "note": "No tax configured for this country/region.",
        }


def get_tax_rates() -> dict[str, Any]:
    """获取所有税率配置"""
    return {
        "us_sales_tax": {
            "states": len(US_STATE_SALES_TAX),
            "tax_free_states": US_TAX_FREE_STATES,
            "average_rate": "0.055",
            "note": "State rates only. Local taxes may apply and vary by location.",
        },
        "eu_vat": {
            "countries": len(EU_VAT_RATES),
            "average_standard_rate": "0.21",
            "note": "Standard VAT rates. Reduced rates may apply to certain product categories.",
        },
        "ioss": IOSS_CONFIG,
    }


def get_tax_compliance_status() -> dict[str, Any]:
    """获取税务合规服务状态"""
    return {
        "status": "running",
        "us_sales_tax_configured": True,
        "eu_vat_configured": True,
        "ioss_configured": IOSS_CONFIG["enabled"],
        "ioss_number": IOSS_CONFIG["ioss_number"],
        "supported_countries": len(US_STATE_SALES_TAX) + len(EU_VAT_RATES) + 1,
        "note": "Tax rates are static and should be updated regularly. For production, integrate with a tax calculation API like TaxJar or Avalara.",
    }
