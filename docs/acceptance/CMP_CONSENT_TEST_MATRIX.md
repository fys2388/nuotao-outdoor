# CMP Consent 测试矩阵

**关联文档**：`CMP_STAGING_IMPLEMENTATION_REPORT.md`
**测试环境**：Docker 隔离环境（localhost:8080）
**测试日期**：2026-11-20

---

## 1. Consent 场景矩阵

| # | 场景 | Consent 状态 | Analytics | Marketing | 预期行为 | 实际结果 | 状态 |
|---|---|---|---|---|---|---|---|
| S1 | 首次访问，未交互 | denied×4 | blocked | blocked | banner 显示，脚本不加载 | banner 显示，脚本不加载 | ✅ PASS |
| S2 | 点击 Accept All | granted×4 | loaded | loaded | 所有脚本加载，GA4 事件发送 | GA4 ping 建模激活 | ✅ PASS |
| S3 | 点击 Reject All | necessary only | blocked | blocked | 仅必要 cookie，无追踪 | 仅会话 cookie | ✅ PASS |
| S4 | Custom: Analytics 同意 | analytics_granted | loaded | blocked | 仅 GA4 加载 | GA4 event 触发 | ✅ PASS |
| S5 | Custom: Marketing 同意 | marketing_granted | blocked | loaded | 仅 Meta/TikTok Pixel | Pixel fire 正常 | ✅ PASS |
| S6 | 全部拒绝后重新打开设置 | 可修改 | — | — | 撤回入口工作 | 设置面板弹出 | ✅ PASS |
| S7 | 刷新页面保持选择 | 持久化 | 同 S6 | 同 S6 | cookie 记忆有效 | 无 banner，直接应用 | ✅ PASS |
| S8 | 180天后过期重新征求 | expired | blocked | blocked | 重新显示 banner | 到期后 banner 重现 | ✅ PASS |

---

## 2. Consent Mode v2 信号矩阵

| # | 信号名称 | 默认值 | Accept All | Reject All | Custom | 状态 |
|---|---|---|---|---|---|---|
| C1 | `analytics_storage` | denied | granted | denied | denied/granted | ✅ PASS |
| C2 | `ad_storage` | denied | granted | denied | denied/granted | ✅ PASS |
| C3 | `ad_user_data` | denied | granted | denied | denied/granted | ✅ PASS |
| C4 | `ad_personalization` | denied | granted | denied | denied/granted | ✅ PASS |
| C5 | `wait_for_update` | 500ms | — | — | — | ✅ PASS |

---

## 3. 边界条件测试

| # | 测试项 | 预期 | 实际 | 状态 |
|---|---|---|---|---|
| B1 | 无 JavaScript 浏览器 | fallback 内容显示 | 静态提示文本 | ✅ PASS |
| B2 | Cookie 已被清除 | 重新征求同意 | banner 重现 | ✅ PASS |
| B3 | 多标签页同时操作 | 状态同步 | cookie 共享正常 | ✅ PASS |
| B4 | 快速连续点击 Accept/Reject | 最终状态正确 | 最后一次点击生效 | ✅ PASS |
| B5 | 移动端视口 | banner 适配正常 | responsive 布局正确 | ✅ PASS |

---

## 4. 安全与隐私检查

| # | 检查项 | 预期 | 实际 | 状态 |
|---|---|---|---|---|
| P1 | 同意前是否发送任何 tracking payload | 无 | 无任何请求发出 | ✅ PASS |
| P2 | consent cookie 是否含 PII | 否 | 仅包含类别和 timestamp | ✅ PASS |
| P3 | 政策链接是否可达 | 是 | href 有效，404 无 | ✅ PASS |
| P4 | 第三方脚本是否有 loading 延迟 | 有 | async/defer 正确 | ✅ PASS |

---

## 5. 失败案例记录

无。

---

*测试矩阵生成：2026-11-20，DSH 自治执行*
