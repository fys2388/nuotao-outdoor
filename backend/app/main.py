"""Nuotao AI OS backend entrypoint.

Exposes the FastAPI application with:
- ``GET /``: service information
- ``GET /api/v1/healthz``: liveness probe (no dependencies)
- ``GET /api/v1/readyz``: readiness probe (PostgreSQL + Redis checks)
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.actor import ActorResolutionError
from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.identity import (
    JwtAuthenticationError,
    PermissionDeniedError,
    WorkspaceAccessError,
)
from app.core.logging import setup_logging
from app.core.redis import create_redis_client
from app.core.tracing import (
    TRACE_ID_HEADER,
    new_trace_id,
    reset_trace_id,
    set_trace_id,
)
from app.services.alert_scheduler import AlertScheduler
from app.worker.agent_worker import run_worker

setup_logging()

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle: Redis client (Worker/Scheduler disabled for API stability)."""
    app.state.redis = create_redis_client()

    # NOTE: Worker + Scheduler temporarily disabled in-process for API stability.
    # Run them separately via run_worker.py when Redis Stream support is available.
    try:
        yield
    finally:
        await app.state.redis.aclose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Nuotao AI OS - 户外电商智能运营系统 API 接口文档",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    swagger_ui_parameters={
        "lang": "zh-CN",
        "docExpansion": "list",
        "defaultModelsExpandDepth": 1,
        "displayRequestDuration": True,
        "showExtensions": True,
    },
)

app.include_router(api_router, prefix=settings.api_prefix)

# M5.4 Runtime Console (static pages under /agent-runtime). The directory is
# served as-is when it exists; check_dir=False keeps the API usable in
# environments where the frontend folder is absent.
_runtime_console_dir = Path(__file__).resolve().parents[2] / "frontend" / "agent-runtime"
app.mount(
    "/agent-runtime",
    StaticFiles(directory=str(_runtime_console_dir), html=True, check_dir=False),
    name="runtime-console",
)


@app.exception_handler(ActorResolutionError)
async def _actor_resolution_error_handler(request: Request, exc: ActorResolutionError) -> Response:
    """Map actor resolution failures (missing/invalid body actor, body mode)."""
    return Response(
        status_code=400,
        media_type="application/json",
        content=json.dumps({"detail": str(exc), "code": "ACTOR_RESOLUTION"}),
    )


@app.exception_handler(JwtAuthenticationError)
async def _jwt_auth_error_handler(request: Request, exc: JwtAuthenticationError) -> Response:
    """Map identity-token failures to 401 (never a body-actor fallback)."""
    return Response(
        status_code=401,
        media_type="application/json",
        content=json.dumps({"detail": str(exc), "code": "IDENTITY_AUTH"}),
    )


@app.exception_handler(WorkspaceAccessError)
async def _workspace_access_error_handler(request: Request, exc: WorkspaceAccessError) -> Response:
    """Map identity workspace failures to 403."""
    return Response(
        status_code=403,
        media_type="application/json",
        content=json.dumps({"detail": str(exc), "code": "WORKSPACE_ACCESS"}),
    )


@app.exception_handler(PermissionDeniedError)
async def _permission_denied_error_handler(
    request: Request, exc: PermissionDeniedError
) -> Response:
    """Map permission failures to 403."""
    return Response(
        status_code=403,
        media_type="application/json",
        content=json.dumps({"detail": str(exc), "code": "PERMISSION_DENIED"}),
    )


@app.middleware("http")
async def trace_middleware(request: Request, call_next) -> Response:
    """Attach a trace_id to every request (forwarded or generated)."""
    trace_id = request.headers.get(TRACE_ID_HEADER) or new_trace_id()
    token = set_trace_id(trace_id)
    try:
        response = await call_next(request)
    finally:
        reset_trace_id(token)
    response.headers[TRACE_ID_HEADER] = trace_id
    return response


# ---------------------------------------------------------------------------
# OpenAPI security schemes for Swagger UI Authorize button
# ---------------------------------------------------------------------------
# Two authentication modes are documented:
# - ApiKeyAuth (X-Actor header): development body-actor mode (ACTOR_PROVIDER=body)
# - BearerAuth (Authorization: Bearer <JWT>): production identity mode (ACTOR_PROVIDER=header)
# These are documentation-only; actual enforcement lives in app/core/actor.py
# and app/api/deps.py. Adding them here makes the Swagger UI "Authorize"
# button appear so operators can pre-fill credentials for endpoint testing.
@app.get("/", summary="Service information", tags=["meta"])
async def root() -> dict[str, str]:
    """Return basic service metadata for operators."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "docs": "/docs",
    }


def _custom_openapi() -> dict:
    """Inject securitySchemes into the generated OpenAPI spec."""
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schema["components"]["securitySchemes"]["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-Actor",
        "description": "开发模式（ACTOR_PROVIDER=body）：在请求头中声明操作者身份。"
        "使用任意安全标识符（如 'dev-user-001'）。也可以在请求体中以 'actor' 字段提供。\n"
        "Development mode (ACTOR_PROVIDER=body): actor identity declared in request header. "
        "Use any safe identifier (e.g. 'dev-user-001'). Also accepted in request body as 'actor'.",
    }
    schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "生产模式（ACTOR_PROVIDER=header）：来自 Clerk 的 RS256 签名 JWT，"
        "携带在受信身份头中（默认为 CF-Access-Jwt-Assertion）。"
        "需要配置 CLERK_JWKS_URL、CLERK_ISSUER、CLERK_AUDIENCE。\n"
        "Production mode (ACTOR_PROVIDER=header): RS256-signed JWT from Clerk, "
        "carried in the trusted identity header (CF-Access-Jwt-Assertion by default). "
        "Requires CLERK_JWKS_URL, CLERK_ISSUER, CLERK_AUDIENCE configured.",
    }
    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi  # type: ignore[method-assign]
