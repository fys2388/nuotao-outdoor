"""WooCommerce 商品状态与删除集成服务。

覆盖三层生命周期的渠道侧动作（完整设计见 ``docs/wc_unpublish_design.md``）：

- **下架**：``set_wc_product_status(product, "trash")`` —— 进 WooCommerce 回收站，可恢复
- **恢复**：``set_wc_product_status(product, "publish" | "draft")`` —— 还原前台可见性
- **彻底删除**：``delete_wc_product_permanently(product)`` —— ``DELETE ?force=true``

设计约束：

1. **不经过 V3.0 选品闸门。** 闸门用于阻止不合格商品上架；下架是降低风险的方向。
   若下架也走闸门，当商品因成本或文案变更被闸门判为 ``blocked`` 时，就会出现
   「想下架却下架不了、商品继续在售」——这是比错误上架更危险的失效模式。

2. **只发送最小 payload**（``{"status": ...}``）。下架/恢复是可见性操作，不应顺带
   覆盖文案、价格、图片。

3. **全部通过 WooCommerce REST API**，禁止直接改其数据库（``AGENTS.md`` §1.4）。

4. **绝不静默失败**：改完状态必须回读确认；确认不了就报失败，绝不把「没改成功」
   报成成功。
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# 与 ``listing_publish.py`` 保持一致：nuotaooutdoor.com 前面是 Cloudflare，会间歇性
# 在传输中途掐断 TLS 握手（SSLEOFError / UNEXPECTED_EOF_WHILE_READING），单次尝试
# 约有半数概率报假失败，因此必须有重试预算。
_REQUEST_TIMEOUT = 12
_WC_MAX_ATTEMPTS = 4
_WC_RETRY_BACKOFF = (0.5, 1.5, 3.0)
# 单次状态变更最多 3 次调用（查状态 → PUT → 回读验证），预算比全量推送小。
_STATE_BUDGET_SECONDS = 45.0

#: WooCommerce 回收站状态。与「下架」语义一致：前台不可见、可恢复。
WC_STATUS_TRASH = "trash"

_ALLOWED_STATUSES = frozenset({"publish", "draft", "pending", "private", "trash"})


class WcCallBudget:
    """单次操作共享的 wall-clock 预算，避免重试把客户端拖到超时。"""

    def __init__(self, seconds: float = _STATE_BUDGET_SECONDS) -> None:
        self.deadline = time.monotonic() + seconds

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def per_attempt(self) -> float:
        return max(1.0, min(float(_REQUEST_TIMEOUT), self.remaining() - 1.0))

    def exhausted(self) -> bool:
        return self.remaining() < 2.0


def _wc_base_url() -> str:
    from app.services.woocommerce_sync_service import WC_URL

    return str(WC_URL).rstrip("/")


def _wc_credentials() -> tuple[Any, dict[str, str]]:
    from app.services.woocommerce_sync_service import _get_wc_auth, _get_wc_headers

    return _get_wc_auth(), _get_wc_headers()


def _tag_attempts(exc: Exception, attempts: int) -> None:
    with contextlib.suppress(AttributeError, TypeError):
        exc.attempts = attempts  # type: ignore[attr-defined]


def _wc_error_detail(exc: Exception) -> tuple[int | None, str]:
    response = getattr(exc, "response", None)
    if response is not None:
        body = getattr(response, "text", "") or ""
        return response.status_code, body[:500]
    return None, str(exc)


def _wc_call(
    method: str,
    url: str,
    *,
    auth: Any,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    budget: WcCallBudget | None = None,
) -> requests.Response:
    """调用 WooCommerce REST API，对瞬时传输故障重试。

    4xx 是明确答复（不重试）；5xx 与连接层错误才重试。
    """
    budget = budget or WcCallBudget()
    last: Exception | None = None
    for attempt in range(1, _WC_MAX_ATTEMPTS + 1):
        if budget.exhausted():
            break
        try:
            response = requests.request(
                method,
                url,
                auth=auth,
                headers=headers,
                json=json_body,
                params=params,
                timeout=budget.per_attempt(),
            )
            if response.status_code >= 500:
                err = requests.exceptions.HTTPError(
                    f"{response.status_code} from {url}", response=response
                )
                if attempt >= _WC_MAX_ATTEMPTS:
                    _tag_attempts(err, attempt)
                    raise err
                last = err
                logger.warning(
                    "WooCommerce %s %s returned %s, retry %d/%d",
                    method, url, response.status_code, attempt, _WC_MAX_ATTEMPTS,
                )
                time.sleep(_WC_RETRY_BACKOFF[min(attempt - 1, len(_WC_RETRY_BACKOFF) - 1)])
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as exc:
            _tag_attempts(exc, attempt)
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last = exc
            if attempt >= _WC_MAX_ATTEMPTS:
                _tag_attempts(exc, attempt)
                break
            delay = _WC_RETRY_BACKOFF[min(attempt - 1, len(_WC_RETRY_BACKOFF) - 1)]
            logger.warning(
                "WooCommerce %s %s transport error (%s), retry %d/%d in %.1fs",
                method, url, type(exc).__name__, attempt, _WC_MAX_ATTEMPTS, delay,
            )
            time.sleep(delay)
    if last is not None:
        _tag_attempts(last, _WC_MAX_ATTEMPTS)
    raise last if last is not None else RuntimeError("WooCommerce call failed")


def find_wc_id_by_sku(
    sku: str, *, auth: Any, headers: dict[str, str], budget: WcCallBudget | None = None
) -> int | None:
    """按 SKU 找回 WooCommerce 商品 ID。

    本地 ``meta.woocommerce_id`` 可能丢失（例如推送响应在 Cloudflare 断连中丢失），
    但商品实际已在店里。下架/删除前必须尽力找回，否则会漏掉一个仍在售的链接。
    """
    if not sku:
        return None
    try:
        response = _wc_call(
            "GET",
            f"{_wc_base_url()}/wp-json/wc/v3/products",
            auth=auth,
            headers=headers,
            params={"sku": sku, "per_page": 5, "status": "any"},
            budget=budget,
        )
        for item in response.json() or []:
            if str(item.get("sku", "")).strip() == sku:
                return int(item["id"])
    except requests.exceptions.RequestException as exc:
        logger.warning("按 SKU 查找 WC 商品失败 sku=%s: %s", sku, exc)
    return None


def resolve_wc_id(
    product: Any, *, auth: Any, headers: dict[str, str], budget: WcCallBudget
) -> int | None:
    """解析商品对应的 WooCommerce ID，必要时按 SKU 反查。"""
    meta = getattr(product, "meta", None)
    meta = meta if isinstance(meta, dict) else {}
    raw = meta.get("woocommerce_id")
    if raw not in (None, ""):
        try:
            return int(raw)
        except (TypeError, ValueError):
            logger.warning("忽略无效的 woocommerce_id=%r，回退到 SKU 反查", raw)
    sku = str(getattr(product, "sku", "") or "")
    adopted = find_wc_id_by_sku(sku, auth=auth, headers=headers, budget=budget)
    if adopted:
        logger.info("按 SKU 找回 WC 商品 id=%s sku=%s", adopted, sku)
    return adopted


def _current_wc_status(
    wc_id: int, *, auth: Any, headers: dict[str, str], budget: WcCallBudget
) -> tuple[bool, str]:
    """读取 WC 商品当前状态，返回 ``(是否存在, status)``。

    404 表示商品已不在 WooCommerce（可能被人工删除，或 WordPress 回收站已被自动
    清空），调用方按幂等处理。
    """
    url = f"{_wc_base_url()}/wp-json/wc/v3/products/{wc_id}"
    try:
        response = _wc_call("GET", url, auth=auth, headers=headers, budget=budget)
        return True, str(response.json().get("status") or "").lower()
    except requests.exceptions.HTTPError as exc:
        status_code, _ = _wc_error_detail(exc)
        if status_code == 404:
            return False, ""
        raise


def desired_status_for_restore(product: Any) -> str:
    """恢复时的目标 WC 状态。

    本地仍在售（``active``）则回到 ``publish``，否则回到 ``draft`` —— 与
    ``listing_gate.build_wc_payload`` 的 ``status`` 推导规则保持一致，避免恢复后
    与推送口径不一致。
    """
    return "publish" if getattr(product, "status", None) == "active" else "draft"


def _base_result(product: Any) -> dict[str, Any]:
    return {
        "product_id": str(getattr(product, "id", "") or ""),
        "sku": str(getattr(product, "sku", "") or ""),
        "woocommerce_id": None,
        "woocommerce_status": None,
        "verified": False,
        "error": None,
    }


def set_wc_product_status(
    product: Any,
    target_status: str,
    *,
    budget: WcCallBudget | None = None,
) -> dict[str, Any]:
    """把商品的 WooCommerce 状态设为 ``target_status``（最小 payload）。

    不修改本地数据库。

    Returns:
        结果字典，``action`` 取值：

        - ``updated``：本次成功改状态并回读确认
        - ``already_set``：WC 侧已是目标状态，幂等成功
        - ``already_absent``：WC 侧商品已不存在，幂等成功
        - ``skipped``：本地无 WC 关联，无需操作
        - ``failed``：失败，``error`` 说明原因（绝不谎报成功）
    """
    if target_status not in _ALLOWED_STATUSES:
        # 参数错误是编程错误，直接抛，不走网络。
        raise ValueError(f"不支持的 WooCommerce 状态: {target_status!r}")

    result = _base_result(product)
    budget = budget or WcCallBudget()
    auth, headers = _wc_credentials()

    wc_id = resolve_wc_id(product, auth=auth, headers=headers, budget=budget)
    if not wc_id:
        return {**result, "success": True, "action": "skipped",
                "reason": "not_linked",
                "message": "商品未关联 WooCommerce，无需处理"}
    result["woocommerce_id"] = wc_id

    url = f"{_wc_base_url()}/wp-json/wc/v3/products/{wc_id}"
    try:
        exists, current = _current_wc_status(
            wc_id, auth=auth, headers=headers, budget=budget
        )
        if not exists:
            logger.info("WC 商品已不存在，按幂等成功处理 id=%s sku=%s", wc_id, result["sku"])
            return {**result, "success": True, "action": "already_absent",
                    "message": "WooCommerce 中该商品已不存在"}

        if current == target_status:
            return {**result, "success": True, "action": "already_set",
                    "woocommerce_status": current, "verified": True,
                    "message": f"WooCommerce 商品已是 {target_status} 状态"}

        _wc_call(
            "PUT",
            url,
            auth=auth,
            headers=headers,
            json_body={"status": target_status},
            budget=budget,
        )

        # 回读验证：PUT 返回 200 不代表状态真的落库（插件/缓存都可能吞掉）。
        exists_after, confirmed = _current_wc_status(
            wc_id, auth=auth, headers=headers, budget=budget
        )
        if not (exists_after and confirmed == target_status):
            message = (
                f"WooCommerce 状态变更后回读未确认"
                f"（当前 {confirmed or 'unknown'}，期望 {target_status}）"
            )
            logger.warning("状态变更回读失败 id=%s sku=%s: %s", wc_id, result["sku"], message)
            return {**result, "success": False, "action": "failed",
                    "woocommerce_status": confirmed, "error": message}

        logger.info(
            "WC 商品状态已变更 id=%s sku=%s (%s → %s)",
            wc_id, result["sku"], current, target_status,
        )
        return {**result, "success": True, "action": "updated",
                "woocommerce_status": confirmed, "verified": True,
                "previous_status": current,
                "message": f"WooCommerce 商品状态已更新为 {target_status}"}

    except requests.exceptions.RequestException as exc:
        wc_status, wc_body = _wc_error_detail(exc)
        attempts = int(getattr(exc, "attempts", 0)) or _WC_MAX_ATTEMPTS
        error = (
            f"WooCommerce 状态变更失败（尝试 {attempts} 次）: "
            f"HTTP {wc_status} {wc_body}"
        ).strip()
        logger.error("状态变更失败 id=%s sku=%s: %s", wc_id, result["sku"], error)
        return {**result, "success": False, "action": "failed",
                "error": error, "http_status": wc_status, "attempts": attempts}
    except Exception as exc:  # 凭据缺失、URL 配置错误等
        error = f"WooCommerce 调用异常: {type(exc).__name__}: {exc}"
        logger.exception("状态变更异常 id=%s sku=%s", wc_id, result["sku"])
        return {**result, "success": False, "action": "failed", "error": error}


def _relabel_updated(result: dict[str, Any], semantic_action: str) -> dict[str, Any]:
    """把通用的 ``updated`` 换成调用方语义的动作名。

    ``action`` 会进入 API 响应与审计事件，"updated" 对运营和排障都不够明确；
    下架/恢复分别给出 ``unpublished`` / ``restored``，让结果自解释。
    """
    if result.get("action") == "updated":
        return {**result, "action": semantic_action}
    return result


def unpublish_product_from_wc(
    product: Any, *, budget: WcCallBudget | None = None
) -> dict[str, Any]:
    """下架：把 WooCommerce 商品移入回收站（``status = trash``）。"""
    result = set_wc_product_status(product, WC_STATUS_TRASH, budget=budget)
    return _relabel_updated(result, "unpublished")


def restore_product_to_wc(
    product: Any, *, budget: WcCallBudget | None = None
) -> dict[str, Any]:
    """恢复：按本地状态把 WooCommerce 商品还原为 ``publish`` 或 ``draft``。"""
    result = set_wc_product_status(product, desired_status_for_restore(product), budget=budget)
    return _relabel_updated(result, "restored")


def delete_wc_product_permanently(
    product: Any, *, budget: WcCallBudget | None = None
) -> dict[str, Any]:
    """彻底删除 WooCommerce 商品（``DELETE ?force=true``，不可逆）。

    ``force=true`` 才会绕过 WC 回收站真正删除；不带 force 的 DELETE 只是移入回收站。

    Returns:
        ``action`` 取值：``deleted`` / ``already_absent`` / ``skipped`` / ``failed``。
    """
    result = _base_result(product)
    budget = budget or WcCallBudget()
    auth, headers = _wc_credentials()

    wc_id = resolve_wc_id(product, auth=auth, headers=headers, budget=budget)
    if not wc_id:
        return {**result, "success": True, "action": "skipped",
                "reason": "not_linked",
                "message": "商品未关联 WooCommerce，无需删除"}
    result["woocommerce_id"] = wc_id

    url = f"{_wc_base_url()}/wp-json/wc/v3/products/{wc_id}"
    try:
        response = _wc_call(
            "DELETE",
            url,
            auth=auth,
            headers=headers,
            params={"force": "true"},
            budget=budget,
        )
        payload = response.json() if response.content else {}

        # 回读验证：确认真的不存在了（404）。
        exists_after, _ = _current_wc_status(
            wc_id, auth=auth, headers=headers, budget=budget
        )
        if exists_after:
            message = "WooCommerce 删除后回读仍能取到该商品，删除未生效"
            logger.warning("永久删除回读失败 id=%s sku=%s", wc_id, result["sku"])
            return {**result, "success": False, "action": "failed", "error": message}

        logger.info("已永久删除 WC 商品 id=%s sku=%s", wc_id, result["sku"])
        return {**result, "success": True, "action": "deleted", "verified": True,
                "deleted": bool(payload.get("deleted", True)),
                "message": "已从 WooCommerce 永久删除"}

    except requests.exceptions.HTTPError as exc:
        wc_status, wc_body = _wc_error_detail(exc)
        if wc_status == 404:
            return {**result, "success": True, "action": "already_absent",
                    "message": "WooCommerce 中该商品已不存在"}
        attempts = int(getattr(exc, "attempts", 0)) or _WC_MAX_ATTEMPTS
        error = f"WooCommerce 永久删除失败: HTTP {wc_status} {wc_body}".strip()
        logger.error("永久删除失败 id=%s sku=%s: %s", wc_id, result["sku"], error)
        return {**result, "success": False, "action": "failed",
                "error": error, "http_status": wc_status, "attempts": attempts}
    except requests.exceptions.RequestException as exc:
        wc_status, wc_body = _wc_error_detail(exc)
        attempts = int(getattr(exc, "attempts", 0)) or _WC_MAX_ATTEMPTS
        error = f"WooCommerce 永久删除失败: HTTP {wc_status} {wc_body}".strip()
        logger.error("永久删除失败 id=%s sku=%s: %s", wc_id, result["sku"], error)
        return {**result, "success": False, "action": "failed",
                "error": error, "http_status": wc_status, "attempts": attempts}
    except Exception as exc:
        error = f"WooCommerce 调用异常: {type(exc).__name__}: {exc}"
        logger.exception("永久删除异常 id=%s sku=%s", wc_id, result["sku"])
        return {**result, "success": False, "action": "failed", "error": error}
