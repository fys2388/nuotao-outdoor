# Nuotao AI OS backend image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# Migrations and runtime configuration.
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000

# M4.4-INC-001/APR-INC-002: 普通应用部署/容器启动不自动迁移数据库。
# 数据库迁移统一走 B2B Lead Migration Gate workflow（fail-closed 门禁），
# 部署与迁移解耦；容器启动只负责启动 API 服务，避免把仓库最新迁移当成
# 已批准生产迁移。
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]