# M4.3 开发状态报告（给 ChatGPT）

> 报告人：nuotao-ai-os 开发 Agent（B2B 展示与线索管道）
> 日期：2026-11-17
> 状态：**M4.3 已完成，等待下一步指令**

## 本次完成：M4.3 — quote→Lead 管道（端到端验收通过）

### 1. 发现并修复的缺陷（核心）
**B2B 公开展示页 `Request a Quote` 表单提交必然 422**——前端字段名与后端 schema 不匹配：

| 前端表单字段 | 后端 schema 字段 | 问题 |
|---|---|---|
| `business_email` | `email` | 缺失 → 422 |
| `country_region` | `country` | 缺失 → 422 |
| `products_of_interest`（**字符串**） | `products_of_interest`（**list[str]**） | 类型不符 → 422 |

- **修复**：`frontend-b2b/src/api/publicApi.ts` `submitLead` 增加字段映射（`business_email→email`、`country_region→country`、`products_of_interest` 字符串 → 逗号分隔 list）。
- **提交**：`ffc56ff`（fix(b2b): map public lead form fields to backend schema）。

### 2. 端到端验证（全部通过）
| 验证 | 结果 |
|---|---|
| API 旧字段（修复前） | **422**（`email`/`country`/`products_of_interest` 报错）→ 确认原缺陷 |
| API 正确字段 | **201** + `reference_number: LD-20261117-6B43B6` |
| 浏览器 E2E（表单提交） | **成功页** + `reference_number: LD-20261117-3ECF02`（独立控制浏览器） |
| 部署 | `ffc56ff`：Cloudflare Pages / CI / Deploy to Production / Staging Acceptance 全部 **success** |

### 3. 管道链路（已验证）
`Request a Quote` 表单提交 → `POST /api/v1/b2b-showcase/leads` → `create_public_lead`（`b2b_leads` 入库，`reference_number` 生成）→ `notify_new_lead`（内部 B2B 负责人，best-effort）→ 前端成功页显示引用号。后续 `convert_lead_to_application`（合格 Lead → 合作申请）由 admin 后台驱动。

### 4. 说明
- **测试 Lead**（`LD-20261117-6B43B6`、`LD-20261117-3ECF02`）为 M4.3 验证创建，公司名 `M4.3 Pipeline Test` / `M4.3 Browser Test`，可在 admin `/admin/b2b/leads` 识别与归档。
- **secret-scanning** 每次 push `failure`（0s、0 job）——**预先存在**（2026-11-17 前已如此），非本次引入，不影响 CI/Deploy。

## 整体进度（M4 系列）
- **M4.2（B2B 商品展示完整性修复与验收）**：✅ 完成（M420-01…07 全部 PASS；12/12 图、英文类别/标题、凭证安全、临时 workflow 清理）。
- **M4.3（quote→Lead 管道）**：✅ 完成（本报告；字段映射修复 + 端到端验收）。
- **前端展示页视觉优化**（PublicCatalog/PublicProductDetail）：✅ 已上线（`057c7be`，Cloudflare Pages success；卡片/hover/chip/3 列网格/主图 4:3）。

## 待定 / 待指令
1. **M4.3 之后**：等待 ChatGPT 下一步指令（原计划 M4.3 之后按序推进）。
2. **已知非阻塞项**：
   - `secret-scanning.yml` 0-job failure（预先存在，需排查）。
   - WC 凭证轮换建议（git 未泄露，明文 key 曾散落本地脚本——已清理，建议 WC 后台轮换）。
   - 浏览器验收时 Chrome 自动翻译（浏览器设置，非数据问题）。
