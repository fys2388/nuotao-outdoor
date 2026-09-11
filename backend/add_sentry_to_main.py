#!/usr/bin/env python3
"""在生产服务器app/main.py中添加Sentry集成"""
import sys

filepath = sys.argv[1] if len(sys.argv) > 1 else 'app/main.py'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 检查是否已经有Sentry代码
if 'sentry_sdk' in content:
    print('Sentry集成已存在，跳过')
    sys.exit(0)

# 1. 在文件开头的docstring后添加 import os
content = content.replace(
    '"""Nuotao AI OS backend entrypoint.',
    'import os\n"""Nuotao AI OS backend entrypoint.',
    1
)

# 2. 在 from fastapi.staticfiles import StaticFiles 后添加sentry import
sentry_import = """
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
"""
content = content.replace(
    'from fastapi.staticfiles import StaticFiles\n',
    'from fastapi.staticfiles import StaticFiles\n' + sentry_import,
    1
)

# 3. 在 setup_logging() 后添加Sentry初始化
sentry_init = """
# Sentry 错误监控（配置 SENTRY_DSN 后自动启用）
SENTRY_DSN = os.getenv('SENTRY_DSN', '')
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            FastApiIntegration(transaction_style='endpoint'),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1,
        environment=os.getenv('APP_ENV', 'production'),
        release='nuotao-ai-os@1.0.0',
    )
    print('Sentry 错误监控已启用')
"""
content = content.replace(
    'setup_logging()\n',
    'setup_logging()\n' + sentry_init,
    1
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print('Sentry集成已添加到', filepath)
