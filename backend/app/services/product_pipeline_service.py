"""
产品端到端工作流服务（P2-2）

串联选品→产品分析→主图生产→生图Prompt→上架WooCommerce的一键流转。

工作流步骤：
Step 1: 商品信息输入（从牛顿选品结果导入或手动输入）
Step 2: AI产品分析（10字段识别 + 17字段产品报告）
Step 3: 主图生产（3套方向 + 短文案 + 10个变体）
Step 4: 生图Prompt生成（主图Prompt + 详情页Prompt）
Step 5: 上架数据生成（名称/描述/价格/SKU/分类/标签）
Step 6: 上架WooCommerce（可选，人工确认后执行）

遵循AGENTS.md规范：
- 业务规则集中在服务层
- Agent禁止直连数据库，通过services层访问
- 全链路可审计
- Human-in-the-loop：上架前必须人工确认
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

from app.services.main_image_service import (
    run_complete_workflow as run_main_image_workflow,
)
from app.services.product_analysis_service import (
    analyze_and_generate_report,
)
from app.services.product_listing_service import (
    check_image_gate,
    is_restricted,
    list_to_woocommerce,
    map_category_to_wc,
)
from app.services.product_content_service import normalize_image_urls
from app.services.prompt_generator_service import generate_full_prompt
from app.services.llm_gateway import LLMRequest, complete as llm_complete

logger = logging.getLogger(__name__)

# 服务配置
SERVICE_NAME = "product_pipeline"
SERVICE_VERSION = "1.0.0"

# 工作流状态
PIPELINE_STATUS = {
    "PENDING": "pending",
    "RUNNING": "running",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "PARTIAL": "partial",
}

# 步骤定义
PIPELINE_STEPS = [
    {"id": "input", "name": "商品信息输入", "description": "从牛顿选品结果导入或手动输入商品信息"},
    {"id": "analysis", "name": "AI产品分析", "description": "10字段AI识别 + 17字段产品信息报告"},
    {"id": "main_image", "name": "主图生产", "description": "3套主图方向 + 短文案 + 10个变体"},
    {"id": "prompt", "name": "生图Prompt生成", "description": "主图Prompt + 详情页Prompt"},
    {"id": "listing_data", "name": "上架数据生成", "description": "名称/描述/价格/SKU/分类/标签"},
    {"id": "v3_gate", "name": "V3.0选品闸门", "description": "Nuotao Score 六维评分 + V1-V12 一票否决 + 漏斗阶段判定"},
    {"id": "listing", "name": "上架WooCommerce", "description": "人工确认后上架到WooCommerce"},
]

# V3.0 闸门判定阈值：11 维运营分覆盖率低于此值时，多数品牌维度取的是中性
# 默认分，此时算出的 Reject 等级是「数据不足」的产物而非真实低分，转人工
# 复核而不是硬阻断，避免闸门在缺数据阶段误杀全部候选。
GATE_MIN_COVERAGE_RATIO = 0.30

# 闸门三种结论：blocked 有一票否决的确定性证据，必须阻断上架；needs_review
# 无否决但评分不足以自动放行；passed 可自动放行。
GATE_BLOCKED = "blocked"
GATE_NEEDS_REVIEW = "needs_review"
GATE_PASSED = "passed"

# 漏斗阶段取值（与 nuotao_selection_service 写入 products.funnel_stage 一致）。
FUNNEL_REJECTED = "rejected"


class PipelineError(Exception):
    """工作流异常"""


def get_pipeline_status() -> dict[str, Any]:
    """获取工作流服务状态"""
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "status": "operational",
        "steps": PIPELINE_STEPS,
        "statuses": PIPELINE_STATUS,
    }


def _safe_get(data: dict[str, Any], key: str, default: str = "") -> str:
    """安全获取字典值"""
    value = data.get(key, default)
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    return str(value) if value else default


def _safe_get_list(data: dict[str, Any], key: str, default: list[str] | None = None) -> list[str]:
    """安全获取列表值"""
    value = data.get(key, default or [])
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value else (default or [])


def _generate_sku(product_name: str, category: str = "") -> str:
    """生成纯 ASCII 的 SKU（跨境渠道要求：无中文、无空格、无空段）。

    规则：NT-<品牌/标题关键词>-<MMDDHHMM>。非 ASCII 字符（含中文）整体剔除，
    若剔除后没有可用拉丁词（纯中文名），退回到英文类目词或 OUTDOOR，
    最后统一清洗连续连字符与空段，杜绝双连字符。
    """
    # 只保留 ASCII 字母/数字，其余全部转成分隔符
    ascii_only = re.sub(r"[^A-Za-z0-9]+", "-", product_name or "")
    tokens = [tok for tok in ascii_only.split("-") if tok]
    # 取前两个有意义的英文词，每词最多 6 字符，避免过长
    stop = {"THE", "AND", "FOR", "WITH", "HIGH", "BACK", "PORTABLE", "FOLDING", "CHAIR"}
    picked: list[str] = []
    for tok in tokens:
        up = tok.upper()
        if up in stop and picked:
            continue
        picked.append(up[:6])
        if len(picked) >= 2:
            break
    core = "-".join(picked) if picked else ""

    if not core:
        # 纯中文名等无拉丁词场景：用英文类目或固定前缀
        cat_ascii = re.sub(r"[^A-Za-z0-9]+", "-", category or "")
        cat_tokens = [t.upper()[:6] for t in cat_ascii.split("-") if t]
        core = "-".join(cat_tokens[:2]) if cat_tokens else "OUTDOOR"

    timestamp = datetime.now().strftime("%m%d%H%M")
    sku = f"NT-{core}-{timestamp}"
    # 兜底：再次压缩连续连字符、去掉首尾连字符，保证无空段
    sku = re.sub(r"-+", "-", sku).strip("-")
    return sku


def _generate_listing_data(
    product_info: dict[str, Any],
    product_report: dict[str, Any],
    main_image_result: dict[str, Any],
) -> dict[str, Any]:
    """
    生成上架数据

    Args:
        product_info: 商品信息
        product_report: 产品报告
        main_image_result: 主图生产结果

    Returns:
        上架数据
    """
    # 产品名称（优化后的电商名称）
    product_name = _safe_get(product_report, "product_name", _safe_get(product_info, "name", "产品"))

    # 产品描述（长描述）
    product_description = _safe_get(product_report, "product_description", "")
    if not product_description:
        # 从卖点和功能拼接描述
        selling_points = _safe_get_list(product_report, "core_selling_points", [])
        features = _safe_get_list(product_report, "product_features", [])
        desc_parts = []
        if selling_points:
            desc_parts.append("【核心卖点】\n" + "\n".join(f"• {sp}" for sp in selling_points))
        if features:
            desc_parts.append("【产品功能】\n" + "\n".join(f"• {f}" for f in features))
        product_description = "\n\n".join(desc_parts)

    # 短描述
    short_description = _safe_get(product_info, "description", "")
    if not short_description:
        short_description = product_description[:100] + "..." if len(product_description) > 100 else product_description

    # 价格（从1688价格推算，默认加价率100%）
    price_str = _safe_get(product_info, "price", "")
    regular_price = ""
    try:
        # 提取价格数字
        import re
        price_match = re.search(r'[\d.]+', price_str)
        if price_match:
            source_price = float(price_match.group())
            # 加价率100%（可配置）
            regular_price = f"{source_price * 2:.2f}"
    except Exception:
        pass

    # SKU
    sku = _generate_sku(product_name)

    # 分类：按商品名 + 内部类目映射到 WooCommerce 真实分类 term id
    # （旧逻辑硬编码内部 id 15，恰好等于 WC 的 Uncategorized，导致全部归到未分类）
    category = _safe_get(product_info, "category", "")
    categories = map_category_to_wc(product_name, category)

    # 标签：保留完整文本。旧实现截断到 10 字符，中文标签入库即残缺，
    # 直接影响 WooCommerce 端搜索与过滤；长度上限放宽到 60 字符防极端长句。
    tags = []
    selling_points = _safe_get_list(product_report, "core_selling_points", [])
    for sp in selling_points[:3]:
        tags.append({"name": sp.strip()[:60]})
    usage_scenarios = _safe_get_list(product_report, "usage_scenarios", [])
    for scenario in usage_scenarios[:2]:
        tags.append({"name": scenario.strip()[:60]})

    # 上架优先使用已导入的 1688 原图；AI 生图结果需审核后写回商品媒体字段。
    # A-3 fix (2026-09-18): 把图片拆成 main_images / detail_images 两个字段，
    # 与 check_image_gate 的主图 5 + 详情图 6 语义对齐。1688 原图默认归入
    # main_images（取前 5 张），detail_images 留空由批量生图填充；
    # images 保留扁平合并数组做向后兼容（WC API 与旧前端仍读此字段）。
    all_1688_images = [{"src": url} for url in normalize_image_urls(product_info.get("images"))]
    
    # BUG #5 fix: 合并 AI 生成图片
    generated_images = []
    if isinstance(main_image_result, dict):
        generated_images = [{"src": url} for url in main_image_result.get("generated_images", [])]
    
    all_images = all_1688_images + generated_images
    main_images = all_images[:5]  # 最多取 5 张作为主图
    detail_images: list[dict[str, str]] = all_images[5:]  # 剩余作为详情图
    images = main_images + detail_images  # 扁平合并，向后兼容
    
    logger.info("Listing: %d 1688 + %d generated = %d total", 
                len(all_1688_images), len(generated_images), len(all_images))

    return {
        "name": product_name,
        "type": "simple",
        "regular_price": regular_price,
        "description": product_description,
        "short_description": short_description,
        "sku": sku,
        "manage_stock": True,
        "stock_quantity": 100,  # 默认库存
        "status": "draft",  # 默认草稿，人工确认后发布
        "categories": categories,
        "tags": tags,
        "images": images,
        "main_images": main_images,
        "detail_images": detail_images,
        "meta_data": [
            {"key": "source", "value": "1688"},
            {"key": "source_price", "value": price_str},
            {"key": "pipeline_id", "value": str(uuid.uuid4())},
        ],
    }




# 目标市场默认美国——上架 WooCommerce 的商品文案必须为英文。
# 该函数把 Step 5 生成的中文/中英混排 listing 交给 LLM 做一次英文本地化，
# 失败时降级保留原文并在 warnings 里标注，不阻塞主流程。
def _has_cjk(text: str) -> bool:
    """粗判文本是否含中文字符。"""
    if not text:
        return False
    return any('\u4e00' <= ch <= '\u9fff' for ch in text)


async def _english_localize_listing_data(listing_data: dict[str, Any]) -> dict[str, Any]:
    """把上架数据中的 name / short_description / description / tags 本地化到英文。"""
    try:
        name = listing_data.get("name", "") or ""
        short_desc = listing_data.get("short_description", "") or ""
        long_desc = listing_data.get("description", "") or ""
        tags = [t.get("name", "") for t in listing_data.get("tags", []) if isinstance(t, dict)]

        # 不需要本地化就跳过
        if not (_has_cjk(name) or _has_cjk(short_desc) or _has_cjk(long_desc)
                 or any(_has_cjk(t) for t in tags)):
            listing_data.setdefault("_localization", {"status": "skipped", "reason": "no CJK content"})
            return listing_data

        prompt = (
            "You are an e-commerce localization expert for a US outdoor gear DTC brand. "
            "Translate and adapt the following Chinese product listing into natural, SEO-friendly "
            "American English. Keep brand names and model names as-is. Do NOT add marketing fluff "
            "not supported by the source. Return ONLY a JSON object with keys: "
            "name (max 80 chars), short_description (max 300 chars plain text), "
            "description (HTML allowed, 200-600 words), tags (array of 5-8 short English keywords).\n\n"
            f"SOURCE_NAME: {name}\n"
            f"SOURCE_SHORT: {short_desc}\n"
            f"SOURCE_LONG: {long_desc}\n"
            f"SOURCE_TAGS: {', '.join(tags)}\n"
        )

        resp = await llm_complete(
            LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                task_type="listing_localization",
                temperature=0.3,
                max_tokens=1500,
                response_format="json_object",
            ),
        )
        import json as _json
        localized = _json.loads(resp.content)

        if isinstance(localized, dict):
            if localized.get("name"):
                listing_data["name"] = str(localized["name"])[:120]
                # 英文标题确定后，重新生成纯 ASCII SKU，覆盖 Step5 基于中文名生成的 SKU
                try:
                    old_sku = str(listing_data.get("sku") or "")
                    # 保留原 SKU 的时间戳后缀（若有），避免同次运行时间戳漂移
                    ts_match = re.search(r"(\d{6,})$", old_sku)
                    new_sku = _generate_sku(listing_data["name"], listing_data.get("categories_label", ""))
                    if ts_match:
                        new_sku = re.sub(r"\d{6,}$", ts_match.group(1), new_sku)
                    listing_data["sku"] = new_sku
                except Exception:  # noqa: BLE001
                    pass
            if localized.get("short_description"):
                listing_data["short_description"] = str(localized["short_description"])[:500]
            if localized.get("description"):
                listing_data["description"] = str(localized["description"])
            if isinstance(localized.get("tags"), list) and localized["tags"]:
                listing_data["tags"] = [{"name": str(t)[:80]} for t in localized["tags"][:10]]
            listing_data.setdefault("_localization", {
                "status": "localized",
                "provider": resp.provider,
                "model": resp.model,
            })
        else:
            listing_data.setdefault("_localization", {"status": "degraded", "reason": "LLM returned non-object"})
    except Exception as e:  # noqa: BLE001
        logger.warning("English localization failed, keeping source text: %s", e)
        listing_data.setdefault("_localization", {"status": "failed", "reason": str(e)[:300]})
    return listing_data


# 主图方向 → 英文背景/画面描述（生图 prompt 必须英文化，主体不允许保留中文名）
_EN_BG_BY_KEY: dict[str, str] = {
    "white_background": "pure white background, clean and minimal e-commerce studio shot, soft even lighting, product centered",
    "real_scene": "realistic outdoor lifestyle scene in nature, natural daylight, immersive usage context, product clearly visible",
    "promotion_conversion": "vibrant promotional background with strong visual impact, sale campaign mood, bold composition",
}
_EN_BG_BY_NAME: dict[str, str] = {
    "白底清爽": _EN_BG_BY_KEY["white_background"],
    "真实场景": _EN_BG_BY_KEY["real_scene"],
    "促销转化": _EN_BG_BY_KEY["promotion_conversion"],
}


def _english_subject_prompt(english_name: str) -> str:
    return f"{english_name}, premium quality, accurate product appearance, high detail, e-commerce product photography"


def localize_main_image_prompts(main_image_data: dict[str, Any], english_name: str) -> dict[str, Any]:
    """把主图生产结果里用于生图的方向 prompt 主体/背景改写为英文。

    Step3 主图生产在 Step5 英文化之前运行，方向 prompt 的主体原本是中文名。
    在拿到英文 listing 标题后回填，保证最终送进生图模型的 prompt 全英文。
    就地更新并返回 main_image_data。
    """
    if not main_image_data or not english_name:
        return main_image_data
    subject_en = _english_subject_prompt(english_name)
    try:
        # 1) 顶层扁平 directions 数组（前端直接读取/用于生图）
        for d in main_image_data.get("directions", []) or []:
            if not isinstance(d, dict):
                continue
            bg_en = _EN_BG_BY_NAME.get(str(d.get("name", ""))) or _EN_BG_BY_KEY["white_background"]
            d["prompt"] = f"Subject: {subject_en} | Background: {bg_en}"
            prompt_block = d.get("prompt")
        # 2) 底层 step02 三方向结构
        workflow = main_image_data.get("workflow", {}) or {}
        step02 = workflow.get("step02_three_directions", {}) or {}
        for key, d in (step02.get("directions", {}) or {}).items():
            if not isinstance(d, dict):
                continue
            bg_en = _EN_BG_BY_KEY.get(key, _EN_BG_BY_KEY["white_background"])
            p = d.get("prompt")
            if isinstance(p, dict):
                p["subject"] = subject_en
                p["background"] = bg_en
        if main_image_data.get("product_name"):
            main_image_data["product_name"] = english_name
    except Exception as e:  # noqa: BLE001
        logger.warning("Localize main image prompts failed (non-blocking): %s", e)
    return main_image_data


def evaluate_v3_gate(evaluation: dict[str, Any]) -> dict[str, Any]:
    """把一次 V3.0 评估结果判定为闸门结论（纯函数，无副作用）。

    闸门只对「有一票否决确定性证据」的产品硬阻断。评分等级为 Reject 但 11 维
    覆盖率不足时，多数维度取的是中性默认分，这种 Reject 是数据缺失的产物而非
    真实低分，按 needs_review 交人工处理，不能据此误杀候选
    （docs/nuotao_product_score_v3.0.md §2.3、§3）。
    """
    veto = evaluation.get("veto") or {}
    failed = [str(item) for item in (veto.get("failed") or [])]
    pending = [str(item) for item in (veto.get("pending") or [])]
    grade = evaluation.get("grade")
    total = evaluation.get("nuotao_total")
    coverage = (evaluation.get("evidence") or {}).get("operational_v2_coverage") or {}
    coverage_ratio = coverage.get("coverage_ratio")

    if failed:
        verdict = GATE_BLOCKED
        reason = f"触发一票否决：{'、'.join(failed)}"
    elif grade == "reject" and (
        coverage_ratio is None or float(coverage_ratio) < GATE_MIN_COVERAGE_RATIO
    ):
        verdict = GATE_NEEDS_REVIEW
        reason = (
            f"Nuotao Score {total} 为 Reject，但 11 维运营分覆盖率仅 {coverage_ratio}"
            f"（阈值 {GATE_MIN_COVERAGE_RATIO}），多数维度为中性默认分；"
            "需补全成本/供应商等数据后重评，或人工复核放行"
        )
    elif grade == "reject":
        verdict = GATE_NEEDS_REVIEW
        reason = f"Nuotao Score {total} 低于 65（Reject 等级），不建议上架"
    else:
        verdict = GATE_PASSED
        reason = f"无一票否决，Nuotao Score {total}（{grade}）"

    return {
        "verdict": verdict,
        "reason": reason,
        "blocked": verdict == GATE_BLOCKED,
        "auto_list_allowed": verdict == GATE_PASSED,
        "nuotao_total": total,
        "grade": grade,
        "funnel_stage": evaluation.get("funnel_stage"),
        "veto_failed": failed,
        "veto_pending": pending,
        "coverage_ratio": coverage_ratio,
    }


async def check_product_push_gate(
    session: AsyncSession,
    product_id: str,
    *,
    workspace_id: UUID | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """上架推送前的 V3.0 闸门检查（对已落库商品）。

    与 run_v3_gate 的区别：那里为流水线阶段的商品建档并评估，这里直接评估
    既有 Product 行，用于渠道与上架页的推送通道（docs/sop_audit_selection_to_
    listing.md §3.1 记录的「通道②裸奔」）。

    判定规则：
    - blocked（触发一票否决）：硬阻断，force 也不放行；
    - needs_review（低分 / 覆盖率不足 / 评估失败）：需人工显式确认后 force 放行，
      符合 AGENTS.md 3.1「AI 只建议、关键动作人审」；
    - passed：直接放行。

    评估异常（LLM 网关不可用等）按 needs_review 处理，绝不静默放行。
    """
    from app.core.workspace import DEFAULT_WORKSPACE_ID
    from app.models.product import Product
    from app.services.nuotao_selection_service import evaluate_product

    workspace_id = workspace_id or DEFAULT_WORKSPACE_ID
    product = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if product is None:
        return {
            "verdict": GATE_NEEDS_REVIEW,
            "blocked": True,
            "force_required": True,
            "reason": f"产品不存在: {product_id}",
        }

    try:
        evaluation = await evaluate_product(
            session, product.id, workspace_id=workspace_id,
        )
        gate = evaluate_v3_gate(evaluation)
    except Exception as e:  # noqa: BLE001
        # 评估不可用时不阻断也不放行，转人工确认
        logger.warning(
            "V3.0 闸门评估失败，转人工确认: product=%s, error=%s", product_id, e
        )
        return {
            "verdict": GATE_NEEDS_REVIEW,
            "blocked": False,
            "force_required": True,
            "reason": f"V3.0 选品闸门评估失败（{e}），需人工复核确认后继续",
            "product_id": str(product.id),
            "sku": product.sku,
        }

    gate["product_id"] = str(product.id)
    gate["sku"] = product.sku
    gate["blocked"] = bool(gate["blocked"])
    gate["force_required"] = (gate["verdict"] == GATE_NEEDS_REVIEW) and not force
    return gate


def _parse_weight_kg(raw: Any) -> Decimal | None:
    """从 '500g' / '0.5kg' / '1.2 千克' 解析公斤数；解析不出返回 None。"""
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return raw
    matches = re.findall(
        r"(\d+(?:\.\d+)?)\s*(kg|kgs|千克|公斤|g|克)?", str(raw).strip().lower()
    )
    if not matches:
        return None
    unit = next((m[1] for m in reversed(matches) if m[1]), "kg")
    # ROUND-4D: 范围值（如 "1462-2100g"）按上界计费，取首数字会低估运费。
    # 仅在明确的数字-数字范围内取上界，避免误伤 "1800g 型号X2" 这类值。
    text = str(raw).strip().lower()
    try:
        if re.search(r"\d\s*[-~–—]\s*\d", text):
            value = max(Decimal(m[0]) for m in matches)
        else:
            value = Decimal(matches[0][0])
    except (ArithmeticError, ValueError):
        return None
    return (value / Decimal("1000")).quantize(Decimal("0.001")) if unit in ("g", "克") else value


def _parse_decimal(raw: Any) -> Decimal | None:
    """从 '¥6.7' / '6.7-19.7' 取第一个数值；取不到返回 None。"""
    if raw is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(raw))
    if not match:
        return None
    try:
        return Decimal(match.group())
    except (ArithmeticError, ValueError):
        return None


async def run_v3_gate(
    session: AsyncSession,
    product_info: dict[str, Any],
    listing_data: dict[str, Any],
    *,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """落库候选产品并执行 V3.0 评估，返回闸门结论。

    流水线阶段产品尚未落库，而 V3.0 评估以 Product 行为输入，因此闸门先用上架
    数据创建 candidate 行（同 SKU 已存在则复用，避免重复建档），再评估。产品由
    此进入 V3.0 漏斗，后续可在候选页补全成本/供应商数据重评。

    闸门不伪造成本数据：流水线阶段没有真实落地成本，宁缺勿造，因此不写
    ProductCost，V9/V10 保持 pending（AGENTS.md §1.2.5、§2.1 显式空值处理）。
    """
    from app.core.workspace import DEFAULT_WORKSPACE_ID
    from app.models.product import Product
    from app.services.nuotao_selection_service import evaluate_product

    workspace_id = workspace_id or DEFAULT_WORKSPACE_ID
    sku = str(listing_data.get("sku") or _generate_sku(str(listing_data.get("name") or "")))
    name = str(listing_data.get("name") or product_info.get("name") or "未命名商品")

    existing = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.sku == sku,
                Product.deleted_at.is_(None),
            )
        )
    ).scalars().first()

    source_price = _parse_decimal(product_info.get("price"))
    sale_price = _parse_decimal(listing_data.get("regular_price"))
    meta = {
        "source": "product_pipeline",
        "source_url": product_info.get("source_url") or None,
        "source_id": product_info.get("source_id") or None,
        "source_price": str(source_price) if source_price is not None else None,
        "sale_price": str(sale_price) if sale_price is not None else None,
        "pipeline_trace_id": trace_id,
    }

    if existing is not None:
        product = existing
        product.name = name
        product.category = product.category or product_info.get("category") or None
        product.meta = {
            **(product.meta or {}),
            **{key: value for key, value in meta.items() if value is not None},
        }
        if product.weight_kg is None:
            product.weight_kg = _parse_weight_kg(product_info.get("weight"))
    else:
        product = Product(
            workspace_id=workspace_id,
            sku=sku,
            name=name,
            description=str(listing_data.get("short_description") or "")[:2000] or None,
            category=product_info.get("category") or None,
            status="draft",
            candidate_status="candidate",
            source="1688" if product_info.get("source_url") else "pipeline",
            source_url=product_info.get("source_url") or None,
            weight_kg=_parse_weight_kg(product_info.get("weight")),
            target_market=str(product_info.get("target_market") or "US"),
            meta=meta,
        )
        session.add(product)

    # BUG-13 (2026-09-20): listing_data already carries the media and taxonomy
    # this pipeline produced - 1688 originals + AI-generated images, tags - and
    # product_info carries the parsed weight / dimensions / attributes. None of
    # it was persisted here, so every product reached the store without a main
    # image, tags or attributes. listing_data only went back to the caller in
    # the pipeline result; it never reached the product row.
    from sqlalchemy.orm.attributes import flag_modified
    from app.services.listing_gate import (
        collect_attributes,
        normalise_listing_images,
        normalise_listing_tags,
        parse_dimensions,
    )

    listing_media = normalise_listing_images(
        listing_data.get("main_images") or listing_data.get("images")
    )
    listing_tag_names = normalise_listing_tags(listing_data.get("tags"))
    listing_attrs = collect_attributes(product_info)
    listing_dims = parse_dimensions(product_info.get("dimensions"))

    if listing_media and not (product.meta or {}).get("main_images"):
        product.meta = {**(product.meta or {}), "main_images": listing_media}
    if listing_tag_names and not product.tags:
        product.tags = listing_tag_names
    if listing_attrs and not product.attributes:
        product.attributes = listing_attrs
    if listing_dims and not product.dimensions:
        product.dimensions = listing_dims

    # The products JSON columns are plain JSON with no MutableDict, so plain
    # reassignment is not reliably flushed. Flag each column we actually touched
    # - this is the pattern that verifiably persisted in production.
    if listing_media:
        flag_modified(product, "meta")
    if listing_tag_names:
        flag_modified(product, "tags")
    if listing_attrs:
        flag_modified(product, "attributes")
    if listing_dims:
        flag_modified(product, "dimensions")
    if product.weight_kg is None:
        product.weight_kg = _parse_weight_kg(product_info.get("weight"))

    await session.flush()

    evaluation = await evaluate_product(
        session, product.id, workspace_id=workspace_id, trace_id=trace_id
    )
    gate = evaluate_v3_gate(evaluation)
    gate["product_id"] = str(product.id)
    gate["sku"] = sku
    gate["dimensions"] = evaluation.get("dimensions")
    await session.flush()
    return gate


async def run_pipeline(
    product_info: dict[str, Any],
    *,
    auto_list: bool = False,
    include_images: bool = False,
    session: AsyncSession | None = None,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    运行完整的产品端到端工作流

    Args:
        product_info: 商品信息
        auto_list: 是否自动上架（默认False，需要人工确认）
        include_images: 是否包含图片生成（需要数据库session，默认False）
        session: 数据库会话。传入时执行 V3.0 选品闸门（落库候选并评估否决），
            为 None 时闸门标记 skipped、不评估也不阻断，保持旧调用方行为不变。
        workspace_id: 工作空间 ID，闸门落库使用；缺省用默认工作空间
        trace_id: 全链路追踪 ID

    Returns:
        工作流结果
    """
    pipeline_id = str(uuid.uuid4())
    start_time = time.time()
    steps_result: dict[str, Any] = {}
    errors: list[str] = []

    logger.info("Pipeline %s started for product: %s", pipeline_id, product_info.get("name", "unknown"))

    try:
        # Step 1: 商品信息输入
        steps_result["input"] = {
            "status": "completed",
            "data": product_info,
            "timestamp": datetime.now().isoformat(),
        }
        logger.info("Pipeline %s Step 1 (input) completed", pipeline_id)

        # Step 2: AI产品分析
        try:
            analysis_result = await analyze_and_generate_report(product_info)
            if analysis_result["success"]:
                steps_result["analysis"] = {
                    "status": "completed",
                    "data": {
                        "ai_recognition": analysis_result["data"]["ai_recognition"],
                        "product_report": analysis_result["data"]["product_report"],
                    },
                    "timestamp": datetime.now().isoformat(),
                }
                logger.info("Pipeline %s Step 2 (analysis) completed", pipeline_id)
            else:
                raise PipelineError(analysis_result.get("error", "Analysis failed"))
        except Exception as e:
            errors.append(f"Analysis failed: {str(e)}")
            steps_result["analysis"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 2 (analysis) failed: %s", pipeline_id, str(e))

        # 获取产品报告（如果分析成功）
        product_report = steps_result.get("analysis", {}).get("data", {}).get("product_report", {})

        # Step 3: 主图生产
        try:
            main_image_result = run_main_image_workflow(product_info)
            if main_image_result["success"]:
                main_image_data = main_image_result["data"]
                
                # BUG #5 fix: 生成实际图片（使用 Pollinations.ai 免费模型）
                if session and main_image_data.get("directions"):
                    try:
                        from app.services.image_generation_service import generate_image_and_save
                        import random
                        
                        generated_images = []
                        directions = main_image_data.get("directions", [])
                        
                        # 为每个方向生成一张图片（最多 3 张）
                        for i, direction in enumerate(directions[:3]):
                            direction_name = direction.get("direction", "")
                            description = direction.get("description", "")
                            
                            # 构建英文 Prompt（将中文翻译为英文，用于 AI 图片生成）
                            # 简单翻译：移除中文，保留英文关键词
                            name_en = product_info.get('name', 'product')
                            # 尝试提取英文部分（如果有）
                            import re
                            en_parts = re.findall(r'[a-zA-Z]+', name_en)
                            if en_parts:
                                name_en = ' '.join(en_parts[:10])
                            else:
                                name_en = 'outdoor folding chair'  # 默认英文描述
                            
                            direction_en = direction_name
                            # 翻译常见方向名称
                            direction_map = {
                                '白底清爽': 'white background clean',
                                '真实场景': 'realistic outdoor scene',
                                '促销转化': 'promotional sale',
                                '生活方式': 'lifestyle scene',
                                '细节展示': 'product detail closeup'
                            }
                            direction_en = direction_map.get(direction_name, 'product photography')
                            
                            description_en = description
                            # 简单移除中文字符，保留英文
                            description_en = re.sub(r'[\u4e00-\u9fff]+', ' ', description_en)
                            description_en = ' '.join(description_en.split())  # 清理多余空格
                            
                            prompt = f"{name_en}, {direction_en}, {description_en}, premium quality, e-commerce photography, high detail"
                            
                            # 使用 Pollinations.ai 免费模型
                            gen_task = await generate_image_and_save(
                                session,
                                prompt=prompt,
                                use_case="main_image",
                                model=None,
                                width=1024,
                                height=1024,
                            )
                            
                            if gen_task and gen_task.image_url:
                                generated_images.append(gen_task.image_url)
                                logger.info("Pipeline %s Step 3: generated image %d/%d: %s", 
                                           pipeline_id, i+1, min(3, len(directions)), gen_task.image_url)
                        
                        if generated_images:
                            main_image_data["generated_images"] = generated_images
                            logger.info("Pipeline %s Step 3: successfully generated %d images", pipeline_id, len(generated_images))
                    except Exception as img_err:
                        logger.warning("Pipeline %s Step 3: image generation failed: %s", pipeline_id, str(img_err))
                
                steps_result["main_image"] = {
                    "status": "completed",
                    "data": main_image_data,
                    "timestamp": datetime.now().isoformat(),
                }
                logger.info("Pipeline %s Step 3 (main_image) completed", pipeline_id)
            else:
                raise PipelineError(main_image_result.get("error", "Main image generation failed"))
        except Exception as e:
            errors.append(f"Main image generation failed: {str(e)}")
            steps_result["main_image"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 3 (main_image) failed: %s", pipeline_id, str(e))

        # Step 4: 生图Prompt生成
        try:
            if product_report:
                # 生成主图Prompt（白底清爽方向）
                main_prompt_result = generate_full_prompt(product_report, page_type="brand_scene")
                # 生成详情页Prompt
                detail_prompt_result = generate_full_prompt(product_report, page_type="feature_selling")

                steps_result["prompt"] = {
                    "status": "completed",
                    "data": {
                        "main_image_prompt": main_prompt_result["data"]["full_prompt"] if main_prompt_result["success"] else "",
                        "detail_image_prompt": detail_prompt_result["data"]["full_prompt"] if detail_prompt_result["success"] else "",
                        "prompt_parts": main_prompt_result["data"]["parts"] if main_prompt_result["success"] else {},
                    },
                    "timestamp": datetime.now().isoformat(),
                }
                logger.info("Pipeline %s Step 4 (prompt) completed", pipeline_id)
            else:
                steps_result["prompt"] = {"status": "skipped", "reason": "No product report available"}
        except Exception as e:
            errors.append(f"Prompt generation failed: {str(e)}")
            steps_result["prompt"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 4 (prompt) failed: %s", pipeline_id, str(e))

        # Step 5: 上架数据生成（含英文本地化，目标市场默认 US）
        try:
            main_image_data = steps_result.get("main_image", {}).get("data", {})
            listing_data = _generate_listing_data(product_info, product_report, main_image_data)
            listing_data = await _english_localize_listing_data(listing_data)
            # 用英文标题回填主图方向 prompt 的主体/背景，保证送生图模型全英文
            try:
                english_name = listing_data.get("name", "")
                if english_name and not _has_cjk(english_name):
                    localized_mi = localize_main_image_prompts(main_image_data, english_name)
                    steps_result["main_image"]["data"] = localized_mi
            except Exception as loc_err:  # noqa: BLE001
                logger.warning("Backfill English main-image prompt failed: %s", loc_err)
            steps_result["listing_data"] = {
                "status": "completed",
                "data": listing_data,
                "timestamp": datetime.now().isoformat(),
            }
            logger.info("Pipeline %s Step 5 (listing_data) completed; localization=%s",
                        pipeline_id, listing_data.get("_localization", {}).get("status", "n/a"))
        except Exception as e:
            errors.append(f"Listing data generation failed: {str(e)}")
            steps_result["listing_data"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 5 (listing_data) failed: %s", pipeline_id, str(e))

        # Step 6: V3.0 选品闸门（六维评分 + V1-V12 一票否决 + 漏斗阶段）
        # 闸门必须在上架之前：被一票否决的产品不允许进入 WooCommerce，否则
        # 「主动拒绝不适合 Nuotao 的商品」这条 V3.0 核心策略形同虚设。
        gate: dict[str, Any] | None = None
        if session is not None:
            try:
                gate_listing_data = steps_result.get("listing_data", {}).get("data", {})
                if not gate_listing_data:
                    raise PipelineError("无上架数据，无法执行 V3.0 闸门")
                gate = await run_v3_gate(
                    session,
                    product_info,
                    gate_listing_data,
                    workspace_id=workspace_id,
                    trace_id=trace_id or f"pipeline-{pipeline_id}",
                )
                steps_result["v3_gate"] = {
                    "status": "completed",
                    "data": gate,
                    "timestamp": datetime.now().isoformat(),
                }
                logger.info(
                    "Pipeline %s Step 6 (v3_gate) completed: verdict=%s, nuotao=%s, failed=%s",
                    pipeline_id, gate.get("verdict"), gate.get("nuotao_total"),
                    gate.get("veto_failed"),
                )
            except Exception as e:
                errors.append(f"V3.0 gate failed: {e!s}")
                steps_result["v3_gate"] = {"status": "failed", "error": str(e)}
                logger.error("Pipeline %s Step 6 (v3_gate) failed: %s", pipeline_id, str(e))
        else:
            steps_result["v3_gate"] = {
                "status": "skipped",
                "reason": "未提供数据库会话，V3.0 选品闸门未执行",
            }
            logger.warning(
                "Pipeline %s Step 6 (v3_gate) skipped: no DB session supplied", pipeline_id
            )

        # Step 7: 上架WooCommerce（可选，需要人工确认；被闸门否决则阻断）
        # 闸门否决要在人工确认前就暴露：若仍提示「请确认上架」，被否决的产品
        # 会被人工放行，闸门等于没装。
        gate_blocked = bool(gate and gate.get("blocked"))
        gate_needs_review = bool(gate and gate.get("verdict") == GATE_NEEDS_REVIEW)

        if gate_blocked:
            steps_result["listing"] = {
                "status": "blocked",
                "error": f"V3.0 闸门否决，禁止上架：{(gate or {}).get('reason')}",
                "gate": gate,
                "message": "产品触发一票否决，不允许上架；如需上架须人工复核并留档",
            }
            logger.warning(
                "Pipeline %s Step 7 (listing) blocked by V3.0 gate: %s",
                pipeline_id, (gate or {}).get("veto_failed"),
            )
        elif gate_needs_review:
            # Needs-review is checked BEFORE auto_list: with auto_list ahead, this
            # branch was unreachable and a flagged product would be pushed to
            # WooCommerce anyway - the gate degraded to a footnote. Review is a
            # business decision and must win over an automation flag.
            steps_result["listing"] = {
                "status": "pending_review",
                "gate": gate,
                "message": f"V3.0 闸门待人工复核：{(gate or {}).get('reason')}",
            }
        elif auto_list:
            try:
                listing_data = steps_result.get("listing_data", {}).get("data", {})
                if listing_data:
                    # 检查是否管制物品
                    restricted, reason = is_restricted(listing_data.get("name", ""), listing_data.get("sku", ""))
                    if restricted:
                        raise PipelineError(f"Product is restricted: {reason}")

                    listing_result = list_to_woocommerce(listing_data, status="draft")
                    steps_result["listing"] = {
                        "status": "completed" if listing_result.get("success") else "failed",
                        "data": listing_result,
                        "timestamp": datetime.now().isoformat(),
                    }
                    if listing_result.get("success"):
                        logger.info("Pipeline %s Step 7 (listing) completed: WC ID=%s", pipeline_id, listing_result.get("woocommerce_id"))
                    else:
                        errors.append(f"Listing failed: {listing_result.get('error')}")
                        logger.error("Pipeline %s Step 7 (listing) failed: %s", pipeline_id, listing_result.get("error"))
            except Exception as e:
                errors.append(f"Listing failed: {str(e)}")
                steps_result["listing"] = {"status": "failed", "error": str(e)}
                logger.error("Pipeline %s Step 7 (listing) failed: %s", pipeline_id, str(e))
        else:
            steps_result["listing"] = {
                "status": "pending_confirmation",
                "gate": gate,
                "message": "上架数据已生成，请人工确认后执行上架",
            }

        # 计算总体状态。闸门否决是明确的业务结论，不是技术错误：单独给出
        # blocked 状态，让调用方能区分「跑失败了」和「被选品策略拒绝了」。
        completed_steps = sum(1 for s in steps_result.values() if s.get("status") == "completed")
        total_steps = len(PIPELINE_STEPS)
        gate_verdict = (gate or {}).get("verdict")
        if gate_blocked:
            overall_status = "blocked"
        elif errors:
            overall_status = "partial" if completed_steps > 0 else "failed"
        else:
            overall_status = "completed"

        elapsed_time = time.time() - start_time

        result = {
            "success": overall_status in ["completed", "partial"],
            "data": {
                "pipeline_id": pipeline_id,
                "status": overall_status,
                "completed_steps": completed_steps,
                "total_steps": total_steps,
                "progress": round(completed_steps / total_steps * 100, 1),
                "elapsed_time_seconds": round(elapsed_time, 2),
                "steps": steps_result,
                "errors": errors,
                "product_name": _safe_get(product_info, "name", ""),
                "sku": steps_result.get("listing_data", {}).get("data", {}).get("sku", ""),
                # V3.0 闸门结论：调用方据此决定是否允许确认上架
                "v3_gate": gate,
                "gate_verdict": gate_verdict,
                "gate_blocked": gate_blocked,
                "gate_needs_review": gate_needs_review,
            },
            "error": None if not errors else f"{len(errors)} errors occurred",
        }
        if gate_blocked:
            result["error"] = f"V3.0 选品闸门否决，禁止上架：{(gate or {}).get('reason')}"

        logger.info("Pipeline %s finished: status=%s, completed=%d/%d, errors=%d",
                    pipeline_id, overall_status, completed_steps, total_steps, len(errors))

        return result

    except Exception as e:
        logger.error("Pipeline %s unexpected error: %s", pipeline_id, str(e))
        return {
            "success": False,
            "data": {
                "pipeline_id": pipeline_id,
                "status": "failed",
                "steps": steps_result,
                "errors": [str(e)],
            },
            "error": str(e),
        }


def confirm_and_list(
    pipeline_result: dict[str, Any],
    *,
    status: str = "publish",
) -> dict[str, Any]:
    """
    人工确认后执行上架

    Args:
        pipeline_result: 工作流结果（包含listing_data）
        status: 上架状态（publish/draft/pending）

    Returns:
        上架结果
    """
    try:
        listing_data = pipeline_result.get("data", {}).get("steps", {}).get("listing_data", {}).get("data", {})
        if not listing_data:
            return {"success": False, "error": "No listing data found in pipeline result"}

        # 检查是否管制物品
        restricted, reason = is_restricted(listing_data.get("name", ""), listing_data.get("sku", ""))
        if restricted:
            return {"success": False, "error": f"Product is restricted: {reason}"}

        # 图片齐套门禁（硬门禁，用户决策 2026-09-16）：主图5+详情6 不齐时，
        # 草稿与正式发布一律阻止推送 WC，避免"裸奔"草稿流入渠道。
        gate = check_image_gate(listing_data)
        gate_notice = "；".join(gate.get("reasons", []))
        if not gate.get("passed"):
            return {
                "success": False,
                "error": f"图片未达上架标准，已阻止上架（{status}）：{gate_notice}",
                "image_gate": gate,
            }

        listing_result = list_to_woocommerce(listing_data, status=status)
        return listing_result

    except Exception as e:
        logger.error("Confirm and list error: %s", str(e))
        return {"success": False, "error": str(e)}


async def upsert_local_listed_product(
    db: "AsyncSession",
    listing_data: dict[str, Any],
    wc_result: dict[str, Any],
    workspace_id: "UUID",
    *,
    source: str = "pipeline",
    source_url: str = "",
) -> dict[str, Any]:
    """
    上架 WooCommerce 成功后，把商品 upsert 到本地 products 主数据表。

    解决"只推 WC、本地商品主数据为空"的数据断层：按 workspace + SKU 查找，
    存在（含软删行）则更新并复活，不存在则新建。

    Returns:
        {"product_id", "created": bool}
    """
    from app.models.product import Product

    sku = str(listing_data.get("sku") or "").strip()
    name = str(listing_data.get("name") or "").strip()
    if not sku or not name:
        return {"product_id": None, "created": False, "error": "missing sku/name"}

    # WC status 映射到本地 commerce status
    wc_status = (wc_result.get("status") or listing_data.get("status") or "draft").lower()
    local_status = "active" if wc_status == "publish" else "draft"

    # tags: listing 里可能是 [{"name":...}] 或 ["tag",...]
    raw_tags = listing_data.get("tags") or []
    tags: list[str] = []
    for t in raw_tags:
        if isinstance(t, dict):
            if t.get("name"):
                tags.append(str(t["name"]))
        elif t:
            tags.append(str(t))

    # category：取第一个分类 id/名
    raw_cats = listing_data.get("categories") or []
    category = None
    if raw_cats:
        first = raw_cats[0]
        category = str(first.get("name") or first.get("id")) if isinstance(first, dict) else str(first)

    # 价格
    regular_price = listing_data.get("regular_price") or listing_data.get("price")

    row = (
        await db.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.sku == sku,
            )
        )
    ).scalar_one_or_none()

    wc_id = wc_result.get("woocommerce_id")
    base_meta = {
        "woocommerce_id": wc_id,
        "woocommerce_permalink": wc_result.get("permalink"),
        "regular_price": str(regular_price) if regular_price is not None else None,
        "localizations": {"en": {
            "title": name,
            "description": listing_data.get("description", ""),
            "short_description": listing_data.get("short_description", ""),
            "status": "approved",
        }},
    }

    if row is None:
        row = Product(
            workspace_id=workspace_id,
            sku=sku,
            name=name,
            description=(listing_data.get("description") or "")[:2000] or None,
            category=category,
            status=local_status,
            source=source,
            source_url=source_url or None,
            tags=tags,
            target_market="US",
            meta=base_meta,
            deleted_at=None,
        )
        db.add(row)
        await db.flush()
        created = True
    else:
        row.name = name
        if listing_data.get("description"):
            row.description = listing_data["description"][:2000]
        if category:
            row.category = category
        row.status = local_status
        row.tags = tags
        # 复活软删行
        row.deleted_at = None
        merged_meta = {**(row.meta or {}), **base_meta}
        row.meta = merged_meta
        if source_url:
            row.source_url = source_url
        created = False

    await db.commit()
    await db.refresh(row)
    logger.info(
        "Upserted local product sku=%s wc_id=%s created=%s",
        sku, wc_id, created,
    )
    return {"product_id": str(row.id), "created": created}


# ============================================
# 1688 商品一键导入
# ============================================


# ---------------------------------------------------------------------------
# 1688 抓取结果缓存（BUG-20）
#
# 牛顿 Agent 单次抓取实测 53s/114s/174s/208s，超过入口网关（Cloudflare）约 100s
# 的请求上限，浏览器会收到 499、连接被掐断，但后端仍在继续执行。为让操作者能够
# 重试成功，这里按 1688 商品 ID 缓存抓取结果：首次调用可能超时，重复导入秒回。
# 幂等重试路径，符合 AGENTS.md 2.4「所有外部调用必须有超时、重试（幂等接口）、
# 熔断与降级」。
# ---------------------------------------------------------------------------
_IMPORT_CACHE_PREFIX = "nuotao:1688-fetch:"
_IMPORT_CACHE_TTL_SECONDS = 3600
_IMPORT_CACHE_TTL_SPARSE = 300  # 稀疏结果短 TTL：让下一次导入重新抽取

_cache_redis: Any = None


def _get_cache_redis() -> Any:
    """惰性单例：避免每次调用都新建一条 Redis 连接。不可用时返回 None（缓存降级为关闭）。"""
    global _cache_redis
    if _cache_redis is None:
        try:
            from app.core.redis import create_redis_client

            _cache_redis = create_redis_client()
        except Exception as exc:  # Redis 不可用不应阻断导入
            logger.warning("1688 import cache: Redis unavailable: %s", exc)
            _cache_redis = False
    return _cache_redis or None


def _import_cache_key(url_or_id: str) -> str:
    pid = parse_1688_url(url_or_id) or str(url_or_id).strip()
    return f"{_IMPORT_CACHE_PREFIX}{pid}"


def _extract_richness(info: dict[str, Any]) -> int:
    """结果丰富度：属性条数 + 是否带重量 + 是否带尺寸。用于在多次抽取间择优。"""
    if not isinstance(info, dict):
        return -1
    attrs = info.get("attributes") or []
    score = len(attrs) if isinstance(attrs, list) else 0
    if str(info.get("weight") or "").strip():
        score += 2
    if str(info.get("dimensions") or "").strip():
        score += 2
    return score


def _is_sparse_fetch(result: dict[str, Any]) -> bool:
    """牛顿返回成功但没有属性表、重量和尺寸：视为稀疏，值得重试一次。"""
    info = ((result or {}).get("data") or {}).get("product_info") or {}
    return (
        (not (info.get("attributes") or []))
        and not str(info.get("weight") or "").strip()
        and not str(info.get("dimensions") or "").strip()
    )

async def _cached_fetch_1688_product(url_or_id: str) -> dict[str, Any]:
    """带 Redis 幂等缓存的 1688 商品抓取。命中时附带 from_cache 标记。"""
    import json  # 本模块未顶层导入 json

    key = _import_cache_key(url_or_id)
    redis = _get_cache_redis()
    if redis is not None:
        try:
            raw = await redis.get(key)
            if raw:
                cached = json.loads(raw)
                cached["from_cache"] = True
                logger.info("1688 import cache hit: %s", key)
                return cached
        except Exception as exc:
            logger.warning("1688 import cache read failed for %s: %s", key, exc)

    # ROUND-4F: 牛顿是 LLM Agent，属性表提取不稳定（同一 offer 实测 23 条 / 0 条 / 0 条）。
    # 稀疏结果重试一次并保留较丰富者；稀疏结果用短 TTL，避免把单薄数据缓存一小时。
    result = await asyncio.to_thread(_fetch_1688_product, url_or_id)
    if _is_sparse_fetch(result):
        logger.info("1688 fetch sparse (no attributes/weight/dims), retrying once")
        retry = await asyncio.to_thread(_fetch_1688_product, url_or_id)
        first_info = ((result.get("data") or {}).get("product_info") or {})
        retry_info = ((retry.get("data") or {}).get("product_info") or {})
        if _extract_richness(retry_info) > _extract_richness(first_info):
            retry["merged_from_retry"] = True
            result = retry

    ttl = _IMPORT_CACHE_TTL_SECONDS if not _is_sparse_fetch(result) else _IMPORT_CACHE_TTL_SPARSE
    if redis is not None:
        try:
            await redis.set(
                key,
                json.dumps(result, ensure_ascii=False, default=str),
                ex=ttl,
            )
        except Exception as exc:
            logger.warning("1688 import cache write failed for %s: %s", key, exc)
    return result


def parse_1688_url(url: str) -> str:
    """
    从1688商品URL中提取商品ID

    支持的URL格式：
    - https://detail.1688.com/offer/123456789.html
    - https://detail.1688.com/offer/123456789.html?spm=...
    - 123456789（直接输入商品ID）

    Args:
        url: 1688商品URL或商品ID

    Returns:
        商品ID
    """
    import re

    # 如果是纯数字，直接返回
    if url.isdigit():
        return url

    # 从URL中提取offer ID
    # 匹配 /offer/数字.html 或 offerId=数字
    patterns = [
        r'/offer/(\d+)\.html',
        r'offerId=(\d+)',
        r'offer/(\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError(f"无法从URL中提取1688商品ID: {url}")


def convert_1688_to_pipeline_input(
    product_detail: dict[str, Any],
    source_url: str = "",
    source_id: str = "",
) -> dict[str, Any]:
    """
    将1688商品详情转换为产品工作流输入格式

    Args:
        product_detail: 1688商品详情（来自sourcing_1688_service.get_product_detail）
        source_url: 1688商品链接
        source_id: 1688商品ID

    Returns:
        产品工作流输入格式的商品信息
    """
    product = product_detail.get("product", {}) if product_detail.get("success") else {}

    # 提取商品名称
    name = product.get("subject", product.get("title", "未命名商品"))

    # 提取价格（优先保留完整价格区间）
    # 价格：只保留纯数值。1688 常返回 "¥20" 或 "6.7-19.7" 区间字符串，
    # 直接带入 number 输入框会造成解析失败；区间取最低价（采购成本口径）。
    raw_price = str(product.get("price", "")).strip()
    if not raw_price:
        price_info = product.get("price_range") or product.get("priceRange") or []
        if isinstance(price_info, list) and price_info:
            first_price = price_info[0]
            raw_price = (
                str(first_price.get("price", ""))
                if isinstance(first_price, dict)
                else str(first_price)
            )
    parsed_price = _parse_decimal(raw_price)
    price = str(parsed_price) if parsed_price is not None else ""

    # 提取描述
    description = product.get("description", "")
    if not description:
        description = product.get("detail", "")

    # 提取核心卖点（从标题和属性中提取）
    core_selling_points = []
    attributes = product.get("attributes", [])
    if isinstance(attributes, list):
        for attr in attributes[:5]:
            if isinstance(attr, dict):
                attr_name = attr.get("name") or attr.get("attributeName") or ""
                attr_value = attr.get("value", "")
                if attr_name and attr_value:
                    core_selling_points.append(f"{attr_name}: {attr_value}")

    # 提取材质
    materials = []
    for attr in attributes if isinstance(attributes, list) else []:
        if isinstance(attr, dict):
            attr_name = (
                attr.get("name") or attr.get("attributeName") or ""
            ).lower()
            if "材质" in attr_name or "material" in attr_name:
                materials.append(attr.get("value", ""))

    # 提取尺寸（ROUND-4C: 优先包装尺寸——运费按外包装计费；
    # 产品规格 47x47x90 与包装 92x16x16 差约 20 倍）
    dimensions = ""
    pack = {}
    for attr in attributes if isinstance(attributes, list) else []:
        if isinstance(attr, dict):
            attr_name_raw = str(
                attr.get("name") or attr.get("attributeName") or ""
            )
            attr_name = attr_name_raw.lower()
            for axis in ("长", "宽", "高"):
                if attr_name.startswith("包装" + axis):
                    pack[axis] = str(attr.get("value", "")).strip()
    if all(pack.get(a) for a in ("长", "宽", "高")):
        dimensions = f"{pack['长']}*{pack['宽']}*{pack['高']}"
    if not dimensions:
        for attr in attributes if isinstance(attributes, list) else []:
            if isinstance(attr, dict):
                attr_name = (
                    attr.get("name") or attr.get("attributeName") or ""
                ).lower()
                if "尺寸" in attr_name or "dimension" in attr_name or "规格" in attr_name:
                    dimensions = attr.get("value", "")
                    break

    # 提取重量（ROUND-4C: 单位在属性名里，如「重量(g)」。
    # 只取 value 会把 1800 g 当成 1800 kg，运费错一千倍；标准统一 kg）
    weight = ""
    for attr in attributes if isinstance(attributes, list) else []:
        if isinstance(attr, dict):
            attr_name_raw = str(
                attr.get("name") or attr.get("attributeName") or ""
            )
            attr_name = attr_name_raw.lower()
            if "重量" in attr_name or "weight" in attr_name:
                unit_match = re.search(r"[(（]([^)）]{1,6})[)）]", attr_name_raw)
                unit_hint = unit_match.group(1).strip() if unit_match else ""
                raw_value = str(attr.get("value", ""))
                # ROUND-4D: 值本身已带单位时不要重复追加
                if unit_hint and not re.search(
                    r"\d\s*" + re.escape(unit_hint), raw_value, re.I
                ):
                    weight = f"{raw_value} {unit_hint}".strip()
                else:
                    weight = raw_value
                break

    # 提取商品图片
    images = product.get("images", [])
    if not images:
        images = product.get("imageUrls", [])
    if isinstance(images, list):
        image_urls = [
            (
                img.get("url")
                or img.get("imageUrl")
                or img.get("urls")
                or ""
            )
            if isinstance(img, dict)
            else str(img)
            for img in images
            if img
        ]
    else:
        image_urls = []

    # 提取类目
    category = (
        product.get("category_name")
        or product.get("categoryName")
        or product.get("category")
        or ""
    )

    # 提取SKU信息
    sku_info = product.get("sku_list") or product.get("skuInfos") or []
    if isinstance(sku_info, list) and sku_info:
        first_sku = sku_info[0] if isinstance(sku_info[0], dict) else {}
        sku = first_sku.get("skuCode", first_sku.get("skuId", ""))
    else:
        sku = ""

    # 如果没有SKU，生成一个
    if not sku:
        sku = _generate_sku(name)

    return {
        "name": name,
        "category": str(category),
        "price": price,
        "description": str(description),
        "core_selling_points": core_selling_points[:5],
        "target_audience": "",
        "usage_scenarios": [],
        "product_features": core_selling_points[:5],
        "materials": materials,
        "dimensions": str(dimensions),
        "weight": str(weight),
        "source_url": source_url,
        "source_id": source_id,
        "sku": sku,
        "images": image_urls[:10],  # 最多10张图片
        "attributes": attributes,  # ROUND-4A: 保留原始属性表供 listing_gate 消费
        "supplier": product.get("supplier") or {
            "company_name": product.get("company_name", ""),
            "login_id": product.get("supplier_login_id", ""),
        },
    }


def _fetch_1688_product(url_or_id: str) -> dict[str, Any]:
    """1688 商品抓取与格式转换（Step 1-3），同步阻塞实现。

    开放平台与牛顿 Agent 都是同步 HTTP 调用，QA 实测单次可达 42s，因此整段
    必须放到线程池执行，不能直接在事件循环里调用，否则会拖垮所有并发请求。
    """
    import_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        # Step 1: 解析URL提取商品ID
        product_id = parse_1688_url(url_or_id)
        logger.info("1688 import %s: parsed product_id=%s", import_id, product_id)

        # Step 2: 优先使用牛顿 Agent 读取商品（1688 官方 API 权限不足）
        from app.services.newton_agent_service import (
            extract_1688_product,
            is_configured as newton_is_configured,
        )

        data_source = "unknown"
        product_detail = None

        if newton_is_configured():
            logger.info(
                "1688 import %s: using Newton Agent to fetch product",
                import_id,
            )
            product_detail = extract_1688_product(url_or_id, product_id)
            data_source = product_detail.get("source", "newton_agent")

        # 牛顿 Agent 失败时，降级到 1688 官方 API
        if not product_detail or not product_detail.get("success"):
            logger.info(
                "1688 import %s: Newton Agent failed, fallback to open API",
                import_id,
            )
            from app.services.sourcing_1688_service import get_product_detail
            product_detail = get_product_detail(product_id)
            data_source = product_detail.get("source", "1688_open_api")
            if product_detail.get("error"):
                logger.warning(
                    "1688 import %s: open API error: %s",
                    import_id,
                    product_detail.get("error"),
                )

        open_api_error = product_detail.get("error")
        
        if (
            not product_detail.get("success")
            or product_detail.get("source") == "mock"
        ):
            error_msg = (
                product_detail.get("error")
                or "未获得真实 1688 商品数据，已拒绝使用示例数据"
            )
            if open_api_error:
                error_msg = f"{error_msg}（开放平台：{open_api_error}）"
            logger.error("1688 import %s: get product detail failed: %s", import_id, error_msg)
            return {
                "success": False,
                "error": error_msg,
                "data": {
                    "import_id": import_id,
                    "product_id": product_id,
                    "source_url": url_or_id,
                    "data_source": data_source,
                },
            }

        # Step 3: 转换为产品工作流输入格式
        product_info = convert_1688_to_pipeline_input(
            product_detail,
            source_url=url_or_id,
            source_id=product_id,
        )

        logger.info("1688 import %s: converted product info: name=%s, sku=%s, images=%d",
                    import_id, product_info.get("name"), product_info.get("sku"),
                    len(product_info.get("images", [])))

        return {
            "success": True,
            "data": {
                "import_id": import_id,
                "product_id": product_id,
                "source_url": url_or_id,
                "data_source": data_source or "unknown",
                "product_info": product_info,
                "elapsed_time_seconds": round(time.time() - start_time, 2),
            },
            "error": None,
        }

    except ValueError as e:
        logger.error("1688 import %s: URL parse error: %s", import_id, str(e))
        return {
            "success": False,
            "error": f"URL解析失败: {str(e)}",
            "data": {"import_id": import_id, "source_url": url_or_id},
        }
    except Exception as e:
        logger.error("1688 import %s: unexpected error: %s", import_id, str(e))
        return {
            "success": False,
            "error": str(e),
            "data": {"import_id": import_id, "source_url": url_or_id},
        }


async def import_from_1688(
    url_or_id: str,
    *,
    auto_run_pipeline: bool = False,
    auto_list: bool = False,
    session: AsyncSession | None = None,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    从1688商品URL或ID一键导入商品信息

    流程：
    1. 解析URL提取商品ID
    2. 优先调用1688开放平台，未授权或无铺货关系时降级到牛顿 Agent
    3. 转换为产品工作流输入格式
    4. 可选：自动运行工作流（含 V3.0 选品闸门）
    5. 可选：自动上架WooCommerce

    Args:
        url_or_id: 1688商品URL或商品ID
        auto_run_pipeline: 是否自动运行完整工作流
        auto_list: 是否自动上架（仅在auto_run_pipeline=True时生效）
        session: 数据库会话。传入时工作流执行 V3.0 选品闸门；为 None 时闸门跳过
        workspace_id: 工作空间 ID，闸门落库使用
        trace_id: 全链路追踪 ID

    Returns:
        导入结果，包含商品信息和可选的工作流结果
    """
    logger.info("1688 import started: url=%s, auto_run=%s, auto_list=%s",
                url_or_id, auto_run_pipeline, auto_list)

    # Step 1-3：阻塞抓取放线程池，避免卡死事件循环
    # ROUND-4E: 牛顿抓取可能超过入口网关超时导致客户端 499，缓存供幂等重试
    result = await _cached_fetch_1688_product(url_or_id)
    if not result.get("success") or not auto_run_pipeline:
        return result

    # Step 4: 自动运行完整工作流
    product_info = result["data"]["product_info"]
    logger.info("1688 import: auto running pipeline for %s", url_or_id)
    try:
        # run_pipeline 是协程：必须 await，否则 pipeline_result 会是协程对象，
        # 随后 .get() 直接 AttributeError，整条自动流转静默失效。
        pipeline_result = await run_pipeline(
            product_info=product_info,
            auto_list=auto_list,
            include_images=False,  # 图片生成需要额外时间，默认不自动生成
            session=session,
            workspace_id=workspace_id,
            trace_id=trace_id,
        )
    except Exception as e:  # 导入成功但流转失败：降级返回导入结果，不吞异常
        logger.error("1688 import: pipeline failed for %s: %s", url_or_id, str(e))
        result["data"]["pipeline_error"] = str(e)
        return result

    result["data"]["pipeline_result"] = pipeline_result
    result["data"]["pipeline_status"] = pipeline_result.get("data", {}).get("status", "unknown")

    logger.info("1688 import completed: success=True, pipeline_status=%s",
                result["data"]["pipeline_status"])
    return result


async def import_and_analyze_from_1688(
    url_or_id: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """
    导入单个 1688 商品并立即执行 AI 分析与产品报告。

    该函数用于管理端批量导入的逐条工作单元。阻塞的 1688 抓取已由
    ``import_from_1688`` 内部切换到线程执行，这里直接 await 即可，不会阻塞
    FastAPI 事件循环。
    """
    # import_from_1688 已是协程（内部自行把阻塞抓取放到线程池），这里直接
    # await；再用 to_thread 包装只会拿到未执行的协程对象，随后 .get() 崩溃。
    import_result = await import_from_1688(
        url_or_id,
        auto_run_pipeline=False,
        auto_list=False,
    )
    if not import_result.get("success"):
        return import_result

    product_info = import_result.get("data", {}).get("product_info", {})
    supplier = product_info.get("supplier")
    if isinstance(supplier, dict) and not product_info.get("supplier_name"):
        product_info["supplier_name"] = (
            supplier.get("company_name")
            or supplier.get("name")
            or supplier.get("member_id")
            or ""
        )

    try:
        analysis_result = await analyze_and_generate_report(
            product_info,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error("1688 import analysis failed for %s: %s", url_or_id, str(e))
        return {
            "success": False,
            "error": f"商品已导入，但 AI 分析失败: {e!s}",
            "data": {
                **import_result.get("data", {}),
                "product_info": product_info,
            },
        }

    return {
        "success": True,
        "data": {
            **import_result.get("data", {}),
            "product_info": product_info,
            "ai_recognition": analysis_result["data"]["ai_recognition"],
            "product_report": analysis_result["data"]["product_report"],
            "analysis_metadata": analysis_result["data"].get("metadata", {}),
        },
        "error": None,
    }
