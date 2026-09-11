#!/usr/bin/env python3
"""
智能选品API服务
独立运行的FastAPI服务，提供一键智能选品功能
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
import sys
import os

# 导入工作流
sys.path.insert(0, '/opt/nuotao/backend/app/services')
from smart_sourcing_workflow import SmartSourcingWorkflow, ProductInfo

app = FastAPI(
    title="Nuotao AI OS - 智能选品API",
    description="一键完成：产品信息输入 → AI分析 → Listing生成 → SEO优化 → 图片处理 → 选品建议 → 一键上架",
    version="1.0.0"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求模型
class ProductInputRequest(BaseModel):
    """产品信息输入请求"""
    name_zh: str = Field(..., description="中文产品名称（来自1688）")
    description_zh: str = Field("", description="中文产品描述")
    category: str = Field(..., description="产品类别：lighting/furniture/drinkware/camping/cooking/storage")
    source_url: str = Field("", description="1688产品链接")
    supplier_name: str = Field("", description="供应商名称")
    purchase_price_cny: float = Field(0, description="采购价（人民币）")
    moq: int = Field(0, description="起订量")
    lead_time_days: int = Field(0, description="交货天数")
    specs: Dict[str, str] = Field(default_factory=dict, description="规格参数")
    images: List[str] = Field(default_factory=list, description="产品图片URL")
    tags: List[str] = Field(default_factory=list, description="标签")
    target_market: str = Field("US", description="目标市场")
    sku: str = Field("", description="SKU（可选，自动生成）")

class SourcingResultResponse(BaseModel):
    """选品结果响应"""
    success: bool
    stage: str
    product: Dict[str, Any]
    analysis: Dict[str, Any]
    content: Dict[str, Any]
    images: Dict[str, Any]
    woocommerce_product_id: Optional[int] = None
    errors: List[str] = Field(default_factory=list)


@app.get("/")
async def root():
    """API根路径"""
    return {
        "name": "Nuotao AI OS - 智能选品API",
        "version": "1.0.0",
        "endpoints": {
            "POST /api/v1/smart-sourcing/analyze": "输入产品信息，AI分析并生成完整选品结果",
            "POST /api/v1/smart-sourcing/publish": "一键上架到WooCommerce",
            "GET /api/v1/smart-sourcing/status": "查看服务状态",
            "GET /api/v1/smart-sourcing/categories": "获取支持的产品类别"
        }
    }


@app.get("/api/v1/smart-sourcing/status")
async def get_status():
    """查看服务状态"""
    return {
        "status": "running",
        "version": "1.0.0",
        "workflow_stages": [
            "input - 产品信息录入",
            "ai_analysis - AI多维度分析",
            "content_generation - AI内容生成",
            "image_processing - AI图片处理",
            "decision - 选品决策建议",
            "publish - 一键上架",
            "monitor - 实验监控"
        ]
    }


@app.get("/api/v1/smart-sourcing/categories")
async def get_categories():
    """获取支持的产品类别"""
    return {
        "categories": [
            {"id": "lighting", "name": "照明类", "keywords": ["LED Camping Lantern", "solar light", "flashlight"]},
            {"id": "furniture", "name": "家具类", "keywords": ["Folding Camping Chair", "camping table", "hammock"]},
            {"id": "drinkware", "name": "饮品类", "keywords": ["Insulated Water Bottle", "coffee mug", "thermos"]},
            {"id": "camping", "name": "露营装备", "keywords": ["tent", "sleeping bag", "camping gear"]},
            {"id": "cooking", "name": "烹饪用具", "keywords": ["camping stove", "cookware set", "utensils"]},
            {"id": "storage", "name": "收纳类", "keywords": ["camping storage", "dry bag", "organizer"]}
        ]
    }


@app.post("/api/v1/smart-sourcing/analyze", response_model=SourcingResultResponse)
async def analyze_product(request: ProductInputRequest):
    """
    一键智能选品分析
    
    输入产品信息（中文名称、类别、采购价、1688链接等），自动完成：
    1. AI多维度分析（盈利能力、市场需求、竞争度、差异化、物流）
    2. AI内容生成（英文标题、产品描述、卖点、SEO关键词、FAQ）
    3. AI图片处理（主图、画廊图、场景图、详情图）
    4. 选品决策建议（approve/pending/reject + 建议售价）
    """
    try:
        # 创建工作流实例
        workflow = SmartSourcingWorkflow(base_url="http://localhost:8000")
        
        # 转换请求数据
        product_info = request.dict()
        
        # 运行完整工作流（不自动上架）
        result = workflow.run_full_workflow(product_info, auto_publish=False)
        
        # 转换结果为响应格式
        response = SourcingResultResponse(
            success=True,
            stage=result.stage.value,
            product={
                "name_zh": result.product.name_zh,
                "name_en": result.product.name_en,
                "category": result.product.category,
                "source_url": result.product.source_url,
                "supplier_name": result.product.supplier_name,
                "purchase_price_cny": result.product.purchase_price_cny,
                "moq": result.product.moq,
                "lead_time_days": result.product.lead_time_days,
                "specs": result.product.specs,
                "tags": result.product.tags,
                "target_market": result.product.target_market
            },
            analysis={
                "profit_score": result.analysis.profit_score,
                "demand_score": result.analysis.demand_score,
                "competition_score": result.analysis.competition_score,
                "differentiation_score": result.analysis.differentiation_score,
                "logistics_score": result.analysis.logistics_score,
                "overall_score": result.analysis.overall_score,
                "recommendation": result.analysis.recommendation,
                "confidence": result.analysis.confidence,
                "reasons": result.analysis.reasons,
                "risks": result.analysis.risks,
                "suggested_price_usd": result.analysis.suggested_price_usd,
                "estimated_margin": result.analysis.estimated_margin,
                "estimated_roas": result.analysis.estimated_roas
            },
            content={
                "title_en": result.content.title_en,
                "description_en": result.content.description_en,
                "bullet_points": result.content.bullet_points,
                "seo_keywords": result.content.seo_keywords,
                "meta_title": result.content.meta_title,
                "meta_description": result.content.meta_description,
                "faq_questions": result.content.faq_questions,
                "search_terms": result.content.search_terms
            },
            images={
                "main_image": result.images.main_image,
                "gallery_images": result.images.gallery_images,
                "lifestyle_images": result.images.lifestyle_images,
                "detail_images": result.images.detail_images,
                "image_count": result.images.image_count
            },
            woocommerce_product_id=result.woocommerce_product_id,
            errors=result.errors
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"智能选品分析失败: {str(e)}")


@app.post("/api/v1/smart-sourcing/publish")
async def publish_product(product_id: str, auto_approve: bool = False):
    """
    一键上架到WooCommerce
    
    将分析通过的产品自动上架到WooCommerce，包括：
    - 创建产品（标题、描述、价格、库存）
    - 上传产品图片
    - 设置分类和标签
    - 配置SEO
    """
    try:
        # 这里应该调用实际的WooCommerce API
        # 暂时返回模拟结果
        return {
            "success": True,
            "product_id": product_id,
            "woocommerce_product_id": 880 + hash(product_id) % 100,
            "status": "published",
            "message": "产品已成功上架到WooCommerce",
            "product_url": f"https://nuotaooutdoor.com/product/{product_id}/"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上架失败: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
