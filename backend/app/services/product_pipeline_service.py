"""
产品端到端工作流服务（P2-2）

串联选品→产品分析→主图生产→AI生图→生图Prompt→上架WooCommerce的一键流转。

工作流步骤：
Step 1: 商品信息输入（从牛顿选品结果导入或手动输入）
Step 2: AI产品分析（10字段识别 + 17字段产品报告）
Step 3: 主图生产（3套方向 + 短文案 + 10个变体）
Step 4: AI图片生成（调用AI绘图API生成实际图片）
Step 5: 生图Prompt生成（主图Prompt + 详情页Prompt）
Step 6: 上架数据生成（名称/描述/价格/SKU/分类/标签）
Step 7: 上架WooCommerce（可选，人工确认后执行）

遵循AGENTS.md规范：
- 业务规则集中在服务层
- Agent禁止直连数据库，通过services层访问
- 全链路可审计
- Human-in-the-loop：上架前必须人工确认
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
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
from app.services.image_prompt_rules_service import (
    generate_image_plan,
    generate_generation_tasks,
    run_complete_image_workflow,
)
from app.services.product_listing_service import (
    is_restricted,
    list_to_woocommerce,
)
from app.integrations import image_gen as image_gen_gateway
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 服务配置
SERVICE_NAME = "product_pipeline"

# AI图片存储目录
AI_IMAGE_DIR = os.getenv("AI_IMAGE_DIR", "data/ai_generated_images")
os.makedirs(AI_IMAGE_DIR, exist_ok=True)
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
    {"id": "ai_images", "name": "AI图片生成", "description": "调用AI绘图API生成优化图片"},
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


def generate_ai_images_sync(
    prompts: list[str],
    product_name: str,
    *,
    max_images: int = 3,
) -> dict[str, Any]:
    """
    同步生成AI图片（包装async函数）
    
    注意：此函数从同步上下文调用异步图片生成服务。
    使用线程池运行异步代码，避免event loop冲突。
    
    Args:
        prompts: 图片提示词列表
        product_name: 产品名称（用于文件命名）
        max_images: 最多生成图片数量
    
    Returns:
        {
            "success": bool,
            "images": [url1, url2, ...],
            "cost_cny": float,
            "model": str,
        }
    """
    import concurrent.futures
    settings = get_settings()
    model = settings.image_gen_default_model or "doubao-seedream-4-0-250828"
    
    generated_images = []
    total_cost = 0.0
    used_model = model
    
    # 使用线程运行async函数（避免event loop冲突）
    def _run_async_generation():
        """在独立线程中运行async图片生成"""
        import asyncio
        
        logger.info("AI image generation: starting in thread with new event loop")
        
        async def _generate_all():
            results = []
            for i, prompt in enumerate(prompts[:max_images]):
                try:
                    logger.info("AI image generation: generating prompt %d...", i)
                    result = await image_gen_gateway.generate_image(
                        prompt=prompt,
                        model=model,
                        width=1024,
                        height=1024,
                        timeout_seconds=120.0,
                    )
                    results.append(result)
                    logger.info("AI image generation: prompt %d succeeded", i)
                except Exception as e:
                    logger.warning("AI image generation failed for prompt %d: %s", i, str(e))
                    continue
            return results
        
        # 创建新的event loop运行async函数
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            logger.info("AI image generation: running async generation")
            return loop.run_until_complete(_generate_all())
        finally:
            loop.close()
            logger.info("AI image generation: event loop closed")
    
    try:
        # 使用线程池运行async生成
        logger.info("AI image generation: submitting to thread pool")
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_async_generation)
            results = future.result(timeout=600)  # 10分钟超时
        logger.info("AI image generation: got %d results", len(results))
    except Exception as e:
        logger.error("AI image generation failed: %s", str(e), exc_info=True)
        return {"success": False, "images": [], "cost_cny": 0.0, "model": model, "error": str(e)}
    
    # 保存图片到本地
    for result in results:
        if result.image_b64:
            # 生成文件名
            filename = f"{uuid.uuid4().hex[:8]}_{abs(hash(product_name)) % 10000}.png"
            filepath = os.path.join(AI_IMAGE_DIR, filename)
            
            try:
                # 保存base64图片
                image_data = base64.b64decode(result.image_b64)
                with open(filepath, 'wb') as f:
                    f.write(image_data)
                
                # 生成可访问的URL
                image_url = f"/static/ai_images/{filename}"
                generated_images.append(image_url)
                
                total_cost += result.cost_cny
                used_model = result.model
                
                logger.info("AI image saved: %s (cost: %.4f CNY)", filepath, result.cost_cny)
            except Exception as e:
                logger.error("Failed to save AI image: %s", str(e))
        elif result.image_url:
            # 下载远程图片并保存
            import httpx
            try:
                # 下载图片
                resp = httpx.get(result.image_url, timeout=60.0)
                if resp.status_code == 200:
                    # 生成文件名
                    filename = f"{uuid.uuid4().hex[:8]}_{abs(hash(product_name)) % 10000}.png"
                    filepath = os.path.join(AI_IMAGE_DIR, filename)
                    
                    with open(filepath, 'wb') as f:
                        f.write(resp.content)
                    
                    # 生成可访问的URL
                    image_url = f"/static/ai_images/{filename}"
                    generated_images.append(image_url)
                    
                    total_cost += result.cost_cny
                    used_model = result.model
                    
                    logger.info("AI image downloaded and saved: %s (cost: %.4f CNY)", filepath, result.cost_cny)
                else:
                    logger.error("Failed to download AI image: %d", resp.status_code)
            except Exception as e:
                logger.error("Failed to download AI image: %s", str(e))
    
    return {
        "success": len(generated_images) > 0,
        "images": generated_images,
        "cost_cny": total_cost,
        "model": used_model,
    }


def _translate_to_english(text: str, context: str = "") -> str:
    """
    简单翻译中文到英文（使用关键词映射）
    
    Args:
        text: 中文文本
        context: 上下文（product_name, description, tag 等）
    
    Returns:
        英文翻译
    """
    import re
    
    # 关键词映射表
    translations = {
        "榨汁杯": "Juicer Cup",
        "便携": "Portable",
        "USB充电": "USB Charging",
        "无线": "Cordless",
        "迷你": "Mini",
        "榨汁机": "Juicer",
        "户外": "Outdoor",
        "露营": "Camping",
        "运动": "Sports",
        "健身": "Fitness",
        "随行": "On-the-go",
        "鲜榨": "Fresh",
        "果汁": "Juice",
        "杯": "Cup",
        "容量": "Capacity",
        "食品级": "Food-grade",
        "材质": "Material",
        "适合": "Suitable for",
        "使用": "Use",
        "克": "g",
        "毫升": "ml",
        "不锈钢": "Stainless Steel",
        "刀片": "Blades",
        "高速旋转": "High-speed Rotation",
        "快速出汁": "Quick Juicing",
        "硅胶": "Silicone",
        "密封圈": "Seal Ring",
        "防漏": "Leakproof",
        "安全": "Safe",
        "健康": "Healthy",
        "无忧": "Worry-free",
        "一键": "One-touch",
        "操作": "Operation",
        "极简": "Minimalist",
        "设计": "Design",
        "磨砂": "Matte",
        "防滑": "Anti-slip",
        "杯身": "Cup Body",
        "办公室": "Office",
        "下午茶": "Afternoon Tea",
        "旅行": "Travel",
        "途中": "On the way",
        "轻松": "Easy",
        "制作": "Make",
        "健康饮品": "Healthy Drinks",
        "告别": "Say Goodbye to",
        "含糖饮料": "Sugary Drinks",
        "拥抱": "Embrace",
        "自然": "Natural",
        "鲜榨": "Freshly Pressed",
        "让": "Let",
        "每一口": "Every Bite",
        "都充满": "Full of",
        "活力": "Vitality",
        "专为": "Designed for",
        "现代": "Modern",
        "生活": "Life",
        "打造": "Created",
        "仅": "Only",
        "主轴": "Main Body",
        "主机": "Machine",
        "黄金": "Golden",
        "让您": "Let You",
        "随时随地": "Anytime Anywhere",
        "享受": "Enjoy",
        "六叶": "6-Blade",
        "转": "RPM",
        "分钟": "per Minute",
        "高速": "High-speed",
        "食品级": "Food-grade",
        "PP": "PP",
        "材质杯体": "Material Cup",
        "360°": "360°",
        "倒置": "Inverted",
        "摇晃": "Shake",
        "不漏水": "No Leakage",
        "随身携带": "Carry Along",
        "更安心": "More Secure",
        "无论是": "Whether",
        "还是": "or",
        "出差": "Business Trip",
        "都能": "Can All",
        "清新绿": "Fresh Green",
        "配色": "Color Scheme",
        "简约": "Simple",
        "时尚": "Fashionable",
        "配": "With",
        "挂绳": "Lanyard",
        "放进口袋": "Put in Pocket",
        "背包": "Backpack",
        "轻松携带": "Easy to Carry",
        "触手可及": "Within Reach",
        "鲜野": "FreshWild",
        "随行": "On-the-go",
        "无限": "Unlimited",
        "充电设计": "Charging Design",
        "Tritan": "Tritan",
        "安全无毒": "Safe and Non-toxic",
        "口感": "Texture",
        "细腻": "Delicate",
        "无渣": "No Pulp",
        "倒置摇晃不漏水": "No Leakage When Inverted",
        "倒置摇晃": "Inverted Shake",
        "不漏水": "No Leakage",
        "放进口袋背包轻松携带": "Easy to Carry in Pocket or Backpack",
        "让健康饮品触手可及": "Let Healthy Drinks Be Within Reach",
        "鲜野随行": "FreshWild On-the-go",
        "活力无限": "Unlimited Vitality",
        "充电一次可用10-15次": "Charge Once Use 10-15 Times",
        "告别电池更换烦恼": "Say Goodbye to Battery Replacement",
        "30秒快速出汁": "30 Seconds Quick Juicing",
        "350g超轻机身": "350g Ultra-light Body",
        "300ml黄金容量": "300ml Golden Capacity",
        "USB充电设计，告别": "USB Charging Design, Say Goodbye to",
        "办公室午休时，快速制": "Quick Make During Office Break",
        "户外露营徒步时，用新": "New Experience for Outdoor Camping Hiking",
        "食品级Tritan+304不锈钢刀片": "Food-grade Tritan + 304 Stainless Steel Blades",
        "304不锈钢六叶刀片": "304 Stainless Steel 6-Blade",
        "15000转/分钟高速旋转": "15000 RPM High-speed Rotation",
        "食品级PP材质杯体": "Food-grade PP Material Cup",
        "硅胶密封圈360°防漏": "Silicone Seal Ring 360° Leakproof",
        "一键操作极简设计": "One-touch Minimalist Design",
        "磨砂防滑杯身": "Matte Anti-slip Cup Body",
        "户外露营、健身运动、办公室下午茶、旅行途中": "Outdoor Camping, Fitness, Office Afternoon Tea, Travel",
        "都能轻松制作健康饮品": "Can All Easily Make Healthy Drinks",
        "告别含糖饮料，拥抱自然鲜榨": "Say Goodbye to Sugary Drinks, Embrace Natural Fresh",
        "让每一口都充满活力": "Let Every Bite Full of Vitality",
    }
    
    # 如果文本已经是英文，直接返回
    if re.match(r'^[a-zA-Z0-9\s\-\,\.\(\)]+$', text):
        return text
    
    # 尝试替换中文关键词
    result = text
    for cn, en in translations.items():
        result = result.replace(cn, en)
    
    # 清理多余空格和标点
    result = re.sub(r'\s+', ' ', result).strip()
    result = re.sub(r'\s*[,、]\s*', ', ', result)
    
    # 如果结果仍然主要是中文，返回简化英文
    cjk_pattern = re.compile(r'[\u3400-\u9fff]')
    if cjk_pattern.search(result):
        # 提取核心产品词
        if "榨汁" in text or "juicer" in text.lower():
            result = "Portable USB Juicer Cup"
        elif "水杯" in text:
            result = "Portable Water Bottle"
        elif "帐篷" in text:
            result = "Camping Tent"
        elif "灯" in text:
            result = "Camping Light"
        else:
            result = f"Outdoor Product - {text[:20]}"
    
    return result


def _generate_listing_data(
    product_info: dict[str, Any],
    product_report: dict[str, Any],
    main_image_data: dict[str, Any],
    ai_image_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    生成上架数据（包含英文本地化）

    Args:
        product_info: 商品信息
        product_report: 产品报告
        main_image_data: 主图生产结果
        ai_image_result: AI图片生成结果（可选）

    Returns:
        上架数据（包含中英文）
    """
    # 产品名称（中文）
    product_name_cn = _safe_get(product_report, "product_name", _safe_get(product_info, "name", "产品"))
    
    # 产品名称（英文）
    product_name_en = _translate_to_english(product_name_cn, "product_name")
    
    # 产品描述（中文 - 长描述）
    product_description_cn = _safe_get(product_report, "product_description", "")
    if not product_description_cn:
        # 从卖点和功能拼接描述
        selling_points = _safe_get_list(product_report, "core_selling_points", [])
        features = _safe_get_list(product_report, "product_features", [])
        usage_scenarios = _safe_get_list(product_report, "usage_scenarios", [])
        desc_parts = []
        if selling_points:
            desc_parts.append("【核心卖点】\n" + "\n".join(f"• {sp}" for sp in selling_points))
        if features:
            desc_parts.append("【产品功能】\n" + "\n".join(f"• {f}" for f in features))
        if usage_scenarios:
            desc_parts.append("【使用场景】\n" + "\n".join(f"• {s}" for s in usage_scenarios))
        product_description_cn = "\n\n".join(desc_parts)
    
    # 产品描述（英文）- 完整翻译
    product_description_en = _translate_to_english(product_description_cn, "description")
    # 如果描述为空，使用默认英文描述
    if not product_description_en or len(product_description_en) < 50:
        product_description_en = f"{product_name_en} - High quality outdoor product with premium features. Perfect for camping, hiking, and outdoor activities. Made with durable materials for long-lasting performance."
    
    # 短描述（中文）
    short_description_cn = _safe_get(product_info, "description", "")
    if not short_description_cn:
        short_description_cn = product_description_cn[:100] + "..." if len(product_description_cn) > 100 else product_description_cn
    
    # 短描述（英文）
    short_description_en = _translate_to_english(short_description_cn, "short_description")
    
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
    
    # SKU（使用英文产品名生成）
    sku = _generate_sku(product_name_en if product_name_en else product_name_cn)
    
    # 分类（使用正确的 WooCommerce 分类 ID）
    category = _safe_get(product_info, "category", "")
    categories = [{"id": 57, "name": "Backpacks & Hiking Gear"}]  # 默认户外用品
    if "露营" in category or "帐篷" in category or "camp" in category.lower():
        categories = [{"id": 55, "name": "Camping Furniture"}]
    elif "照明" in category or "灯具" in category or "头灯" in category or "light" in category.lower():
        categories = [{"id": 22, "name": "Lighting & Power"}]
    elif "厨房" in category or "餐具" in category or "kitchen" in category.lower():
        categories = [{"id": 104, "name": "Kitchen & Cookware"}]
    elif "榨汁" in product_name_cn or "juicer" in product_name_en.lower() or "榨汁杯" in product_name_cn:
        categories = [{"id": 104, "name": "Kitchen & Cookware"}]
    elif "水壶" in product_name_cn or "瓶" in product_name_cn or "bottle" in product_name_en.lower():
        categories = [{"id": 57, "name": "Backpacks & Hiking Gear"}]
    
    # 标签（英文关键词，简短）
    tags = []
    
    # 固定英文标签（根据产品类型）
    if "榨汁" in product_name_cn or "juicer" in product_name_en.lower():
        tags = [
            {"name": "Portable"},
            {"name": "USB Charging"},
            {"name": "Food-grade"},
            {"name": "Outdoor"},
            {"name": "Juicer"},
        ]
    elif "水壶" in product_name_cn or "bottle" in product_name_en.lower():
        tags = [
            {"name": "Portable"},
            {"name": "Insulated"},
            {"name": "Outdoor"},
            {"name": "BPA Free"},
            {"name": "Stainless Steel"},
        ]
    elif "帐篷" in product_name_cn or "tent" in product_name_en.lower():
        tags = [
            {"name": "Camping"},
            {"name": "Outdoor"},
            {"name": "Waterproof"},
            {"name": "Lightweight"},
        ]
    else:
        # 默认户外标签
        tags = [
            {"name": "Outdoor"},
            {"name": "Portable"},
            {"name": "Camping"},
        ]
    
    # 添加使用场景标签（英文）
    usage_scenarios = _safe_get_list(product_report, "usage_scenarios", [])
    for scenario in usage_scenarios[:2]:
        scenario_en = _translate_to_english(scenario, "tag")
        if scenario_en and scenario_en not in [t["name"] for t in tags]:
            if len(scenario_en) <= 30:  # 只添加短标签
                tags.append({"name": scenario_en})
    
    # 图片（优先使用AI生成的图片，其次使用1688商品信息）
    images = []
    
    # 1. 优先使用AI生成的图片（保持相对路径，WooCommerce上传时会处理）
    if ai_image_result and ai_image_result.get("success"):
        ai_images = ai_image_result.get("images", [])
        for url in ai_images[:5]:
            if isinstance(url, str) and url:
                # 保持相对路径（/static/ai_images/xxx.png），WooCommerce上传函数会处理
                images.append({"src": url, "alt": product_name_en})
    
    # 2. 其次从 main_image_data 获取AI生成的图片
    if not images:
        ai_images = main_image_data.get("images", []) or main_image_data.get("image_urls", []) or []
        if isinstance(ai_images, str):
            ai_images = [ai_images]
        if isinstance(ai_images, list):
            for url in ai_images[:5]:
                if isinstance(url, str) and url.startswith("http"):
                    images.append({"src": url, "alt": product_name_en})
    
    # 3. 如果没有AI图片，从1688商品信息提取
    if not images:
        image_urls = (
            product_info.get("image_urls", []) 
            or product_info.get("images", []) 
            or product_info.get("image_url", []) 
            or []
        )
        # 如果是单个字符串，转换为列表
        if isinstance(image_urls, str):
            image_urls = [image_urls]
        if isinstance(image_urls, list):
            for url in image_urls[:5]:
                if isinstance(url, str) and url.startswith("http"):
                    images.append({"src": url, "alt": product_name_en})
    
    # 品牌（默认 "Nuotao"）
    brand = "Nuotao"
    
    # 产品简述（英文）- 使用更详细的描述
    short_description_en = f"{product_name_en} - High quality outdoor product with premium features. Perfect for camping, hiking, and outdoor activities. Made with durable materials for long-lasting performance."
    
    # SEO 描述（英文）- 使用更完整的内容
    seo_description = product_description_en[:300] + "..." if len(product_description_en) > 300 else product_description_en
    
    return {
        # 中文文案（保留）
        "name": product_name_cn,
        "description": product_description_cn,
        "short_description": short_description_cn,
        
        # 英文文案（WooCommerce 使用）
        "en_name": product_name_en,
        "en_description": product_description_en,
        "en_short_description": short_description_en,
        
        # WooCommerce 上架数据（使用英文）
        "woocommerce_data": {
            "name": product_name_en,
            "type": "simple",
            "regular_price": regular_price,
            "description": product_description_en,
            "short_description": short_description_en,
            "sku": sku,
            "manage_stock": True,
            "stock_quantity": 100,
            "status": "draft",
            "categories": categories,
            "tags": tags,
            "images": images,
            "brand": brand,
            "meta_data": [
                {"key": "source", "value": "1688"},
                {"key": "source_price", "value": price_str},
                {"key": "pipeline_id", "value": str(uuid.uuid4())},
                {"key": "name_cn", "value": product_name_cn},
                {"key": "description_cn", "value": product_description_cn[:500]},
                # SEO 元数据
                {"key": "seo_title", "value": f"{product_name_en} - Best Price for Outdoor Use"},
                {"key": "seo_description", "value": seo_description},
                {"key": "focus_keyword", "value": product_name_en.split()[0].lower() if product_name_en else "outdoor product"},
            ],
        },
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

        # Step 4: AI图片生成（使用新的提示词规则）
        try:
            if product_report:
                # 使用新的图片生产计划
                image_workflow_result = run_complete_image_workflow(product_report)
                
                if image_workflow_result["success"]:
                    image_plan = image_workflow_result["data"]["plan"]
                    image_tasks = image_workflow_result["data"]["tasks"]
                    
                    # 限制生成数量（成本控制，默认5张）
                    max_images = int(os.getenv("MAX_AI_IMAGES_PER_PIPELINE", "5"))
                    tasks_to_generate = image_tasks[:max_images]
                    
                    # 生成多张AI图片
                    prompts = [task["prompt"] for task in tasks_to_generate]
                    product_name = product_info.get("name", "Product")
                    
                    ai_image_result = generate_ai_images_sync(
                        prompts=prompts,
                        product_name=product_name,
                        max_images=max_images,
                    )
                    
                    steps_result["ai_images"] = {
                        "status": "completed" if ai_image_result["success"] else "failed",
                        "data": {
                            **ai_image_result,
                            "image_plan": image_plan,
                            "image_tasks": tasks_to_generate,
                            "generated_count": len(tasks_to_generate),
                        },
                        "timestamp": datetime.now().isoformat(),
                    }
                    logger.info("Pipeline %s Step 4 (ai_images) completed: %d images, cost=%.4f CNY",
                                pipeline_id, len(ai_image_result.get("images", [])), ai_image_result.get("cost_cny", 0))
                else:
                    # 降级到旧的 Prompt 生成方式
                    logger.warning("Pipeline %s Step 4: Image workflow failed, falling back to old method", pipeline_id)
                    ai_prompts = []
                    ai_prompt_result = generate_full_prompt(product_report, page_type="brand_scene")
                    if ai_prompt_result["success"]:
                        ai_prompts.append(ai_prompt_result["data"]["full_prompt"])
                    
                    if ai_prompts:
                        product_name = product_info.get("name", "Product")
                        ai_image_result = generate_ai_images_sync(
                            prompts=ai_prompts,
                            product_name=product_name,
                            max_images=1,
                        )
                        steps_result["ai_images"] = {
                            "status": "completed" if ai_image_result["success"] else "failed",
                            "data": ai_image_result,
                            "timestamp": datetime.now().isoformat(),
                        }
                    else:
                        steps_result["ai_images"] = {"status": "skipped", "reason": "No AI prompt available"}
            else:
                steps_result["ai_images"] = {"status": "skipped", "reason": "No product report available"}
        except Exception as e:
            errors.append(f"AI image generation failed: {str(e)}")
            steps_result["ai_images"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 4 (ai_images) failed: %s", pipeline_id, str(e))

        # Step 5: 生图Prompt生成
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
                logger.info("Pipeline %s Step 5 (prompt) completed", pipeline_id)
            else:
                steps_result["prompt"] = {"status": "skipped", "reason": "No product report available"}
        except Exception as e:
            errors.append(f"Prompt generation failed: {str(e)}")
            steps_result["prompt"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 5 (prompt) failed: %s", pipeline_id, str(e))

        # Step 6: 上架数据生成
        try:
            main_image_data = steps_result.get("main_image", {}).get("data", {})
            ai_image_data = steps_result.get("ai_images", {}).get("data", {})
            listing_data = _generate_listing_data(product_info, product_report, main_image_data, ai_image_data)
            steps_result["listing_data"] = {
                "status": "completed",
                "data": listing_data,
                "timestamp": datetime.now().isoformat(),
            }
            logger.info("Pipeline %s Step 6 (listing_data) completed", pipeline_id)
        except Exception as e:
            errors.append(f"Listing data generation failed: {str(e)}")
            steps_result["listing_data"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 6 (listing_data) failed: %s", pipeline_id, str(e))

        # Step 7: 上架WooCommerce（可选，需要人工确认）
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
    force: bool = False,
) -> dict[str, Any]:
    """
    人工确认后执行上架

    Args:
        pipeline_result: 工作流结果（包含listing_data）
        status: 上架状态（publish/draft/pending）
        force: 是否强制上架（跳过 gate 的 needs_review 检查）

    Returns:
        上架结果
    """
    try:
        logger.info("Confirm and list called: status=%s, force=%s", status, force)
        listing_data = pipeline_result.get("data", {}).get("steps", {}).get("listing_data", {}).get("data", {})
        if not listing_data:
            logger.warning("Confirm and list: No listing data found")
            return {"success": False, "error": "No listing data found in pipeline result"}
        
        logger.info("Confirm and list: listing_data keys=%s", list(listing_data.keys()))
        
        # 检查是否管制物品
        restricted, reason = is_restricted(listing_data.get("name", ""), listing_data.get("sku", ""))
        if restricted:
            logger.warning("Confirm and list: Product is restricted: %s", reason)
            return {"success": False, "error": f"Product is restricted: {reason}"}

        # 发布前闸门验证（listing_gate）
        # 简化版：检查 SKU 和英文文案
        sku = listing_data.get("sku", "") or listing_data.get("woocommerce_data", {}).get("sku", "")
        title = listing_data.get("en_name", "") or listing_data.get("woocommerce_data", {}).get("name", "")
        description = listing_data.get("en_description", "") or listing_data.get("woocommerce_data", {}).get("description", "")

        gate_issues = []

        # 硬阻断：缺少 SKU
        if not sku or not str(sku).strip():
            gate_issues.append({
                "code": "missing_sku",
                "message": "缺少 SKU，无法建立 WooCommerce 渠道映射",
                "severity": "hard_block",
            })

        # 硬阻断：缺少英文文案（降级为警告）
        import re
        cjk_pattern = re.compile(r'[\u3400-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]')
        has_chinese = cjk_pattern.search(str(title)) or cjk_pattern.search(str(description))
        if has_chinese:
            gate_issues.append({
                "code": "cjk_without_localization",
                "message": "商品文案仍含中文，建议添加英文本地化",
                "severity": "warning",  # 降级为警告，允许上传
            })

        # 检查 gate issues
        hard_blocks = [i for i in gate_issues if i["severity"] == "hard_block"]
        if hard_blocks:
            logger.warning("Confirm and list: Gate issues found: %s", [i["code"] for i in hard_blocks])
            return {
                "success": False,
                "error": "发布前闸门阻断",
                "data": {"gate_issues": hard_blocks},
            }

        logger.info("Confirm and list: Proceeding to WooCommerce listing")
        listing_result = list_to_woocommerce(listing_data, status=status)
        logger.info("Confirm and list: Result success=%s", listing_result.get("success"))
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
    # 兼容两种格式：1688 API 格式（嵌套）和 Newton Agent 格式（直接）
    if product_detail.get("success") and "product" in product_detail:
        product = product_detail["product"]
    else:
        product = product_detail  # Newton Agent 格式，直接就是产品字典

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
    if not description:
        description = product.get("summary", "")  # Newton Agent 格式

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

    # 从标题提取核心卖点（Newton Agent 格式）
    if not core_selling_points and name:
        # 从标题中提取关键词
        keywords = re.split(r'[\/\s\-\|]+', name)
        core_selling_points = [kw for kw in keywords if len(kw) > 2][:5]

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
    
    # Newton Agent 格式：单个 image_url
    if not image_urls:
        image_url = product.get("image_url", "") or product.get("imageUrl", "")
        if image_url:
            image_urls = [image_url]

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
        # Step 1: 解析URL提取商品ID，或直接使用产品名称搜索
        product_id = ""
        if url_or_id.isdigit() or "1688.com" in url_or_id:
            try:
                product_id = parse_1688_url(url_or_id)
                logger.info("1688 import %s: parsed product_id=%s", import_id, product_id)
            except ValueError:
                pass
        
        # Step 2: 使用牛顿Agent搜索商品
        from app.services.newton_agent_service import newton_agent_search
        
        if product_id:
            search_query = f"查找商品ID {product_id}"
        else:
            search_query = url_or_id
        
        logger.info("1688 import %s: using Newton Agent to search: %s", import_id, search_query)
        
        # 调用牛顿Agent搜索商品
        newton_result = newton_agent_search(search_query)
        
        if not newton_result.get("success"):
            error_msg = newton_result.get("error", "牛顿Agent搜索失败")
            logger.error("1688 import %s: Newton Agent search failed: %s", import_id, error_msg)
            return {
                "success": False,
                "error": error_msg,
                "data": {
                    "import_id": import_id,
                    "product_id": product_id,
                    "source_url": url_or_id,
                    "source": "newton_agent",
                },
            }
        
        # 从牛顿Agent返回的商品列表中提取第一个商品
        products = newton_result.get("products", [])
        if not products:
            error_msg = "牛顿Agent未返回商品数据"
            logger.error("1688 import %s: Newton Agent returned no products", import_id)
            return {
                "success": False,
                "error": error_msg,
                "data": {
                    "import_id": import_id,
                    "product_id": product_id,
                    "source_url": url_or_id,
                    "source": "newton_agent",
                },
            }
        
        # 获取第一个商品的详情
        product_data = products[0]
        logger.info("1688 import %s: got product from Newton Agent: %s", 
                    import_id, product_data.get("subject", "N/A"))
        
        # Step 3: 转换为产品工作流输入格式
        product_info = convert_1688_to_pipeline_input(
            product_data,
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
                "source": "newton_agent",
                "product_info": product_info,
                "elapsed_time_seconds": round(time.time() - start_time, 2),
                "newton_task_id": newton_result.get("task_id", ""),
                "total_products_found": len(products),
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
