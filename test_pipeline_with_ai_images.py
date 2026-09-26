#!/usr/bin/env python3
"""Test full pipeline with AI image generation"""
import requests
import json

# Step 1: Import from 1688 (Newton Agent)
print("=" * 60)
print("Step 1: Import from 1688 via Newton Agent")
print("=" * 60)

import_url = "http://127.0.0.1:8000/api/v1/product-pipeline/import-from-1688"
import_data = {
    "url_or_id": "便携式户外榨汁杯",
    "auto_run_pipeline": False,
    "auto_list": False,
}

resp = requests.post(import_url, json=import_data, timeout=120)
result = resp.json()

if not result.get("success"):
    print(f"Import failed: {result.get('error')}")
    exit(1)

product_info = result["data"]["product_info"]
print(f"Product name: {product_info.get('name')}")
print(f"Product price: {product_info.get('price')}")
print(f"Product SKU: {product_info.get('sku')}")
print(f"Product images: {len(product_info.get('images', []))}")
for i, img in enumerate(product_info.get('images', [])):
    print(f"  Image {i+1}: {img[:80]}...")

# Step 2: Run pipeline (with AI image generation)
print("\n" + "=" * 60)
print("Step 2: Run pipeline (with AI image generation)")
print("=" * 60)

pipeline_url = "http://127.0.0.1:8000/api/v1/product-pipeline/run"
pipeline_data = {
    "product_info": product_info,
    "auto_list": True,  # Enable auto-upload to WooCommerce
}

print("Running pipeline... (this may take a few minutes due to AI image generation)")
resp = requests.post(pipeline_url, json=pipeline_data, timeout=600)
result = resp.json()

if result.get("success"):
    pipeline_result = result.get("data", {})
    print(f"Pipeline status: {pipeline_result.get('status')}")
    print(f"Completed steps: {pipeline_result.get('completed_steps')}/{pipeline_result.get('total_steps')}")
    
    # Check AI images step
    ai_images_step = pipeline_result.get("steps", {}).get("ai_images", {})
    print(f"\nAI Images Step: {ai_images_step.get('status')}")
    if ai_images_step.get("data"):
        ai_data = ai_images_step["data"]
        print(f"  Generated images: {len(ai_data.get('images', []))}")
        print(f"  Total cost: {ai_data.get('cost_cny', 0):.4f} CNY")
        print(f"  Model used: {ai_data.get('model', 'N/A')}")
        for i, img in enumerate(ai_data.get('images', [])):
            print(f"  Image {i+1}: {img}")
        if ai_data.get('error'):
            print(f"  Error: {ai_data.get('error')}")
    else:
        print(f"  No data returned")
        print(f"  Step data: {ai_images_step}")
    
    # Check listing data
    listing_data = pipeline_result.get("steps", {}).get("listing_data", {}).get("data", {})
    if listing_data:
        wc_data = listing_data.get("woocommerce_data", {})
        images = wc_data.get("images", [])
        print(f"\nListing Data:")
        print(f"  Name: {listing_data.get('name', listing_data.get('en_name', 'N/A'))}")
        print(f"  SKU: {wc_data.get('sku', 'N/A')}")
        print(f"  WooCommerce images: {len(images)}")
        for i, img in enumerate(images):
            print(f"    Image {i+1}: {img.get('src', 'N/A')[:80]}...")
    
    # Check WooCommerce listing (Step 7)
    listing_step = pipeline_result.get("steps", {}).get("listing", {})
    print(f"\nWooCommerce Listing (Step 7): {listing_step.get('status')}")
    if listing_step.get("data"):
        listing_data_wc = listing_step["data"]
        print(f"  WooCommerce ID: {listing_data_wc.get('woocommerce_id', 'N/A')}")
        print(f"  Success: {listing_data_wc.get('success', 'N/A')}")
        if listing_data_wc.get('error'):
            print(f"  Error: {listing_data_wc.get('error')}")
    elif listing_step.get("message"):
        print(f"  Message: {listing_step.get('message')}")
else:
    print(f"Pipeline failed: {result.get('error')}")
    print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
