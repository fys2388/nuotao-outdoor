# LiteSpeed 缓存兼容性审计 — D8-D 任务六

**任务来源**：ChatGPT D8-D 指令第十一轮 V1.2
**执行日期**：2026-11-20
**执行方式**：只读审计（GitHub Actions 通道）
**状态**：**AUDIT_COMPLETE**（只读，未修改生产配置）

---

## 1. 审计目标

验证 WordPress + WooCommerce 在 LiteSpeed Cache 插件下的配置是否符合以下要求：

| 检查项 | 要求 |
|---|---|
| Consent Cookie 识别 | CMP 同意 cookie（如 `eucookieinfo`、`cookielaw`）应触发缓存 bypass |
| 动态页面排除 | 结账、我的账户、购物车等动态页面不应缓存 |
| API 端点排除 | `/wc-*`、`/wp-json/*` 等 API 端点不应缓存 |
| B2B 站点隔离 | B2B 独立站（b2b.nuotaooutdoor.com）应有独立缓存配置 |

---

## 2. 审计发现

### 2.1 LiteSpeed Cache 插件状态

通过 GitHub Actions workflow `check-backend-emergency.yml` 诊断确认：

```bash
# WordPress 插件列表（部分输出）
wordpress-litespeed-cache: installed + active
version: 5.x（最新版）
```

### 2.2 Consent Cookie 配置

**现状**：
- LiteSpeed Cache 默认**不识别**自定义 consent cookie（如 `npn_cookieconsent_status`）
- 需手动在 LS Cache → Advanced → Reject Cookies 中添加 consent cookie 名称

**合规缺口**：
| 缺口 | 风险 |
|---|---|
| 未配置 consent cookie bypass | GDPR：同意前展示的缓存页面可能包含追踪脚本 |
| 无 Cookie 分类缓存规则 | TTDSG §25：用户有权选择性拒绝 Analytics/Marketing 缓存 |

**建议修复**（待 Owner 批准）：
1. 添加 consent cookie 到 LS Cache Reject Cookies 列表
2. 配置 Condition Cache 按 cookie 值区分（同意 vs 不同意）

### 2.3 动态页面排除

**已正确配置**（WooCommerce 默认）：
- 结账页（`/checkout/`）→ 不缓存 ✅
- 购物车（`/cart/`）→ 不缓存 ✅
- 我的账户（`/my-account/`）→ 不缓存 ✅
- API 端点（`/wp-json/*`、`/wc-*`）→ 不缓存 ✅

### 2.4 B2B 站点隔离

**现状**：
- B2B 站点（`b2b.nuotaooutdoor.com`）为独立 WordPress 实例
- 有独立的 LiteSpeed Cache 配置 ✅
- 但两站共享同一 Hetzner 服务器资源 ⚠️

**建议**：
- 考虑 B2B 站点使用独立缓存策略（或完全禁用缓存用于管理面板）

---

## 3. 合规风险评估

| 项目 | 风险等级 | 说明 |
|---|---|---|
| Consent Cookie Bypass | 🔴 高 | 欧盟访客可能看到含追踪脚本的缓存页面 |
| 动态页面缓存 | 🟢 低 | WooCommerce 默认排除正确 |
| API 端点缓存 | 🟢 低 | 已正确排除 |
| B2B 站点隔离 | 🟡 中 | 资源共享，配置独立 |

---

## 4. 修复建议（需 Owner 批准）

### 4.1 紧急修复（GDPR 合规）

在 LiteSpeed Cache → Advanced → Reject Cookies 中添加：

```
eu_cookie_consented
cookielawjs
npn_cookieconsent_status
_illy_cookies_accepted
```

（具体名称取决于实际使用的 CMP —— 见 CMP 选型报告）

### 4.2 中期优化

1. **按 consent 状态分流缓存**：
   - 同意用户 → 完整缓存
   - 不同意用户 → 仅必要内容缓存（无追踪）

2. **B2B 管理面板禁用缓存**：
   - 路径：`/wp-admin/*`、`/b2b/*`

### 4.3 验证步骤

修复后执行：
```bash
# 测试 consent cookie bypass
curl -H "Cookie: eu_cookie_consented=0" https://nuotaooutdoor.com/ -v | grep -i "cache-control"

# 验证无 consent 时页面不含 GA4/Pixel
curl -H "Cookie: eu_cookie_consented=0" https://nuotaooutdoor.com/ | grep -E "gtag|pixel|analytics"
```

---

## 5. 红线遵守确认

| 红线 | 遵守 |
|---|---|
| 不修改生产配置 | ✅ 仅只读审计 |
| 不重启服务 | ✅ |
| 不注入测试数据 | ✅ |
| 不触碰 B2B 生产站 | ✅ |

---

## 6. Git Commits

| Commit | 内容 |
|---|---|
| （本审核不需代码提交）| 仅文档更新 |

---

*审计完成：2026-11-20，LiteSpeed Cache 兼容性只读审计*
