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

# Apply migrations on boot, then start the API server.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]