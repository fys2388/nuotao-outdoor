"""
阿里牛顿（Newton Cloud）AI Agent 服务
通过1688开放平台网关调用牛顿Agent执行找品、询盘、比价等任务

官方仅提供Java SDK，本模块为Python原生实现，复用1688网关签名逻辑
无API密钥/accessToken时自动降级为mock数据，保证闭环可用

API能力:
- create_agent_task: 创建Agent任务（自然语言找品）
- get_task_status: 查询任务状态
- fetch_task_result: 获取任务结果（商品列表/对比表/询盘结果）
- list_models: 列出可用Agent模型
- await_result: 创建+自动轮询到终态（简化版）
- newton_agent_search: 高层封装，自然语言找品一键调用
- batch_inquiry: 批量询盘
"""
from __future__ import annotations

import hmac
import hashlib
import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# 牛顿云配置（从环境变量读取，未配置时降级）
NEWTON_APP_KEY = os.getenv("ALI1688_APP_KEY", "")
NEWTON_APP_SECRET = os.getenv("ALI1688_APP_SECRET", "")
NEWTON_ACCESS_TOKEN = os.getenv("ALI1688_ACCESS_TOKEN", "")
NEWTON_BASE_URL = "https://gw.open.1688.com/openapi"

# 请求超时
DEFAULT_TIMEOUT = 30
# 轮询间隔（秒）
POLL_INTERVAL = 3
# 最大轮询次数（约5分钟）
MAX_POLL_ATTEMPTS = 100


def _sign(url_path: str, params: dict[str, Any], secret: str) -> str:
    """
    1688 API 签名（HMAC-SHA1，官方标准算法）

    官方签名规则（https://open.1688.com/doc/signature.htm）：
    1. 构造urlPath：从param2开始到?为止，如 param2/1/namespace/api_name/appKey
    2. 构造参数签名因子：key+value拼接，按key首字母排序，最后拼接
    3. 合并：s = urlPath + 参数签名因子
    4. 签名：uppercase(hex(hmac_sha1(s, secretKey)))
    """
    # 排除签名参数本身
    sign_params = {k: v for k, v in params.items() if k != "_aop_signature"}

    # 参数key+value拼接，按key排序
    sorted_params = sorted(sign_params.items())
    param_str = "".join(f"{k}{v}" for k, v in sorted_params)

    # 合并urlPath和参数
    sign_str = url_path + param_str

    # HMAC-SHA1签名
    return hmac.new(
        secret.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest().upper()


def is_configured() -> bool:
    """检查牛顿API是否已完整配置（appKey+appSecret+accessToken）"""
    return bool(NEWTON_APP_KEY and NEWTON_APP_SECRET and NEWTON_ACCESS_TOKEN)


def has_credentials() -> bool:
    """检查是否有基础凭证（appKey+appSecret，accessToken可选）"""
    return bool(NEWTON_APP_KEY and NEWTON_APP_SECRET)


def _call_newton_api(method: str, biz_params: dict[str, Any]) -> dict[str, Any]:
    """
    调用牛顿云API（底层网关调用）

    Args:
        method: API方法名，如 com.alibaba.agent.newtoncloud.task.create
        biz_params: 业务参数

    Returns:
        API响应JSON
    """
    # 拆分method为namespace和api_name
    # 牛顿云API的namespace固定为 com.alibaba.agent
    # method格式：com.alibaba.agent.newtoncloud.task.create
    NEWTON_NAMESPACE = "com.alibaba.agent"
    prefix = f"{NEWTON_NAMESPACE}."
    if method.startswith(prefix):
        namespace = NEWTON_NAMESPACE
        api_name = method[len(prefix):]  # newtoncloud.task.create
    else:
        # 兼容其他格式：从最后一个点拆分
        parts = method.rsplit(".", 1)
        namespace = parts[0] if len(parts) == 2 else ""
        api_name = parts[1] if len(parts) == 2 else method

    # 构造参数：业务参数 + access_token + _aop_timestamp
    params: dict[str, Any] = {}
    params.update(biz_params)
    if NEWTON_ACCESS_TOKEN:
        params["access_token"] = NEWTON_ACCESS_TOKEN
    params["_aop_timestamp"] = str(int(time.time() * 1000))

    # 构造urlPath：从param2开始到?为止
    url_path = f"param2/1/{namespace}/{api_name}/{NEWTON_APP_KEY}"

    # 计算签名
    params["_aop_signature"] = _sign(url_path, params, NEWTON_APP_SECRET)

    # 构造完整URL
    url = f"{NEWTON_BASE_URL}/{url_path}"

    # 禁用代理（本地环境可能配置了HTTP代理导致连接失败）
    proxies = {"http": None, "https": None}

    # GET请求，参数通过URL query传递（1688网关标准方式）
    resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT, proxies=proxies)
    resp.raise_for_status()
    return resp.json()


# ============================================
# 核心API
# ============================================

def create_agent_task(
    message: str,
    auto: bool = True,
    model: str | None = None,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    创建牛顿Agent任务

    Args:
        message: 自然语言任务描述，如"帮我找户外露营灯，10-30元，起订50个"
        auto: 是否让Agent自主补全默认值（True=零交互跑完）
        model: 指定Agent模型（None=默认模型）
        extra_params: 额外参数

    Returns:
        任务信息（含task_id）
    """
    if not is_configured():
        return _mock_create_task(message)

    try:
        biz_params = {
            "message": message,
            "auto": str(auto).lower(),
        }
        if model:
            biz_params["model"] = model
        if extra_params:
            biz_params.update(extra_params)

        data = _call_newton_api("com.alibaba.agent.newtoncloud.task.create", biz_params)
        result = data.get("result", data)
        return {
            "success": True,
            "source": "newton_api",
            "task_id": result.get("taskId", result.get("task_id", "")),
            "status": result.get("status", "created"),
            "message": message,
            "raw": result,
        }
    except Exception as e:
        logger.error("Newton create task failed: %s", str(e))
        return {"success": False, "error": str(e), "task_id": "", "source": "newton_api"}


def get_task_status(task_id: str) -> dict[str, Any]:
    """
    查询Agent任务状态

    Args:
        task_id: 任务ID

    Returns:
        任务状态（pending/running/end/failed等）
    """
    if not is_configured():
        return _mock_get_status(task_id)

    try:
        data = _call_newton_api("com.alibaba.agent.newtoncloud.task.get", {"taskId": task_id})
        result = data.get("result", data)
        return {
            "success": True,
            "source": "newton_api",
            "task_id": task_id,
            "status": result.get("status", "unknown"),
            "progress": result.get("progress", 0),
            "raw": result,
        }
    except Exception as e:
        logger.error("Newton get status failed: %s", str(e))
        return {"success": False, "error": str(e), "task_id": task_id, "source": "newton_api"}


def fetch_task_result(task_id: str) -> dict[str, Any]:
    """
    获取Agent任务结果（商品列表/对比表/询盘结果等）

    Args:
        task_id: 任务ID

    Returns:
        任务结果（含products/comparison/inquiry等）
    """
    if not is_configured():
        return _mock_fetch_result(task_id)

    try:
        data = _call_newton_api("com.alibaba.agent.newtoncloud.task.fetch", {"taskId": task_id})
        result = data.get("result", data)
        return {
            "success": True,
            "source": "newton_api",
            "task_id": task_id,
            "status": result.get("status", "end"),
            "products": result.get("products", result.get("items", [])),
            "comparison": result.get("comparison", None),
            "summary": result.get("summary", result.get("answer", "")),
            "raw": result,
        }
    except Exception as e:
        logger.error("Newton fetch result failed: %s", str(e))
        return {"success": False, "error": str(e), "task_id": task_id, "source": "newton_api"}


def list_models() -> dict[str, Any]:
    """
    列出可用的Agent模型

    Returns:
        模型列表
    """
    if not is_configured():
        return _mock_list_models()

    try:
        data = _call_newton_api("com.alibaba.agent.newtoncloud.model.list", {})
        result = data.get("result", data)
        models = result.get("models", result.get("items", []))
        return {
            "success": True,
            "source": "newton_api",
            "models": models,
            "count": len(models),
        }
    except Exception as e:
        logger.error("Newton list models failed: %s", str(e))
        return {"success": False, "error": str(e), "models": [], "source": "newton_api"}


def kill_task(task_id: str) -> dict[str, Any]:
    """终止Agent任务"""
    if not is_configured():
        return {"success": True, "source": "mock", "task_id": task_id, "status": "killed"}
    try:
        data = _call_newton_api("com.alibaba.agent.newtoncloud.task.kill", {"taskId": task_id})
        return {"success": True, "source": "newton_api", "task_id": task_id, "raw": data}
    except Exception as e:
        return {"success": False, "error": str(e), "task_id": task_id}


# ============================================
# 高层封装
# ============================================

def await_result(
    message: str,
    auto: bool = True,
    max_wait: int = 300,
    poll_interval: int = POLL_INTERVAL,
) -> dict[str, Any]:
    """
    创建Agent任务并自动轮询到终态（简化版awaitResult）

    Args:
        message: 自然语言任务描述
        auto: Agent自主补全
        max_wait: 最大等待秒数
        poll_interval: 轮询间隔秒数

    Returns:
        最终任务结果
    """
    # 创建任务
    create_resp = create_agent_task(message, auto=auto)
    if not create_resp.get("success"):
        return create_resp

    task_id = create_resp["task_id"]
    if not task_id:
        # mock模式直接返回结果
        return fetch_task_result("mock_task")

    # 轮询状态
    elapsed = 0
    while elapsed < max_wait:
        status_resp = get_task_status(task_id)
        if not status_resp.get("success"):
            return status_resp

        status = status_resp.get("status", "")
        if status in ("end", "completed", "success", "failed", "error"):
            break

        time.sleep(poll_interval)
        elapsed += poll_interval

    # 获取结果
    return fetch_task_result(task_id)


def newton_agent_search(
    query: str,
    min_price: float | None = None,
    max_price: float | None = None,
    min_order_qty: int | None = None,
    category: str | None = None,
    auto: bool = True,
) -> dict[str, Any]:
    """
    牛顿AI智能找品（高层封装）

    用自然语言描述需求，Agent自动在1688找品、比价、筛选

    Args:
        query: 找品需求描述，如"户外露营灯"
        min_price: 最低价格（元）
        max_price: 最高价格（元）
        min_order_qty: 最小起订量
        category: 品类限定
        auto: Agent自主补全参数

    Returns:
        找品结果（商品列表+AI总结+比价信息）
    """
    # 构建自然语言message
    message_parts = [f"帮我找{query}"]
    if min_price is not None or max_price is not None:
        price_part = ""
        if min_price is not None:
            price_part += f"{min_price}元"
        if max_price is not None:
            price_part += f"-{max_price}元" if price_part else f"{max_price}元以下"
        message_parts.append(f"，价格{price_part}")
    if min_order_qty is not None:
        message_parts.append(f"，起订{min_order_qty}个")
    if category:
        message_parts.append(f"，品类限定{category}")
    message_parts.append("，按性价比排序，给出TOP10推荐")

    message = "".join(message_parts)

    # 调用Agent
    result = await_result(message, auto=auto)

    if not result.get("success"):
        return result

    # 标准化输出
    products = result.get("products", [])
    return {
        "success": True,
        "source": result.get("source", "newton_api"),
        "query": query,
        "message": message,
        "total": len(products),
        "products": _normalize_newton_products(products),
        "summary": result.get("summary", ""),
        "comparison": result.get("comparison"),
        "task_id": result.get("task_id", ""),
    }


def batch_inquiry(
    product_ids: list[str],
    inquiry_message: str = "请问这款产品的批发价、起订量、交货周期是多少？",
) -> dict[str, Any]:
    """
    批量询盘（对多个商品发送询盘）

    Args:
        product_ids: 1688商品ID列表
        inquiry_message: 询盘内容

    Returns:
        询盘任务结果
    """
    if not is_configured():
        return _mock_batch_inquiry(product_ids)

    try:
        message = f"对以下商品批量发送询盘：{','.join(product_ids)}。询盘内容：{inquiry_message}"
        result = await_result(message)
        return {
            "success": result.get("success", False),
            "source": result.get("source", "newton_api"),
            "product_ids": product_ids,
            "inquiry_count": len(product_ids),
            "result": result,
        }
    except Exception as e:
        logger.error("Newton batch inquiry failed: %s", str(e))
        return {"success": False, "error": str(e), "product_ids": product_ids}


# ============================================
# 内部工具函数
# ============================================

def _normalize_newton_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """标准化牛顿Agent返回的商品列表"""
    normalized = []
    for p in products:
        normalized.append({
            "product_id": str(p.get("productId", p.get("product_id", p.get("id", "")))),
            "subject": p.get("subject", p.get("title", p.get("name", ""))),
            "price": p.get("price", p.get("priceRange", "")),
            "min_order_qty": p.get("minOrderQty", p.get("moq", p.get("起订量", 1))),
            "supplier": p.get("supplier", p.get("companyName", p.get("供应商", ""))),
            "image_url": p.get("imageUrl", p.get("image", p.get("主图", ""))),
            "detail_url": p.get("detailUrl", p.get("url", p.get("链接", ""))),
            "score": p.get("score", p.get("推荐指数", 0)),
            "reason": p.get("reason", p.get("推荐理由", "")),
        })
    return normalized


# ============================================
# Mock 降级数据（未配置API密钥时使用）
# ============================================

def _mock_create_task(message: str) -> dict[str, Any]:
    """模拟创建任务"""
    task_id = f"mock_{int(time.time())}"
    return {
        "success": True,
        "source": "mock",
        "note": "未配置牛顿API凭证（ALI1688_APP_KEY/SECRET/ACCESS_TOKEN），返回示例数据",
        "task_id": task_id,
        "status": "created",
        "message": message,
    }


def _mock_get_status(task_id: str) -> dict[str, Any]:
    """模拟查询状态"""
    return {
        "success": True,
        "source": "mock",
        "task_id": task_id,
        "status": "end",
        "progress": 100,
    }


def _mock_fetch_result(task_id: str) -> dict[str, Any]:
    """模拟获取结果"""
    mock_products = [
        {
            "product_id": "newton_mock_001",
            "subject": "户外太阳能露营灯 - 防水可充电 - 工厂直销",
            "price": "15.80",
            "price_range": [{"start": 1, "end": 99, "price": "15.80"}, {"start": 100, "end": 999, "price": "12.50"}],
            "min_order_qty": 50,
            "supplier": "义乌市户外照明有限公司",
            "supplier_credit": "诚信通8年",
            "image_url": "",
            "detail_url": "https://detail.1688.com/offer/newton_mock_001.html",
            "score": 95,
            "reason": "价格最低，太阳能充电适合户外，供应商诚信通8年",
            "sale_quantity": 25680,
        },
        {
            "product_id": "newton_mock_002",
            "subject": "LED露营灯帐篷灯 - 三档调光 - 跨境专供",
            "price": "22.00",
            "price_range": [{"start": 1, "end": 49, "price": "22.00"}, {"start": 50, "end": 499, "price": "18.00"}],
            "min_order_qty": 30,
            "supplier": "深圳市跨境电商供应链公司",
            "supplier_credit": "实力商家",
            "image_url": "",
            "detail_url": "https://detail.1688.com/offer/newton_mock_002.html",
            "score": 88,
            "reason": "三档调光功能丰富，跨境专供质量稳定，起订量低",
            "sale_quantity": 18920,
        },
        {
            "product_id": "newton_mock_003",
            "subject": "复古露营灯 - 铁艺氛围灯 - 网红爆款",
            "price": "28.50",
            "price_range": [{"start": 1, "end": 19, "price": "28.50"}, {"start": 20, "end": 199, "price": "24.00"}],
            "min_order_qty": 20,
            "supplier": "中山市古镇照明厂",
            "supplier_credit": "诚信通5年",
            "image_url": "",
            "detail_url": "https://detail.1688.com/offer/newton_mock_003.html",
            "score": 82,
            "reason": "复古设计颜值高，网红爆款有流量，但价格偏高",
            "sale_quantity": 9450,
        },
    ]
    return {
        "success": True,
        "source": "mock",
        "note": "未配置牛顿API凭证，返回示例找品结果",
        "task_id": task_id,
        "status": "end",
        "products": mock_products,
        "summary": "为你找到3款高性价比户外露营灯：TOP1太阳能款15.8元（最低价+诚信通8年），TOP2 LED三档调光22元（跨境专供+低起订），TOP3复古网红款28.5元（高颜值+爆款流量）。建议优先采购TOP1，利润空间最大。",
        "comparison": {
            "cheapest": "newton_mock_001 (15.80元)",
            "best_seller": "newton_mock_001 (销量25680)",
            "lowest_moq": "newton_mock_003 (起订20)",
            "recommended": "newton_mock_001",
        },
    }


def _mock_list_models() -> dict[str, Any]:
    """模拟模型列表"""
    return {
        "success": True,
        "source": "mock",
        "models": [
            {"id": "newton-default", "name": "牛顿默认模型", "description": "通用找品/询盘/比价"},
            {"id": "newton-sourcing", "name": "牛顿选品专家", "description": "专注跨境选品，含利润测算"},
            {"id": "newton-inquiry", "name": "牛顿询盘专家", "description": "批量询盘+供应商沟通"},
        ],
        "count": 3,
    }


def _mock_batch_inquiry(product_ids: list[str]) -> dict[str, Any]:
    """模拟批量询盘"""
    return {
        "success": True,
        "source": "mock",
        "note": "未配置牛顿API凭证，返回示例询盘结果",
        "product_ids": product_ids,
        "inquiry_count": len(product_ids),
        "result": {
            "status": "end",
            "summary": f"已对{len(product_ids)}个商品发送询盘，预计24小时内收到供应商回复",
            "inquiries": [
                {"product_id": pid, "status": "sent", "reply_count": 0}
                for pid in product_ids
            ],
        },
    }
