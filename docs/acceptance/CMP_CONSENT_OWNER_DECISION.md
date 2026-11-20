# CMP Consent Owner 决策记录（D8-E P1）

**决策日期**：2026-11-20
**相关文档**：`CMP_STAGING_IMPLEMENTATION_REPORT.md`、`CMP_STAGING_PHASE1_ACCEPTANCE_REPORT.md`

---

## 决策背景

Owner 在 D8-E 指令中明确指出：

> "需要确定当前系统中 cookie consent 管理的唯一拥有者：Complianz 是否作为唯一 consent owner，`class-tracking.php` 是否仅作为被 consent state 驱动的追踪脚本加载器（而非独立的 consent 决策层）。需要在 staging 环境中明确此边界后再推进。"

---

## 技术决策

### 架构分层

```
┌─────────────────────────────────────────────┐
│         Consent Decision Layer               │
│         （唯一 Consent Owner = Complianz）    │
│                                              │
│  Cookie Banner 展示                         │
│  Cookie 分类（Necessary/Analytics/Marketing/Preferences）│
│  同意/拒绝/撤回入口                          │
│  同意凭证存储                                │
│  Consent Mode v2 信号发射                    │
└─────────────────┬───────────────────────────┘
                  │ 写 cookie: cmplz_*, 发 gtag('consent', 'update')
                  ▼
┌─────────────────────────────────────────────┐
│         Tracking Loader Layer                │
│         class-tracking.php（被驱动的加载器）  │
│                                              │
│  读取 Complianz cookie/cmplz_status          │
│  根据 consent state 决定是否注入跟踪脚本      │
│  仅负责加载/不加载，不做 consent 决策          │
└─────────────────────────────────────────────┘
```

### 决策要点

| 组件 | 角色 | 是否有 consent 决策权 |
|---|---|---|
| **Complianz** | **唯一 Consent Owner** | ✅ 是（Banner 展示、分类管理、同意/拒绝/撤回）|
| `class-tracking.php` | Tracking Script Loader | ❌ 否（仅读取 consent state 决定是否注入脚本）|
| LiteSpeed Cache | 缓存层 | ❌ 否（须将 cookie consent 页面排除缓存）|
| GA4 gtag.js | Analytics 执行层 | ❌ 否（受 consent state 控制触发）|

### 代码层约束

```php
// class-tracking.php 的正确实现模式：
if (compliance_consent_given('analytics_storage')) {
    // 允许注入 GA4
    load_ga4_script();
} else {
    // 阻塞 GA4（Consent Mode v2 default denied）
    // 但不做其他 consent 决策
}
```

---

## 生效范围

- **立即生效**：所有新开发的 consent-related 功能均通过 Complianz 统一管理
- **迁移路径**：现有 `class-tracking.php` 中的 consent 判断逻辑将改为只读 Complianz cookie 状态，移除任何独立的 consent 决策
- **审计追踪**：每次 consent 变更通过 Complianz 写入 `cmplz_consent_log`，class-tracking.php 仅作数据消费者

---

## 验证方法

Phase 1 Staging 上线时验证：
1. 删除/禁用 Complianz 插件 → `class-tracking.php` 应无法获取 consent state → 默认拒绝所有追踪（fail-closed）
2. 直接修改 `class-tracking.php` 逻辑 → 不应能绕过 Complianz 的 consent 决策

---

*决策记录：2026-11-20*
