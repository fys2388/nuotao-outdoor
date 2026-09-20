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

import hashlib
import hmac
import json
import logging
import os
import re
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


def _deep_find(node: Any, keys: tuple[str, ...]) -> str:
    """递归在嵌套 dict/list 中查找第一个命中的键值，找不到返回空串。

    牛顿网关响应结构不固定（result/data/content 多层嵌套），
    直接 .get() 容易漏掉真实 taskId 导致误判为 mock 模式。
    """
    if isinstance(node, dict):
        for key in keys:
            value = node.get(key)
            if value not in (None, ""):
                return str(value)
        for value in node.values():
            found = _deep_find(value, keys)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _deep_find(item, keys)
            if found:
                return found
    return ""


def _redact_secret(text: str) -> str:
    """脱敏 URL 中的敏感 query 参数（access_token / _aop_signature）。

    1688 网关错误会带完整 URL，直接记日志等于把生产密钥落盘（AGENTS.md 4.2）。
    """
    redacted = re.sub(r"([?&]access_token=)[^&]+", r"\1[REDACTED]", text)
    redacted = re.sub(r"([?&]_aop_signature=)[^&]+", r"\1[REDACTED]", redacted)
    return redacted


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

    if not resp.ok:
        # 网关错误信息含完整URL（access_token/_aop_signature 明文），
        # 直接 raise_for_status 会把密钥写进日志，这里统一脱敏后再抛
        raise RuntimeError(
            f"Newton gateway HTTP {resp.status_code} for {method}: "
            f"{_redact_secret(resp.url)}"
        )
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

        # 网关业务失败：HTTP 200 但 success=False（如积分不足），此时无 taskId。
        # 必须在源头捕获并把网关原始错误透出，否则会被误判为 mock 模式。
        gw_error = (
            result.get("error")
            or result.get("errorMsg")
            or result.get("message")
        )
        task_id = _deep_find(result, ("taskId", "task_id"))
        if not task_id and (result.get("success") is False or gw_error):
            detail = str(gw_error) if gw_error else "网关未返回 taskId"
            return {
                "success": False,
                "source": "newton_api",
                "task_id": "",
                "error": f"牛顿网关返回失败：{detail}",
                "raw": result,
            }

        return {
            "success": True,
            "source": "newton_api",
            "task_id": task_id,
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


def query_points() -> dict[str, Any]:
    """
    查询积分/额度详情

    Returns:
        积分信息（总积分、已用积分、剩余积分、每日额度等）
    """
    if not is_configured():
        return {"success": True, "source": "mock", "total": 5000, "used": 0, "remaining": 5000}

    try:
        data = _call_newton_api("com.alibaba.agent.newtoncloud.points.query", {})
        result = data.get("result", data)
        return {
            "success": True,
            "source": "newton_api",
            "total": result.get("totalPoints", result.get("total", 5000)),
            "used": result.get("usedPoints", result.get("used", 0)),
            "remaining": result.get("remainingPoints", result.get("remaining", 5000)),
            "daily_limit": result.get("dailyLimit", 5000),
            "raw": result,
        }
    except Exception as e:
        logger.error("Newton query points failed: %s", str(e))
        return {"success": False, "error": str(e), "source": "newton_api"}


def list_tasks(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """
    查询任务列表

    Args:
        page: 页码
        page_size: 每页数量

    Returns:
        任务列表
    """
    if not is_configured():
        return {"success": True, "source": "mock", "tasks": [], "total": 0}

    try:
        data = _call_newton_api("com.alibaba.agent.newtoncloud.task.list", {
            "page": page,
            "pageSize": page_size,
        })
        result = data.get("result", data)
        tasks = result.get("tasks", result.get("items", []))
        return {
            "success": True,
            "source": "newton_api",
            "tasks": tasks,
            "total": result.get("total", len(tasks)),
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error("Newton list tasks failed: %s", str(e))
        return {"success": False, "error": str(e), "tasks": [], "source": "newton_api"}


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
        if not is_configured():
            # 未配置凭证的降级模式：直接返回mock结果，不走网络
            return _mock_fetch_result(task_id)
        # 已配置凭证但创建任务未返回task_id：明确报错，
        # 严禁拿占位taskId去调真实网关（会触发 400 Bad Request）
        logger.error(
            "Newton create task succeeded but returned no task_id, raw: %s",
            create_resp.get("raw"),
        )
        return {
            "success": False,
            "source": "newton_api",
            "task_id": "",
            "status": "FAILED",
            "error": "牛顿 Agent 创建任务成功但未返回 task_id，请检查 API 响应结构或网关权限",
            "raw": create_resp.get("raw"),
        }

    # 轮询状态（牛顿API状态为大写：INIT/RUNNING/WAIT_SKILL/WAIT_USER/END/KILL）
    elapsed = 0
    final_status = None
    final_raw = None
    while elapsed < max_wait:
        status_resp = get_task_status(task_id)
        if not status_resp.get("success"):
            return status_resp

        status = status_resp.get("status", "").upper()
        final_raw = status_resp.get("raw", {})

        if status in ("END", "KILL", "FAILED", "ERROR", "COMPLETED", "SUCCESS"):
            final_status = status
            break

        time.sleep(poll_interval)
        elapsed += poll_interval

    # 从get_task_status的raw中提取内容（牛顿API返回content字段）
    content = final_raw.get("content", "") if final_raw else ""
    chunks = final_raw.get("chunks", "") if final_raw else ""

    return {
        "success": final_status in ("END", "COMPLETED", "SUCCESS"),
        "source": "newton_api",
        "task_id": task_id,
        "status": final_status or "TIMEOUT",
        "summary": content,
        "content": content,
        "chunks": chunks,
        "products": final_raw.get("products", final_raw.get("items", [])) if final_raw else [],
        "raw": final_raw,
        "elapsed_seconds": elapsed,
    }


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

    # 标准化输出；牛顿常把商品以 ```product-card 文本块放在 content 里，
    # 当结构化 products 为空时，回退从文本中解析商品卡片
    products = result.get("products", [])
    if not products:
        products = _extract_product_cards(
            result.get("content") or result.get("summary") or ""
        )
    normalized = _normalize_newton_products(products)
    for idx, item in enumerate(normalized):
        raw = products[idx] if idx < len(products) else {}
        if not item.get("score"):
            # Agent 已按性价比排序，缺失评分时按名次递减补分，便于前端分级
            item["score"] = max(55, 92 - idx * 5)
        if not item.get("reason"):
            bits = [str(raw[k]) for k in ("soldCount", "supplierBadge") if raw.get(k)]
            item["reason"] = "牛顿AI按性价比排序推荐" + (
                "（" + "·".join(bits) + "）" if bits else ""
            )
    return {
        "success": True,
        "source": result.get("source", "newton_api"),
        "query": query,
        "message": message,
        "total": len(normalized),
        "products": normalized,
        "summary": result.get("summary", ""),
        "comparison": result.get("comparison"),
        "task_id": result.get("task_id", ""),
    }


def _extract_json_object(content: str) -> dict[str, Any]:
    """从 Agent 最终回复中提取 JSON 对象，兼容 Markdown 代码块。"""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    candidates = [cleaned]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidates.append(cleaned[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Newton Agent returned no valid JSON object")


def _normalize_extracted_product(
    data: dict[str, Any],
    *,
    product_id: str,
    source_url: str,
) -> dict[str, Any]:
    """把牛顿 Agent 的字段统一为开放平台商品详情结构。"""
    title = (
        data.get("title")
        or data.get("product_title")
        or data.get("商品标题")
        or ""
    )
    if not str(title).strip():
        raise ValueError("Newton Agent did not return a product title")

    price_min = data.get("price_min", data.get("priceMin"))
    price_max = data.get("price_max", data.get("priceMax"))
    if price_min is None and price_max is None:
        price_range_raw = (
            data.get("price_range")
            or data.get("priceRange")
            or data.get("价格区间")
            or ""
        )
        prices = re.findall(r"\d+(?:\.\d+)?", str(price_range_raw))
        if prices:
            price_min = prices[0]
            price_max = prices[1] if len(prices) > 1 else prices[0]

    if price_min is None:
        price = str(price_max or "")
    elif price_max is None or str(price_min) == str(price_max):
        price = str(price_min)
    else:
        price = f"{price_min}-{price_max}"

    images_raw = (
        data.get("image_urls")
        or data.get("images")
        or data.get("商品图片URL")
        or []
    )
    if not isinstance(images_raw, list):
        images_raw = [images_raw]
    images = [
        str(image).strip()
        for image in images_raw
        if str(image).strip().startswith(("http://", "https://"))
    ]

    moq = data.get("moq") or data.get("min_order_quantity") or data.get("起订量") or ""
    supplier_name = (
        data.get("supplier_name")
        or data.get("supplier")
        or data.get("供应商名称")
        or ""
    )
    description = data.get("description") or data.get("商品描述") or str(title)
    category = data.get("category") or data.get("category_name") or ""

    return {
        "product_id": str(data.get("product_id") or product_id),
        "subject": str(title).strip(),
        "description": str(description).strip(),
        "price": price,
        "price_range": (
            [{"startQuantity": moq or 1, "price": price_min}]
            if price_min is not None
            else []
        ),
        "sku_list": [],
        "attributes": (
            data.get("attributes")
            if isinstance(data.get("attributes"), list)
            else []
        ),  # ROUND-4A: 1688 属性表原样透传，重量/尺寸/材质靠它落地
        "images": images,
        "supplier_login_id": "",
        "company_name": str(supplier_name).strip(),
        "supplier": {"company_name": str(supplier_name).strip()},
        "main_image": images[0] if images else "",
        "category_id": "",
        "category_name": str(category).strip(),
        "min_order_quantity": moq,
        "source_url": source_url,
        "source": "newton_agent",
    }


def extract_1688_product(
    url_or_id: str,
    product_id: str,
    *,
    max_wait: int = 300,
    poll_interval: int = POLL_INTERVAL,
) -> dict[str, Any]:
    """
    使用已授权的牛顿 Agent 读取指定 1688 公开商品页。

    该函数只提取页面公开商品字段，不自动询盘、下单或修改任何业务数据。
    ROUND-4A: max_wait 90->300；实测单次 53s/114s，90s 会误报超时。
    调用方必须在开放平台商品详情接口因 ACL 或铺货关系不可用时再降级到这里。
    """
    if not is_configured():
        return {
            "success": False,
            "source": "newton_agent",
            "error": "牛顿 Agent 未配置，无法读取该 1688 商品",
        }

    message = f"""请使用你已授权的 1688 供应链能力读取下面这个公开商品页，并严格按以下英文键返回 JSON：
{{
  "title": "商品标题",
  "product_id": "商品ID",
  "price_min": 最低价格数字或null,
  "price_max": 最高价格数字或null,
  "price_range": "页面展示的原始价格区间",
  "moq": 最小起订量数字或null,
  "supplier_name": "供应商公司名称",
  "image_urls": ["主图URL"],
  "description": "页面公开商品描述或标题",
  "category": "商品类目"
}}

要求：
1. 只输出 JSON 对象，不要 Markdown，不要解释。
2. 禁止猜测；页面无法读取或字段不存在时使用 null 或空数组。
3. 不要联系供应商，不要下单，不要修改任何数据。

商品ID：{product_id}
商品链接：{url_or_id}
"""

    created = create_agent_task(message, auto=True, model="qwen3.6-plus")
    if not created.get("success") or not created.get("task_id"):
        return {
            "success": False,
            "source": "newton_agent",
            "error": created.get("error") or "创建牛顿 Agent 任务失败",
        }

    task_id = str(created["task_id"])
    deadline = time.monotonic() + max_wait
    last_status = "UNKNOWN"

    while time.monotonic() < deadline:
        status_result = get_task_status(task_id)
        if not status_result.get("success"):
            return {
                "success": False,
                "source": "newton_agent",
                "task_id": task_id,
                "error": status_result.get("error") or "查询牛顿 Agent 任务失败",
            }

        last_status = str(status_result.get("status") or "UNKNOWN").upper()
        if last_status in {"END", "COMPLETED", "SUCCESS"}:
            raw = status_result.get("raw") or {}
            content = str(raw.get("content") or "")
            try:
                parsed = _extract_json_object(content)
                product = _normalize_extracted_product(
                    parsed,
                    product_id=product_id,
                    source_url=url_or_id,
                )
            except ValueError as exc:
                return {
                    "success": False,
                    "source": "newton_agent",
                    "task_id": task_id,
                    "error": f"牛顿 Agent 返回结果无法解析: {exc}",
                }
            return {
                "success": True,
                "source": "newton_agent",
                "task_id": task_id,
                "product": product,
            }

        if last_status in {"FAILED", "ERROR", "KILL", "KILLED"}:
            return {
                "success": False,
                "source": "newton_agent",
                "task_id": task_id,
                "error": f"牛顿 Agent 任务失败，状态: {last_status}",
            }

        time.sleep(max(1, poll_interval))

    logger.warning("Newton product extraction timed out for task %s", task_id)
    kill_result = kill_task(task_id)
    return {
        "success": False,
        "source": "newton_agent",
        "task_id": task_id,
        "kill_requested": kill_result.get("success", False),
        "error": (
            f"牛顿 Agent 读取超时（当前状态 {last_status}），"
            "已请求终止任务，请稍后重试"
        ),
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

def _extract_product_cards(content: str) -> list[dict[str, Any]]:
    """从牛顿 Agent 回复文本里的 product-card 代码块解析商品列表。

    牛顿找品常把商品以 ```product-card [{...}]``` 形式嵌在自然语言总结中，
    而不是独立的 products 字段。这里做容错抽取，返回原始商品 dict 列表。
    """
    if not content:
        return []
    products: list[dict[str, Any]] = []
    blocks = re.findall(r"```(?:product-card|json)?\s*([\s\S]*?)```", content)
    for block in blocks:
        block = block.strip()
        if not block or "{" not in block:
            continue
        try:
            parsed = json.loads(block)
        except ValueError:
            continue
        candidates = parsed if isinstance(parsed, list) else [parsed]
        for item in candidates:
            if isinstance(item, dict) and (
                item.get("title")
                or item.get("subject")
                or item.get("id")
                or item.get("product_id")
            ):
                products.append(item)
    return products


def _normalize_newton_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """标准化牛顿Agent返回的商品列表"""
    normalized = []
    for p in products:
        normalized.append({
            "product_id": str(p.get("productId", p.get("product_id", p.get("id", "")))),
            "subject": p.get("subject", p.get("title", p.get("name", ""))),
            "price": p.get("price", p.get("priceRange", "")),
            "min_order_qty": p.get("minOrderQty", p.get("minOrderQuantity", p.get("moq", p.get("起订量", 1)))),
            "supplier": p.get("supplier", p.get("supplierName", p.get("companyName", p.get("供应商", "")))),
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
