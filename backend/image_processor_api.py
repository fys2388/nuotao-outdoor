#!/usr/bin/env python3
"""
1688图片自动处理API服务
功能：从1688链接提取图片 → 下载 → ImageMagick处理 → 上传WooCommerce
"""
import os
import io
import json
import base64
import tempfile
import subprocess
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from requests.auth import HTTPBasicAuth

app = FastAPI(title="1688图片处理API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置
WOOCOMMERCE_URL = "https://nuotaooutdoor.com"
WOOCOMMERCE_CK = "ck_483264900d40e98874a3415aabde3b9493e236ed"
WOOCOMMERCE_CS = "cs_0e6ba22a04376077c3c8d96c06b795b1b07dc24c"
AUTH = HTTPBasicAuth(WOOCOMMERCE_CK, WOOCOMMERCE_CS)

WORK_DIR = "/tmp/1688-image-processor"
os.makedirs(WORK_DIR, exist_ok=True)

class ExtractImagesRequest(BaseModel):
    url: str
    max_images: Optional[int] = 10

class ProcessImagesRequest(BaseModel):
    image_urls: List[str]
    product_id: Optional[int] = None
    product_name: Optional[str] = "product"
    process: Optional[bool] = True
    upload: Optional[bool] = True

class AutoImagesRequest(BaseModel):
    url: str
    product_id: Optional[int] = None
    product_name: Optional[str] = "product"
    max_images: Optional[int] = 8
    process: Optional[bool] = True
    upload: Optional[bool] = True

def extract_1688_images(url: str, max_images: int = 10) -> List[str]:
    """从1688产品页面提取图片URL"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://detail.1688.com/",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        html = resp.text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"获取1688页面失败: {str(e)}")
    
    # 提取alicdn图片URL
    import re
    # 匹配 cbu01.alicdn.com 和 img.alicdn.com 的图片
    pattern = r'https?://(?:cbu01|img)\.alicdn\.com/[^"\'\s<>]+\.(?:jpg|jpeg|png|webp)(?:_[^"\'\s<>]*)?'
    urls = re.findall(pattern, html)
    
    # 去重并过滤小图标（SVG、小尺寸）
    unique_urls = []
    seen = set()
    for u in urls:
        # 去掉webp后缀，获取原始jpg
        clean = u.replace("_.webp", "").replace(".webp", "")
        if clean not in seen and ".svg" not in clean and "tps-" not in clean:
            seen.add(clean)
            unique_urls.append(clean)
        if len(unique_urls) >= max_images:
            break
    
    return unique_urls

def download_image(url: str, save_path: str) -> bool:
    """下载图片"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://detail.1688.com/",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 5000:  # 大于5KB
            with open(save_path, "wb") as f:
                f.write(resp.content)
            return True
    except Exception:
        pass
    return False

def process_image(input_path: str, output_path: str) -> bool:
    """用ImageMagick处理图片"""
    try:
        cmd = [
            "convert", input_path,
            "-resize", "1200x1200",
            "-gravity", "center",
            "-background", "white",
            "-extent", "1200x1200",
            "-auto-gamma",
            "-auto-level",
            "-modulate", "105,110,100",
            "-sharpen", "0x1",
            "-quality", "90",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False

def upload_to_woocommerce(image_url: str, name: str, alt: str, product_id: int = None) -> Optional[dict]:
    """上传图片到WooCommerce（通过产品API的images字段，传入图片URL）"""
    try:
        if product_id:
            image_data = {
                "images": [{
                    "src": image_url,
                    "name": name,
                    "alt": alt
                }]
            }
            resp = requests.put(
                f"{WOOCOMMERCE_URL}/wp-json/wc/v3/products/{product_id}",
                auth=AUTH, json=image_data, timeout=60
            )
            if resp.status_code == 200:
                result = resp.json()
                images = result.get("images", [])
                if images:
                    return {"id": images[-1].get("id"), "source_url": images[-1].get("src"), "name": name}
    except Exception as e:
        print(f"Upload error: {e}")
    return None

def link_images_to_product(product_id: int, images: List[dict]) -> bool:
    """把图片关联到WooCommerce产品"""
    try:
        image_data = [{"src": img["source_url"], "name": img.get("name", ""), "alt": img.get("alt_text", "")} for img in images]
        resp = requests.put(
            f"{WOOCOMMERCE_URL}/wp-json/wc/v3/products/{product_id}",
            auth=AUTH, json={"images": image_data}, timeout=60
        )
        return resp.status_code == 200
    except Exception:
        return False

@app.get("/api/v1/image-processor/status")
async def status():
    """服务状态检查"""
    has_imagemagick = subprocess.run(["which", "convert"], capture_output=True).returncode == 0
    return {
        "status": "running",
        "imagemagick": has_imagemagick,
        "work_dir": WORK_DIR,
        "woocommerce": WOOCOMMERCE_URL,
    }

@app.post("/api/v1/image-processor/extract")
async def extract_images(req: ExtractImagesRequest):
    """从1688链接提取图片URL"""
    urls = extract_1688_images(req.url, req.max_images)
    return {
        "success": True,
        "url": req.url,
        "count": len(urls),
        "image_urls": urls,
    }

@app.post("/api/v1/image-processor/process")
async def process_images(req: ProcessImagesRequest):
    """处理图片：下载→处理→上传"""
    task_id = os.urandom(4).hex()
    task_dir = os.path.join(WORK_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    results = []
    uploaded_images = []
    
    for i, img_url in enumerate(req.image_urls):
        name = f"{req.product_name}-{i+1:02d}.jpg"
        alt = f"{req.product_name} Image {i+1}"
        raw_path = os.path.join(task_dir, f"raw_{i+1:02d}.jpg")
        proc_path = os.path.join(task_dir, f"proc_{i+1:02d}.jpg")
        
        result = {"url": img_url, "name": name, "downloaded": False, "processed": False, "uploaded": False}
        
        # 下载
        if download_image(img_url, raw_path):
            result["downloaded"] = True
            result["raw_size"] = os.path.getsize(raw_path)
            
            # 处理
            if req.process:
                if process_image(raw_path, proc_path):
                    result["processed"] = True
                    result["processed_size"] = os.path.getsize(proc_path)
                    upload_path = proc_path
                else:
                    upload_path = raw_path
            else:
                upload_path = raw_path
            
            # 上传：把处理后的图片放到Nginx静态目录，获取公网URL后上传到WooCommerce
            if req.upload:
                public_url = None
                # 复制到Nginx静态目录
                static_dir = "/var/www/nuotao/temp-images"
                os.makedirs(static_dir, exist_ok=True)
                public_path = os.path.join(static_dir, name)
                import shutil
                shutil.copy2(upload_path, public_path)
                public_url = f"https://admin.nuotaooutdoor.com/temp-images/{name}"
                
                if public_url and req.product_id:
                    uploaded = upload_to_woocommerce(public_url, name, alt, req.product_id)
                else:
                    uploaded = None
                if uploaded:
                    result["uploaded"] = True
                    result["media_id"] = uploaded.get("id")
                    result["media_url"] = uploaded.get("source_url")
                    uploaded_images.append(uploaded)
        
        results.append(result)
    
    # 关联到产品
    linked = False
    if req.product_id and uploaded_images:
        linked = link_images_to_product(req.product_id, uploaded_images)
    
    return {
        "success": True,
        "task_id": task_id,
        "total": len(req.image_urls),
        "downloaded": sum(1 for r in results if r["downloaded"]),
        "processed": sum(1 for r in results if r["processed"]),
        "uploaded": sum(1 for r in results if r["uploaded"]),
        "linked_to_product": linked,
        "product_id": req.product_id,
        "results": results,
    }

@app.post("/api/v1/image-processor/auto")
async def auto_process(req: AutoImagesRequest):
    """全自动：提取→下载→处理→上传→关联"""
    # 1. 提取图片
    image_urls = extract_1688_images(req.url, req.max_images)
    
    if not image_urls:
        raise HTTPException(status_code=400, detail="未能从1688页面提取到图片")
    
    # 2. 处理图片
    process_req = ProcessImagesRequest(
        image_urls=image_urls,
        product_id=req.product_id,
        product_name=req.product_name,
        process=req.process,
        upload=req.upload,
    )
    
    result = await process_images(process_req)
    result["extracted_count"] = len(image_urls)
    result["source_url"] = req.url
    
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
