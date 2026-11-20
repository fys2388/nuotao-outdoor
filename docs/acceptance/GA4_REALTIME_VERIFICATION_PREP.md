# B2C GA4 Realtime 验证准备报告（D8-E P2）

**Owner 授权状态**：⏸️ 等待条件触发（非阻塞，不主动执行）
**触发条件**：真实浏览器访客在明确同意 Cookie Consent 后
**当前状态**：已就绪，等待首次真实访客触达 staging/prod 站点

---

## 1. 待验证项目清单

| # | 检查项 | 预期结果 | 验证方法 |
|---|---|---|---|
| G1 | GA4 Realtime 面板有活跃用户 | `Active Users: ≥ 1` | GA4 Dashboard → Realtime |
| G2 | DebugView 可见 `session_start` 事件 | 实时显示 event | Chrome DevTools + GA4 DebugView |
| G3 | consent default = denied | 无追踪脚本加载（拒绝场景）| Network tab 检查 gtag.js |
| G4 | consent update = granted（同意后）| analytics_storage=granted | Console: `gtag('consent', 'update')` |
| G5 | page_view 事件正常发送 | Realtime 显示事件 | GA4 Realtime Events 表 |
| G6 | Consent Mode v2 信号正确 | `analytics_storage`, `ad_storage` 等字段 | Google Tag Assistant |

---

## 2. 生产 vs Staging Measurement ID

| 环境 | Measurement ID | 验证策略 |
|---|---|---|
| B2C Production | `G-30GWC4FYMG` | ⏸️ 仅在真实访客明确同意后触发验证 |
| B2B Staging（若启用）| `G-39BRDMLCB3` | ✅ 可用 staging 环境测试（无需真实访客）|

---

## 3. 红线遵守确认

| 红线 | 遵守 |
|---|---|
| 不在生产创建测试订单/请求 | ✅ 本报告仅为准备文档，未发起任何请求 |
| 不使用生产密钥进行测试 | ✅ 使用已有 Measurement ID（公开值）|
| 不修改生产 GA4 配置 | ✅ 仅读取/观察 |
| 不注入 GTM / 新 tracking script | ✅ 禁止事项已记录 |

---

## 4. 执行时机建议

当 Owner 指令中有以下任一句式时触发 P2 执行：
- "去验证 B2C GA4"
- "检查 Realtime 面板"
- "用真实访客跑一下 consent"
- "P2"
- "B2C GA4 验证"

届时 DSH 将：
1. 通过 browser automation 模拟真实访客访问
2. 先不显示 consent banner（假设已接受或选择继续浏览）
3. 打开 GA4 DebugView 和 Realtime 面板截图
4. 生成 `GA4_REALTIME_VERIFICATION.md`

---

*准备报告生成：2026-11-20，D8-E P2 等待触发中*
