"""Seed initial creative prompt templates (v0.17 C2).

Run: python seed_creative_templates.py
Idempotent: skips templates that already exist (same workspace/template_key).

Templates are sourced from docs/ai_image_prompt_template_library.md V1.0.
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

sys.path.insert(0, ".")

from app.core.database import async_session_factory
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.services.creative_service import create_prompt_template, get_prompt_template_by_key

DEFAULT_WORKSPACE = DEFAULT_WORKSPACE_ID

# Initial prompt templates (from ai_image_prompt_template_library.md V1.0)
INITIAL_TEMPLATES: list[dict] = [
    {
        "template_key": "hero-white-bg-v1",
        "name": "Hero Image - White Background",
        "description": "Clean e-commerce product image with pure white background",
        "asset_type": "hero_image",
        "category": "main_image",
        "prompt_text": (
            "参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。"
            "将背景替换为纯白色背景，产品位于画面中央，采用45度俯视角展示，"
            "产品占画面约65%，下方有柔和的接触阴影。"
            "整体采用专业电商产品摄影风格，柔和均匀的顶光照明，"
            "无任何文字、水印或其他装饰元素，画面干净清爽。"
            "关键主体完整置于安全边界内，四周边距均衡，背景自然铺满画布。"
        ),
        "variables": {"product_reference": "[img0]"},
        "default_parameters": {"aspect_ratio": "1:1", "resolution": "2048x2048"},
        "version": "1.0.0",
        "status": "ACTIVE",
    },
    {
        "template_key": "hero-camping-scene-v1",
        "name": "Hero Image - Camping Scene",
        "description": "Product in real outdoor camping environment",
        "asset_type": "hero_image",
        "category": "main_image",
        "prompt_text": (
            "参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。"
            "将背景替换为真实的户外露营场景：绿色草地、远处的帐篷或树林，"
            "自然光线，产品位于画面中央偏左，占画面约60%。"
            "整体采用生活方式摄影风格，自然柔和的光线，"
            "传递户外探险和自然生活的氛围。"
            "无任何文字、水印或其他品牌元素，画面真实自然。"
        ),
        "variables": {"product_reference": "[img0]"},
        "default_parameters": {"aspect_ratio": "1:1", "resolution": "2048x2048"},
        "version": "1.0.0",
        "status": "ACTIVE",
    },
    {
        "template_key": "hero-promotion-v1",
        "name": "Hero Image - Promotion Conversion",
        "description": "Promotional hero image with selling points and price anchor",
        "asset_type": "hero_image",
        "category": "main_image",
        "prompt_text": (
            "参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。"
            "将背景替换为浅灰色渐变背景，产品位于画面左侧，占画面约50%。"
            "右侧留出空间用于添加文字信息。"
            "整体采用电商促销风格，明亮专业的照明，"
            "传递高品质和促销转化的氛围。"
            "产品下方添加柔和阴影，增强立体感。"
        ),
        "variables": {"product_reference": "[img0]"},
        "default_parameters": {"aspect_ratio": "1:1", "resolution": "2048x2048"},
        "version": "1.0.0",
        "status": "ACTIVE",
    },
    {
        "template_key": "hero-structure-detail-v1",
        "name": "Hero Image - Structure Detail",
        "description": "Product structure detail showcase with multiple angles",
        "asset_type": "hero_image",
        "category": "main_image",
        "prompt_text": (
            "参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。"
            "将背景替换为浅灰色背景，产品采用侧面或俯视角度展示，"
            "清晰展示产品结构和关键部件。"
            "产品占画面约70%，位于画面中央。"
            "整体采用工业产品摄影风格，精确的细节表现，"
            "柔和均匀的照明，突出产品工艺和材质。"
        ),
        "variables": {"product_reference": "[img0]"},
        "default_parameters": {"aspect_ratio": "1:1", "resolution": "2048x2048"},
        "version": "1.0.0",
        "status": "ACTIVE",
    },
    {
        "template_key": "hero-multi-color-v1",
        "name": "Hero Image - Multi Color Display",
        "description": "Multiple color variants displayed side by side",
        "asset_type": "hero_image",
        "category": "main_image",
        "prompt_text": (
            "参考[img0]作为产品外观参考，保持产品的形状、材质、结构100%不变。"
            "生成同一产品的多个颜色版本，并排展示在纯白背景上。"
            "每个产品版本保持相同角度和大小，占画面约15-20%。"
            "整体采用电商产品展示风格，均匀照明，"
            "清晰展示颜色差异，方便用户选择。"
        ),
        "variables": {"product_reference": "[img0]", "colors": "red,blue,black,green"},
        "default_parameters": {"aspect_ratio": "1:1", "resolution": "2048x2048"},
        "version": "1.0.0",
        "status": "ACTIVE",
    },
    {
        "template_key": "detail-brand-visual-v1",
        "name": "Detail Page - Brand Visual",
        "description": "Brand-focused detail page hero image",
        "asset_type": "detail_image",
        "category": "detail_page",
        "prompt_text": (
            "参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。"
            "将背景替换为品牌主视觉场景：大型户外场景（山脉、森林或海滩），"
            "产品位于画面下方中央，占画面约40%。"
            "上方留出空间用于品牌名称和标语。"
            "整体采用品牌宣传风格，大气磅礴的场景，"
            "传递品牌价值观和产品定位。"
        ),
        "variables": {"product_reference": "[img0]", "brand_name": "Nuotao Outdoor"},
        "default_parameters": {"aspect_ratio": "3:4", "resolution": "1536x2048"},
        "version": "1.0.0",
        "status": "ACTIVE",
    },
    {
        "template_key": "detail-selling-points-v1",
        "name": "Detail Page - Core Selling Points",
        "description": "Detail page showcasing 3-4 key selling points with icons",
        "asset_type": "detail_image",
        "category": "detail_page",
        "prompt_text": (
            "参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。"
            "将背景替换为浅灰色背景，产品位于画面中央偏上，占画面约50%。"
            "下方留出空间用于添加卖点图标和文字。"
            "整体采用电商详情页风格，清晰专业的布局，"
            "方便用户快速了解产品核心优势。"
        ),
        "variables": {"product_reference": "[img0]"},
        "default_parameters": {"aspect_ratio": "3:4", "resolution": "1536x2048"},
        "version": "1.0.0",
        "status": "ACTIVE",
    },
    {
        "template_key": "detail-function-structure-v1",
        "name": "Detail Page - Function Structure",
        "description": "Detail page showing product structure with annotation lines",
        "asset_type": "detail_image",
        "category": "detail_page",
        "prompt_text": (
            "参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。"
            "将背景替换为纯白色背景，产品位于画面中央，占画面约60%。"
            "周围留出空间用于添加标注线和功能说明。"
            "整体采用产品结构展示风格，精确的细节表现，"
            "清晰展示产品各部位功能和结构。"
        ),
        "variables": {"product_reference": "[img0]"},
        "default_parameters": {"aspect_ratio": "3:4", "resolution": "1536x2048"},
        "version": "1.0.0",
        "status": "ACTIVE",
    },
    {
        "template_key": "detail-scene-grid-v1",
        "name": "Detail Page - Scene Grid",
        "description": "4-grid collage showing different usage scenarios",
        "asset_type": "detail_image",
        "category": "detail_page",
        "prompt_text": (
            "参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。"
            "生成4个不同使用场景的拼图：露营、徒步、钓鱼、野餐。"
            "每个场景占画面约25%，2x2网格布局。"
            "产品在每个场景中保持相同外观，但环境不同。"
            "整体采用生活方式展示风格，自然真实的场景，"
            "传递产品多功能性和适用性。"
        ),
        "variables": {"product_reference": "[img0]"},
        "default_parameters": {"aspect_ratio": "3:4", "resolution": "1536x2048"},
        "version": "1.0.0",
        "status": "ACTIVE",
    },
    {
        "template_key": "detail-closeup-v1",
        "name": "Detail Page - Closeup Details",
        "description": "3-grid closeup showing material, craftsmanship, accessories",
        "asset_type": "detail_image",
        "category": "detail_page",
        "prompt_text": (
            "参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。"
            "生成3个特写镜头：材质细节、工艺细节、配件细节。"
            "每个特写占画面约33%，横向排列。"
            "背景为浅灰色，突出产品细节。"
            "整体采用产品细节展示风格，微距摄影效果，"
            "清晰展示产品材质和工艺品质。"
        ),
        "variables": {"product_reference": "[img0]"},
        "default_parameters": {"aspect_ratio": "3:4", "resolution": "1536x2048"},
        "version": "1.0.0",
        "status": "ACTIVE",
    },
    {
        "template_key": "detail-quality-guarantee-v1",
        "name": "Detail Page - Quality Guarantee",
        "description": "4-grid service promise and brand slogan",
        "asset_type": "detail_image",
        "category": "detail_page",
        "prompt_text": (
            "参考[img0]作为产品外观参考，保持产品的形状、颜色、材质、结构100%不变。"
            "将背景替换为品牌主色调背景，产品位于画面中央偏上，占画面约40%。"
            "下方留出空间用于添加服务承诺图标和品牌标语。"
            "整体采用品牌信任感风格，专业可靠的视觉传达，"
            "传递品牌服务承诺和品质保障。"
        ),
        "variables": {"product_reference": "[img0]", "brand_name": "Nuotao Outdoor"},
        "default_parameters": {"aspect_ratio": "3:4", "resolution": "1536x2048"},
        "version": "1.0.0",
        "status": "ACTIVE",
    },
]


async def seed_templates() -> None:
    """Seed the initial creative prompt templates."""
    async with async_session_factory() as session:
        for tmpl_data in INITIAL_TEMPLATES:
            # Check if template already exists
            existing = await get_prompt_template_by_key(
                session,
                template_key=tmpl_data["template_key"],
                workspace_id=DEFAULT_WORKSPACE,
            )
            if existing:
                print(f"  [skip] {tmpl_data['template_key']} already exists")
                continue

            template = await create_prompt_template(
                session,
                workspace_id=DEFAULT_WORKSPACE,
                template_key=tmpl_data["template_key"],
                name=tmpl_data["name"],
                description=tmpl_data["description"],
                asset_type=tmpl_data["asset_type"],
                category=tmpl_data["category"],
                prompt_text=tmpl_data["prompt_text"],
                variables=tmpl_data["variables"],
                default_parameters=tmpl_data["default_parameters"],
                version=tmpl_data["version"],
                status=tmpl_data["status"],
                created_by="seed_script",
            )
            print(f"  [created] {template.template_key}: {template.name}")

        await session.commit()
        print(f"\nDone. Seeded {len(INITIAL_TEMPLATES)} templates.")


if __name__ == "__main__":
    asyncio.run(seed_templates())
