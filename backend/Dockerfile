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

# M4.4-INC-001/APR-INC-002: 生产部署与数据库迁移解耦。
# - 若挂载了可信批准清单（/app/infra/migration_approvals.yaml，宿主机
#   /opt/nuotao-ai-os/infra 只读挂载），经 migration_gate.sh（fail-closed）后
#   迁移到 approved_revision；清单缺失/不可读/未批准 -> 不迁移并启动（安全）。
# - 无挂载清单（本地/开发/未接入门禁的部署）默认不自动迁移，只启动服务；
#   迁移统一走 B2B Lead Migration Gate workflow，避免把仓库最新迁移当成
#   已批准生产迁移。
CMD ["sh", "-c", "if [ -r /app/infra/migration_approvals.yaml ]; then APPROVED=$(grep -E '^approved_revision:' /app/infra/migration_approvals.yaml | awk '{print $2}' | tr -d '\"'); bash /app/infra/migration_gate.sh \"$APPROVED\" && alembic upgrade \"$APPROVED\"; else echo '[migration] no approval list mounted; skip DB migration (use migration gate workflow)'; fi; exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]