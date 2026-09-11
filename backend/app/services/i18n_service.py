"""
国际化服务
支持多币种转换、多语言内容、价格格式化
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

logger = logging.getLogger(__name__)

# 支持的货币
SUPPORTED_CURRENCIES = {
    "USD": {"symbol": "$", "name": "US Dollar", "decimal_places": 2},
    "EUR": {"symbol": "€", "name": "Euro", "decimal_places": 2},
    "GBP": {"symbol": "£", "name": "British Pound", "decimal_places": 2},
    "CAD": {"symbol": "C$", "name": "Canadian Dollar", "decimal_places": 2},
    "AUD": {"symbol": "A$", "name": "Australian Dollar", "decimal_places": 2},
}

# 汇率（相对于 USD，生产环境应从 API 实时获取）
# 基准日期：2026-09-01
EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "CAD": 1.36,
    "AUD": 1.51,
}

# 支持的语言
SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "native_name": "English", "default": True},
    "de": {"name": "German", "native_name": "Deutsch"},
    "es": {"name": "Spanish", "native_name": "Español"},
    "fr": {"name": "French", "native_name": "Français"},
}

# 国家到默认货币和语言的映射
COUNTRY_LOCALE = {
    "US": {"currency": "USD", "language": "en"},
    "DE": {"currency": "EUR", "language": "de"},
    "FR": {"currency": "EUR", "language": "fr"},
    "ES": {"currency": "EUR", "language": "es"},
    "IT": {"currency": "EUR", "language": "it"},
    "NL": {"currency": "EUR", "language": "nl"},
    "GB": {"currency": "GBP", "language": "en"},
    "CA": {"currency": "CAD", "language": "en"},
    "AU": {"currency": "AUD", "language": "en"},
}


def convert_currency(
    amount: Decimal | float | str,
    from_currency: str,
    to_currency: str,
) -> Decimal:
    """
    转换货币

    Args:
        amount: 金额
        from_currency: 源货币代码
        to_currency: 目标货币代码

    Returns:
        转换后的金额（Decimal）
    """
    if from_currency not in EXCHANGE_RATES:
        raise ValueError(f"Unsupported source currency: {from_currency}")
    if to_currency not in EXCHANGE_RATES:
        raise ValueError(f"Unsupported target currency: {to_currency}")

    amount_decimal = Decimal(str(amount))
    from_rate = Decimal(str(EXCHANGE_RATES[from_currency]))
    to_rate = Decimal(str(EXCHANGE_RATES[to_currency]))

    # 先转换为 USD，再转换为目标货币
    usd_amount = amount_decimal / from_rate
    target_amount = usd_amount * to_rate

    # 四舍五入到目标货币的小数位数
    decimal_places = SUPPORTED_CURRENCIES.get(to_currency, {}).get("decimal_places", 2)
    quantize_str = f"0.{'0' * decimal_places}"
    return target_amount.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)


def format_price(
    amount: Decimal | float | str,
    currency: str,
    include_symbol: bool = True,
    locale: str = "en_US",
) -> str:
    """
    格式化价格

    Args:
        amount: 金额
        currency: 货币代码
        include_symbol: 是否包含货币符号
        locale: 区域设置（影响千位分隔符和小数点）

    Returns:
        格式化后的价格字符串
    """
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency: {currency}")

    amount_decimal = Decimal(str(amount))
    currency_info = SUPPORTED_CURRENCIES[currency]
    decimal_places = currency_info["decimal_places"]
    symbol = currency_info["symbol"]

    # 格式化数字（使用英文格式，生产环境应根据 locale 调整）
    quantize_str = f"0.{'0' * decimal_places}"
    formatted_amount = f"{amount_decimal.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP):,}"

    if include_symbol:
        # 欧元符号在金额后面，其他货币符号在前面
        if currency == "EUR":
            return f"{formatted_amount} {symbol}"
        else:
            return f"{symbol}{formatted_amount}"
    else:
        return formatted_amount


def get_locale_for_country(country_code: str) -> dict[str, str]:
    """
    获取国家对应的默认区域设置

    Args:
        country_code: 国家代码（ISO 3166-1 alpha-2）

    Returns:
        包含 currency 和 language 的字典
    """
    country_code_upper = country_code.upper()
    if country_code_upper in COUNTRY_LOCALE:
        return COUNTRY_LOCALE[country_code_upper]
    # 默认使用 USD 和英文
    return {"currency": "USD", "language": "en"}


def get_supported_currencies() -> list[dict[str, Any]]:
    """获取所有支持的货币"""
    return [
        {
            "code": code,
            "symbol": info["symbol"],
            "name": info["name"],
            "exchange_rate_to_usd": EXCHANGE_RATES[code],
        }
        for code, info in SUPPORTED_CURRENCIES.items()
    ]


def get_supported_languages() -> list[dict[str, Any]]:
    """获取所有支持的语言"""
    return [
        {
            "code": code,
            "name": info["name"],
            "native_name": info["native_name"],
            "is_default": info.get("default", False),
        }
        for code, info in SUPPORTED_LANGUAGES.items()
    ]


def translate_product_content(
    product: dict[str, Any],
    target_language: str,
) -> dict[str, Any]:
    """
    翻译产品内容（简化版，生产环境应调用翻译 API）

    Args:
        product: 产品数据
        target_language: 目标语言代码

    Returns:
        翻译后的产品数据
    """
    if target_language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {target_language}")

    # 简化版：直接返回原内容，标记为需要翻译
    # 生产环境应调用 DeepSeek 或其他翻译 API
    translated = product.copy()
    translated["_translation"] = {
        "target_language": target_language,
        "status": "needs_translation",
        "note": "Translation service not configured. Using original content.",
    }
    return translated


def get_i18n_status() -> dict[str, Any]:
    """获取国际化服务状态"""
    return {
        "status": "running",
        "supported_currencies": list(SUPPORTED_CURRENCIES.keys()),
        "supported_languages": list(SUPPORTED_LANGUAGES.keys()),
        "default_currency": "USD",
        "default_language": "en",
        "exchange_rate_source": "static (2026-09-01)",
        "countries_configured": len(COUNTRY_LOCALE),
        "note": "Exchange rates are static. For production, integrate with a live exchange rate API.",
    }
