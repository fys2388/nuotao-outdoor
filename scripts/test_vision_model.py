"""
视觉模型验证脚本
验证 Agnes AI (OpenAI 兼容) 视觉模型是否正常工作
"""

import asyncio
import base64
import os
import sys
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.llm_gateway import LLMRequest, complete, LLMError
from app.core.config import get_settings


async def test_vision_model():
    """测试视觉模型调用"""
    print("=" * 60)
    print("视觉模型验证测试")
    print("=" * 60)
    
    settings = get_settings()
    
    # 检查配置
    print(f"\n配置检查:")
    print(f"  OPENAI_API_KEY: {'已配置' if settings.openai_api_key else '未配置'}")
    print(f"  OPENAI_BASE_URL: {settings.openai_base_url}")
    print(f"  OPENAI_DEFAULT_MODEL: {settings.openai_default_model}")
    
    if not settings.openai_api_key:
        print("\n❌ 未配置 OPENAI_API_KEY")
        return False
    
    # 创建一个简单的测试图片 (1x1 像素的红色 PNG)
    # 使用 base64 编码的 PNG
    test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    
    print("\n测试 1: 视觉模型调用")
    print("-" * 40)
    
    try:
        # 创建视觉请求
        request = LLMRequest(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请描述这张图片的内容。"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{test_image_base64}"}},
                    ],
                }
            ],
            provider="openai",
            model="gpt-4o-mini",
            vision=True,
            images=[f"data:image/png;base64,{test_image_base64}"],
        )
        
        # 调用模型
        response = await complete(request, allow_fallback=False)
        
        print(f"\n✅ 视觉模型调用成功!")
        print(f"  Provider: {response.provider}")
        print(f"  Model: {response.model}")
        print(f"  Latency: {response.latency_ms}ms")
        print(f"  Cost: ${response.cost}")
        print(f"  Trace ID: {response.trace_id}")
        print(f"\n模型响应:")
        print(f"  {response.content[:200]}...")
        
        vision_test_passed = True
        
    except LLMError as e:
        print(f"\n❌ 视觉模型调用失败!")
        print(f"  Error kind: {e.kind}")
        print(f"  Error message: {e}")
        vision_test_passed = False
        
    except Exception as e:
        print(f"\n❌ 视觉模型调用异常!")
        print(f"  Exception: {e}")
        vision_test_passed = False
    
    # 测试 2: 文本模型调用 (对比测试)
    print("\n测试 2: 文本模型调用 (对比测试)")
    print("-" * 40)
    
    try:
        text_request = LLMRequest(
            messages=[
                {"role": "user", "content": "请用一句话介绍你自己。"}
            ],
            provider="openai",
            model="gpt-4o-mini",
        )
        
        text_response = await complete(text_request, allow_fallback=False)
        
        print(f"\n✅ 文本模型调用成功!")
        print(f"  Provider: {text_response.provider}")
        print(f"  Model: {text_response.model}")
        print(f"  Latency: {text_response.latency_ms}ms")
        print(f"  Cost: ${text_response.cost}")
        print(f"\n模型响应:")
        print(f"  {text_response.content[:200]}")
        
        text_test_passed = True
        
    except LLMError as e:
        print(f"\n❌ 文本模型调用失败!")
        print(f"  Error kind: {e.kind}")
        print(f"  Error message: {e}")
        text_test_passed = False
        
    except Exception as e:
        print(f"\n❌ 文本模型调用异常!")
        print(f"  Exception: {e}")
        text_test_passed = False
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    
    results = {
        "vision_model": vision_test_passed,
        "text_model": text_test_passed,
    }
    
    print(f"\n  {'✅' if results['vision_model'] else '❌'} 视觉模型: {'通过' if results['vision_model'] else '失败'}")
    print(f"  {'✅' if results['text_model'] else '❌'} 文本模型: {'通过' if results['text_model'] else '失败'}")
    
    all_passed = all(results.values())
    print(f"\n  总体结果: {'✅ 全部通过' if all_passed else '❌ 部分失败'}")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(test_vision_model())
    sys.exit(0 if success else 1)