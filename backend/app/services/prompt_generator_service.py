"""
Prompt自动生成引擎（P0-2）

基于产品信息报告（17字段），自动生成8部分完整的生图Prompt。

参考流程：STEP 03 根据产品信息报告生成生图提示词

8部分Prompt结构：
1. 产品主体（名称、外观、型号、主要特征）
2. 品牌风格（品牌调性、设计风格、参考竞品风格）
3. 画面场景（使用场景、环境氛围、生活方式）
4. 详情页类型（页面结构、板块内容、信息层级）
5. 色调光影（主色调、光影类型、氛围感受）
6. 构图比例（画面比例、构图方式、留白比例）
7. 视觉效果（画质要求、细节程度、真实感）
8. 禁止内容（不需要的元素、文字、风格等）

遵循AGENTS.md规范：
- 业务规则集中在服务层
- 纯模板填充，不需要LLM调用
- 输出结构化，可直接用于AI生图
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 服务配置
SERVICE_NAME = "prompt_generator"
SERVICE_VERSION = "1.0.0"

# 详情页类型配置
DETAIL_PAGE_TYPES: dict[str, dict[str, Any]] = {
    "brand_scene": {
        "name": "品牌场景页",
        "description": "产品+使用场景+主标题+核心卖点，详情页第1屏，吸引注意",
        "structure": "主标题 + 产品+使用场景大图 + 3-4个核心卖点图标",
    },
    "product_hero": {
        "name": "产品主视觉页",
        "description": "产品大图+产品名称+核心参数+品牌Logo，产品展示，建立认知",
        "structure": "产品名称 + 产品大图（多角度） + 核心参数 + 品牌Logo",
    },
    "feature_selling": {
        "name": "功能卖点页",
        "description": "功能标题+结构爆炸图/原理图+卖点说明，核心功能，说服购买",
        "structure": "功能标题 + 结构爆炸图/原理图 + 卖点说明（3-5个）",
    },
    "scene_showcase": {
        "name": "场景展示页",
        "description": "场景标题+3-4个使用场景图+风格标签，生活方式，情感共鸣",
        "structure": "场景标题 + 3-4个使用场景图 + 风格标签",
    },
    "detail_closeup": {
        "name": "细节特写页",
        "description": "细节标题+4-5个细节特写+品质标签，品质证明，消除顾虑",
        "structure": "细节标题 + 4-5个细节特写 + 品质标签",
    },
    "quality_assurance": {
        "name": "品质保障页",
        "description": "品质标题+材质/认证/售后说明+信任图标，建立信任",
        "structure": "品质标题 + 材质/认证/售后说明 + 信任图标",
    },
    "comparison": {
        "name": "对比图页",
        "description": "对比标题+使用前后对比/竞品对比+优势说明，突出优势",
        "structure": "对比标题 + 使用前后对比/竞品对比 + 优势说明",
    },
    "faq": {
        "name": "FAQ页",
        "description": "常见问题标题+问答列表+解答，消除购买疑虑",
        "structure": "常见问题标题 + 问答列表（5-8个）",
    },
}

# 默认详情页板块顺序
DEFAULT_PAGE_SECTIONS = [
    "brand_scene",
    "product_hero",
    "feature_selling",
    "scene_showcase",
    "detail_closeup",
    "quality_assurance",
]


def get_prompt_generator_status() -> dict[str, Any]:
    """获取Prompt生成器状态"""
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "status": "operational",
        "prompt_structure": [
            "product_subject",
            "brand_style",
            "scene",
            "detail_page_type",
            "color_light",
            "composition",
            "visual_effect",
            "forbidden_content",
        ],
        "supported_page_types": list(DETAIL_PAGE_TYPES.keys()),
        "default_page_sections": DEFAULT_PAGE_SECTIONS,
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


def generate_product_subject_prompt(product_report: dict[str, Any]) -> str:
    """生成第1部分：产品主体"""
    product_name = _safe_get(product_report, "product_name", "产品")
    product_appearance = _safe_get(product_report, "product_appearance", "")
    material_craft = _safe_get(product_report, "material_craft", "")
    product_color = _safe_get(product_report, "product_color", "")
    product_dimensions = _safe_get(product_report, "product_dimensions", "")
    product_capacity = _safe_get(product_report, "product_capacity", "")
    core_selling_points = _safe_get(product_report, "core_selling_points", "")

    prompt = f"""【产品主体】
产品名称：{product_name}
产品外观：{product_appearance or '简洁现代的设计风格'}
材质工艺：{material_craft or '高品质材质，精致工艺'}
产品颜色：{product_color or '主色调'}
产品尺寸：{product_dimensions or '适中尺寸'}
产品规格：{product_capacity or '标准规格'}
核心卖点：{core_selling_points or '高品质、实用、美观'}

要求：产品外观、结构、比例、Logo保持一致，不要改变产品造型。产品要清晰可见，占据画面主要位置，细节丰富，质感真实。"""

    return prompt


def generate_brand_style_prompt(product_report: dict[str, Any]) -> str:
    """生成第2部分：品牌风格"""
    brand_name = _safe_get(product_report, "brand_name", "Nuotao Outdoor")
    visual_style = _safe_get(product_report, "visual_style", "")
    primary_colors = _safe_get(product_report, "primary_colors", "")
    target_audience = _safe_get(product_report, "target_audience", "")

    prompt = f"""【品牌风格】
品牌名称：{brand_name}
品牌调性：{visual_style or '高端、极简、科技感、温馨舒适'}
设计风格：参考国际户外品牌风格，简约大气，有品质感
整体色调：以{primary_colors or '米白、浅咖、暖灰'}为主，干净、柔和、有质感
目标人群：{target_audience or '注重生活品质的消费者'}

要求：整体风格统一，品牌调性一致，视觉高级感强，符合目标人群审美。不要使用过于花哨、廉价、低质的设计风格。"""

    return prompt


def generate_scene_prompt(product_report: dict[str, Any]) -> str:
    """生成第3部分：画面场景"""
    usage_scenarios = _safe_get(product_report, "usage_scenarios", "")
    applicable_target = _safe_get(product_report, "applicable_target", "")
    product_description = _safe_get(product_report, "product_description", "")

    prompt = f"""【画面场景】
使用场景：{usage_scenarios or '家庭、户外、办公室等多种场景'}
适用对象：{applicable_target or '广泛适用'}
产品描述：{product_description or '高品质实用产品'}

要求：画面要营造真实的使用场景氛围，环境自然舒适，有生活气息。产品在场景中自然融入，不突兀。光线自然柔和，有层次感和空间感。可以适当展示使用状态，但不要出现人物面部特写。"""

    return prompt


def generate_detail_page_type_prompt(
    product_report: dict[str, Any],
    page_type: str = "brand_scene",
    custom_sections: list[str] | None = None,
) -> str:
    """生成第4部分：详情页类型"""
    page_config = DETAIL_PAGE_TYPES.get(page_type, DETAIL_PAGE_TYPES["brand_scene"])
    extendable_pages = _safe_get_list(product_report, "extendable_pages", DEFAULT_PAGE_SECTIONS)

    # 如果指定了自定义板块，使用自定义；否则使用产品报告中的可延展页面
    sections = custom_sections or extendable_pages
    sections_desc = ""
    for i, section in enumerate(sections, 1):
        section_config = DETAIL_PAGE_TYPES.get(section, {})
        section_name = section_config.get("name", section)
        section_desc = section_config.get("description", "")
        sections_desc += f"{i}. {section_name}：{section_desc}\n"

    prompt = f"""【详情页类型】
当前页面类型：{page_config['name']}
页面说明：{page_config['description']}
页面结构：{page_config['structure']}

完整详情页包含以下板块（按顺序）：
{sections_desc}
要求：信息层级清晰，重点突出，易于阅读。每个板块有明确的标题和内容，图文结合，排版美观。适合电商平台展示，信息层级清晰，易于阅读。"""

    return prompt


def generate_color_light_prompt(product_report: dict[str, Any]) -> str:
    """生成第5部分：色调光影"""
    primary_colors = _safe_get(product_report, "primary_colors", "")
    visual_style = _safe_get(product_report, "visual_style", "")

    prompt = f"""【色调光影】
主色调：{primary_colors or '米白、浅咖、暖灰'}
色调风格：{visual_style or '温暖、自然、高级'}
光影类型：自然光，柔和均匀，有层次感
氛围感受：温馨、舒适、有品质感、有呼吸感

要求：光线自然柔和，画面干净简约，有呼吸感。色调统一和谐，不要出现过于鲜艳、刺眼、杂乱的颜色。阴影自然，有立体感和空间感。"""

    return prompt


def generate_composition_prompt(
    product_report: dict[str, Any],
    aspect_ratio: str = "3:4",
) -> str:
    """生成第6部分：构图比例"""
    prompt = f"""【构图比例】
画面比例：{aspect_ratio} 竖版比例，适合电商详情页
构图方式：产品居中或偏左/右，留白适当，有呼吸感
留白比例：上下左右适当留白，不要填满整个画面
信息层级：标题在上，产品在中，卖点在下，层次清晰

要求：构图平衡稳定，产品突出，信息清晰。不要出现过于拥挤、杂乱、失衡的构图。有明确的视觉焦点和阅读引导。"""

    return prompt


def generate_visual_effect_prompt(product_report: dict[str, Any]) -> str:
    """生成第7部分：视觉效果"""
    prompt = f"""【视觉效果】
画质要求：4K高清，商业广告质感，真实细腻
细节程度：产品细节丰富，材质质感真实，纹理清晰
真实感：照片级真实感，光影自然，有立体感
整体风格：高端电商详情页风格，专业、精致、有品质感

要求：画面清晰锐利，细节丰富，质感真实。不要出现模糊、噪点、低质、失真的画面。整体视觉效果专业高级，符合电商大品牌标准。"""

    return prompt


def generate_forbidden_content_prompt(product_report: dict[str, Any]) -> str:
    """生成第8部分：禁止内容"""
    brand_name = _safe_get(product_report, "brand_name", "Nuotao Outdoor")

    prompt = f"""【禁止内容】
1. 不要改变产品结构、外观、比例，不要出现错别字，不要出现水印，不要出现{brand_name}以外的品牌Logo
2. 不要使用低质感、脏乱、过于花哨的背景
3. 不要出现人物面部特写，避免复杂的文字排版
4. 不要出现文字遮挡、信息重叠、排版混乱
5. 不要出现过于鲜艳、刺眼、不和谐的颜色
6. 不要出现模糊、噪点、失真、低质的画面
7. 不要出现违反广告法、虚假宣传、夸大其词的内容
8. 不要出现危险、不安全、不卫生的使用场景

要求：严格遵守以上禁止内容，确保生成的图片专业、合规、高质量。"""

    return prompt


def generate_full_prompt(
    product_report: dict[str, Any],
    *,
    page_type: str = "brand_scene",
    aspect_ratio: str = "3:4",
    custom_sections: list[str] | None = None,
    include_header: bool = True,
) -> dict[str, Any]:
    """
    生成完整的生图Prompt（8部分结构）

    Args:
        product_report: 产品信息报告（17字段）
        page_type: 详情页类型（brand_scene/product_hero/feature_selling/scene_showcase/detail_closeup/quality_assurance/comparison/faq）
        aspect_ratio: 画面比例（默认3:4竖版）
        custom_sections: 自定义详情页板块顺序
        include_header: 是否包含头部说明

    Returns:
        包含完整Prompt和各部分的字典
    """
    # 生成8个部分
    parts = {
        "product_subject": generate_product_subject_prompt(product_report),
        "brand_style": generate_brand_style_prompt(product_report),
        "scene": generate_scene_prompt(product_report),
        "detail_page_type": generate_detail_page_type_prompt(product_report, page_type, custom_sections),
        "color_light": generate_color_light_prompt(product_report),
        "composition": generate_composition_prompt(product_report, aspect_ratio),
        "visual_effect": generate_visual_effect_prompt(product_report),
        "forbidden_content": generate_forbidden_content_prompt(product_report),
    }

    # 拼接完整Prompt
    header = ""
    if include_header:
        product_name = _safe_get(product_report, "product_name", "产品")
        page_config = DETAIL_PAGE_TYPES.get(page_type, DETAIL_PAGE_TYPES["brand_scene"])
        header = f"""请基于上传的{product_name}产品图，生成一组高端电商品牌详情页。

产品外观、结构、比例、Logo保持一致，不要改变产品造型。

"""

    full_prompt = header + "\n\n".join(parts.values())

    return {
        "success": True,
        "data": {
            "full_prompt": full_prompt,
            "parts": parts,
            "metadata": {
                "product_name": _safe_get(product_report, "product_name", ""),
                "page_type": page_type,
                "page_type_name": page_config.get("name", page_type),
                "aspect_ratio": aspect_ratio,
                "prompt_length": len(full_prompt),
                "generator_version": SERVICE_VERSION,
            },
        },
        "error": None,
    }


def generate_batch_prompts(
    product_report: dict[str, Any],
    *,
    page_types: list[str] | None = None,
    aspect_ratio: str = "3:4",
) -> dict[str, Any]:
    """
    批量生成多种详情页类型的Prompt

    Args:
        product_report: 产品信息报告
        page_types: 要生成的页面类型列表（默认生成所有默认板块）
        aspect_ratio: 画面比例

    Returns:
        包含多个Prompt的字典
    """
    if page_types is None:
        page_types = DEFAULT_PAGE_SECTIONS

    prompts = {}
    for page_type in page_types:
        result = generate_full_prompt(
            product_report,
            page_type=page_type,
            aspect_ratio=aspect_ratio,
        )
        if result["success"]:
            prompts[page_type] = result["data"]

    return {
        "success": True,
        "data": {
            "prompts": prompts,
            "page_types": page_types,
            "count": len(prompts),
        },
        "error": None,
    }
