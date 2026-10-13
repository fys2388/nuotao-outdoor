# 选品 → 上架 WooCommerce SOP 端到端执行报告

- **执行日期**：2026-10-12
- **执行方式**：浏览器端到端操作（Chrome，`https://admin.nuotaooutdoor.com/products/pipeline`），商品工作台（产品工作台）
- **约束**：禁止用 API 替代 SOP 步骤；所有业务流程动作均通过系统 UI 点击完成（下文的 API 读取仅用于故障定位与结果核对）
- **结论**：**流程闭环达成**。1688 商品已作为变量商品上架到 WooCommerce（商品 ID `2499`，草稿状态），18 个规格各自带独立 SKU / 美元价 / 库存，前台渲染与价格联动均正确。

---

## 一、SOP 步骤记录（实际执行路径）

| # | 阶段 | 操作 | 结果 |
|---|---|---|---|
| 0 | 进入 | 左侧导航「商品与 AI 选品 → 商品工作台」(`/products/pipeline`) | 页面标题确认「当前模块：商品工作台」 |
| 1 | 选品 | 「1688 一键导入」输入 `https://detail.1688.com/offer/996759597513.html`，开关保持「自动运行」，点「导入」 | 抓取 + 自动流转，约 90–250s |
| 2 | AI 分析 | 管线自动执行 | `completed` — 10 字段识别 + 17 字段报告 |
| 3 | 主图生产 | 管线自动执行 | `completed` — 3 套方向 + 文案 + 变体 |
| 4 | 生图 Prompt | 管线自动执行 | `completed` — 主图 + 详情页 Prompt |
| 5 | 上架数据 | 管线自动执行 | `completed` — 名称/描述/价格/SKU/分类/标签（英文） |
| 6 | V3.0 闸门 | 管线自动执行 | `gate_verdict = passed` |
| 7 | 上架确认 | 工作流进度 →「上架数据」页签 →「确认上架」→ 弹窗选「保存为草稿」 | 进度 `7/8`、`87.5%`、状态「成功」；上架 WC 步骤 = `pending_confirmation` → 确认后提交 |
| 8 | WC 上架 | 后端推送 | **WC 商品 #2499 创建成功**，渠道与上架页显示「推送 #2499」 |

### 关键中间数据（本轮）

- 商品名：`Outdoor Folding Egg Roll Table & Chair Set – Portable Camping Picnic Setup`
- 父 SKU：`NT-OUTDOO-EGG-6142820055649`
- 类型：`variable`，规格数 **18**，属性轴 **Style**
- 价格：`¥12 → $10.00`，`¥20 → $16.67`，`¥140 → $116.67`（公式 `CNY ÷ 7.2 × 6`）
- 分类：`119` Camping Chairs；标签 7–8 个英文关键词
- 状态：草稿（符合 SOP「人工确认后上架，默认草稿」）

---

## 二、WooCommerce 端验收证据（浏览器，店铺前台预览）

商品页：`https://nuotaooutdoor.com/?post_type=product&p=2499&preview=true`

| 验收项 | 结果 |
|---|---|
| 商品标题 | `Outdoor Folding Egg Roll Table & Chair Set – Portable Camping Picnic Setup`（英文、`&` 正常，无实体残留） |
| 面包屑 / 分类 | Home / Camping Furniture / **Camping Chairs** | 
| 商品类型 | 变量商品（显示价格区间 `$10.00 – $116.67`） |
| 规格轴 | **Style**（英文，非中文「颜色」） |
| 规格数量 | **18**，全部 `attached enabled` |
| 规格名（抽样） | Black Folding Chair / Small Square Table (Black) / 95cm Long Table (Beige) / 1.2m Long Table 5-Piece Set (Black) / 1.2m Long Table 7-Piece Set (Beige) |
| 逐规格定价 | 选中 `1.2m Long Table 7-Piece Set (Beige)` → 价格切换 **$116.67**、库存 8885、变体 SKU `6142820055666`、Add to cart 可用 |
| 图片 | 4 张（主图 + 详情图已上传 Media Library） |
| 短描述 / 长描述 | 英文 |
| 标签 | camping chair set / camping table / egg roll table / folding table / outdoor picnic / Oxford fabric / portable furniture |
| 状态 | Draft（Visibility: Public，未对公众发布） |

结论：**逐规格 SKU、价格、库存、规格名、分类、图片全部正确落库并可售** —— 满足「WC 商品上架质量达标」判定。

---

## 三、执行中发现并修复的缺陷

| 编号 | 缺陷 | 影响 | 修复 |
|---|---|---|---|
| BUG-14 | Pydantic 丢弃未声明字段 | 数据静默丢失 | 补 schema 字段 |
| BUG-15 | 回填逻辑耦合自我识别 | 多规格退化单 SKU | 分离自我识别与回填 |
| BUG-16 | 变体价直传人民币当美元 | 价格错约 5 倍 | 变体价走同一换算 |
| BUG-17 | 变体失败只告警不暴露 | 18 变体只剩 1 个仍报成功 | 收集失败明细并显式返回；变体全军覆没即失败 |
| BUG-18 | `pipelineResult` 未写入 | 进度区空白 | 补状态写入 |
| BUG-19 | 定价预览恒为 `$—` | 无法核对价格 | 修正预览取值 |
| BUG-20 | 管线同步 `/run` 触发网关 524 | HTML 报错不可读 | 改异步 + 轮询；网关错误转可读信息 |
| BUG-21 | 一键运行用表单重建 productInfo | 丢失 variations/attributes/source_url/sku | 以导入结果为基底合并表单覆盖 |
| BUG-22 | `pipeline_error` 被静默吞掉 | 长任务失败无迹可寻 | 持久化错误提示 |
| BUG-23 | 回填提前 return 致自我识别缺失 | 导入成功却报「同一链接禁止重复上架」 | 自我识别必须先于回填判断 |
| BUG-24 | 牛顿 Agent KILL 率 > 50% | 导入间歇失败 | 上游已知问题，重试导入规避 |
| BUG-25 | 失败 toast 3s 消失 | 5 分钟任务失败后页面无痕 | 持久 Alert |
| BUG-26 | 轮询一次网络抖动即整体失败 | 后端已成功结果被丢弃、页面「什么都没发生」 | 单次失败计数重试，连续 5 次才判失败 |
| BUG-27 | 变体价格塌缩（18 个变体同一价） | 折叠椅与七件套卖同一价，定价事故 | 识别退化数据，用落库快照逐条修正价格并补齐 SKU（按名对齐，长度不一致不修） |
| BUG-28 | 上架数据预览不显示规格 | 人工确认看不到要发布的规格，只能盲签 | 补「规格明细」表：规格名/SKU/美元价/源价/库存 |
| BUG-30 | 本地化每次即兴发明品牌名 | 同一商品三次得到 Lightwild/TuoTu/Wild Fun；标题无品牌而描述有「Wild Fun」，前台像两个商品 | 新增配置 `house_brand`（env `BRAND_NAME`/`HOUSE_BRAND`，**默认 `nuotao`**，留空表示不带品牌）。AI 分析/报告/本地化三处提示词统一改为固定使用该品牌，禁止推测或编造；候选行写入 `Product.brand`；上架时独立调用 WC brands 端点查找/创建品牌分类法条目并绑定 |
| BUG-31 | 已推送商品在渠道页显示「零售价 缺失」 | 运营误判未定价、可能重复推送 | `regular_price` / `price` / `localizations.en.price` 三键同写 |
| BUG-32 | WC brands 字段格式错误导致变体创建被跳过 | 产品 #2526 有 18 个属性选项但 `variations: []`，不可售。WC REST API 的 `brands` 字段期望整数 ID 数组，代码传了 `[{name:...}]`，WC 部分处理请求后创建父商品但跳过变体创建 | 移除父商品 POST 中的 brands 字段；改为父商品+变体全部就绪后，独立调用 `/products/brands` 端点查找/创建品牌，再用 PATCH 绑定到商品。品牌绑定全程 try/except，失败不影响上架成功 |

### 已排查但不成立的疑点

- **WC 标题 HTML 实体双重编码**：observe 显示标题输入框含 `&amp;`，但 URL Slug 为 `outdoor-folding-egg-roll-table-chair-set-portable-camping-picnic-setup`（`sanitize_title` 会去掉 `&`；若标题含 `&amp;` 必然留下 `amp`），且 Rank Math SEO 预览与店铺前台 H1 均显示普通 `&`。判定为观察工具自身输出转义，**非缺陷**，未做无谓改动。

---

## 四、遗留问题（不影响本次闭环，建议排期）

1. **确认弹窗不含规格明细**：`确认上架` 弹窗只列父商品字段，虽然后方「上架数据预览」已有规格表，弹窗内仍建议同步展示。
2. **两条上架路径未统一**：商品工作台直推不生成「上架工单」（SOP ③ 人工终审队列），上架工单页恒为空；建议统一或明确二者边界。
3. **牛顿 1688 抓取质量波动**：同一 offer 两次抓取可能一次给全各 SKU 真实价、一次只给基准价（BUG-27 已做兜底，但根因在上游）。
4. **品牌资产**：品牌已固定为自有品牌 `nuotao`（配置 `BRAND_NAME`，留空则不带品牌）。后续如需改为其他品牌名，只需改环境变量，无需改代码。
5. **分类映射靠关键词**：`map_category_to_wc` 以商品名关键词匹配 WC term，命中「椅」优先于「桌」，桌椅套装归入 Camping Chairs；建议引入类目配置或人工可改。
6. **WC brands 分类法绑定**：BUG-32 修复后品牌通过独立 API 调用绑定，但 WC brands 端点可用性取决于 WC 版本（9.4+）。若版本过低，品牌绑定会静默跳过（不影响上架成功）。

---

## 六、第二轮执行：品牌验证（2026-10-13）

### 触发

用户确认品牌固定为 `nuotao`，部署 `63db0af` 后重新执行 SOP。

### 执行结果

| 步骤 | 结果 |
|---|---|
| 登录 | `admin` / `***REMOVED***` |
| 1688 导入 | 成功，表单自动填充（¥12 → $10.00） |
| 管线运行 | 7/8 步完成，87.5%，95.99 秒 |
| 商品名称 | **`nuotao Portable Folding Camping Table and Chair Set`** ✓ |
| SKU | **`NT-NUOTAO-CAMPIN-6142820055649`**（含品牌前缀） ✓ |
| 短描述 | `nuotao folding table and chair set for camping...` ✓ |
| 长描述 | `The nuotao Portable Folding Camping Table and Chair Set is...` ✓ |
| 确认上架 | 推送成功 |
| WC 商品 | **#2526**，Draft 状态 |

### 发现的问题

WC API 返回 `variations: []`，产品 #2526 有 18 个属性选项但无变体，不可售。

**根因**：WC REST API 的 `brands` 字段期望整数 ID 数组，代码传了 `[{name: "nuotao"}]`。WC 部分处理请求后创建父商品但跳过变体创建。

**修复**（`a173067`）：移除 brands 字段，改为父商品+变体就绪后独立调用 brands 端点绑定。

### 品牌一致性验证

| 位置 | 品牌 | 状态 |
|---|---|---|
| 商品名称 | `nuotao` | ✓ |
| SKU 前缀 | `NUOTAO` | ✓ |
| 短描述 | `nuotao` | ✓ |
| 长描述 | `nuotao` | ✓ |
| URL slug | `nuotao-portable-folding-camping-table-and-chair-set` | ✓ |
| WC brands 分类法 | 待第二轮修复后验证 | ⏳ |

结论：品牌 `nuotao` 已贯穿所有文本字段，彻底消除 BUG-30（品牌漂移）。

---

## 五、本次交付的上线记录

| commit | 内容 |
|---|---|
| `41bd2d9` | BUG-20 + BUG-21 |
| `045faf5` | BUG-22 + BUG-23 |
| `b2741b0` | BUG-25 |
| `58230ae` | BUG-26 + G1（变体名本地化）+ G3（可变属性轴英文化） |
| `af83a53` | G3b（父属性 options 同步）+ BUG-27（变体价格塌缩） |
| `2edea12` | BUG-28（上架数据预览规格明细） |
| `9e39ab0` | BUG-30（品牌规则初版）+ BUG-31（零售价回填） |
| `63db0af` | 品牌固定为自有品牌 `nuotao`（可配置/可留空）+ WC `product_brand` 推送 |
| `a173067` | BUG-32（WC brands 字段格式错误导致变体创建被跳过） |
