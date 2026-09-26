"""
AI Image Prompt Rules Service (E-commerce Full Automatic Image Generation)

Based on "Codex E-commerce Full Automatic Image Generation" article, implements
complete e-commerce product image production with English-only prompts and copy.

Core Rules:
1. 6 Image Type Classification (Main/Selling Point/Scene/Detail/Parameter/Comparison)
2. Prompt Template Standards (4 Parts: Subject/Frame/Text/Forbidden)
3. Size Specifications (Compliant with e-commerce platform requirements)
4. Batch Generation Strategy (1 Main + 5 Selling Points + 3 Scenes + 5 Details)

Follows AGENTS.md standards:
- Business rules centralized in service layer
- Pure template filling, no LLM calls required
- Structured output, directly usable for AI image generation
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Service Configuration
SERVICE_NAME = "image_prompt_rules"
SERVICE_VERSION = "2.1.0"

# ============ 6 Image Type Configuration ============

IMAGE_TYPES: dict[str, dict[str, Any]] = {
    "main_image": {
        "name": "Main Image",
        "description": "White background product image for listing display",
        "count": 1,
        "priority": 1,
        "background": "Pure white background (#FFFFFF)",
        "lighting": "Even soft lighting, no shadows",
        "composition": "Product centered, occupies 60-70% of frame",
        "props": "No props",
        "text": "No text",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "Test product recognition and search click-through rate",
    },
    "selling_point": {
        "name": "Selling Point Image",
        "description": "Information graphic highlighting core selling points",
        "count": 5,
        "priority": 2,
        "background": "Light gradient background",
        "lighting": "Even soft lighting",
        "composition": "Icon + text + product, moderate information density",
        "props": "Selling point icons",
        "text": "Short copy under 10 words",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "Test selling point communication and click-through rate",
    },
    "scene_image": {
        "name": "Scene Image",
        "description": "Product usage scenario showcase",
        "count": 3,
        "priority": 3,
        "background": "Real usage scenario background",
        "lighting": "Natural light with depth",
        "composition": "Product integrated into scene, occupies 40-50% of frame",
        "props": "Scene-related props",
        "text": "No text or scene label",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "Test scene immersion and user imagination",
    },
    "detail_image": {
        "name": "Detail Image",
        "description": "Product material, craftsmanship, and size close-ups",
        "count": 5,
        "priority": 4,
        "background": "Light gray background",
        "lighting": "Side lighting to highlight texture",
        "composition": "Close-up detail, enlarged features",
        "props": "No props",
        "text": "Detail labels (optional)",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "Test quality communication and purchase trust",
    },
    "parameter_image": {
        "name": "Parameter Image",
        "description": "Specifications and dimensions showcase",
        "count": 1,
        "priority": 5,
        "background": "White background",
        "lighting": "Even soft lighting",
        "composition": "Product + size markings + parameter table",
        "props": "Size lines, parameter icons",
        "text": "Specification text",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "Test information communication efficiency",
    },
    "comparison_image": {
        "name": "Comparison Image",
        "description": "Competitor comparison or before/after usage",
        "count": 1,
        "priority": 6,
        "background": "White background with dividing line",
        "lighting": "Even soft lighting",
        "composition": "Side-by-side comparison, our product highlighted",
        "props": "Comparison icons",
        "text": "Comparison labels",
        "size": {"width": 800, "height": 800, "ratio": "1:1"},
        "test_goal": "Test advantage communication and purchase decision",
    },
}

# ============ Selling Point Type Configuration ============

SELLING_POINT_TYPES: dict[str, dict[str, Any]] = {
    "portability": {
        "name": "Portability",
        "icons": ["🎒", "✈️", "🚶"],
        "templates": ["Portable", "Lightweight", "One-Hand Carry"],
    },
    "capacity": {
        "name": "Capacity",
        "icons": ["🥤", "📦", "💧"],
        "templates": ["Large Capacity", "Fits More", "Full Satisfaction"],
    },
    "cleaning": {
        "name": "Easy Clean",
        "icons": ["🧼", "✨", "💦"],
        "templates": ["Easy to Clean", "Rinse Clean", "Worry-Free Hygiene"],
    },
    "scene": {
        "name": "Scene Versatility",
        "icons": ["🏢", "🏕️", "🏋️"],
        "templates": ["Office Essential", "Outdoor Must-Have", "Gym Companion"],
    },
    "quality": {
        "name": "Premium Quality",
        "icons": ["⭐", "💎", "🏆"],
        "templates": ["Quality Choice", "Fine Craftsmanship", "Built to Last"],
    },
    "function": {
        "name": "Smart Function",
        "icons": ["⚡", "🔌", "📱"],
        "templates": ["One-Touch Operation", "Smart & Convenient", "Multi-Function"],
    },
    "design": {
        "name": "Modern Design",
        "icons": ["🎨", "🌈", "✨"],
        "templates": ["Minimalist Aesthetic", "Stunning Look", "Fashion Design"],
    },
    "price": {
        "name": "Value Deal",
        "icons": ["💰", "🏷️", "🎉"],
        "templates": ["Limited Offer", "Great Value", "Today's Deal"],
    },
}

# ============ Prompt Template Configuration ============

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

# ============ Checklist Configuration ============

CHECKLIST_ITEMS: dict[str, list[str]] = {
    "product_check": [
        "Product appearance matches original",
        "Core selling points accurately expressed",
        "No non-brand logos present",
        "Product proportions are normal",
    ],
    "text_check": [
        "Text is clear and readable",
        "No typos or spelling errors",
        "No garbled characters",
        "Copy is natural and fluent",
        "Font style is consistent",
    ],
    "compliance_check": [
        "No absolute superlative terms used",
        "No exaggerated efficacy claims",
        "Compliant with advertising regulations",
        "No false advertising",
    ],
    "technical_check": [
        "Image resolution meets specifications",
        "Background is clean",
        "Lighting is even",
        "Composition is balanced",
    ],
}


def get_image_prompt_rules_status() -> dict[str, Any]:
    """Get service status"""
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
    """Safely get dictionary value"""
    value = data.get(key, default)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value) if value else default


def _safe_get_list(data: dict[str, Any], key: str, default: list[str] | None = None) -> list[str]:
    """Safely get list value"""
    value = data.get(key, default or [])
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value else (default or [])


def _sanitize_filename(name: str) -> str:
    """Clean filename - keep only ASCII alphanumeric characters"""
    sanitized = re.sub(r'[^\x00-\x7F]+', '', name)
    sanitized = re.sub(r'[^\w\s-]', '', sanitized)
    sanitized = re.sub(r'[-\s]+', '_', sanitized)
    return sanitized.lower() or 'product'


def generate_image_plan(product_info: dict[str, Any]) -> dict[str, Any]:
    """
    Generate complete image production plan
    
    Based on product information, generate 6 types of image production plans and prompts.
    All prompts and copy are in English only.
    
    Args:
        product_info: Product information (17-field product report)
    
    Returns:
        Complete image production plan
    """
    product_name = _safe_get(product_info, "product_name_en", "Product")
    product_type = _safe_get(product_info, "product_category", "Product")
    product_color = _safe_get(product_info, "product_color", "white")
    core_selling_points = _safe_get_list(product_info, "core_selling_points", ["High Quality", "Portable", "Durable"])
    usage_scenarios = _safe_get_list(product_info, "usage_scenarios", ["Home", "Outdoor", "Office"])
    material_craft = _safe_get(product_info, "material_craft", "High-quality materials")
    product_dimensions = _safe_get(product_info, "product_dimensions", "Standard size")
    
    plan: dict[str, Any] = {
        "product_name": product_name,
        "image_types": {},
        "total_images": 0,
        "estimated_cost": 0,
    }
    
    # 1. Main Image (1 image)
    main_prompt = PROMPT_TEMPLATES["main_image"].format(
        product_name=product_name,
        product_color=product_color,
        product_type=product_type,
    )
    plan["image_types"]["main_image"] = {
        "count": 1,
        "prompts": [main_prompt],
        "filenames": [f"product_{_sanitize_filename(product_name)}_main_01.png"],
        "status": "pending",
    }
    
    # 2. Selling Point Images (5 images)
    selling_points_prompts = []
    selling_points_filenames = []
    for i, point in enumerate(core_selling_points[:5], 1):
        point_type = _match_selling_point_type(point)
        point_config = SELLING_POINT_TYPES.get(point_type, SELLING_POINT_TYPES["quality"])
        prompt = PROMPT_TEMPLATES["selling_point"].format(
            product_name=product_name,
            selling_point=point[:30],
            selling_point_icon=point_config["icons"][0],
            copy_text=point_config["templates"][0],
        )
        selling_points_prompts.append(prompt)
        selling_points_filenames.append(f"product_{_sanitize_filename(product_name)}_point_{i:02d}.png")
    
    plan["image_types"]["selling_point"] = {
        "count": len(selling_points_prompts),
        "prompts": selling_points_prompts,
        "filenames": selling_points_filenames,
        "selling_points": core_selling_points[:5],
        "status": "pending",
    }
    
    # 3. Scene Images (3 images)
    scene_prompts = []
    scene_filenames = []
    scene_props = {
        "Home": "home decor",
        "Outdoor": "camping equipment",
        "Office": "office supplies",
        "Travel": "travel accessories",
        "Gym": "fitness equipment",
        "Camp": "camping gear",
        "Kitchen": "kitchen items",
    }
    for i, scene in enumerate(usage_scenarios[:3], 1):
        props = scene_props.get(scene.capitalize(), "relevant props")
        prompt = PROMPT_TEMPLATES["scene_image"].format(
            product_name=product_name,
            scene=scene.lower(),
            props=props,
        )
        scene_prompts.append(prompt)
        scene_filenames.append(f"product_{_sanitize_filename(product_name)}_scene_{i:02d}.png")
    
    plan["image_types"]["scene_image"] = {
        "count": len(scene_prompts),
        "prompts": scene_prompts,
        "filenames": scene_filenames,
        "scenes": usage_scenarios[:3],
        "status": "pending",
    }
    
    # 4. Detail Images (5 images)
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
            product_name=product_name,
            detail_focus=focus,
            detail_description=material_craft[:50],
        )
        detail_prompts.append(prompt)
        detail_filenames.append(f"product_{_sanitize_filename(product_name)}_detail_{i:02d}.png")
    
    plan["image_types"]["detail_image"] = {
        "count": len(detail_prompts),
        "prompts": detail_prompts,
        "filenames": detail_filenames,
        "details": detail_foci[:5],
        "status": "pending",
    }
    
    # 5. Parameter Image (1 image)
    parameter_prompt = PROMPT_TEMPLATES["parameter_image"].format(
        product_name=product_name,
        dimensions=product_dimensions[:40] if product_dimensions else "Standard dimensions",
    )
    plan["image_types"]["parameter_image"] = {
        "count": 1,
        "prompts": [parameter_prompt],
        "filenames": [f"product_{_sanitize_filename(product_name)}_parameter_01.png"],
        "status": "pending",
    }
    
    # 6. Comparison Image (1 image)
    comparison_prompt = PROMPT_TEMPLATES["comparison_image"].format(
        product_name=product_name,
        comparison_point="Quality" if core_selling_points else "Features",
    )
    plan["image_types"]["comparison_image"] = {
        "count": 1,
        "prompts": [comparison_prompt],
        "filenames": [f"product_{_sanitize_filename(product_name)}_comparison_01.png"],
        "status": "pending",
    }
    
    # Calculate totals
    plan["total_images"] = sum(t["count"] for t in plan["image_types"].values())
    plan["estimated_cost"] = round(plan["total_images"] * 0.1, 2)
    
    return {
        "success": True,
        "data": plan,
        "error": None,
    }


def _match_selling_point_type(selling_point: str) -> str:
    """Match selling point type based on text (English keywords)"""
    point_lower = selling_point.lower()
    
    if any(kw in point_lower for kw in ["portable", "light", "carry", "travel", "mobile"]):
        return "portability"
    elif any(kw in point_lower for kw in ["capacity", "large", "big", "volume", "size"]):
        return "capacity"
    elif any(kw in point_lower for kw in ["clean", "wash", "hygiene", "easy", "simple"]):
        return "cleaning"
    elif any(kw in point_lower for kw in ["scene", "outdoor", "office", "camp", "travel", "home"]):
        return "scene"
    elif any(kw in point_lower for kw in ["quality", "premium", "durable", "solid", "strong"]):
        return "quality"
    elif any(kw in point_lower for kw in ["function", "smart", "multi", "feature", "tech"]):
        return "function"
    elif any(kw in point_lower for kw in ["design", "fashion", "style", "aesthetic", "modern"]):
        return "design"
    elif any(kw in point_lower for kw in ["price", "deal", "sale", "value", "offer", "discount"]):
        return "price"
    
    return "quality"


def generate_generation_tasks(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Convert image plan to executable generation task list
    
    Args:
        plan: Image production plan
    
    Returns:
        Generation task list
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
    
    # Sort by priority
    tasks.sort(key=lambda x: x["priority"])
    
    return tasks


def generate_execution_checklist(plan: dict[str, Any]) -> dict[str, Any]:
    """
    Generate execution checklist
    
    Args:
        plan: Image production plan
    
    Returns:
        Execution checklist
    """
    checklist = {
        "product_check": {
            "name": "Product Check",
            "items": CHECKLIST_ITEMS["product_check"],
            "status": "pending",
        },
        "text_check": {
            "name": "Text Check",
            "items": CHECKLIST_ITEMS["text_check"],
            "status": "pending",
        },
        "compliance_check": {
            "name": "Compliance Check",
            "items": CHECKLIST_ITEMS["compliance_check"],
            "status": "pending",
        },
        "technical_check": {
            "name": "Technical Check",
            "items": CHECKLIST_ITEMS["technical_check"],
            "status": "pending",
        },
    }
    
    # Generate check items for each image type
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
    Run complete AI image workflow
    
    Step 1: Generate image production plan
    Step 2: Convert to generation tasks
    Step 3: Generate execution checklist
    
    All prompts and copy are in English only.
    
    Args:
        product_info: Product information (17-field product report)
    
    Returns:
        Complete workflow result
    """
    # Step 1: Generate image plan
    plan_result = generate_image_plan(product_info)
    if not plan_result["success"]:
        return {"success": False, "data": None, "error": plan_result["error"]}
    
    plan = plan_result["data"]
    
    # Step 2: Generate task list
    tasks = generate_generation_tasks(plan)
    
    # Step 3: Generate checklist
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
