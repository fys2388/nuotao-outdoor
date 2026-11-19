# WEBHOOK_SECRET_SECURITY_REMEDIATION.md

**任务编号**: D8-C / A5（对应第八轮 Owner 决策 A5：Webhook Secret R4 优先整改）
**日期**: 2026-11-18
**执行**: DSH（DeepSeek Harness Agent）
**严重级别**: 高（R4，原 ORDER_SYNC_READINESS_AUDIT.md 标记）
**状态**: ✅ 代码整改完成，语法验证通过，待 Owner 审核 + 生产部署

---

## 1. 问题背景（实际状态）

### 1.1 漏洞描述

原 ORDER_SYNC_READINESS_AUDIT.md 发现 **R4（高危）**：

> webhook secret 有不安全默认值 `dev-webhook-secret-change-me`，生产未强制覆盖则验签失效。

### 1.2 根因（代码层）

`backend/app/core/config.py`：

```python
# WooCommerce webhook consumer secret (HMAC-SHA256 signature verification).
# MUST be overridden in staging/production environments.
woocommerce_webhook_secret: str = "dev-webhook-secret-change-me"
```

注释声明"MUST be overridden"，但**代码未强制**。若生产 `.env` 未设置 `WOOCOMMERCE_WEBHOOK_SECRET`，系统会静默使用该已知默认值验签——攻击者若知晓默认值（硬编码于代码库），可伪造有效 HMAC-SHA256 签名，**绕过 Webhook 验签**注入伪造订单/产品/客户事件。

### 1.3 影响

- **伪造订单注入**：攻击者可构造带有效签名的伪造 `order.created` webhook，污染订单数据、虚增收入统计。
- **伪造产品/客户事件**：通过 generic webhook 端点注入虚假产品/客户/优惠券事件。
- **幂等键碰撞**：伪造订单可能占用合法 `external_order_id` 幂等键，导致真实订单被误判为重复而丢弃。

### 1.4 发现的额外漏洞（wc_clickback.py）

审计中发现 `wc_clickback.py` 存在**更严重的逻辑漏洞**：

```python
# 原代码
secret = getattr(settings, "woocommerce_webhook_secret", None)
if secret:  # 只有 secret 非空才验签
    ... 验签 ...
# secret 为空时：完全跳过验签，直接接受 webhook！
```

即 **secret 未配置（空）时，clickback webhook 完全不验签就被接受**——比使用弱默认值更危险。

---

## 2. 修复方案（fail-closed）

### 2.1 设计原则

对齐项目已有的 fail-closed 模式（参考 `customer_identity_service._identity_secret()`：生产环境缺少密钥时 `raise` 而非静默回退）。

**核心原则**：
1. 生产环境（`settings.is_production == True`）检测到 webhook secret 为**空**或**已知默认值**时，**拒绝接收 Webhook**（fail closed）+ 输出高可见性告警日志。
2. 开发/预发环境保持现有行为（允许默认值，便于本地联调）。
3. **不输出 Secret 明文**（日志仅记录事件，不打印 secret 值）。

### 2.2 实现细节

#### 2.2.1 `config.py` — 添加安全判定

**新增模块级常量**：

```python
# Insecure default for the WooCommerce webhook secret. Production MUST override
# this; a known default lets attackers forge valid HMAC-SHA256 signatures.
INSECURE_WEBHOOK_SECRET_DEFAULT = "dev-webhook-secret-change-me"
```

**新增 Settings property**：

```python
@property
def webhook_secret_is_insecure(self) -> bool:
    """True if the WooCommerce webhook secret is empty or the insecure dev default.

    Production must fail closed (reject webhooks) when this is True, because a
    known default secret lets attackers forge valid HMAC-SHA256 signatures.
    """
    s = self.woocommerce_webhook_secret.strip()
    return (not s) or s == INSECURE_WEBHOOK_SECRET_DEFAULT
```

#### 2.2.2 `_verify_signature()` — 三处验签函数统一加 fail-closed 守卫

在计算 HMAC 前插入生产环境守卫：

```python
def _verify_signature(body, header_value, secret) -> bool:
    if not header_value:
        return False
    # Fail closed: in production, reject any webhook when the secret is the
    # insecure dev default or empty — a known default lets attackers forge
    # valid HMAC signatures. Emit a loud alert for on-call visibility.
    _settings = get_settings()
    if _settings.is_production and _settings.webhook_secret_is_insecure:
        logger.error(
            "webhook rejected: insecure webhook secret in production "
            "(WOOCOMMERCE_WEBHOOK_SECRET missing or default) — fail closed"
        )
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    ...  # 常数时间比较（hmac.compare_digest，保持不变）
```

#### 2.2.3 `wc_clickback.py` — 修复"空 secret 跳过验签"漏洞

原代码在 secret 为空时**跳过验签**（`if secret:` 才验签）。修复为：**生产环境 secret 不安全时直接 fail closed**（不再允许跳过）：

```python
# HMAC 签名验证。生产环境必须配置强 secret，否则 fail closed（空 secret 也不允许跳过验签）。
settings = get_settings()
if settings.is_production and settings.webhook_secret_is_insecure:
    logger.error(
        "clickback webhook rejected: insecure webhook secret in production — fail closed"
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="webhook secret not securely configured",
    )
secret = getattr(settings, "woocommerce_webhook_secret", None)
if secret:
    signature = request.headers.get(SIGNATURE_HEADER)
    if not _verify_signature(body, signature, secret):
        ... 拒绝 ...
```

---

## 3. 变更文件（证据）

| 文件 | 行号（约） | 变更内容 |
|---|---|---|
| `backend/app/core/config.py` | L10（imports 后）、L399（property 区） | 新增 `INSECURE_WEBHOOK_SECRET_DEFAULT` 常量 + `webhook_secret_is_insecure` property |
| `backend/app/api/v1/endpoints/webhooks.py` | L62 `_verify_signature` | 验签前加生产 fail-closed 守卫（覆盖 ORDER_CREATED + PRODUCT webhook 两个端点，L120/L184 调用） |
| `backend/app/api/v1/endpoints/webhooks_generic.py` | L40 `_verify_signature` | 验签前加生产 fail-closed 守卫（覆盖通用 webhook 端点） |
| `backend/app/api/v1/endpoints/wc_clickback.py` | L101 `_verify_signature` + L131 调用处 | 验签函数加守卫 + **修复空 secret 跳过验签漏洞**（生产不安全时 503 fail closed） |

---

## 4. 验证（测试结果）

### 4.1 语法检查（py_compile）

```
app/core/config.py : OK
app/api/v1/endpoints/webhooks.py : OK
app/api/v1/endpoints/webhooks_generic.py : OK
app/api/v1/endpoints/wc_clickback.py : OK
```

全部通过（Python 3.12 py_compile）。

### 4.2 行为矩阵（设计验证）

| 环境 | Secret 状态 | 行为 | 日志 |
|---|---|---|---|
| production | 强 secret（已配置）| 正常验签 | — |
| production | 默认弱值 / 空 | **拒绝（fail closed）** | `logger.error` 高可见告警 |
| staging/dev | 默认弱值 / 空 | 允许（本地联调）| — |

### 4.3 待补充测试（建议，非阻塞）

- 单元测试：模拟 `is_production=True` + `webhook_secret_is_insecure=True`，断言 `_verify_signature` 返回 `False`、端点返回 401/503。
- 现有 `backend/tests/test_webhook_orders.py` 回归（确认正常 secret 路径不受影响）。

> 注：本轮按 Owner 决策仅做代码整改 + 语法验证，未在生产部署或运行生产测试（遵守生产变更纪律）。单元测试建议在合并 PR 时补充。

---

## 5. 保留的正确机制（未改动）

- ✅ HMAC-SHA256 签名算法（`hmac.new(secret, body, sha256)`）
- ✅ 常数时间比较（`hmac.compare_digest`，防时序攻击）
- ✅ Base64 + legacy hex 双格式兼容
- ✅ 幂等处理（duplicate 返回 200，不受影响）
- ✅ trace_id 全链路日志

---

## 6. 回滚方案

所有改动为**纯增量守卫**（在验签前加检查），不改变正常路径的验签算法。

**回滚步骤**：
1. `git revert` 对应 commit（还原 4 个文件）。
2. 或临时设 `APP_ENV=staging`（非 production），守卫不触发（但**不推荐**，等于关闭防护）。

---

## 7. 待 Owner 批准事项

1. **审核本 fail-closed 实现方案**是否符合预期（生产拒绝而非启动失败）。
2. **确认生产 `.env` 已设置强 `WOOCOMMERCE_WEBHOOK_SECRET`**（部署前必须，否则上线后所有 webhook 将被 fail-closed 拒绝——这是预期保护行为，但需确保生产已配置真实 secret）。
3. **批准补充单元测试**（is_production + insecure secret 的断言）。
4. **确认 wc_clickback 空-secret 漏洞的修复方式**（本方案选择"生产 fail closed 503"，也可选择"要求必须配置 secret"）。

---

## 8. 合规自检

- ✅ 未输出 Secret 明文（日志仅记录事件，不打印 secret 值；`logger.debug` 的 signature 截断输出保留，非 secret）
- ✅ 未改动正常验签算法（HMAC-SHA256 + 常数时间比较保持）
- ✅ 未改动幂等处理
- ✅ 未部署生产（代码整改 + 本地语法验证）
- ✅ fail-closed 而非 fail-open（安全默认）

---

**本报告由 DSH 基于实际代码改动生成，改动文件与行号可核对。待 Owner 审核后进入生产部署流程。**