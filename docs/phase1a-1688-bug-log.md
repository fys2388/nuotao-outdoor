# 1688 自动找货 · Bug & 问题记录

> 记录 C1 单 SKU 端到端验证过程中遇到的所有问题。
> 开始时间：2026-11-19
> 目标：找到 C1 30L 防水收纳袋 → AI OS 一键导入 → 走完 8 步 SOP

---

## 🔴 Bug-01：1688 首页"官方采购助手"聊天框拦截搜索

**现象**：
- 在 1688 首页输入关键词 "30L 防水收纳袋 户外" 后点搜索按钮
- 弹出 "1688 官方采购助手" 聊天弹窗，遮挡搜索输入框
- 关键词被"吞"，无法真正触发搜索

**影响**：搜索流程被阻断

**尝试的解决**：
- ❌ 用 URL 直接跳到 `s.1688.com/selloffer/offer_search.htm?keywords=...`
- ❌ URL 参数被覆盖，返回 1688 首页

**推测原因**：
- 1688 强制引导用户走 AI 采购助手流程
- URL 参数解析被前端 JS 拦截

---

## 🔴 Bug-02：中文搜索词 URL 编码失效

**现象**：
- 用 `%E9%98%B2%E6%B0%B4%E6%94%B6%E7%BA%BD%E8%A2%8B`（= "防水收纳袋"）访问搜索页
- 页面显示 `闃叉按鏀剁航琚` **乱码**
- 返回的商品全部是"渔具"类（假饵、鱼笼等）——**完全不相关**

**验证**：
```
URL: https://s.1688.com/selloffer/offer_search.htm?keywords=%E9%98%B2%E6%B0%B4%E6%94%B6%E7%BA%BD%E8%A2%8B
预期: "防水收纳袋"
实际: 页面标题显示 "闃叉按鏀剁航琚_闃叉按鏀剁航琚批发..." (乱码)
结果: 返回钓鱼用品 20 个，0 个收纳袋
```

**推测原因**：
- 1688 搜索 URL 需要特殊编码（可能不是标准 URL encoding）
- 或者是 spm 埋点参数丢失导致搜索被 fallback 到"为你推荐"
- 或者是站点识别为"未登录/JS 未跑"状态，跳回默认搜索

**尝试过的 URL 参数组合**：
- `keywords=xxx` ❌
- `keywords=xxx&n=y` ❌
- `keywords=xxx&button_click=top&spm=a26unwd.28223460--18824374949904.top_search` ❌
- `%E6%88%B7%E5%A4%96%E9%98%B2%E6%B0%B4%E6%94%B6%E7%BA%BD%E8%A2%8B30L`（加"户外"前缀）❌

---

## 🔴 Bug-03："1688 找货源" iframe 悬浮插件遮挡

**现象**：
- 页面右下角始终显示 "1688 找货源" 悬浮按钮 + iframe
- 展开后包含 `find-goods-iframe`、`task-detail-iframe`
- 部分 ref 号被 iframe 内容占据，导致 ref 号偏移

**影响**：
- 遮挡内容观察
- 无法关闭（"❯"按钮点击返回 "element not visible"）
- 尝试用 browser_inspect 观察时提示 "geometry incomplete"

**已尝试**：
- 点击 `@e133`/`@e147` 折叠按钮 → 返回 "element not visible"（因 tab 不在 Agent Window 内）

**推测原因**：
- 这是 1688 内置的采购助手扩展，通过 iframe 嵌入
- 只在 Agent Window 打开时能操作，普通 tab 不行

---

## 🟡 Bug-04：session 生命周期脆弱

**现象**：
- 上一次会话 session `yskn`（浏览器扩展创建）在几小时后失效
- 报错：`session "yskn" does not belong to this plugin — only sessions created by browser_session action=start are visible and operable here`
- 尝试 `browser_session start` 时报："no browser is currently connected (hint: open the browser-skill extension in your browser and wait for the popup to show 'connected')"

**影响**：
- 会话断了重连不上
- 用户手动干预才恢复（重新扫码登录）

**推测原因**：
- Browser skill extension 未保持连接
- 或用户端浏览器/扩展被重启

---

## 🟡 Bug-05：搜索页"最近搜索"按钮点击不跳转

**现象**：
- 搜索页显示最近搜索词 "30L 防水收纳袋 户外"
- 点击 `@e17` 或 `@e18`（这两个都是 "30L 防水收纳袋 户外" 按钮）
- 未观察到 URL 变化或搜索结果更新

**推测原因**：
- 按钮点击事件被前端拦截但没触发实际搜索
- 或是 ref 号指向的不是真正的搜索按钮

---

## 🟡 Bug-06：搜索结果排序/相关性差

**现象**：
- 即使 URL 参数正确传递关键词，返回结果也大量不相关
- 搜 "防水收纳袋" 返回大量"渔具"、"假饵"、"鱼笼"
- 搜 "户外防水收纳袋 30L" 返回捏捏乐、发夹等无关商品

**推测原因**：
- 1688 搜索算法默认按"综合"排序，热度高的先出
- 未登录状态下搜索召回策略宽松
- 需要用筛选器（一件代发/销量等）+ 关键词精细化才能命中

---

## 🟡 Bug-07：AI OS 一键导入功能未验证

**来源**：`docs/M0_M4_ACCEPTANCE_MATRIX.md:52`
> M2-1 1688产品来源：代码存在但 **1688 API 需要认证；爬取合规性未验证**

**已知代码事实**：
- 端点：`POST /product-pipeline/import-from-1688` (`backend/app/api/v1/endpoints/product_pipeline.py:158`)
- 依赖 3 个环境变量：`ALI1688_APP_KEY` / `ALI1688_APP_SECRET` / `ALI1688_ACCESS_TOKEN`
- 未配置时，`product_pipeline_orchestrator.py:196` 会返回 "1688 服务待接入"

**风险**：
- 即使找到 1688 商品 URL，导入可能直接失败
- 需要先验证一键导入功能是否真的可用

---

## 🟡 Bug-08：push-woocommerce 假成功 (已知的 AI OS Bug)

**来源**：`docs/keyword_listing_e2e_test_log.md`

**现象**：
- WC API 返回 HTTP 200
- 但产品实际未创建、`woocommerce_id` 未回写
- 表现为"假成功"

**影响**：
- 即使导入 AI OS 成功，推送到 WC 也可能假成功
- 需要前台验证实际是否可见

---

## 🟡 Bug-09：AI 文案 bullet points 字段名不匹配

**来源**：`docs/keyword_listing_e2e_test_log.md`

**现象**：
- AI 生成文案里没有 `bullet_points` 字段
- 前后端字段名不匹配（`bullets` vs `bullet_points`）
- 导致文案缺卖点

---

## 🟡 Bug-10：backend 强制校验声明与实现不一致

**来源**：`docs/keyword_listing_e2e_test_log.md`

**现象**：
- 声明有"合规闸门"，实际实现形同虚设
- 任何 draft 都能推到 WC

---

## 📌 结论

### 无法通过浏览器自动化稳定完成的原因

1. 1688 反爬机制（悬浮 iframe + URL 参数拦截）
2. 中文搜索词 URL 编码不生效
3. AI 采购助手强制引导
4. 搜索相关性差，即使命中也需要大量人工筛选
5. 每次会话需要扫码登录（AI 无法代扫码）

### 建议的替代路径

**方案 A：用 web_search 工具找 1688 商品页**
- 通过 Google/Bing 索引的 1688 详情页 URL
- 直接拿到商品 ID，绕过搜索页
- 优点：绕过反爬；缺点：结果可能老旧

**方案 B：让 AI OS 一键导入端点直接测试**
- 找一个已知 1688 商品 ID，测试导入是否成功
- 如果导入端点可用，找货流程可以后续再补
- 优先验证技术链路

**方案 C：手动找货 + 我处理导入**
- 用户在 1688 手动搜（他能用中文搜索框交互）
- 把商品 URL 发给我
- 我在 AI OS 里做导入 + 后续流程

---

## 🔴 Bug-11：web_search 无 API key

**尝试**：`web_search` 工具查询 1688 详情页 URL
**错误**：`DeepSeek search has no API key for "DEEPSEEK_API_KEY"`

**影响**：外部搜索通道不可用

---

## 🎯 下一步（我这边继续做）

1. **先用 web_search 找 3 个 Hero SKU 的 1688 详情页 URL**（绕过搜索页反爬）
2. **测试 AI OS 一键导入端点**（确认技术链路）
3. **如果导入可用**，走完整 8 步 SOP
4. **如果导入失败**，报告用户申请 1688 API 密钥

---
---

# 🔁 2026-09-24 补充：AI OS 前端部署事故 + Newton 加入候选按钮 Bug

**范围**：本节记录本次会话在 Nuotao AI OS 管理后台（`admin.nuotaooutdoor.com`）上从「服务器 git HEAD 恢复」到「Newton 找品 → 加入候选端到端验证」过程中新发现的 Bug 与部署事故。前 11 个 Bug 是 1688 浏览器自动化阶段的问题，本节的 Bug 是 AI OS 自身工程化问题。

---

## 🟢 Bug-12：「加入候选」按钮 UI 状态不切换（前端交互 bug）

**现象**：
- 页面：`https://admin.nuotaooutdoor.com/products/newton-sourcing`
- 操作：找品返回 2 款商品 → 点击第一个商品的「star 加入候选」按钮
- 网络：`POST /api/v1/newton/sourcing/import` **200 成功**
- 后端：候选池行数 5 → 7（`930055532889` 和 `800075224932` 已入库，SKU 分别为 `NEWTON_930055532889_0`、`NEWTON_800075224932_1`）
- UI：**按钮文字仍是「加入候选」，未切换为「已在候选库」**；批量按钮「加入候选库（0）」也没变为「(1)」

**根因**（读 `NewtonSourcing-B9ge3PRJ.js` 反混淆源码确认）：
- 前端逻辑：`importNewtonSourcing` 返回 `{imported, skipped}`，只有 `imported > 0` 才更新 `candidateDone` Set 触发按钮切换
- 后端返回：由于 `930055532889` / `800075224932` 在**本次请求内已存在**（可能来自上一次测试或首次批量入库的 `_0` 后缀记录），后端把它们视为 `skipped`，`imported=0`
- 结果：`u.warning("没有可导入的商品（可能已存在）")` 分支被触发（这条 warning 消息在浏览器里一闪而过，用户看不到）
- 用户视角：按钮点了没反应，实际是"已成功但 UI 没告诉你是成功"

**严重度**：🟢 低（功能正确，只是交互反馈缺失）

**修复建议**：
```typescript
// NewtonSourcing.tsx handleAddCandidate
const res = await api.importNewtonSourcing([item], ...)
const data = res?.data || {}
const imported = Number(data.imported || 0)
const skipped = Number(data.skipped || 0)
// 只要 imported 或 skipped > 0 都算"该商品已入库"
if (imported + skipped > 0) {
  setCandidateDone(prev => new Set([...prev, productKey(item)]))
  if (skipped > 0) message.info('该商品已在候选库')
  else message.success('已加入候选库')
} else {
  message.warning('未导入，可能 SKU 已存在')
}
```

**当前状态**：功能验证通过，SKU 已入库（`NEWTON_930055532889_0`、`NEWTON_800075224932_1`），仅是 UI 反馈缺失。不阻塞后续流程。

---

## 🔴 Bug-13：本地 dist 被 scp 到服务器覆盖，源码与 dist 分裂

**现象**：
- 服务器 `/opt/nuotao/frontend/dist/index.html` 里引用 `NewtonSourcing-Creb1a1t.js`
- 服务器源码仓库 git HEAD = `8903f9f`（main 分支），`src/pages/NewtonSourcing.tsx` 调 `POST /newton/sourcing/import`
- 但生产 dist 里 `NewtonSourcing-Creb1a1t.js` 调 `POST /sourcing/candidates`（另一条 API 路径）
- 两条路径在生产环境并存，源码和产物分裂

**根因**：
- 我从本地 `hotfix/listing-gate` 分支 build 了 dist，然后 `scp` 上传覆盖了 `/opt/nuotao/frontend/dist`
- 服务器 `/opt/nuotao/frontend` 本身是 git 仓库，工作树源码是 main HEAD `8903f9f`，但我上传的 dist 与它不匹配

**严重度**：🔴 高（破坏可复现性：git bisect 无法工作，源码改动不会反映到生产，除非重新 build）

**恢复动作**：
1. `cp -a dist dist.before-main-build` 备份错误产物
2. `cd /opt/nuotao/frontend && npm run build` 用 main HEAD 源码重 build
3. 结果 dist hash 更新：`index-Cs7hFBGw.js` + `NewtonSourcing-B9ge3PRJ.js`
4. `chmod 755 dist && chmod -R a+rX dist` 修 nginx 权限
5. 公网 curl 验证两个 bundle 都 200

**根因纪律**：见 `docs/deploy-discipline.md` 铁律 1。

---

## 🟡 Bug-14：dist 目录 700 权限导致 nginx 403

**现象**：`curl -sI -H 'Host: admin.nuotaooutdoor.com' http://127.0.0.1/assets/NewtonSourcing-B9ge3PRJ.js` 返回 403，浏览器侧同样 403

**根因**：`npm run build` 生成 `dist/` 时目录权限默认 700（`drwx------`），nginx worker 是 `www-data` 用户，进不去

**修复**：`chmod 755 dist && chmod -R a+rX dist`

**根因纪律**：见 `docs/deploy-discipline.md` 铁律 3。

---

## 🟡 Bug-15：PowerShell scp 命令被 `$()` 语法解释吞掉

**现象**：`scp -r dist/* root@...:"/opt/nuotao/frontend/dist.bak.$(date +%s)/"` 上传后服务器出现一个名为 `dist.bak./` 的目录（`$()` 被 PS 解释为空字符串）

**根因**：PowerShell 单引号内 `$()` 不是插值符号，双引号内才是；混合使用时 PS 会解析 `$(...)` 为 sub-expression，被吞掉

**修复**：改用 `-C` 传字符串或用单引号包裹整段，禁用 shell 变量替换

**根因纪律**：跨平台 shell 命令时避免依赖 bash 语法。

---

## 🟡 Bug-16：`scp` 传输目录导致服务器出现 `dist/dist/` 嵌套

**现象**：`scp -r dist root@...:/opt/nuotao/frontend/dist/` 把本地 dist 目录整个塞到远端 dist 目录里，形成 `dist/dist/` 嵌套

**根因**：`scp -r src dest/` 若 dest 已存在为目录，src 会被复制到 dest 内部而非合并

**修复**：`scp -r dist/* root@...:/opt/nuotao/frontend/dist/`（带 `/*`）或直接覆盖远端目录

**根因纪律**：`scp -r` 语义与 `rsync` 不同，跨目录合并时要用 `/*` 或先 `rm -rf dest`。

---

## 🟢 Bug-17：nginx 未带 Host header 时 404 到 default server

**现象**：`curl -sI http://127.0.0.1/assets/NewtonSourcing-B9ge3PRJ.js` 返回 404（但公网 200）

**根因**：nginx 多 server 配置下，不带 `Host` header 的请求路由到 default server（`listen 8081` 的 `root /var/www/nuotao`），而不是 nuotao 主 server

**修复**：本地验证 nginx 必须带 `-H 'Host: admin.nuotaooutdoor.com'`

**根因纪律**：见 `docs/deploy-discipline.md` 铁律 5。

---

## 🟢 Bug-18：浏览器 disk cache 顽固，`immutable` + 31536000 秒

**现象**：服务器/CDN 已部署新版 bundle，但旧 session 浏览器继续加载旧 hash（`Creb1a1t.js`），Ctrl+Shift+R 也无效

**根因**：`/assets/*.js` 响应头是 `Cache-Control: public, max-age=31536000, immutable`，浏览器 disk cache 优先级最高，HTTP refresh 绕过不了

**修复方式**（按强度递增）：
1. DevTools → Application → Clear site data
2. DevTools → Network → 勾 Disable cache
3. 无痕/隐私窗口访问
4. 换域名（比如走 Cloudflare 缓存另一个 IP）
5. 等自然过期（≈ 1 年，实际不可行）

**根因纪律**：验证部署是否生效必须开新窗口/无痕，不要用现有 session。

---

## 🟡 Bug-19：`browser_inspect html` 返回的 JS bundle 是 HTML 转义乱码

**现象**：`browser_inspect action=html` 抓 `NewtonSourcing-B9ge3PRJ.js` 时，中文注释变成 `鐗涢锛 AI 瀵硅瘽閫夊搧`（UTF-8 被当作 GBK 解码再转义）

**根因**：浏览器把 JS 当 HTML 呈现时使用了错误的 charset 猜测

**规避**：不用 `browser_inspect html` 抓 JS，改用 `read` 工具直接读源码文件或 curl -v 抓响应

---

## 🟢 Bug-20：1688 「找货源」悬浮 iframe 干扰 Admin 页面

**现象**：打开 `admin.nuotaooutdoor.com/products/newton-sourcing` 后，页面右下角被 1688 官方 Chrome 扩展注入的 `find-goods-iframe`、`task-detail-iframe`、`market-mate-for-1688` 遮挡

**影响**：不影响 API 和网络请求，只影响视觉和坐标（`@e` ref 号偏移）

**修复**：扩展市场禁用 `market-mate-for-1688`（扩展 ID `kphldkppgfpjadpabfkghmjbhpcmgpdg`），或用无痕模式（默认不带扩展）

---

## 📊 汇总（2026-09-24 本次会话）

| Bug | 分类 | 严重度 | 状态 |
|---|---|---|---|
| 12 | 前端交互 | 🟢 低 | 功能正常，UI 反馈缺失 |
| 13 | 部署纪律 | 🔴 高 | 已恢复，纪律入 `deploy-discipline.md` |
| 14 | 部署纪律 | 🟡 中 | 已修复 |
| 15 | Shell 语法 | 🟡 中 | 已绕过 |
| 16 | Shell 语法 | 🟡 中 | 已绕过 |
| 17 | nginx 配置 | 🟢 低 | 已确认 |
| 18 | 浏览器缓存 | 🟢 低 | 已绕过（新 session） |
| 19 | 工具使用 | 🟡 中 | 已绕过 |
| 20 | 扩展干扰 | 🟢 低 | 不影响功能 |
| 21 | Newton 导入缺重量+落地成本不自动估算 | 🔴 高 | 待修 |

---

## 🔴 Bug-21：Newton 导入候选缺重量字段，V3 评分全部卡 51.5

**现象**：
- `POST /api/v1/newton/sourcing/import` 入库的 5 条候选，`weight_kg` 全部为 `null`
- 详情弹窗「重量：待补充」「尺寸：待补充」「商品属性：尚未持久化」
- 「最新成本：尚未记录成本快照，重新录入商品后会生成」
- V3 批量评估结果：5 条全 Reject 51.5-52.3，无一通过 60 分门槛

**根因**（三层）：

1. **Newton `importNewtonSourcing` 导入字段不完整**：只抓了 SKU、名称、来源 URL、采购价、供应商，跳过了 1688 详情页的重量、尺寸、属性字段
2. **候选详情页 `CandidatePool.tsx:666` 是只读渲染**：`<Descriptions.Item label="重量（kg）">{p.weight_kg ?? '-'}</Descriptions.Item>` 没有 input，无法 UI 编辑
3. **V3 评分缺数据默认分**：`product_intelligence.py` 缺重量时按 50% 占位分给 6 维（Value 25/50% + Utility 20/50% + Weight 15/50% + Durability 15/50% + Brand 15/50% + Diff 10/50% = 51.5），卡在 60 门槛下

**严重度**：🔴 高（阻塞所有 Newton 候选进入后续流程）

**修复建议**：
- 短期：手工通过 API PATCH `weight_kg` 和 `meta.suggested_price`
- 中期：`CandidatePool.tsx` 详情弹窗加编辑表单
- 长期：`importNewtonSourcing` 补抓 1688 详情页的重量/尺寸字段

---

## 📌 业务规则（用户 m01558 强调）

**头程运费按 max(毛重, 材积重) 计费，不是净重**：

- **净重（Net Weight）**：产品本身重量
- **毛重（Gross Weight）**：产品 + 内包装 + 外箱
- **材积重（Volumetric/Dimensional Weight）**：`长 × 宽 × 高(cm) / 分母`
  - 空运（Express）：分母 5000
  - 海运（Sea Freight）：分母 6000
  - 邮政小包：分母 4000（有时）
- **计费重量（Chargeable Weight）**：`max(毛重, 材积重)`

**示例**：一款 30L 户外防水袋
- 净重 0.4 kg
- 毛重（含内袋+外箱） 0.55 kg
- 尺寸 35×25×15 cm → 材积重 = 13125 / 5000 = **2.625 kg**
- 头程按 **2.625 kg** 计费（不是 0.55 kg）

这意味着：
1. 轻件 + 体积大的商品（收纳袋、折叠碗包）头程运费会显著高于按毛重估的
2. 落地成本估算必须用 `chargeable_weight`，不是 `weight_kg`
3. `cost_prefill_service.py` 里的 `first_leg_shipping` 计算要用材积重，不是净重

**这条规则要更新到 `cost_prefill_service.py` 里**，否则所有体积大、重量轻的户外收纳类 SKU 的落地成本都会被严重低估。

## 🎯 本次会话端到端结果

- ✅ 服务器 main HEAD `8903f9f` 源码 = `dist/` build 产物（源码与 dist 一致）
- ✅ 公网 bundle hash：`index-Cs7hFBGw.js`、`NewtonSourcing-B9ge3PRJ.js`
- ✅ Newton 找品 API：`POST /newton/search` 200，2 款商品
- ✅ 加入候选 API：`POST /newton/sourcing/import` 200，SKU `NEWTON_930055532889_0`、`NEWTON_800075224932_1` 入库
- ✅ 候选池总数 5 → 7
- ✅ 积分消耗 9986.5 → 9983.8（-2.7）
- ⚠️ 唯一遗留：Bug-12 UI 按钮反馈（不阻塞后续流程）
