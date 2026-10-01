"""
Agnes AI API 验证测试
使用正确的 Base URL: https://apihub.agnes-ai.com/v1
使用正确的模型名称: agnes-2.5-flash
"""

import asyncio
import httpx
import sys

API_KEY = "sk-6ZoRZLvoJ99nas5KvCYURq1upJzPAD9KXGqoHUqs0fMUqRWY"
BASE_URL = "https://apihub.agnes-ai.com/v1"
MODEL = "agnes-2.5-flash"


async def test_text_model():
    """测试文本模型"""
    print("测试 1: 文本模型调用")
    print("-" * 40)
    
    url = f"{BASE_URL}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "你好，请用一句话介绍你自己。"}
        ],
        "temperature": 0.2,
        "max_tokens": 100,
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)
        
        print(f"  URL: {url}")
        print(f"  Model: {MODEL}")
        print(f"  Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"  ✅ 成功!")
            print(f"  Response: {content[:200]}")
            return True
        else:
            print(f"  ❌ 失败: {response.text[:300]}")
            return False
            
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return False


async def test_vision_model():
    """测试视觉模型"""
    print("\n测试 2: 视觉模型调用")
    print("-" * 40)
    
    url = f"{BASE_URL}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    
    # 使用 base64 编码的图片 (1x1 像素的红色 PNG)
    test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    test_image_url = f"data:image/png;base64,{test_image_base64}"
    
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请描述这张图片的内容。"},
                    {"type": "image_url", "image_url": {"url": test_image_url}},
                ],
            }
        ],
        "temperature": 0.2,
        "max_tokens": 100,
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)
        
        print(f"  URL: {url}")
        print(f"  Model: {MODEL}")
        print(f"  Image: {test_image_url}")
        print(f"  Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"  ✅ 成功!")
            print(f"  Response: {content[:200]}")
            return True
        else:
            print(f"  ❌ 失败: {response.text[:300]}")
            return False
            
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return False


async def main():
    """主函数"""
    print("=" * 60)
    print("Agnes AI API 验证测试")
    print("=" * 60)
    print(f"\n配置:")
    print(f"  Base URL: {BASE_URL}")
    print(f"  Model: {MODEL}")
    print(f"  API Key: {API_KEY[:20]}...")
    
    text_passed = await test_text_model()
    vision_passed = await test_vision_model()
    
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    
    print(f"\n  {'✅' if text_passed else '❌'} 文本模型: {'通过' if text_passed else '失败'}")
    print(f"  {'✅' if vision_passed else '❌'} 视觉模型: {'通过' if vision_passed else '失败'}")
    
    all_passed = text_passed and vision_passed
    print(f"\n  总体结果: {'✅ 全部通过' if all_passed else '❌ 部分失败'}")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)