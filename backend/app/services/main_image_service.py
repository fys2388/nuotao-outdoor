"""
电商主图生产服务（P1-5）

基于公众号文章"电商主图别再一句话生成"的6步流程，实现电商主图端到端生产。

5大功能模块：
1. 3套主图方向策略层：白底清爽/真实场景/促销转化
2. 主图文案生成器：每个变体3条10字以内短文案，只讲一个卖点
3. 批量变体生成：一张跑通后，自动生成10个变体
4. 执行清单+检查项：文件名规范、商品检查、中文检查、合规检查
5. 可直接照抄的完整Prompt模板：一键从商品资料到执行清单

6步生产流程：
Step 01: 先喂商品信息（4维度：商品资料/目标人群/使用场景/禁用表达）
Step 02: 先出3套主图方向（白底清爽/真实场景/促销转化）
Step 03: 把方案改成绘图提示词（4部分：主体/画面/文字/禁止项）
Step 04: 一张跑通后再批量（10个变体，每图承担测试任务）
Step 05: 主图文案只讲一个卖点（10字以内短文案）
Step 06: 整理成执行清单（文件名+检查项）

遵循AGENTS.md规范：
- 业务规则集中在服务层
- LLM调用走llm_gateway
- 全链路可审计
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.llm_gateway import LLMError, LLMRequest, complete, parse_json_content

logger = logging.getLogger(__name__)

# 服务配置
SERVICE_NAME = "main_image_generator"
SERVICE_VERSION = "1.0.0"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 3000

# ============ 3套主图方向配置 ============

MAIN_IMAGE_DIRECTIONS: dict[str, dict[str, Any]] = {
    "white_background": {
        "name": "白底清爽",
        "description": "突出商品本体，适合搜索场景",
        "background": "纯白色背景，干净简洁",
        "lighting": "均匀柔光，无明显阴影",
        "composition": "商品居中，占画面60-70%",
        "props": "无道具或极简道具",
        "test_goal": "测试商品识别效率和搜索点击率",
    },
    "real_scene": {
        "name": "真实场景",
        "description": "强化代入感，让用户想象使用画面",
        "background": "真实使用场景背景，有生活气息",
        "lighting": "自然光，有层次感和空间感",
        "composition": "商品融入场景，占画面40-50%",
        "props": "场景相关道具，营造使用氛围",
        "test_goal": "测试场景代入感和用户想象力",
    },
    "promotion_conversion": {
        "name": "促销转化",
        "description": "集中表达卖点，适合活动和组合装",
        "background": "促销氛围背景，有视觉冲击力",
        "lighting": "高对比度光线，突出重点",
        "composition": "商品+卖点文案，信息密度高",
        "props": "促销标签、价格标识、组合展示",
        "test_goal": "测试促销点击率和转化率",
    },
}

# ============ 卖点类型配置 ============

SELLING_POINT_TYPES: dict[str, str] = {
    "portability": "便携卖点",
    "capacity": "容量卖点",
    "cleaning": "清洁卖点",
    "scene": "场景卖点",
    "quality": "品质卖点",
    "function": "功能卖点",
    "design": "设计卖点",
    "price": "性价比卖点",
}

# ============ 变体维度配置 ============

VARIANT_DIMENSIONS: list[dict[str, str]] = [
    {"dimension": "background", "name": "背景", "description": "改变背景颜色或纹理"},
    {"dimension": "scene", "name": "场景", "description": "改变使用场景"},
    {"dimension": "props", "name": "道具", "description": "改变搭配道具"},
    {"dimension": "copy", "name": "文案", "description": "改变主图文案"},
    {"dimension": "composition", "name": "构图", "description": "改变构图方式"},
    {"dimension": "lighting", "name": "光线", "description": "改变光线氛围"},
    {"dimension": "angle", "name": "角度", "description": "改变拍摄角度"},
    {"dimension": "color", "name": "色调", "description": "改变整体色调"},
]

# ============ 检查项配置 ============

CHECKLIST_ITEMS: dict[str, dict[str, str]] = {
    "filename": {
        "name": "文件名",
        "description": "规范命名：product_{产品名}_main_{序号}.png",
        "example": "product_juicecup_main_01.png",
        "items": "文件名格式是否正确 | 序号是否连续 | 是否包含特殊字符 | 是否全小写",
    },
    "product_check": {
        "name": "检查商品",
        "description": "是否变形、卖点跑偏、出现虚假logo",
        "items": "商品外观是否与原图一致 | 核心卖点是否准确表达 | 是否出现非品牌logo | 商品比例是否正常",
    },
    "chinese_check": {
        "name": "检查中文",
        "description": "是否错字、乱码、标语不自然",
        "items": "文字是否清晰可读 | 是否有错别字 | 是否有乱码 | 标语是否自然通顺 | 字体是否统一",
    },
    "compliance_check": {
        "name": "检查合规",
        "description": "是否有绝对化承诺和夸张功效",
        "items": "是否使用'最强''第一'等绝对化用语 | 是否有夸张功效承诺 | 是否符合广告法 | 是否有虚假宣传",
    },
}


def get_main_image_service_status() -> dict[str, Any]:
    """获取电商主图生产服务状态"""
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "status": "operational",
        "directions": list(MAIN_IMAGE_DIRECTIONS.keys()),
        "selling_point_types": list(SELLING_POINT_TYPES.keys()),
        "variant_dimensions": [d["dimension"] for d in VARIANT_DIMENSIONS],
        "checklist_items": list(CHECKLIST_ITEMS.keys()),
        "workflow_steps": [
            "Step 01: 先喂商品信息",
            "Step 02: 先出3套主图方向",
            "Step 03: 把方案改成绘图提示词",
            "Step 04: 一张跑通后再批量",
            "Step 05: 主图文案只讲一个卖点",
            "Step 06: 整理成执行清单",
        ],
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
    """清理文件名，移除特殊字符和非ASCII字符"""
    # 移除非ASCII字符（包括中文）
    sanitized = re.sub(r'[^\x00-\x7F]+', '', name)
    # 移除特殊字符
    sanitized = re.sub(r'[^\w\s-]', '', sanitized)
    # 替换空格和连字符为下划线
    sanitized = re.sub(r'[-\s]+', '_', sanitized)
    # 如果清理后为空，使用默认名称
    if not sanitized:
        sanitized = 'product'
    return sanitized.lower()


# ============ 功能1: 3套主图方向策略层 ============

def generate_three_directions(product_info: dict[str, Any]) -> dict[str, Any]:
    """
    生成3套主图方向策略（Step 02）

    Args:
        product_info: 商品信息（名称、卖点、人群、场景等）

    Returns:
        3套主图方向的完整策略
    """
    product_name = _safe_get(product_info, "name", "产品")
    core_selling_points = _safe_get_list(product_info, "core_selling_points", ["高品质", "实用", "美观"])
    target_audience = _safe_get(product_info, "target_audience", "目标用户")
    usage_scenarios = _safe_get_list(product_info, "usage_scenarios", ["日常使用"])

    directions = {}
    for direction_key, direction_config in MAIN_IMAGE_DIRECTIONS.items():
        directions[direction_key] = {
            "name": direction_config["name"],
            "description": direction_config["description"],
            "test_goal": direction_config["test_goal"],
            "prompt": {
                "subject": f"{product_name}，{core_selling_points[0] if core_selling_points else '高品质'}，商品外观保持一致",
                "background": direction_config["background"],
                "lighting": direction_config["lighting"],
                "composition": direction_config["composition"],
                "props": direction_config["props"],
                "target_audience": target_audience,
                "usage_scenario": usage_scenarios[0] if usage_scenarios else "日常场景",
            },
            "recommended_copy": _generate_direction_copy(direction_key, core_selling_points),
        }

    return {
        "success": True,
        "data": {
            "product_name": product_name,
            "directions": directions,
            "recommendation": _recommend_best_direction(product_info),
        },
        "error": None,
    }


def _generate_direction_copy(direction_key: str, selling_points: list[str]) -> list[str]:
    """为每个方向生成推荐文案"""
    if direction_key == "white_background":
        return [selling_points[0] if selling_points else "高品质", "正品保障", "限时特惠"]
    elif direction_key == "real_scene":
        return [selling_points[1] if len(selling_points) > 1 else "实用便捷", "随时随地", "享受生活"]
    elif direction_key == "promotion_conversion":
        return ["限时特惠", "买一送一", "今日特价"]
    return ["高品质", "值得信赖", "立即购买"]


def _recommend_best_direction(product_info: dict[str, Any]) -> dict[str, str]:
    """推荐最适合的主图方向"""
    price = _safe_get(product_info, "price", "")
    category = _safe_get(product_info, "category", "")

    # 简单推荐逻辑
    if any(keyword in price for keyword in ["特惠", "促销", "折扣", "¥9", "¥19", "¥29"]):
        return {"direction": "promotion_conversion", "reason": "价格有促销属性，推荐促销转化方向"}
    elif any(keyword in category for keyword in ["食品", "美妆", "服饰", "家居"]):
        return {"direction": "real_scene", "reason": "消费品类，推荐真实场景方向增强代入感"}
    else:
        return {"direction": "white_background", "reason": "标准商品，推荐白底清爽方向提升搜索识别"}


# ============ 功能2: 主图文案生成器 ============

def generate_main_image_copy(
    product_info: dict[str, Any],
    *,
    selling_point_type: str = "portability",
    count: int = 3,
    max_length: int = 10,
) -> dict[str, Any]:
    """
    生成主图短文案（Step 05）

    每条短文案控制在10个字以内，只讲一个卖点。

    Args:
        product_info: 商品信息
        selling_point_type: 卖点类型（portability/capacity/cleaning/scene/quality/function/design/price）
        count: 生成文案数量
        max_length: 每条文案最大字数

    Returns:
        短文案列表
    """
    product_name = _safe_get(product_info, "name", "产品")
    core_selling_points = _safe_get_list(product_info, "core_selling_points", [])

    # 基于卖点类型生成文案模板
    copy_templates = _get_copy_templates(selling_point_type)

    # 生成文案
    copies = []
    for i in range(min(count, len(copy_templates))):
        template = copy_templates[i]
        # 替换产品名和卖点
        copy = template.replace("{product}", product_name[:4])
        if core_selling_points and i < len(core_selling_points):
            copy = copy.replace("{selling_point}", core_selling_points[i][:6])
        else:
            copy = copy.replace("{selling_point}", "高品质")

        # 确保不超过最大长度
        if len(copy) > max_length:
            copy = copy[:max_length]

        copies.append({
            "text": copy,
            "length": len(copy),
            "selling_point_type": selling_point_type,
            "selling_point_name": SELLING_POINT_TYPES.get(selling_point_type, "其他卖点"),
        })

    return {
        "success": True,
        "data": {
            "product_name": product_name,
            "selling_point_type": selling_point_type,
            "selling_point_name": SELLING_POINT_TYPES.get(selling_point_type, "其他卖点"),
            "max_length": max_length,
            "copies": copies,
            "principle": "主图文案只讲一个卖点，直接、具体、不过度承诺",
        },
        "error": None,
    }


def _get_copy_templates(selling_point_type: str) -> list[str]:
    """获取文案模板"""
    templates = {
        "portability": ["随身{selling_point}", "轻巧便携", "随时随地", "一手掌握", "出行必备"],
        "capacity": ["一杯刚刚好", "大容量满足", "一次喝个够", "容量升级", "足量更尽兴"],
        "cleaning": ["拆洗更省心", "一冲即净", "清洁无忧", "易拆易洗", "卫生看得见"],
        "scene": ["早餐快一点", "办公好搭档", "运动好伴侣", "居家必备", "通勤好选择"],
        "quality": ["品质之选", "精工细作", "耐用可靠", "正品保障", "匠心品质"],
        "function": ["一键操作", "智能便捷", "多功能合一", "高效实用", "轻松搞定"],
        "design": ["简约美学", "颜值在线", "时尚设计", "精致外观", "百搭风格"],
        "price": ["限时特惠", "超值性价比", "今日特价", "买一送一", "亏本冲量"],
    }
    return templates.get(selling_point_type, templates["quality"])


def generate_all_selling_point_copies(product_info: dict[str, Any]) -> dict[str, Any]:
    """生成所有卖点类型的文案"""
    all_copies = {}
    for point_type in SELLING_POINT_TYPES.keys():
        result = generate_main_image_copy(product_info, selling_point_type=point_type, count=3)
        if result["success"]:
            all_copies[point_type] = result["data"]["copies"]

    return {
        "success": True,
        "data": {
            "product_name": _safe_get(product_info, "name", "产品"),
            "all_copies": all_copies,
            "total_count": sum(len(copies) for copies in all_copies.values()),
        },
        "error": None,
    }


# ============ 功能3: 批量变体生成 ============

def generate_variants(
    product_info: dict[str, Any],
    *,
    base_direction: str = "white_background",
    variant_count: int = 10,
) -> dict[str, Any]:
    """
    批量生成主图变体（Step 04）

    一张跑通后，沿用同一套模板，只改变一个重点：背景、场景、道具、文案或构图。
    每张图都要承担一个测试任务。

    Args:
        product_info: 商品信息
        base_direction: 基础方向（white_background/real_scene/promotion_conversion）
        variant_count: 变体数量（默认10个）

    Returns:
        变体列表
    """
    product_name = _safe_get(product_info, "name", "产品")
    base_config = MAIN_IMAGE_DIRECTIONS.get(base_direction, MAIN_IMAGE_DIRECTIONS["white_background"])
    usage_scenarios = _safe_get_list(product_info, "usage_scenarios", ["办公室", "家庭", "户外", "旅行"])
    core_selling_points = _safe_get_list(product_info, "core_selling_points", ["高品质", "实用", "美观", "便捷"])

    # 生成变体
    variants = []
    for i in range(variant_count):
        # 循环使用不同的变体维度
        dimension_index = i % len(VARIANT_DIMENSIONS)
        dimension = VARIANT_DIMENSIONS[dimension_index]

        # 根据维度生成变体配置
        variant_config = _generate_variant_config(
            dimension["dimension"],
            i,
            base_config,
            usage_scenarios,
            core_selling_points,
        )

        # 生成文件名
        filename = f"product_{_sanitize_filename(product_name)}_main_{i+1:02d}.png"

        variants.append({
            "id": i + 1,
            "filename": filename,
            "variant_dimension": dimension["dimension"],
            "variant_name": dimension["name"],
            "test_goal": variant_config["test_goal"],
            "prompt": variant_config["prompt"],
            "recommended_copy": variant_config["recommended_copy"],
        })

    return {
        "success": True,
        "data": {
            "product_name": product_name,
            "base_direction": base_direction,
            "base_direction_name": base_config["name"],
            "variant_count": variant_count,
            "variants": variants,
            "principle": "一张跑通后再批量，每张图都要承担一个测试任务",
        },
        "error": None,
    }


def _generate_variant_config(
    dimension: str,
    index: int,
    base_config: dict[str, Any],
    scenarios: list[str],
    selling_points: list[str],
) -> dict[str, Any]:
    """生成单个变体配置"""
    prompt = base_config.copy()
    test_goal = ""
    recommended_copy = []

    if dimension == "background":
        backgrounds = ["浅灰色背景", "米色背景", "淡蓝色背景", "渐变色背景", "纹理背景"]
        bg = backgrounds[index % len(backgrounds)]
        prompt["background"] = bg
        test_goal = f"测试{bg}下的商品识别效率"
        recommended_copy = [selling_points[0] if selling_points else "高品质", "正品保障"]

    elif dimension == "scene":
        scene = scenarios[index % len(scenarios)] if scenarios else "日常场景"
        prompt["background"] = f"{scene}场景背景"
        prompt["usage_scenario"] = scene
        test_goal = f"测试{scene}场景的用户代入感"
        recommended_copy = [f"{scene}必备", "随时随地"]

    elif dimension == "props":
        props_list = ["搭配绿植", "搭配书籍", "搭配咖啡杯", "搭配花卉", "搭配电子产品"]
        prop = props_list[index % len(props_list)]
        prompt["props"] = prop
        test_goal = f"测试{prop}道具的氛围提升效果"
        recommended_copy = ["品质生活", "精致选择"]

    elif dimension == "copy":
        copy_options = selling_points if selling_points else ["高品质", "实用", "美观", "便捷"]
        copy = copy_options[index % len(copy_options)]
        prompt["copy"] = copy[:10]
        test_goal = f"测试'{copy}'文案的点击率"
        recommended_copy = [copy[:10]]

    elif dimension == "composition":
        compositions = ["商品左对齐", "商品右对齐", "商品偏上", "商品偏下", "对角线构图"]
        comp = compositions[index % len(compositions)]
        prompt["composition"] = comp
        test_goal = f"测试{comp}的视觉吸引力"
        recommended_copy = [selling_points[0] if selling_points else "高品质"]

    elif dimension == "lighting":
        lightings = ["暖光氛围", "冷光清爽", "侧光立体", "逆光剪影", "顶光均匀"]
        light = lightings[index % len(lightings)]
        prompt["lighting"] = light
        test_goal = f"测试{light}的氛围效果"
        recommended_copy = ["光影美学", "品质呈现"]

    elif dimension == "angle":
        angles = ["45度俯拍", "平视角度", "低角度仰拍", "特写角度", "全景角度"]
        angle = angles[index % len(angles)]
        prompt["angle"] = angle
        test_goal = f"测试{angle}的商品展示效果"
        recommended_copy = ["多角度展示", "细节呈现"]

    elif dimension == "color":
        colors = ["暖色调", "冷色调", "莫兰迪色", "高饱和色", "低饱和色"]
        color = colors[index % len(colors)]
        prompt["color_tone"] = color
        test_goal = f"测试{color}的用户偏好"
        recommended_copy = ["色彩美学", "个性选择"]

    else:
        test_goal = "测试变体效果"
        recommended_copy = [selling_points[0] if selling_points else "高品质"]

    return {
        "prompt": prompt,
        "test_goal": test_goal,
        "recommended_copy": recommended_copy,
    }


# ============ 功能4: 执行清单+检查项 ============

def generate_execution_checklist(
    product_info: dict[str, Any],
    *,
    variants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    生成执行清单和检查项（Step 06）

    把方案、提示词、文案、文件名和检查项放进同一张表。

    Args:
        product_info: 商品信息
        variants: 可选的变体列表（如果已生成）

    Returns:
        执行清单
    """
    product_name = _safe_get(product_info, "name", "产品")
    sanitized_name = _sanitize_filename(product_name)

    # 生成文件名规范
    filename_spec = {
        "format": "product_{产品名}_main_{序号}.png",
        "example": f"product_{sanitized_name}_main_01.png",
        "rules": [
            "全小写字母",
            "用下划线分隔",
            "序号两位数字（01-99）",
            "不含特殊字符",
        ],
    }

    # 生成检查项
    checklist = {}
    for check_key, check_config in CHECKLIST_ITEMS.items():
        checklist[check_key] = {
            "name": check_config["name"],
            "description": check_config["description"],
            "items": [item.strip() for item in check_config["items"].split("|")],
            "status": "pending",
        }

    # 如果有变体，生成每个变体检修清单
    variant_checklists = []
    if variants:
        for variant in variants:
            variant_checklists.append({
                "id": variant["id"],
                "filename": variant["filename"],
                "test_goal": variant["test_goal"],
                "checklist_status": {key: "pending" for key in CHECKLIST_ITEMS.keys()},
            })

    return {
        "success": True,
        "data": {
            "product_name": product_name,
            "filename_spec": filename_spec,
            "checklist": checklist,
            "variant_checklists": variant_checklists,
            "total_check_items": sum(len(c["items"]) for c in checklist.values()),
            "principle": "从试试看，变成可交付",
        },
        "error": None,
    }


# ============ 功能5: 可直接照抄的完整Prompt模板 ============

def get_complete_prompt_template() -> dict[str, Any]:
    """
    获取可直接照抄的完整Prompt模板

    让AI从策划到清单一次跑完。

    Returns:
        完整Prompt模板
    """
    template = """你是电商主图策划。
请根据商品资料完成：
1. 整理人群、卖点、场景、禁用表达
2. 给出白底/场景/促销3套方向
3. 改写成 GPT Image 提示词
4. 生成10个主图变体
5. 每个变体写3条10字内短文案
6. 输出执行清单和检查项"""

    return {
        "success": True,
        "data": {
            "template": template,
            "template_length": len(template),
            "steps": [
                "整理人群、卖点、场景、禁用表达",
                "给出白底/场景/促销3套方向",
                "改写成 GPT Image 提示词",
                "生成10个主图变体",
                "每个变体写3条10字内短文案",
                "输出执行清单和检查项",
            ],
            "usage": "将商品资料粘贴到模板后面，让AI从策划到清单一次跑完",
        },
        "error": None,
    }


def run_complete_workflow(
    product_info: dict[str, Any],
    *,
    use_llm: bool = False,
) -> dict[str, Any]:
    """
    运行完整的电商主图生产工作流（6步）

    Step 01: 先喂商品信息
    Step 02: 先出3套主图方向
    Step 03: 把方案改成绘图提示词
    Step 04: 一张跑通后再批量
    Step 05: 主图文案只讲一个卖点
    Step 06: 整理成执行清单

    Args:
        product_info: 商品信息
        use_llm: 是否使用LLM增强（默认False，使用规则引擎）

    Returns:
        完整工作流结果
    """
    # Step 01: 商品信息整理（输入已提供）
    step01 = {
        "product_info": product_info,
        "status": "completed",
    }

    # Step 02: 3套主图方向
    step02 = generate_three_directions(product_info)

    # Step 03: 绘图提示词（基于3套方向）
    step03 = {
        "directions_prompts": {
            key: value["prompt"]
            for key, value in step02["data"]["directions"].items()
        },
        "status": "completed",
    }

    # Step 04: 批量变体（基于推荐方向）
    recommended_direction = step02["data"]["recommendation"]["direction"]
    step04 = generate_variants(product_info, base_direction=recommended_direction, variant_count=10)

    # Step 05: 主图文案
    step05 = generate_all_selling_point_copies(product_info)

    # Step 06: 执行清单
    step06 = generate_execution_checklist(product_info, variants=step04["data"]["variants"])

    return {
        "success": True,
        "data": {
            "product_name": _safe_get(product_info, "name", "产品"),
            "workflow": {
                "step01_product_info": step01,
                "step02_three_directions": step02["data"],
                "step03_prompts": step03,
                "step04_variants": step04["data"],
                "step05_copy": step05["data"],
                "step06_checklist": step06["data"],
            },
            "summary": {
                "directions_count": 3,
                "variants_count": 10,
                "copy_count": step05["data"]["total_count"],
                "check_items_count": step06["data"]["total_check_items"],
                "recommended_direction": recommended_direction,
            },
        },
        "error": None,
    }
