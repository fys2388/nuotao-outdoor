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

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from app.services.product_analysis_service import (
    analyze_and_generate_report,
    generate_product_report,
)
from app.services.prompt_generator_service import generate_full_prompt
from app.services.main_image_service import (
    generate_three_directions,
    generate_all_selling_point_copies,
    generate_variants,
    run_complete_workflow as run_main_image_workflow,
)
from app.services.product_listing_service import (
    is_restricted,
    list_to_woocommerce,
)

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
    {"id": "listing", "name": "上架WooCommerce", "description": "人工确认后上架到WooCommerce"},
]


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


def _generate_sku(product_name: str) -> str:
    """生成SKU"""
    import re
    # 移除特殊字符，取前10个字符
    clean = re.sub(r'[^\w\s-]', '', product_name)
    clean = re.sub(r'[-\s]+', '-', clean)
    clean = clean[:10].upper()
    # 添加时间戳后缀
    timestamp = datetime.now().strftime('%m%d%H%M')
    return f"NT-{clean}-{timestamp}"


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

    # 分类（默认户外用品分类ID=15，可根据类目调整）
    category = _safe_get(product_info, "category", "")
    categories = [{"id": 15}]  # 默认户外用品
    if "露营" in category or "帐篷" in category:
        categories = [{"id": 16}]  # 露营装备
    elif "照明" in category or "灯具" in category or "头灯" in category:
        categories = [{"id": 17}]  # 照明设备
    elif "厨房" in category or "餐具" in category:
        categories = [{"id": 18}]  # 户外厨房

    # 标签
    tags = []
    selling_points = _safe_get_list(product_report, "core_selling_points", [])
    for sp in selling_points[:3]:
        tags.append({"name": sp[:10]})
    usage_scenarios = _safe_get_list(product_report, "usage_scenarios", [])
    for scenario in usage_scenarios[:2]:
        tags.append({"name": scenario[:10]})

    # 图片（待生图后填充）
    images = []

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
        "meta_data": [
            {"key": "source", "value": "1688"},
            {"key": "source_price", "value": price_str},
            {"key": "pipeline_id", "value": str(uuid.uuid4())},
        ],
    }


async def run_pipeline(
    product_info: dict[str, Any],
    *,
    auto_list: bool = False,
    include_images: bool = False,
) -> dict[str, Any]:
    """
    运行完整的产品端到端工作流

    Args:
        product_info: 商品信息
        auto_list: 是否自动上架（默认False，需要人工确认）
        include_images: 是否包含图片生成（需要数据库session，默认False）

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
                steps_result["main_image"] = {
                    "status": "completed",
                    "data": main_image_result["data"],
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

        # Step 5: 上架数据生成
        try:
            main_image_data = steps_result.get("main_image", {}).get("data", {})
            listing_data = _generate_listing_data(product_info, product_report, main_image_data)
            steps_result["listing_data"] = {
                "status": "completed",
                "data": listing_data,
                "timestamp": datetime.now().isoformat(),
            }
            logger.info("Pipeline %s Step 5 (listing_data) completed", pipeline_id)
        except Exception as e:
            errors.append(f"Listing data generation failed: {str(e)}")
            steps_result["listing_data"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 5 (listing_data) failed: %s", pipeline_id, str(e))

        # Step 6: 上架WooCommerce（可选，需要人工确认）
        if auto_list:
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
                        logger.info("Pipeline %s Step 6 (listing) completed: WC ID=%s", pipeline_id, listing_result.get("woocommerce_id"))
                    else:
                        errors.append(f"Listing failed: {listing_result.get('error')}")
                        logger.error("Pipeline %s Step 6 (listing) failed: %s", pipeline_id, listing_result.get("error"))
            except Exception as e:
                errors.append(f"Listing failed: {str(e)}")
                steps_result["listing"] = {"status": "failed", "error": str(e)}
                logger.error("Pipeline %s Step 6 (listing) failed: %s", pipeline_id, str(e))
        else:
            steps_result["listing"] = {
                "status": "pending_confirmation",
                "message": "上架数据已生成，请人工确认后执行上架",
            }

        # 计算总体状态
        completed_steps = sum(1 for s in steps_result.values() if s.get("status") == "completed")
        total_steps = len(PIPELINE_STEPS)
        if errors:
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
            },
            "error": None if not errors else f"{len(errors)} errors occurred",
        }

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

        listing_result = list_to_woocommerce(listing_data, status=status)
        return listing_result

    except Exception as e:
        logger.error("Confirm and list error: %s", str(e))
        return {"success": False, "error": str(e)}


# ============================================
# 1688 商品一键导入
# ============================================


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

    # 提取价格
    price_info = product.get("priceRange", [])
    if price_info and isinstance(price_info, list):
        price = str(price_info[0].get("price", ""))
    else:
        price = str(product.get("price", ""))

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
                attr_name = attr.get("name", "")
                attr_value = attr.get("value", "")
                if attr_name and attr_value:
                    core_selling_points.append(f"{attr_name}: {attr_value}")

    # 提取材质
    materials = []
    for attr in attributes if isinstance(attributes, list) else []:
        if isinstance(attr, dict):
            attr_name = attr.get("name", "").lower()
            if "材质" in attr_name or "material" in attr_name:
                materials.append(attr.get("value", ""))

    # 提取尺寸
    dimensions = ""
    for attr in attributes if isinstance(attributes, list) else []:
        if isinstance(attr, dict):
            attr_name = attr.get("name", "").lower()
            if "尺寸" in attr_name or "dimension" in attr_name or "规格" in attr_name:
                dimensions = attr.get("value", "")
                break

    # 提取重量
    weight = ""
    for attr in attributes if isinstance(attributes, list) else []:
        if isinstance(attr, dict):
            attr_name = attr.get("name", "").lower()
            if "重量" in attr_name or "weight" in attr_name:
                weight = attr.get("value", "")
                break

    # 提取商品图片
    images = product.get("images", [])
    if not images:
        images = product.get("imageUrls", [])
    if isinstance(images, list):
        image_urls = [img.get("url", "") if isinstance(img, dict) else str(img) for img in images if img]
    else:
        image_urls = []

    # 提取类目
    category = product.get("categoryName", product.get("category", ""))

    # 提取SKU信息
    sku_info = product.get("skuInfos", [])
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
        "supplier": product.get("supplier", {}),
    }


def import_from_1688(
    url_or_id: str,
    *,
    auto_run_pipeline: bool = False,
    auto_list: bool = False,
) -> dict[str, Any]:
    """
    从1688商品URL或ID一键导入商品信息

    流程：
    1. 解析URL提取商品ID
    2. 调用1688 API获取商品详情
    3. 转换为产品工作流输入格式
    4. 可选：自动运行工作流
    5. 可选：自动上架WooCommerce

    Args:
        url_or_id: 1688商品URL或商品ID
        auto_run_pipeline: 是否自动运行完整工作流
        auto_list: 是否自动上架（仅在auto_run_pipeline=True时生效）

    Returns:
        导入结果，包含商品信息和可选的工作流结果
    """
    import_id = str(uuid.uuid4())
    start_time = time.time()

    logger.info("1688 import %s started: url=%s, auto_run=%s, auto_list=%s",
                import_id, url_or_id, auto_run_pipeline, auto_list)

    try:
        # Step 1: 解析URL提取商品ID
        product_id = parse_1688_url(url_or_id)
        logger.info("1688 import %s: parsed product_id=%s", import_id, product_id)

        # Step 2: 调用1688 API获取商品详情
        from app.services.sourcing_1688_service import get_product_detail
        product_detail = get_product_detail(product_id)

        if not product_detail.get("success"):
            error_msg = product_detail.get("error", "获取1688商品详情失败")
            logger.error("1688 import %s: get product detail failed: %s", import_id, error_msg)
            return {
                "success": False,
                "error": error_msg,
                "data": {
                    "import_id": import_id,
                    "product_id": product_id,
                    "source_url": url_or_id,
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

        result = {
            "success": True,
            "data": {
                "import_id": import_id,
                "product_id": product_id,
                "source_url": url_or_id,
                "product_info": product_info,
                "elapsed_time_seconds": round(time.time() - start_time, 2),
            },
            "error": None,
        }

        # Step 4: 可选 - 自动运行完整工作流
        if auto_run_pipeline:
            logger.info("1688 import %s: auto running pipeline", import_id)
            pipeline_result = run_pipeline(
                product_info=product_info,
                auto_list=auto_list,
                include_images=False,  # 图片生成需要额外时间，默认不自动生成
            )
            result["data"]["pipeline_result"] = pipeline_result
            result["data"]["pipeline_status"] = pipeline_result.get("data", {}).get("status", "unknown")

        logger.info("1688 import %s completed: success=True, elapsed=%.2fs",
                    import_id, time.time() - start_time)

        return result

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
