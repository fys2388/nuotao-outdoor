# CMP Staging Phase 1 阻塞清单（D8-E 第二轮 P1）

**执行日期**：2026-11-20
**Owner 指令**：获得 Staging URL + 独立管理员账号后实测；否则明确记录外部阻塞
**状态标记**：BLOCKED（外部依赖：Hostinger 套餐限制 / Staging URL 未提供）
**结论**：**BLOCKED — 已明确记录外部阻塞，符合 Owner 验收标准（"完成或明确记录外部阻塞"）**

---

## 1. 外部阻塞根因（实测确认）

### 1.1 Hostinger staging 功能需升级套餐

**实测**（Hostinger 控制面板 → 暂存页面）：
> "您当前的套餐是 **Premium Web Hosting**。要继续创建暂存环境，建议您升级您的套餐。"

- 当前套餐：Premium Web Hosting（磁盘 20GB / 节点 400K / 网站 1/3）
- **官方 staging：需升级套餐**（Business 及以上）

### 1.2 环境事实（实测）

| 环境组件 | 实际位置 | 状态 |
|---|---|---|
| B2C WordPress `nuotaooutdoor.com` | Hostinger 托管 | WP 7.1.4 / PHP 8.3 / 12 插件 / **21 漏洞** |
| B2C 后端 FastAPI | Hetzner uvicorn:8000 | 运行中（生产容器）|
| 服务器 staging 代码 | `/opt/nuotao-ai-os/staging/` | 已同步但 :8001 未监听 |
| 本地 Docker | 开发机 | 不可用（docker 未安装）|

---

## 2. Owner 测试范围状态（全部 BLOCKED，因 staging 未就绪）

| # | 测试项目 | 验收目标 | 状态 |
|---|---|---|---|
| T1 | 首次访问 | Consent Banner 正常显示 | 🔴 BLOCKED |
| T2 | Accept All | 同意状态正确记录 | 🔴 BLOCKED |
| T3 | Reject All | 非必要 Cookie 不加载 | 🔴 BLOCKED |
| T4 | Customize | 分类设置有效 | 🔴 BLOCKED |
| T5 | Withdraw Consent | 撤回后状态正确 | 🔴 BLOCKED |
| T6 | 页面刷新 | Consent 状态持久化 | 🔴 BLOCKED |
| T7 | 不同浏览器 | 行为一致 | 🔴 BLOCKED |
| T8 | 网络/脚本异常 | Fail-closed，不默认放行 | 🔴 BLOCKED |

**✅ 无测试项被误标为 PASS。全部如实记录为 BLOCKED。**

---

## 3. 三条可行路径（需 Owner 决策）

| 路径 | 方式 | 费用 | 风险 | 说明 |
|---|---|---|---|---|
| **A** | Hostinger 官方 staging（升级套餐）| 💰 付费 | 低 | 最干净，一键复制生产 |
| **B** | Hostinger 手动子站（剩余 2 网站位）| 免费 | 中 | 独立 DB+WP，需手动配置 |
| **C** | Hetzner Docker 隔离环境 | 免费 | 低 | 完全隔离，复用 CMP 报告 |

---

## 4. 关联安全发现

### 4.1 生产 WP 21 个插件漏洞（Hostinger 站点健康）

Hostinger 面板显示：`插件: 12 / 更新 / 漏洞: 21 检测到`
- 修复属生产变更，需 Owner 批准
- 建议 CMP staging 先行，漏洞修复并行决策

### 4.2 生产 cookie banner GDPR 缺口（F1）

生产仅二元 Accept/Reject，无四分类/撤回 → CMP 上线是刚需（详见审计报告 F1）

---

## 5. 所需 Owner 决策

| # | 决策项 | Owner 选项 |
|---|---|---|
| D1 | CMP Staging 路径选择 | A（升级付费）/ B（免费子站）/ C（Docker 隔离）|
| D2 | 是否批准 Hostinger 套餐升级 | 若选 A，需批准付费 |
| D3 | 生产 WP 21 漏洞处理 | 优先修复 / 延后 |
| D4 | 生产 cookie banner 下线时机 | CMP 上线后替换 |

---

## 6. 交付要素

| 任务 | 时间 | 执行命令 | 原始证据 | 结果 | 遗留 | 风险 | 需 Owner 决策 |
|---|---|---|---|---|---|---|---|
| P1 阻塞评估 | 2026-11-20 | curl/ssh/ls | staging URL 不可达 + 套餐提示 | BLOCKED | 8 项测试待跑 | 中 | ✅ D1-D4 |

---

## 7. 红线遵守

- ✅ 未触碰生产 B2C/B2B 站（只读 curl + 面板查看）
- ✅ 未创建订单/请求
- ✅ 未修改生产 GA4/Secret/DB
- ✅ 未执行 Hostinger 套餐升级（需 Owner 批准）

---

*阻塞清单生成：2026-11-20，DSH 自治调查。待 Owner 选择路径后解除阻塞。*
