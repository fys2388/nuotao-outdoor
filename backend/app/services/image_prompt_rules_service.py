"""
AI 生图提示词规则服务（电商全自动制图流程）

基于"Codex电商全自动制图流程"文章总结的生图提示词规则，实现电商产品图端到端生产。

核心规则：
1. 6 类图片分类体系（主图/卖点/场景/细节/参数/对比）
2. Prompt 模板规范（4 部分：主体/画面/文字/禁止项）
3. 尺寸规范（符合电商平台要求）
4. 批量生成策略（1 主图 + 5 卖点 + 3 场景 + 5 细节）

遵循 AGENTS.md 规范：
- 业务规则集中在服务层
- 纯模板填充，不需要 LLM 调用
- 输出结构化，可直接用于 AI 生图
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# 服务配置
SERVICE_NAME = "image_prompt_rules"
SERVICE_VERSION = "2.0.0"

# ============ 6 类图片分类配置 ============

IMAGE_TYPES: dict[str, dict[str, Any]] = {
    "main_image": {
        "name": "主图",
        "description": "白底产品图，用于商品列表展示",
        "count": 1,
        "priority": 1,
        "background": "纯白色背景 (#FFFFFF)",
        "lighting": "均匀柔光，无明显阴影",
        "composition": "产品居中，占画面 60-70%",
        "props": "无道具",
        "text": "无文字",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "测试商品识别效率和搜索点击率",
    },
    "selling_point": {
        "name": "卖点图",
        "description": "突出核心卖点的信息图",
        "count": 5,
        "priority": 2,
        "background": "浅色渐变背景",
        "lighting": "均匀柔光",
        "composition": "图标 + 文字 + 产品，信息密度适中",
        "props": "卖点图标",
        "text": "10 字以内卖点文案",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "测试卖点传达效率和点击率",
    },
    "scene_image": {
        "name": "场景图",
        "description": "产品使用场景展示",
        "count": 3,
        "priority": 3,
        "background": "真实使用场景背景",
        "lighting": "自然光，有层次感",
        "composition": "产品融入场景，占画面 40-50%",
        "props": "场景相关道具",
        "text": "无文字或场景标签",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "测试场景代入感和用户想象力",
    },
    "detail_image": {
        "name": "细节图",
        "description": "产品材质、工艺、尺寸特写",
        "count": 5,
        "priority": 4,
        "background": "浅灰色背景",
        "lighting": "侧光，突出质感",
        "composition": "局部特写，放大细节",
        "props": "无道具",
        "text": "细节标注（可选）",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "测试品质传达和购买信任",
    },
    "parameter_image": {
        "name": "参数图",
        "description": "规格参数展示",
        "count": 1,
        "priority": 5,
        "background": "白色背景",
        "lighting": "均匀柔光",
        "composition": "产品 + 尺寸标注 + 参数表",
        "props": "尺寸线、参数图标",
        "text": "规格参数文字",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "测试信息传达效率",
    },
    "comparison_image": {
        "name": "对比图",
        "description": "竞品对比或使用前后对比",
        "count": 1,
        "priority": 6,
        "background": "白色背景，左右分割",
        "lighting": "均匀柔光",
        "composition": "左右对比，本产品突出",
        "props": "对比图标",
        "text": "对比标签",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "测试优势传达和购买决策",
    },
}

# ============ 卖点类型配置 ============

SELLING_POINT_TYPES: dict[str, dict[str, Any]] = {
    "portability": {
        "name": "便携卖点",
        "icons": ["🎒", "✈️", "🚶"],
        "templates": ["随身便携", "轻巧随行", "一手掌握"],
    },
    "capacity": {
        "name": "容量卖点",
        "icons": ["🥤", "📦", "💧"],
        "templates": ["大容量", "一杯满足", "足量更尽兴"],
    },
    "cleaning": {
        "name": "清洁卖点",
        "icons": ["🧼", "✨", "💦"],
        "templates": ["易拆易洗", "一冲即净", "清洁无忧"],
    },
    "scene": {
        "name": "场景卖点",
        "icons": ["🏢", "🏕️", "🏋️"],
        "templates": ["办公好搭档", "户外必备", "运动好伴侣"],
    },
    "quality": {
        "name": "品质卖点",
        "icons": ["⭐", "💎", "🏆"],
        "templates": ["品质之选", "精工细作", "耐用可靠"],
    },
    "function": {
        "name": "功能卖点",
        "icons": ["⚡", "🔌", "📱"],
        "templates": ["一键操作", "智能便捷", "多功能合一"],
    },
    "design": {
        "name": "设计卖点",
        "icons": ["🎨", "🌈", "✨"],
        "templates": ["简约美学", "颜值在线", "时尚设计"],
    },
    "price": {
        "name": "性价比卖点",
        "icons": ["💰", "🏷️", "🎉"],
        "templates": ["限时特惠", "超值性价比", "今日特价"],
    },
}

# ============ Prompt 模板配置 ============

PROMPT_TEMPLATES: dict[str, str] = {
    "main_image": """Professional product photography of {product_name}, {product_color} {product_type}. 
Pure white background, centered composition, product occupies 65% of frame. 
Even soft lighting, no shadows, no props, no text. 
Clean e-commerce style, 800x800px, high resolution, photorealistic.""",
    
    "selling_point": """E-commerce infographic of {product_name} featuring {selling_point} selling point. 
Light gradient background, product on left with icon and short text on right. 
Clean modern design, {selling_point_icon} icon, {copy_text} text. 
Minimalist style, 800x800px, high resolution, professional e-commerce design.""",
    
    "scene_image": """Lifestyle photography of {product_name} in {scene} setting. 
Natural ambient lighting, product naturally integrated into scene. 
Realistic environment with {props} props. 
Product occupies 45% of frame, warm and inviting atmosphere. 
800x800px, photorealistic, e-commerce product showcase.""",
    
    "detail_image": """Extreme close-up detail shot of {product_name} {detail_focus}. 
Light gray background, side lighting to highlight texture and quality. 
Sharp focus on material details, {detail_description}. 
Professional product photography, 800x800px, high resolution, quality showcase.""",
    
    "parameter_image": """Technical product image of {product_name} with dimensions and specifications. 
White background, product with size markings and parameter icons. 
Clean infographic style, {dimensions} size labels. 
Professional product documentation, 800x800px, high resolution.""",
    
    "comparison_image": """Side-by-side comparison image of {product_name} vs competitor product. 
White background with dividing line, our product on right highlighted. 
{comparison_point} comparison labels with checkmarks. 
Clear visual advantage, 800x800px, professional e-commerce comparison.""",
}

# ============ 检查项配置 ============

CHECKLIST_ITEMS: dict[str, list[str]] = {
    "product_check": [
        "商品外观是否与原图一致",
        "核心卖点是否准确表达",
        "是否出现非品牌 Logo",
        "商品比例是否正常",
    ],
    "chinese_check": [
        "文字是否清晰可读",
        "是否有错别字",
        "是否有乱码",
        "标语是否自然通顺",
        "字体是否统一",
    ],
    "compliance_check": [
        "是否使用绝对化用语",
        "是否有夸张功效承诺",
        "是否符合广告法",
        "是否有虚假宣传",
    ],
    "technical_check": [
        "图片分辨率是否达标",
        "背景是否干净",
        "光线是否均匀",
        "构图是否平衡",
    ],
}


def get_image_prompt_rules_status() -> dict[str, Any]:
    """获取服务状态"""
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "status": "operational",
        "image_types": list(IMAGE_TYPES.keys()),
        "selling_point_types": list(SELLING_POINT_TYPES.keys()),
        "prompt_templates": list(PROMPT_TEMPLATES.keys()),
        "checklist_categories": list(CHECKLIST_ITEMS.keys()),
        "total_image_count": sum(t["count"] for t in IMAGE_TYPES.values()),
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


def _sanitize_filename(name: str) -> str:
    """清理文件名"""
    sanitized = re.sub(r'[^\x00-\x7F]+', '', name)
    sanitized = re.sub(r'[^\w\s-]', '', sanitized)
    sanitized = re.sub(r'[-\s]+', '_', sanitized)
    return sanitized.lower() or 'product'


def generate_image_plan(product_info: dict[str, Any]) -> dict[str, Any]:
    """
    生成完整的图片生产计划
    
    基于商品信息，生成 6 类图片的生产计划和 Prompt
    
    Args:
        product_info: 商品信息（17 字段产品报告）
    
    Returns:
        完整的图片生产计划
    """
    product_name = _safe_get(product_info, "product_name", "Product")
    product_name_en = _safe_get(product_info, "product_name_en", product_name)
    product_type = _safe_get(product_info, "product_category", "Product")
    product_color = _safe_get(product_info, "product_color", "white")
    core_selling_points = _safe_get_list(product_info, "core_selling_points", ["High Quality", "Portable", "Durable"])
    usage_scenarios = _safe_get_list(product_info, "usage_scenarios", ["Home", "Outdoor", "Office"])
    material_craft = _safe_get(product_info, "material_craft", "High-quality materials")
    product_dimensions = _safe_get(product_info, "product_dimensions", "Standard size")
    product_capacity = _safe_get(product_info, "product_capacity", "Standard capacity")
    
    plan: dict[str, Any] = {
        "product_name": product_name,
        "product_name_en": product_name_en,
        "image_types": {},
        "total_images": 0,
        "estimated_cost": 0,
    }
    
    # 1. 主图 (1 张)
    main_prompt = PROMPT_TEMPLATES["main_image"].format(
        product_name=product_name_en,
        product_color=product_color,
        product_type=product_type,
    )
    plan["image_types"]["main_image"] = {
        "count": 1,
        "prompts": [main_prompt],
        "filenames": [f"product_{_sanitize_filename(product_name_en)}_main_01.png"],
        "status": "pending",
    }
    
    # 2. 卖点图 (5 张)
    selling_points_prompts = []
    selling_points_filenames = []
    for i, point in enumerate(core_selling_points[:5], 1):
        point_type = _match_selling_point_type(point)
        point_config = SELLING_POINT_TYPES.get(point_type, SELLING_POINT_TYPES["quality"])
        prompt = PROMPT_TEMPLATES["selling_point"].format(
            product_name=product_name_en,
            selling_point=point[:20],
            selling_point_icon=point_config["icons"][0],
            copy_text=point_config["templates"][0],
        )
        selling_points_prompts.append(prompt)
        selling_points_filenames.append(f"product_{_sanitize_filename(product_name_en)}_point_{i:02d}.png")
    
    plan["image_types"]["selling_point"] = {
        "count": len(selling_points_prompts),
        "prompts": selling_points_prompts,
        "filenames": selling_points_filenames,
        "selling_points": core_selling_points[:5],
        "status": "pending",
    }
    
    # 3. 场景图 (3 张)
    scene_prompts = []
    scene_filenames = []
    scene_props = {
        "Home": "home decor",
        "Outdoor": "camping equipment",
        "Office": "office supplies",
        "Travel": "travel accessories",
        "Gym": "fitness equipment",
    }
    for i, scene in enumerate(usage_scenarios[:3], 1):
        props = scene_props.get(scene, "relevant props")
        prompt = PROMPT_TEMPLATES["scene_image"].format(
            product_name=product_name_en,
            scene=scene.lower(),
            props=props,
        )
        scene_prompts.append(prompt)
        scene_filenames.append(f"product_{_sanitize_filename(product_name_en)}_scene_{i:02d}.png")
    
    plan["image_types"]["scene_image"] = {
        "count": len(scene_prompts),
        "prompts": scene_prompts,
        "filenames": scene_filenames,
        "scenes": usage_scenarios[:3],
        "status": "pending",
    }
    
    # 4. 细节图 (5 张)
    detail_foci = [
        "material texture",
        "craftsmanship details",
        "product structure",
        "size comparison",
        "usage demonstration",
    ]
    detail_prompts = []
    detail_filenames = []
    for i, focus in enumerate(detail_foci[:5], 1):
        prompt = PROMPT_TEMPLATES["detail_image"].format(
            product_name=product_name_en,
            detail_focus=focus,
            detail_description=material_craft[:50],
        )
        detail_prompts.append(prompt)
        detail_filenames.append(f"product_{_sanitize_filename(product_name_en)}_detail_{i:02d}.png")
    
    plan["image_types"]["detail_image"] = {
        "count": len(detail_prompts),
        "prompts": detail_prompts,
        "filenames": detail_filenames,
        "details": detail_foci[:5],
        "status": "pending",
    }
    
    # 5. 参数图 (1 张)
    parameter_prompt = PROMPT_TEMPLATES["parameter_image"].format(
        product_name=product_name_en,
        dimensions=product_dimensions[:30] if product_dimensions else "Standard dimensions",
    )
    plan["image_types"]["parameter_image"] = {
        "count": 1,
        "prompts": [parameter_prompt],
        "filenames": [f"product_{_sanitize_filename(product_name_en)}_parameter_01.png"],
        "status": "pending",
    }
    
    # 6. 对比图 (1 张)
    comparison_prompt = PROMPT_TEMPLATES["comparison_image"].format(
        product_name=product_name_en,
        comparison_point="Quality" if core_selling_points else "Features",
    )
    plan["image_types"]["comparison_image"] = {
        "count": 1,
        "prompts": [comparison_prompt],
        "filenames": [f"product_{_sanitize_filename(product_name_en)}_comparison_01.png"],
        "status": "pending",
    }
    
    # 计算总计
    plan["total_images"] = sum(t["count"] for t in plan["image_types"].values())
    plan["estimated_cost"] = round(plan["total_images"] * 0.1, 2)  # 假设每张图片 0.1 元
    
    return {
        "success": True,
        "data": plan,
        "error": None,
    }


def _match_selling_point_type(selling_point: str) -> str:
    """根据卖点文本匹配卖点类型"""
    point_lower = selling_point.lower()
    
    if any(kw in point_lower for kw in ["便携", "轻便", "portable", "light", "carry"]):
        return "portability"
    elif any(kw in point_lower for kw in ["容量", "大", "capacity", "large", "big"]):
        return "capacity"
    elif any(kw in point_lower for kw in ["清洗", "清洗", "clean", "wash", "easy"]):
        return "cleaning"
    elif any(kw in point_lower for kw in ["场景", "户外", "office", "camp", "travel"]):
        return "scene"
    elif any(kw in point_lower for kw in ["品质", "质量", "quality", "premium", "durable"]):
        return "quality"
    elif any(kw in point_lower for kw in ["功能", "智能", "function", "smart", "multi"]):
        return "function"
    elif any(kw in point_lower for kw in ["设计", "颜值", "design", "fashion", "style"]):
        return "design"
    elif any(kw in point_lower for kw in ["价格", "优惠", "price", "deal", "sale"]):
        return "price"
    
    return "quality"


def generate_generation_tasks(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """
    将图片计划转换为可执行的生图任务列表
    
    Args:
        plan: 图片生产计划
    
    Returns:
        生图任务列表
    """
    tasks = []
    
    for image_type, type_data in plan["image_types"].items():
        for i, prompt in enumerate(type_data["prompts"], 1):
            filename = type_data["filenames"][i - 1] if i - 1 < len(type_data["filenames"]) else f"image_{i:02d}.png"
            
            tasks.append({
                "id": f"{image_type}_{i:02d}",
                "image_type": image_type,
                "image_type_name": IMAGE_TYPES[image_type]["name"],
                "prompt": prompt,
                "filename": filename,
                "width": IMAGE_TYPES[image_type]["size"]["width"],
                "height": IMAGE_TYPES[image_type]["size"]["height"],
                "aspect_ratio": IMAGE_TYPES[image_type]["size"]["ratio"],
                "use_case": image_type,
                "priority": IMAGE_TYPES[image_type]["priority"],
                "status": "pending",
            })
    
    # 按优先级排序
    tasks.sort(key=lambda x: x["priority"])
    
    return tasks


def generate_execution_checklist(plan: dict[str, Any]) -> dict[str, Any]:
    """
    生成执行检查清单
    
    Args:
        plan: 图片生产计划
    
    Returns:
        执行检查清单
    """
    checklist = {
        "product_check": {
            "name": "商品检查",
            "items": CHECKLIST_ITEMS["product_check"],
            "status": "pending",
        },
        "chinese_check": {
            "name": "中文检查",
            "items": CHECKLIST_ITEMS["chinese_check"],
            "status": "pending",
        },
        "compliance_check": {
            "name": "合规检查",
            "items": CHECKLIST_ITEMS["compliance_check"],
            "status": "pending",
        },
        "technical_check": {
            "name": "技术检查",
            "items": CHECKLIST_ITEMS["technical_check"],
            "status": "pending",
        },
    }
    
    # 为每个图片类型生成检查项
    image_checklists = []
    for image_type, type_data in plan["image_types"].items():
        for i, filename in enumerate(type_data["filenames"], 1):
            image_checklists.append({
                "filename": filename,
                "image_type": IMAGE_TYPES[image_type]["name"],
                "checks": {cat: "pending" for cat in checklist.keys()},
            })
    
    return {
        "success": True,
        "data": {
            "checklist": checklist,
            "image_checklists": image_checklists,
            "total_images": len(image_checklists),
            "total_check_items": sum(len(c["items"]) for c in checklist.values()),
        },
        "error": None,
    }


def run_complete_image_workflow(product_info: dict[str, Any]) -> dict[str, Any]:
    """
    运行完整的 AI 生图工作流
    
    Step 1: 生成图片生产计划
    Step 2: 转换为生图任务
    Step 3: 生成执行检查清单
    
    Args:
        product_info: 商品信息（17 字段产品报告）
    
    Returns:
        完整工作流结果
    """
    # Step 1: 生成图片计划
    plan_result = generate_image_plan(product_info)
    if not plan_result["success"]:
        return {"success": False, "data": None, "error": plan_result["error"]}
    
    plan = plan_result["data"]
    
    # Step 2: 生成任务列表
    tasks = generate_generation_tasks(plan)
    
    # Step 3: 生成检查清单
    checklist_result = generate_execution_checklist(plan)
    
    return {
        "success": True,
        "data": {
            "product_name": plan["product_name"],
            "plan": plan,
            "tasks": tasks,
            "checklist": checklist_result["data"],
            "summary": {
                "total_images": plan["total_images"],
                "image_types": len(plan["image_types"]),
                "estimated_cost_cny": plan["estimated_cost"],
                "check_items": checklist_result["data"]["total_check_items"],
            },
        },
        "error": None,
    }
