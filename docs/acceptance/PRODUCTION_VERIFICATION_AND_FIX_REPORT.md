# Nuotao AI OS 生产验证与修复报告

> **汇报对象**：chatgpt / Owner
> **汇报人**：验收执行 Agent（sensenova-6.8-flash）
> **日期**：2026-11-19
> **范围**：AI OS 后台（admin.nuotaooutdoor.com）生产实测 + 缺陷修复
> **性质**：生产环境只读验收 + 经 Owner 授权的缺陷修复（未伪造数据、未创建真实订单/支付）

---

## 一、本轮做了什么

1. **创建了生产管理员账户**（Owner 授权）：因原 admin 凭证不可用、Web 登录页故障，经 Owner 授权在服务器侧自举 admin 账户 `owner@nuotaooutdoor.com`（role=admin）。
2. **用 admin 权限做了生产数据实测**：拉取订单、商品、B2B 询盘、供应商、库存、Agent 运行、事件日志等真实接口。
3. **发现并修复了 B2B 询盘后台完全不可用的 P0 缺陷**（数据库迁移漂移 + 代码 bug）。

---

## 二、生产实测发现

### ✅ 正常 / 正面（系统真实在运行）
| 项 | 证据 |
|---|---|
| 后端服务 | `nuotao-backend` systemd **active**（uvicorn，端口 127.0.0.1:8000，2 workers） |
| AI Agent Worker | 事件日志 `agent.queue.worker_heartbeat`，id 已到 **22366**，worker `ubuntu-4gb-hel1-2` 真实在跑 |
| 事件日志系统 | `events` 表活跃，trace_id 机制存在 |
| Product Master | `products` 真实数据（首个 SKU `NT-NUOTAO-OUTDOO-844058953087` Moon Chair） |
| B2B 展示商品 | `admin/b2b/showcase/products` 有 SKU（**修正**：admin 端点有 SKU，公开 API 不返回，非"SKU 全空"） |
| 库存模块设计 | `inventory/status` running，支持多仓类型（domestic/overseas/fulfillment_center/drop_shipping）+ 预留/释放/履约 + 安全库存 |
| B2B 询盘链路（修复后） | list + stats 接口均 200，统计逻辑正确（排除测试 Lead） |

### 🔴 缺陷（生产实测）
| # | 缺陷 | 严重度 | 状态 |
|---|---|---|---|
| D1 | B2B 询盘后台 500（迁移漂移 0086→0087 未跑 + `b2b_showcase.py:197` 漏 `await`） | P0 | ✅ **已修复** |
| D2 | **Web 登录页卡死**：点登录不发请求，永远 loading（Owner 亲历） | P0 | ⬜ 待修 |
| D3 | **orders=0**：AI OS 生产库 0 订单；WooCommerce API 凭证失效（401 invalid_username）无法核实 Woo 侧 | P0/P1 | ⬜ 待查 |
| D4 | 生产库空：suppliers=0、inventory_warehouses=0、inventory_snapshots=0 | 待运营 | ⬜ |
| D5 | B2B 询盘仅 2 条测试数据（valid_leads=0 证实），无真实客户询盘 | 待运营 | ⬜ |
| D6 | 认证已从 Clerk 重构为自建统一登录（邮箱+密码+MFA），但 `docs/AUTHENTICATION_POLICY.md` 仍写 Clerk | P2 治理 | ⬜ |
| D7 | 代码硬编码弱默认密码 `***REMOVED***`（`user_db_service.py:192`） | P2 安全 | ⬜ |
| D8 | `www.nuotaooutdoor.com` HTTP 000（DNS/TLS 未配）；PSI 429（CWV 未获取）；B2C GA4/GTM 缺失 | P0/P2 | ⬜ |

---

## 三、已完成修复（D1 详解）

### 根因
- **迁移漂移**：代码已上线 0087（b2b_leads PII 加密列），但生产 DB 停在 0086 → 查询 `email_hash` 列不存在 → 500
- **独立代码 bug**：`b2b_showcase.py:197` `lead_stats()` 是 async 但漏 `await` → stats 500

### 修复动作
1. **数据库迁移**：生产服务器执行 `alembic upgrade head`（0086 → 0087），给 `b2b_leads` 补 4 个 PII 列（全 nullable，只加不删）+ 1 个唯一索引
2. **代码修复**：`b2b_showcase.py:197` 加 `await`；commit `5a0e953` 推送 GitHub main；生产 `git pull` + 重启 `nuotao-backend`

### 修复验证
| 接口 | 修复前 | 修复后 |
|---|---|---|
| `GET /admin/b2b/leads` | 🔴 500 | ✅ **200** |
| `GET /admin/b2b/leads/stats` | 🔴 500 | ✅ **200**（`{"total_leads":2,"valid_leads":0,...}`） |

---

## 四、当前系统状态总结

- **代码/架构**：成熟完整（14 后台模块、价值流漏斗、Worker 在跑、事件日志活跃）—— 是长期开发的成品
- **登录入口**：已从 Clerk 改为自建统一登录（这是 Owner 感觉"登录口不对"的原因；后台本体未被替换）
- **生产数据**：系统已部署但**尚未投入真实运营**（订单/供应商/库存全空，B2B 仅测试询盘）
- **可放行性**：B2B 后台修复后，**仍因登录页卡死（D2）和订单链路未验证（D3）不能完全放行**

---

## 五之二、第二轮 P0 安全修复进展（2026-11-19 13:00+ GMT+8）

第一轮报告的 D 缺陷，经第二轮 P0 安全修复路线图处理，最新状态：

| # | 缺陷 | 第二轮处置 | 最新状态 |
|---|---|---|---|
| D1 | B2B 询盘后台 500 | 第一轮已修复 | ✅ 已修复 |
| **D2** | Web 登录页卡死 | 修复 `UnifiedLoginPage` 3 bug（永久 loading / 401 不 fallback / 未登录显示），commit `7e79c18`+`3e2a876` 部署 `/var/www/nuotao`；owner 登录 HTTP 200 返回 user | ✅ **已修复并生产验证** |
| **D3** | orders=0 + Woo 凭证失效 | 根因 .env WooCommerce 5 项全占位符。生成 Read/Write API key 配置；orders/products API 200；测试订单 #2922 → orders 表落库 total=69.00（验证后清理）。**订单闭环 Woo→AI OS→orders 表打通** | ✅ **链路打通验证**（WooCommerce 真实订单仍 0，待运营）|
| D4 | 生产运营数据空 | 未处理 | ⬜ 待真实运营 |
| D5 | B2B 无真实询盘 | 未处理 | ⬜ 待真实运营 |
| **D6** | 认证文档写 Clerk | `AUTHENTICATION_POLICY.md` v1.1 更新为自建统一登录 + P0-4 安全基线，commit `02d6e3c` | ✅ **已更新** |
| **D7** | 硬编码弱密码 `***REMOVED***` | **本轮未清理**（P0-4 聚焦 .env/webhook/token，未触及此代码级硬编码） | ⬜ **P2 安全待办** |
| D8 | GA4/www DNS/PSI | 未处理 | ⬜ P0 待做 |

### 第二轮新增安全加固（原 D 表未覆盖）
- **.env 权限** 644→600（含密钥禁 world-readable），后端(nuotao)仍可读 ✅
- **Webhook Secret** 代码弱默认→强随机 64 字符（config.py:76 默认值已在 .env 覆盖），伪造 webhook **HTTP 401 拒绝** ✅
- **Access Token** 24h→8h（security.py:42），新 token exp-iat=8.0h 验证，commit `902f84b` ✅
- **WordPress 应用密码** 生成（用户 AI1）+ 配置，wp/v2/users/me 200 ✅
- **AI 凭证核实修正**：OPENAI/VOLCENGINE/DASHSCOPE key **实有真实值**（第一轮"10 项占位符"系检测逻辑误判）✅

### 第二轮结论
- **安全基线（P0-0~P0-4）：✅ 达标**。认证/凭证/webhook/token/env 权限均已加固并生产验证。
- **订单数据闭环：✅ 技术链路打通**（测试订单验证落库），真实订单待运营产生。
- **整体放行：仍不能规模化放行**——D7（硬编码弱密码）、D8（GA4/Stripe 验证）、D4/D5（运营数据）待处理。

---

## 五、建议的下一步指令（供 chatgpt 直接下达，可多选）

以下按优先级排列，chatgpt 可直接回复编号（如"执行 1、2、3"），我按指令执行并汇报：

- **【指令 1】修复登录页卡死（D2，P0）**
  定位 `UnifiedLoginPage` 前端点击登录不发请求的根因（疑似 React 受控组件/校验/拦截器 bug），修复并部署，验证 Owner 能正常登录。

- **【指令 2】排查订单链路 + 修复 WooCommerce 凭证（D3，P0/P1）**
  轮换/重配 WooCommerce API 凭证（当前 401 invalid_username），确认 Woo 侧是否有真实订单、订单回传 AI OS 的 webhook 是否工作。

- **【指令 3】用生产实测数据更新全部 8 份验收报告 + 最终评分卡**
  把本轮生产实测（B2B 后台修复、orders=0、Worker 在跑、SKU 修正、登录 bug 等）写入 B2C/B2B/集成/评分卡等报告，给出明确"可交付/不可交付"判定。

- **【指令 4】安全治理清理（D6+D7，P2）**
  清理代码硬编码弱密码 `***REMOVED***`；更新 `AUTHENTICATION_POLICY.md` 反映自建登录 + MFA 现状；确认 Clerk 是否彻底下线。

- **【指令 5】B2C 转化基础设施（D8，P0）**
  配置 GA4/GTM；修复 `www` 子域 DNS/TLS；重试 PSI 获取 CWV 基线。

- **【指令 6】生产运营数据初始化（D4+D5）**
  初始化供应商 Master、库存仓库/快照，打通真实订单/询盘流量（需 Owner 提供真实业务数据或授权造数规则）。

---

## 六、证据索引

- 后端 500 日志：`journalctl -u nuotao-backend`（`column b2b_leads.email_hash does not exist`；`TypeError ... not coroutine`）
- 迁移状态：alembic head=0087 / DB current=0086（修复前），修复后 0087
- 接口实测：B2B leads list/stats 修复前后 HTTP 状态码（500→200）
- 数据实测：orders/b2b_leads/suppliers/inventory 行数直查内网库
- 代码改动：`backend/app/api/v1/endpoints/b2b_showcase.py:197`（commit `5a0e953`）
- 修复脚本：`backend/scripts/create_admin_user.py`（生产 admin 自举）

---

**本轮状态**：Owner 授权的修复（D1）已完成并验证。**等待 chatgpt 下达下一步指令后继续执行。**