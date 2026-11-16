# Phase 1A — SDLC 上架全流程缺口审计

> **生成时间**：2026-09-27
> **对应 Goal**：`goal-8d80e16d-0777-4cba-b987-99d733a2157e`
> **目标 SOP**：1688选品抓取 → AI评分筛选 → 元数据编辑 → I2I生图任务 → 图片质检 → 上架数据包组装 → 提交上架 → WC API推送 → WC回读校验 → WC同步完成

---

## 0. 审计方法

对后端 `backend/app/**/*.py` 做 grep 扫描，对 10 步 SOP 逐步定位实现。任何命中「0 match」的关键词视为**未实现**。

## 1. 现状总表

| # | SOP 步骤 | 现状 | 关键证据 |
|---|---|---|---|
| ① 1688选品抓取 | ✅ | Newton importNewtonSourcing 已跑通 5 条候选 | `docs/compliance/INDEX.md` |
| ② AI评分筛选 | ✅ | `POST /products/intake` 触发 `analyze_product()` | `backend/app/services/product_intelligence.py:998` |
| ③ 元数据编辑 | ✅ | intake API 补齐价格/毛重/尺寸/评分 | 已跑 5 条，score_id 见 audit |
| ④ I2I生图任务 | 🟡 **部分** | 有 t2i 网关但**无 input_image 参数**，无法做 I2I | `backend/app/integrations/image_gen.py:155-164` |
| ⑤ 图片质检 | ❌ **0 命中** | 全库 grep `image_qc|图片质检` 无匹配 | grep 结果空 |
| ⑥ 上架数据包组装 | ❌ **0 命中** | 无 B2CListing 独立实体 | grep 结果空 |
| ⑦ 提交上架 | ❌ 无 endpoint | 无 listing approve 状态机 | grep 结果空 |
| ⑧ WC API推送 | ✅ | `POST /products/{id}/push-woocommerce` 存在 | `woocommerce_sync_service.py:965` |
| ⑨ WC回读校验 | ❌ | `get_sync_status()` 只是状态轮询，无 WC GET + diff | grep 结果 |
| ⑩ WC同步完成 | ⚠️ | 存在但依赖 ⑨ | 需改造 |

## 2. 详细缺口

### 2.1 ④ I2I 生图任务（🟡 部分）

**现状**：`backend/app/integrations/image_gen.py`
- 支持 Seedream 4/4.5/5（Volcengine, openai_images 风格）、qwen-image-2/3、wan2.7
- 默认模型 `doubao-seedream-4-0-250828`，¥0.20/img，200 张免费
- `generate_image()` 签名：`(prompt, model, width, height, negative_prompt, timeout, retries)` — **无 `input_image` 参数**
- 所有 backend adapter（`_generate_volcengine` / `_generate_alibaba_sync` / `_generate_alibaba_async`）都只发送 text prompt

**缺口**：
- 无 `input_image: str | None` 参数
- 无 image-to-image 语义（seedream 5.0 pro 明确支持 image input，但当前代码未传递）
- 无 I2I 特定的质量校验（1688 原图还原度、去水印）

**需要补**：
```python
# backend/app/integrations/image_gen.py
async def generate_image(
    *,
    prompt: str,
    model: str = "doubao-seedream-4-0-250828",
    width: int = 1024,
    height: int = 1024,
    negative_prompt: str | None = None,
    input_image: str | None = None,  # NEW: URL or base64
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> ImageGenResult:
```
- `_generate_volcengine`：把 `input_image` 转成 `images: [...]` 字段
- `_generate_alibaba_sync`：qwen-image-2.0-pro 也支持 image input

**工时**：0.5 天

### 2.2 ⑤ 图片质检（❌ 0 命中）

**缺口**：完全没有。

**需要补**：
- `backend/app/models/image_qc.py` — ORM：image_id, image_url, dimensions_check, watermark_check, quality_score, verdict, checked_at
- `backend/app/services/image_qc_service.py` — 
  - `check_dimensions(image_url, expected_w, expected_h)` 
  - `detect_watermark(image_url)` — 简单版：像素边缘扫描；高级版：调用 LLM 视觉
  - `run_full_qc(image_ids)` — 组合校验
- `backend/app/api/v1/endpoints/image_qc.py` — `POST /image-qc/check` + `POST /image-qc/batch`
- `migrations/xxxx_add_image_qc.py` — 建表

**工时**：1.5 天

### 2.3 ⑥ 上架数据包组装（❌ 0 命中）

**缺口**：没有 B2C Listing 独立实体，Product 直推 WC。

**需要补**：
- `backend/app/models/b2c_listing.py` — ORM：product_id, listing_type, json_payload, status, created_at, submitted_at
- `backend/app/services/listing_assembly_service.py` — `assemble_listing(product_id) -> dict`：
  - 从 Product Master 拿标题/描述/图片/SKU
  - 组装成 WC payload（含 media 数组）
  - 存 B2CListing(json_payload, status='draft')
- `backend/app/api/v1/endpoints/b2c_listing.py` — 
  - `POST /b2c-listings/{product_id}/assemble` 
  - `GET /b2c-listings/{id}`
  - `PATCH /b2c-listings/{id}`
- migration

**工时**：2 天

### 2.4 ⑦ 提交上架（❌ 0 命中）

**需要补**：
- `POST /b2c-listings/{id}/submit` — 状态机 draft → pending → processing → done/failed
- 状态机校验：submit 前跑一次 `listing_gate.py` 硬阻断（missing_sku / cjk_without_localization）

**工时**：1 天

### 2.5 ⑨ WC 回读校验（❌）

**现状**：`backend/app/services/woocommerce_sync_service.py:361 get_sync_status()` 只返回内存状态。

**缺口**：无 WC GET + diff。

**需要补**：
- `backend/app/services/wc_readback_service.py` —
  - `readback_wc_product(wc_id)` — GET /wp-json/wc/v3/products/{id}
  - `diff_wc_product(local_payload, remote_product)` — 比较 title/sku/price/media_count
  - `verify_sync(listing_id)` — 拉回 + diff + 更新状态
- `backend/app/api/v1/endpoints/woocommerce_sync.py` — `POST /sync/{listing_id}/verify`

**工时**：1 天

### 2.6 前端页面

**缺口**：
- 图片质检页面（显示 QC 结果、允许重试）
- Listing 编辑页面（编辑 json_payload、预览）
- 提交上架按钮（触发状态机）

**工时**：3-5 天

## 3. 总工程量

| 组件 | 后端 | 前端 | 测试 | 合计 |
|---|---|---|---|---|
| I2I 参数透传 | 0.5 | - | 0.5 | 1 |
| 图片质检 | 1.5 | 1 | 0.5 | 3 |
| B2C Listing 实体 | 2 | 1.5 | 1 | 4.5 |
| 提交上架状态机 | 1 | 0.5 | 0.5 | 2 |
| WC 回读校验 | 1 | 0.5 | 0.5 | 2 |
| 前端路由/集成 | 0 | 1 | - | 1 |
| **合计** | **6** | **4.5** | **3** | **13.5 人日** |

## 4. 实施顺序（按依赖排序）

```
1. I2I 参数透传（0.5 天）— 独立，无依赖
2. WC 回读校验（1 天）— 独立，可先做，立刻有验证价值
3. 图片质检（1.5 天）— 独立，可并行 2
4. B2C Listing 实体 + 状态机（2 天）— 独立，可并行 3
5. 前端页面（3-5 天）— 依赖 2/3/4 后端完成
```

**推荐**：优先 1+2，两者独立、总工时 1.5 天，能立刻在系统里看到「I2I 生图 + WC 回读」这两个之前完全没有的能力。

## 5. 本轮能交付什么

**本轮工具限制**：
- 无 `subagent_claude_code` / `subagent_codex`（Nexus 配方禁止普通 subagent）
- 后端未启动（8000 端口无响应）
- 前端未启动（3000/5173 端口无响应）
- 当前模型不支持图像输入（视觉验证不可行）

**本轮能真实交付**：
- ✅ 本文档（gap audit）
- ✅ ① I2I 参数透传（改 `image_gen.py` + `image_gen_service.py` + endpoint，~50 行）
- ✅ ⑨ WC 回读校验 service + endpoint（~150 行）
- ✅ 单元测试（backend/tests/）
- ❌ 视觉验证（前端页面截图看不到）
- ❌ 端到端联调（服务未启动）

**本轮不能交付**：图片质检、B2C Listing 实体、前端页面 —— 这些需要更多轮次。

---

## 6. 后续轮次计划

| Round | 交付 |
|---|---|
| 本轮 | 审计 + I2I 参数透传 + WC 回读校验 |
| Round 3 | 图片质检服务 + endpoint + tests |
| Round 4 | B2C Listing 实体 + migration + assemble endpoint |
| Round 5 | 提交上架状态机 + WC push 改造（走 Listing） |
| Round 6 | 前端 3 页面 + 路由 + 集成测试 |
| Round 7 | 端到端联调（启动服务，跑 SKU #1 全流程） |
| Round 8 | 蒸馏交付文档 |

**总计 8 轮，每轮 30-90 分钟**。

