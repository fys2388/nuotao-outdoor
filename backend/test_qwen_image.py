"""Test qwen-image-2.0-pro real image generation with free quota."""
import asyncio
from app.integrations.image_gen import generate_image, list_available_models


async def test() -> None:
    print("Available models:")
    for m in list_available_models():
        print(f"  {m['model']}: CNY {m['cost_cny']}/img, default={m['is_default']}")

    print()
    print("Generating image with qwen-image-2.0-pro-2026-06-22 (free quota)...")
    result = await generate_image(
        prompt=(
            "A professional product photo of a red hiking backpack on a clean "
            "white background, studio lighting, e-commerce style, high resolution"
        ),
        model="qwen-image-2.0-pro-2026-06-22",
        width=1024,
        height=1024,
    )
    print()
    print("SUCCESS!")
    print("Model:", result.model)
    print("Cost CNY:", result.cost_cny)
    print("Image URL:", result.image_url or "N/A")
    print("Has b64:", result.image_b64 is not None)


if __name__ == "__main__":
    asyncio.run(test())
