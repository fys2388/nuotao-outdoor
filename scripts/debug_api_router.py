#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from app.api.v1.router import api_router

print(f"Type: {type(api_router)}")
print(f"Routes count: {len(api_router.routes)}")
print(f"First route type: {type(api_router.routes[0])}")
print(f"First route: {api_router.routes[0]}")

if hasattr(api_router.routes[0], 'path'):
    print(f"First route path: {api_router.routes[0].path}")

# 检查是否有子router
print(f"\napi_router.__dict__ keys: {list(api_router.__dict__.keys())}")
