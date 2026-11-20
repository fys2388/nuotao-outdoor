# D8-E 1688 凭据轮换与 Provider 路线图报告

> 对应指令：D8-E 1688 凭据轮换与长期数据源升级指令。
> 日期：2026-11-20。执行方：DSH (sensenova)。
> 本报告不含任何凭据明文。P0 中涉及凭据的步骤已按安全红线交由 Owner 完成。

---

## 一、P0：Cookie 轮换闭环状态 — **待 Owner 一步**

### 已完成（DSH，全部进 main 且验证）
| 项 | 状态 | 证据 |
|---|---|---|
| Cookie 状态诊断 | ✅ 确诊旧 Cookie 失效 | 非硬编码商品(994387007112) Playwright 走 Cookie 注入，返回 generic 占位名 `1688 Product`（登录墙外壳），非真实商品 |
| `verify-1688-cookie.yml` | ✅ 建成 | 一键验 Cookie 死活，只回 VALID/EXPIRED，Cookie `::add-mask::` 掩码，绝不回显值 |
| `rotate-1688-cookie.yml` | ✅ 建成并端到端验证 | Secret→原子写 .env→重启 nuotao-backend→自动诊断，四环节全通（掩码✓ 写.env✓ 重启active✓ 诊断✓） |
| Backend | ✅ ACTIVE | 轮换 workflow 实测 `nuotao-backend=active` |
| CI | ✅ PASS | PR #9-#13 全部合并，Backend CI 通过 |
| 敏感凭据 | ✅ 无泄露 | 所有日志只见 length，值经 `::add-mask::`；文档/报告零 Cookie 明文 |

### 唯一阻塞：等待 Owner 更新 GitHub Secret
- **连续 4 轮探针确认** Secret `ALI1688_LOGIN_COOKIE` 内仍是过期旧值（`length=196`，诊断持续 EXPIRED）。
- 按指令"Owner 尚未更新 Secret 时不得反复执行无意义探针、不得自行提取浏览器 Cookie"——**DSH 已停止探测，等待 Owner 信号**。
- 有效 Cookie 只能来自 Owner 本人在浏览器登录 1688（DSH 无读 cookie store 能力，且提取 Cookie 违反 browser-skill 硬红线 `Never extract cookies` + 项目安全铁律，不能经聊天明文）。

### Owner 更新后 DSH 将执行（严格 VALID 验收）
按指令一的第 1-8 步：触发 rotate workflow → 验证 workflow 成功 → 验证 .env 原子更新 → 验证 Backend ACTIVE → 用真实商品 ID Playwright 抓取 → 检查名称/价格/SKU/规格 → 确认 `data_source` 为真实抓取 → 确认无 `hardcoded_fallback` 进自动上架。

**验收门禁（采纳 ChatGPT 严格 VALID 定义）**：
- Cookie：VALID —— 但**不以 HTTP 200/页面加载成功为证据**，必须商品名为真实名（非 `1688 Product`）。
- 真实商品抓取：PASS（价格来自实际页面、SKU 真实、product_id 一致）。
- `data_source` = 真实抓取来源，**非** `hardcoded_fallback`。
- Backend ACTIVE；CI PASS；敏感凭据无日志泄露。
- 抓取失败必须 fail-closed，不回退假数据自动上架。

### P0 附带修复（超出原范围但必要，已进 main）
- **PR#13 更严重隐患修复**：`import_from_1688` 原只看 `success` 不读 `data_source`，导致 `hardcoded_fallback` 假数据可流进 `run_pipeline` 自动上架 WooCommerce。已加闸门阻断 + 单测，CI 通过。
- 修复诊断脚本 3 个原有 bug（asyncio.to_thread 包 async、误选硬编码商品、PYTHONPATH 缺失），使 Cookie 验证第一次真正可信。

---

## 二、P1：1688 官方开放平台 API 调研结果

详见 `docs/architecture/1688_DATA_PROVIDER_EVALUATION.md` §1-§8。要点：

- **申请资格**：主体资质具备（tb638676，AppKey 2819733，采购服务商，广西诺涛公司）。寻源通/跨境方案**尚未开通**，需跨境小二(sicongwz)加白。
- **接口能力**：详情接口可拿标题/价格/SKU/图片/属性；**无独立库存 API**；图片搜款/自动下单/订单查询当前未实现（寻源通开通后需补开发）。
- **调用限制**：本地材料无权威 QPS 数值（仅"5000 次/日免费"对比表述）；申请规划日 200-300 次。**gap：需向小二确认权威限流与库存/价格推送机制。**
- **收费标准 — 关键硬门槛**：寻源通免费无调用费，但受 **GMV 双门槛**：月 GMV≥160,000 元 + 单次调用 GMV≥0.5 元。高频低客单批量采集天然不达标，须靠缓存压缩调用量。**这是商业而非技术阻塞。**
- **商业用途/授权**：官方授权、可审计，符合生产红线。
- **批量分析支持**：支持（开通后）。
- **当前代码状态**：`sourcing_1688_service.py` 完整实现 AOP 签名/调用框架/归一化，但 `ALI1688_APP_SECRET` 缺失致长期跑 Mock；公共详情接口 `alibaba.product.get` 被拒(`gw.APIACLDecline`)；**唯一已订购可用 = `simple.get`(200 万次额度)**。

---

## 三、P1：第三方服务 / 牛顿 AI Agent 调研结果

详见 `1688_DATA_PROVIDER_EVALUATION.md`。要点：

- **阿里牛顿 AI Agent**：有正式 OAuth 授权；积分制（每日 300 分，单次 20-100 分），**2026-10-19 起停发**；代码 `newton_agent_service.py` 就绪但凭证未配（Mock）。返回结构不固定、字段靠推断、单任务 53-114 秒 → **稳定性中等偏低，仅宜作 AI 找品建议层，关键动作人审**。
- **寻源通（xunyuantong）**：官方供应链 API，免费按 GMV 考核，是最合规生产级源，但需加白+GMV 达标。
- **妙手跨境**：第三方跨境 SaaS，**其 API 授权属其自有 SaaS，Nuotao 不可借用**，仅作功能对标。
- **Scrapling 爬虫**：**无授权、不可审计、灰色地带**，严禁进生产自动流转，仅人工调研且须先过合规评审。
- **审计/来源追溯**：只有官方 API（寻源通/传统）与牛顿(OAuth)具备；Scrapling/fallback 不具备。

**合规红线**：未经验证授权和商业使用权限前，不接入任何第三方服务（指令禁止事项）。

---

## 四、P1：统一数据源 Provider 架构方案

详见 `docs/architecture/1688_PROVIDER_ARCHITECTURE.md`。要点：

- **三个 Provider + Mock**：`Official1688APIProvider`(寻源通主/simple.get 降级)、`AuthorizedThirdPartyProvider`(牛顿/未来合规第三方)、`BrowserSessionProvider`(现有 Playwright，过渡)；Mock **仅测试环境注册**。
- **七条硬要求逐条满足**：数据信封 `Provenance`(provider/method/product_id/fetched_at/raw_evidence_ref/verified) 满足来源记录与采集审计；`ProviderResult.ok` 与 `data` 绑定（拿不到可信数据即 `ok=False, data=None`）实现严格隔离与 fail-closed；生产路由表物理移除 Mock/fallback 满足"fallback 不进自动流转"；配置化路由满足平滑切换；**Agent 业务接口签名不变**。
- **本阶段只设计不实施**（遵守指令），现有 `sourcing_1688_service.py` 生产行为不动。

---

## 五、风险清单

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | Cookie 长期人工维护不可持续（本轮根因） | 高 | 迁往官方 API（P1），Cookie 仅过渡 |
| R2 | fallback/estimated 假数据污染选品定价上架 | 高 | PR#13 闸门 + Provider fail-closed + 生产移除 Mock |
| R3 | GMV 双门槛不达标致寻源通开不通 | 高 | 过渡用 simple.get；缓存压缩调用量；合并采购提客单 |
| R4 | 牛顿积分停发致建议层中断 | 中 | 牛顿仅作建议层非硬依赖；关键动作人审 |
| R5 | 权威限流/库存推送机制不明 | 中 | Phase 1 向小二确认（已知 gap） |
| R6 | get_price_trend 模拟被误当真实成本 | 中 | 显式标记 estimated，隔离于成本模型 |
| R7 | 凭证泄露 | 高(后果) | 全程掩码、不经聊天、Secret 管理、禁读 cookie store |

---

## 六、Owner 待决事项

1. **P0 收尾**：更新 GitHub Secret `ALI1688_LOGIN_COOKIE`（本人登录 1688 → 复制 Cookie → 粘入 Secret），然后回 DSH 一句"粘好了"由 DSH 触发轮换并按严格 VALID 验收。**这是 P0 唯一剩余动作。**
2. **P1 凭证**：批准获取并注入 `ALI1688_APP_SECRET` + OAuth `ALI1688_ACCESS_TOKEN`（解除 Mock、启用 simple.get 过渡）。
3. **P1 申请**：是否联系跨境小二申请寻源通白名单（P0 不依赖此，可并行）。
4. **GMV 达标策略**：是否启动"合并采购/提客单/杜绝跳单"以达月 16 万门槛。
5. **Provider 架构实施**：是否批准将 `1688_PROVIDER_ARCHITECTURE.md` 从设计转入代码实施（当前按指令仅设计）。

---

## 七、下一阶段建议

1. **立即**：Owner 完成 P0 Secret 更新 → DSH 收尾轮换闭环（唯一阻塞 P0 的动作）。
2. **并行（不阻塞 P0）**：注入 AppSecret+AccessToken 解除 Mock，用 simple.get 验证真实数据链路。
3. **短期**：DSH 将 Provider 架构设计交付评审；Owner 批准后转入实施（生产移除 Mock、Provenance 落库、fail-closed 路由）。
4. **中期**：申请寻源通白名单 + GMV 达标，切换生产主源；补齐寻源通下单/订单/物流接口。
5. **长期目标**（引用指令）：**从人工维护浏览器登录态，逐步升级为可持续、可审计、可切换的合规商品数据供应体系。**

---

## 附：本会话代码产出（全部进 main，CI 通过）

| PR/提交 | 内容 |
|---|---|
| #9 | 诊断脚本 PYTHONPATH 修复 |
| #10 | 诊断脚本 await async 修复（原 to_thread 包 async 从没真正抓取） |
| #11 | 诊断改用非硬编码商品真测 Cookie |
| #12 | `rotate-1688-cookie.yml` 轮换机制 |
| #13 | fallback 自动上架闸门 + 单测（Backend CI 通过） |
| `bbc72f5` | OWNER_PENDING_ACTIONS 文档更新 |
| `ef97521` | verify workflow 判定文案修正 |
| 本报告 + 2 份 architecture 文档 | P1 交付 |
