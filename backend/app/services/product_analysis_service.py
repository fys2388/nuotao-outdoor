"""
AI产品分析服务（P0-1）

基于1688商品信息，AI自动分析产品，输出：
1. AI识别结果（10字段）：品牌、类目、外观、材质、卖点、场景、人群、风格、色调、延展页面
2. 产品信息报告（17字段）：品牌名称、产品名称、产品类别、产品尺寸、材质工艺、产品颜色、
   产品容量、适用对象、核心卖点、产品功能、目标人群、使用场景、视觉风格、主色调、可延展页面

参考流程：STEP 01 让AI读懂产品 → STEP 02 产品信息报告

遵循AGENTS.md规范：
- 业务规则集中在服务层
- Agent禁止直连数据库，通过services层访问
- 全链路可审计
- LLM调用走llm_gateway（禁止业务代码直连单一模型供应商）
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.llm_gateway import LLMError, LLMRequest, complete, parse_json_content

logger = logging.getLogger(__name__)

# 服务配置
AGENT_ID = "product_analyst"
AGENT_NAME = "Product Analyst"
TRIGGER = "api:product_analysis:analyze"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 2000

# AI识别结果输出Schema（10字段）
AI_RECOGNITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "brand_name": {"type": "string", "description": "品牌名称/Logo"},
        "product_category": {"type": "string", "description": "产品类目"},
        "product_appearance": {"type": "string", "description": "产品外观描述（形状、颜色、结构）"},
        "material_texture": {"type": "string", "description": "材质质感（如ABS塑料、不锈钢、食品级硅胶等）"},
        "core_selling_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "核心卖点列表（3-5个）",
        },
        "usage_scenarios": {
            "type": "array",
            "items": {"type": "string"},
            "description": "适用场景列表（如客厅、卧室、户外、办公室等）",
        },
        "target_audience": {"type": "string", "description": "目标人群描述"},
        "visual_style": {"type": "string", "description": "视觉风格（如极简、高端、温馨、科技感等）"},
        "primary_colors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "主色调列表（如米白、浅咖、暖灰等）",
        },
        "extendable_page_types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "可延展页面类型（如主视觉、卖点展示、结构展示、场景展示、细节特写等）",
        },
    },
    "required": [
        "brand_name", "product_category", "product_appearance", "material_texture",
        "core_selling_points", "usage_scenarios", "target_audience", "visual_style",
        "primary_colors", "extendable_page_types",
    ],
}

# 产品信息报告输出Schema（17字段）
PRODUCT_REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "brand_name": {"type": "string", "description": "品牌名称"},
        "product_name": {"type": "string", "description": "产品名称"},
        "product_category": {"type": "string", "description": "产品类别"},
        "product_dimensions": {"type": "string", "description": "产品尺寸（如约19.5cm直径×16.3cm高）"},
        "material_craft": {"type": "string", "description": "材质工艺（如ABS塑料/透明PC/食品级材质）"},
        "product_color": {"type": "string", "description": "产品颜色"},
        "product_capacity": {"type": "string", "description": "产品容量/规格"},
        "applicable_target": {"type": "string", "description": "适用对象"},
        "core_selling_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "核心卖点列表",
        },
        "product_features": {
            "type": "array",
            "items": {"type": "string"},
            "description": "产品功能列表",
        },
        "target_audience": {"type": "string", "description": "目标人群"},
        "usage_scenarios": {
            "type": "array",
            "items": {"type": "string"},
            "description": "使用场景列表",
        },
        "visual_style": {"type": "string", "description": "视觉风格"},
        "primary_colors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "主色调列表",
        },
        "extendable_pages": {
            "type": "array",
            "items": {"type": "string"},
            "description": "可延展页面列表",
        },
        "product_description": {"type": "string", "description": "产品详细描述（200字以内）"},
        "quality_assurance": {"type": "string", "description": "品质保障说明"},
    },
    "required": [
        "brand_name", "product_name", "product_category", "product_dimensions",
        "material_craft", "product_color", "product_capacity", "applicable_target",
        "core_selling_points", "product_features", "target_audience", "usage_scenarios",
        "visual_style", "primary_colors", "extendable_pages", "product_description",
        "quality_assurance",
    ],
}


class ProductAnalysisError(Exception):
    """产品分析失败异常"""


def get_product_analysis_status() -> dict[str, Any]:
    """获取产品分析服务状态"""
    return {
        "service": "product_analysis",
        "status": "operational",
        "agent_id": AGENT_ID,
        "agent_name": AGENT_NAME,
        "ai_recognition_fields": list(AI_RECOGNITION_SCHEMA["properties"].keys()),
        "product_report_fields": list(PRODUCT_REPORT_SCHEMA["properties"].keys()),
        "default_temperature": DEFAULT_TEMPERATURE,
        "default_max_tokens": DEFAULT_MAX_TOKENS,
    }


def _build_analysis_prompt(product_info: dict[str, Any]) -> str:
    """构建产品分析Prompt"""
    product_name = product_info.get("name", "未知产品")
    product_desc = product_info.get("description", "")
    product_price = product_info.get("price", "")
    product_category = product_info.get("category", "")
    product_images = product_info.get("images", [])
    supplier_name = product_info.get("supplier_name", "")
    additional_info = product_info.get("additional_info", "")

    image_desc = ""
    if product_images:
        image_desc = f"\n产品图片URL（供参考）: {', '.join(product_images[:3])}"

    prompt = f"""你是一位专业的电商产品分析师。请根据以下1688商品信息，全面分析这个产品，并输出结构化的JSON结果。

## 产品信息
- 产品名称: {product_name}
- 产品类目: {product_category or '未知'}
- 产品价格: {product_price or '未知'}
- 供应商: {supplier_name or '未知'}
- 产品描述: {product_desc or '无'}
{image_desc}
{additional_info}

## 分析要求
请分析以下10个维度，并输出JSON：
1. brand_name: 品牌名称/Logo（如果没有明确品牌，根据产品风格推测一个合适的品牌定位）
2. product_category: 产品类目（具体到细分品类）
3. product_appearance: 产品外观描述（形状、颜色、结构、设计特点）
4. material_texture: 材质质感（推测主要材质和质感）
5. core_selling_points: 核心卖点列表（3-5个，每个一句话）
6. usage_scenarios: 适用场景列表（3-5个具体场景）
7. target_audience: 目标人群描述（具体到人群画像）
8. visual_style: 视觉风格（如极简、高端、温馨、科技感、户外风等）
9. primary_colors: 主色调列表（2-3个颜色描述）
10. extendable_page_types: 可延展页面类型列表（3-5个，如主视觉、卖点展示、结构展示、场景展示、细节特写、对比图、FAQ等）

## 输出要求
- 只输出JSON对象，不要输出任何其他文字
- 所有字段必须填写，不要留空
- 卖点、场景、颜色等使用数组格式
- 分析要专业、具体、有商业价值
"""
    return prompt


def _build_report_prompt(product_info: dict[str, Any], ai_recognition: dict[str, Any] | None = None) -> str:
    """构建产品信息报告Prompt"""
    product_name = product_info.get("name", "未知产品")
    product_desc = product_info.get("description", "")
    product_price = product_info.get("price", "")
    product_category = product_info.get("category", "")
    supplier_name = product_info.get("supplier_name", "")

    recognition_context = ""
    if ai_recognition:
        recognition_context = f"""
## AI初步识别结果（供参考，请在此基础上深化和完善）
{json.dumps(ai_recognition, ensure_ascii=False, indent=2)}
"""

    prompt = f"""你是一位专业的电商产品策划师。请根据以下1688商品信息和AI初步识别结果，生成一份完整的产品信息报告，用于后续的电商详情页设计和生图提示词生成。

## 产品信息
- 产品名称: {product_name}
- 产品类目: {product_category or '未知'}
- 产品价格: {product_price or '未知'}
- 供应商: {supplier_name or '未知'}
- 产品描述: {product_desc or '无'}
{recognition_context}

## 报告要求
请生成包含以下17个字段的产品信息报告，输出JSON：

1. brand_name: 品牌名称（如果没有明确品牌，根据产品风格和定位起一个合适的品牌名）
2. product_name: 产品名称（优化后的电商产品名，包含核心关键词）
3. product_category: 产品类别（具体到细分品类）
4. product_dimensions: 产品尺寸（推测合理尺寸，格式如"约Xcm×Ycm×Zcm"）
5. material_craft: 材质工艺（主要材质和工艺特点）
6. product_color: 产品颜色（主色调描述）
7. product_capacity: 产品容量/规格（如容量、重量、功率等规格参数）
8. applicable_target: 适用对象（适用人群/对象描述）
9. core_selling_points: 核心卖点列表（5-7个，每个一句话，要有吸引力）
10. product_features: 产品功能列表（5-7个具体功能点）
11. target_audience: 目标人群（具体人群画像，包括年龄、性别、消费能力、生活方式等）
12. usage_scenarios: 使用场景列表（4-6个具体使用场景）
13. visual_style: 视觉风格（详细描述视觉风格定位）
14. primary_colors: 主色调列表（3-4个颜色，用于详情页设计）
15. extendable_pages: 可延展页面列表（5-7个详情页板块类型，如品牌主视觉、核心卖点、结构展示、场景展示、细节特写、品质保障、FAQ等）
16. product_description: 产品详细描述（200字以内，吸引人的产品介绍）
17. quality_assurance: 品质保障说明（材质安全、耐用性、售后服务等）

## 输出要求
- 只输出JSON对象，不要输出任何其他文字
- 所有字段必须填写，不要留空
- 数组字段使用数组格式
- 报告要专业、具体、有商业价值，可直接用于电商详情页设计
- 尺寸、容量等参数如果无法确定，根据同类产品推测合理值
"""
    return prompt


async def analyze_product(
    product_info: dict[str, Any],
    *,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    AI产品分析（STEP 01）：输入1688商品信息，输出10字段AI识别结果

    Args:
        product_info: 1688商品信息（name, description, price, category, images, supplier_name等）
        temperature: LLM温度
        max_tokens: 最大token数
        trace_id: 追踪ID

    Returns:
        包含AI识别结果的字典
    """
    prompt = _build_analysis_prompt(product_info)

    request = LLMRequest(
        messages=[
            {"role": "system", "content": "你是一位专业的电商产品分析师，擅长从商品信息中提取关键商业信息。"},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format="json_object",
        task_type="product_analysis",
    )

    try:
        response = await complete(request, trace_id=trace_id)
        result = parse_json_content(response.content)

        return {
            "success": True,
            "data": {
                "ai_recognition": result,
                "product_name": product_info.get("name", ""),
                "analysis_metadata": {
                    "provider": response.provider,
                    "model": response.model,
                    "tokens": response.tokens,
                    "cost": str(response.cost),
                    "latency_ms": response.latency_ms,
                    "trace_id": response.trace_id,
                },
            },
            "error": None,
        }
    except LLMError as e:
        logger.error("Product analysis LLM error: %s", str(e))
        raise ProductAnalysisError(f"AI产品分析失败: {str(e)}") from e
    except Exception as e:
        logger.error("Product analysis unexpected error: %s", str(e))
        raise ProductAnalysisError(f"AI产品分析异常: {str(e)}") from e


async def generate_product_report(
    product_info: dict[str, Any],
    *,
    ai_recognition: dict[str, Any] | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    生成产品信息报告（STEP 02）：输入1688商品信息和AI识别结果，输出17字段产品信息报告

    Args:
        product_info: 1688商品信息
        ai_recognition: 可选的AI识别结果（如果已完成STEP 01）
        temperature: LLM温度
        max_tokens: 最大token数
        trace_id: 追踪ID

    Returns:
        包含产品信息报告的字典
    """
    prompt = _build_report_prompt(product_info, ai_recognition)

    request = LLMRequest(
        messages=[
            {"role": "system", "content": "你是一位专业的电商产品策划师，擅长生成高质量的产品信息报告，用于电商详情页设计。"},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format="json_object",
        task_type="product_report",
    )

    try:
        response = await complete(request, trace_id=trace_id)
        result = parse_json_content(response.content)

        return {
            "success": True,
            "data": {
                "product_report": result,
                "product_name": product_info.get("name", ""),
                "report_metadata": {
                    "provider": response.provider,
                    "model": response.model,
                    "tokens": response.tokens,
                    "cost": str(response.cost),
                    "latency_ms": response.latency_ms,
                    "trace_id": response.trace_id,
                },
            },
            "error": None,
        }
    except LLMError as e:
        logger.error("Product report LLM error: %s", str(e))
        raise ProductAnalysisError(f"产品信息报告生成失败: {str(e)}") from e
    except Exception as e:
        logger.error("Product report unexpected error: %s", str(e))
        raise ProductAnalysisError(f"产品信息报告生成异常: {str(e)}") from e


async def analyze_and_generate_report(
    product_info: dict[str, Any],
    *,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    一键完成产品分析+报告生成（STEP 01 + STEP 02）

    先进行AI产品分析（10字段），再基于分析结果生成产品信息报告（17字段）

    Args:
        product_info: 1688商品信息
        temperature: LLM温度
        max_tokens: 最大token数
        trace_id: 追踪ID

    Returns:
        包含AI识别结果和产品信息报告的字典
    """
    # STEP 01: AI产品分析
    analysis_result = await analyze_product(
        product_info,
        temperature=temperature,
        max_tokens=max_tokens,
        trace_id=trace_id,
    )
    ai_recognition = analysis_result["data"]["ai_recognition"]

    # STEP 02: 生成产品信息报告
    report_result = await generate_product_report(
        product_info,
        ai_recognition=ai_recognition,
        temperature=temperature,
        max_tokens=max_tokens,
        trace_id=trace_id,
    )

    return {
        "success": True,
        "data": {
            "ai_recognition": ai_recognition,
            "product_report": report_result["data"]["product_report"],
            "product_name": product_info.get("name", ""),
            "metadata": {
                "analysis": analysis_result["data"]["analysis_metadata"],
                "report": report_result["data"]["report_metadata"],
            },
        },
        "error": None,
    }
