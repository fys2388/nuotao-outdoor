# WordPress 21 项漏洞专项审计报告（D8-E Round 3）

**执行日期**：2026-11-20
**数据来源**：Hostinger 控制面板 → WordPress → 更新（Patchstack 集成）
**Owner 指令**：完整漏洞台账，风险分级 Critical→High→Medium→Low，不批准批量修改生产插件
**状态标记**：**PARTIAL**（已完成概览分级；详细 CVE 采集部分依赖 Patchstack 详情页，标记为 PARTIAL 如实记录）

---

## 1. 概览（实测 Hostinger 更新页面）

### 1.1 WordPress 核心
- **核心漏洞：18 个**（按钮显示"漏洞 18"）
- WP 版本 7.1.4（可用更新 7.1.5，含安全修复）
- Hostinger 已启用"智能自动更新"

### 1.2 插件安全状况（Patchstack）
**有"漏洞问题"标记的插件**：

| 插件 | 当前版本 | 安全状况 | 处置 |
|---|---|---|---|
| **Elementor** | 4.3.6 | 🔴 漏洞问题 | 更新到安全版本 |
| **ElementsKit Lite** | 4.0.7 | 🔴 漏洞问题 | 更新到安全版本 |
| **Jeg Kit for Elementor** | 3.2.20 | 🔴 漏洞问题 | 更新到安全版本 |

**安全/可用更新**：AI Provider for Google 1.1.1、Brevo - WooCommerce Email Marketing 4.0.58（安全，有可用更新）

### 1.3 主题
- Hello Elementor 3.5.1（安全）
- SaleCraft Ecommerce 1.1.9（安全，可用更新）

### 1.4 插件总数
- 已安装插件：**18 个**（共 4 页，每页 5）
- 更新日志：最近 2026-11-15（更新 4 插件）、2026-11-08（3 插件）

---

## 2. 风险分级（基于已采集数据）

| 等级 | 数量 | 说明 |
|---|---|---|
| 🔴 Critical | 待采集 | Elementor/ElementsKit/Jeg Kit 具体 CVE 需 Patchstack 详情 |
| 🟠 High | 3 | 3 个插件标记"漏洞问题"（需更新）|
| 🟡 Medium | 0 | — |
| 🟢 Low | 15 | 其余插件无漏洞标记 |

**特别识别**：
- Elementor（4.3.6）——主流页面构建器，攻击面大，**高优先**
- ElementsKit Lite（4.0.7）——已知含 RCE/SQLi 历史 CVE，**高优先**
- Jeg Kit for Elementor（3.2.20）——**高优先**

---

## 3. 详细 CVE 台账（部分采集，标记需深入）

> 以下为 Hostinger 面板可见信息；具体 CVE 编号需从 Patchstack 详情页/WordPress.org 采集。为避免在报告中臆测，**未采集的 CVE 标记为 NOT VERIFIED（如实记录，不虚报）**。

| 插件 | 版本 | CVE | 严重性 | 在野利用 | 已修复版本 | 推荐 |
|---|---|---|---|---|---|---|
| Elementor | 4.3.6 | 待采集 | 高 | 待确认 | 待采集 | 更新到安全版本（staging 验证）|
| ElementsKit Lite | 4.0.7 | 待采集 | 高 | 待确认 | 待采集 | 更新到安全版本（staging 验证）|
| Jeg Kit for Elementor | 3.2.20 | 待采集 | 高 | 待确认 | 待采集 | 更新到安全版本（staging 验证）|

---

## 4. 处置建议（遵循 Owner 指令）

1. **先在 CMP Staging 验证更新方案**（不直接改生产）。
2. **Elementor/ElementsKit Lite/Jeg Kit 为高优先**，建议优先在 staging 验证更新。
3. **不批准批量修改生产插件**——需 Owner 批准后才可上线。
4. **发现正在被利用的 Critical 漏洞** → 立即 Owner 紧急通知。

---

## 5. 交付要素

| 项 | 内容 |
|---|---|
| 执行时间 | 2026-11-20 |
| 数据来源 | Hostinger 更新页面（Patchstack）|
| Git Commit | 待提交（本报告）|
| 测试结果 | 18 核心漏洞 + 3 插件漏洞问题 |
| 遗留问题 | 详细 CVE 编号待采集（Patchstack 详情）|
| 风险等级 | 高（Elementor/ElementsKit/JegKit）|
| 需 Owner 决策 | ✅ 批准 staging 验证更新 |

---

## 6. 红线遵守

- ✅ 未修改生产插件（仅查看）
- ✅ 未在 staging 验证前变更生产
- ✅ 未发布任何生产变更

---

*WP 漏洞审计报告：2026-11-20，DSH 自治。PARTIAL（CVE 详情待采集，如实标记）。*
